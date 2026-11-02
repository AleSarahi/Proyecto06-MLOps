"""Compara detecciones reales de P5-05 entre las dos rutas de P5-06, sin benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import torch

from contrato import validar_evento, validar_flujo
from infer.config import RUTA_CONFIG_DETECTOR, cargar_config_detector
from infer.detector import DetectorJPEG
from infer.eventos import ejecutar_run
from infer.pesos import cargar_pesos
from infer.rutas_seguras import abrir_exclusivo, directorio_evidencia, verificar_checkpoint
from infer.trabajador import ejecutar_run_supervisado

RAIZ = Path(__file__).resolve().parents[1]
IMAGEN = RAIZ / "docs/carro/objeto_taza_centro_cerca.jpg"
REFERENCIA = RAIZ / "resultados/p5-05-aceptacion-2h-a.jsonl"
MODELO_SHA256 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
CONFIG_SHA256 = "6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08"
IMAGEN_SHA256 = "670fec5473ceda61b5a6283711596d610d75577dfb1bc9d5ffc8de52c1e9cbcc"


def _sha256(ruta: Path) -> str:
    with ruta.open("rb") as archivo:
        return hashlib.file_digest(archivo, "sha256").hexdigest()


def _jsonl(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def _diferencias(actual: list[dict], esperado: list[dict]) -> list[dict]:
    diferencias = []
    if len(actual) != len(esperado):
        diferencias.append({"campo": "cantidad", "actual": len(actual), "esperado": len(esperado)})
    for indice, (a, e) in enumerate(zip(actual, esperado, strict=False)):
        for campo in ("class_id", "confidence", "bbox"):
            if a[campo] != e[campo]:
                diferencias.append(
                    {"indice": indice, "campo": campo, "actual": a[campo], "esperado": e[campo]}
                )
    return diferencias


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    pesos = args.weights.absolute()
    config = cargar_config_detector()
    verificar_checkpoint(pesos, MODELO_SHA256, bytes_esperados=5_613_764)
    if config.config_sha256 != CONFIG_SHA256 or config.expected_model_sha256 != MODELO_SHA256:
        raise RuntimeError("configuración distinta a P5-05 de dos hilos")
    if config.torch_threads != 2 or _sha256(IMAGEN) != IMAGEN_SHA256:
        raise RuntimeError("hilos o bytes del JPEG distintos a P5-05")

    # --output lo elige el operador local; integraciones con entrada no confiable
    # deben llamar directorio_evidencia con raiz_restringida.
    salida = directorio_evidencia(args.output.absolute())
    detector = DetectorJPEG(cargar_pesos(pesos, config), config)
    ruta_control, n_control, e_control = ejecutar_run(
        detector, IMAGEN, salida / "un_proceso.jsonl", run_id="p506-taza-un-proceso"
    )
    hilos_control = torch.get_num_threads()
    ruta_supervisada, n_supervisado, e_supervisado, fallo = ejecutar_run_supervisado(
        IMAGEN,
        salida / "supervisado.jsonl",
        run_id="p506-taza-supervisado",
        config_ruta=RUTA_CONFIG_DETECTOR,
        pesos_ruta=pesos,
    )
    control, supervisado = _jsonl(ruta_control), _jsonl(ruta_supervisada)
    referencia = next(e for e in _jsonl(REFERENCIA) if e["frame_id"] == "ensayo-0012")
    manifiesto = json.loads((salida / "p506-taza-supervisado.infer-run.json").read_text())
    ready = [g for g in manifiesto["generaciones"] if g["estado"] == "ready"]

    for eventos in (control, supervisado):
        if len(eventos) != 1 or validar_flujo(eventos) or validar_evento(eventos[0]):
            raise RuntimeError("evento A→B v1 inválido o duplicado")
        evento = eventos[0]
        if (
            evento["status"] != "ok"
            or evento["frame_id"] != IMAGEN.stem
            or (evento["image_width"], evento["image_height"]) != (640, 480)
            or evento["t_emit_ms"] < evento["t_capture_ms"]
        ):
            raise RuntimeError("estado, identidad, dimensiones o tiempos incorrectos")
    if cv2.imread(str(IMAGEN)).shape[:2] != (480, 640):
        raise RuntimeError("las dimensiones del JPEG cambiaron")
    if not control[0]["detections"] or not supervisado[0]["detections"]:
        raise RuntimeError("la imagen elegida no produjo detecciones")
    if (n_control, n_supervisado, e_control, e_supervisado, fallo) != (1, 1, 0, 0, False):
        raise RuntimeError("la ejecución perdió cuadros o tuvo errores")
    if (
        hilos_control != 2
        or len(ready) != 1
        or ready[0]["model_sha256"] != MODELO_SHA256
        or ready[0]["config_sha256"] != CONFIG_SHA256
        or ready[0]["torch_threads"] != 2
        or manifiesto["cierre_limpio"] is not True
    ):
        raise RuntimeError("READY, hashes, hilos o cierre incorrectos")

    diferencias = {
        "un_proceso_vs_supervisado": _diferencias(
            control[0]["detections"], supervisado[0]["detections"]
        ),
        "un_proceso_vs_p5_05": _diferencias(control[0]["detections"], referencia["detections"]),
        "supervisado_vs_p5_05": _diferencias(
            supervisado[0]["detections"], referencia["detections"]
        ),
    }
    resumen = {
        "tipo": "validacion_funcional_sin_benchmark",
        "criterio": "igualdad exacta en el mismo host/runtime; cualquier diferencia se investiga",
        "imagen": str(IMAGEN.relative_to(RAIZ)),
        "imagen_sha256": IMAGEN_SHA256,
        "referencia_p5_05": str(REFERENCIA.relative_to(RAIZ)),
        "checkpoint_sha256": MODELO_SHA256,
        "config_sha256": CONFIG_SHA256,
        "hilos_control": hilos_control,
        "ready": ready[0],
        "cierre_limpio": manifiesto["cierre_limpio"],
        "detections_un_proceso": control[0]["detections"],
        "detections_supervisado": supervisado[0]["detections"],
        "detections_p5_05": referencia["detections"],
        "diferencias": diferencias,
        "contrato_v1_valido": True,
    }
    with abrir_exclusivo(salida / "comparacion.json") as evidencia:
        evidencia.write(json.dumps(resumen, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    if any(diferencias.values()):
        raise RuntimeError("las detecciones difieren; revisar comparacion.json")
    print(json.dumps({"detecciones": len(control[0]["detections"]), "diferencias": diferencias}))


if __name__ == "__main__":
    main()
