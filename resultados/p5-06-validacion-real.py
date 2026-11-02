"""Validación funcional P5-06 con dos JPEG sintéticos; no ejecuta benchmarks.

Uso desde la raíz del worktree:
    .venv/bin/python resultados/p5-06-validacion-real.py \
        --weights '/ruta/local/yolo11n.pt' --output resultados/p5-06-validacion-real
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import torch

from contrato import validar_evento, validar_flujo
from infer.config import RUTA_CONFIG_DETECTOR, cargar_config_detector
from infer.detector import DetectorJPEG
from infer.eventos import ejecutar_run
from infer.pesos import cargar_pesos
from infer.rutas_seguras import abrir_exclusivo, directorio_evidencia, verificar_checkpoint
from infer.trabajador import ejecutar_run_supervisado

PESO_BYTES = 5_613_764
PESO_SHA256 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
CONFIG_SHA256 = "6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08"


def _sha256(ruta: Path) -> str:
    with ruta.open("rb") as archivo:
        return hashlib.file_digest(archivo, "sha256").hexdigest()


def _leer_jsonl(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def _crear_jpeg(carpeta: Path) -> list[Path]:
    carpeta.mkdir()
    nombres = ("sintetico_negro.jpg", "sintetico_geometria.jpg")
    negro = np.zeros((480, 640, 3), dtype=np.uint8)
    geometria = np.full((480, 640, 3), 220, dtype=np.uint8)
    cv2.rectangle(geometria, (100, 90), (300, 390), (30, 80, 180), -1)
    cv2.circle(geometria, (470, 240), 85, (180, 50, 40), -1)
    imagenes = (negro, geometria)
    rutas = [carpeta / nombre for nombre in nombres]
    for ruta, imagen in zip(rutas, imagenes, strict=True):
        if not cv2.imwrite(str(ruta), imagen):
            raise RuntimeError(f"no se pudo generar {ruta.name}")
    return rutas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    pesos = args.weights.absolute()
    config = cargar_config_detector()
    verificar_checkpoint(pesos, PESO_SHA256, bytes_esperados=PESO_BYTES)
    if config.expected_model_sha256 != PESO_SHA256 or config.config_sha256 != CONFIG_SHA256:
        raise RuntimeError("configuración efectiva distinta a P5-05 de dos hilos")
    if config.torch_threads != 2:
        raise RuntimeError("se requieren dos hilos efectivos")

    # --output lo elige el operador local; integraciones con entrada no confiable
    # deben llamar directorio_evidencia con raiz_restringida.
    salida = directorio_evidencia(args.output)
    rutas = _crear_jpeg(salida / "jpeg_sinteticos")
    imagenes_sha = {ruta.stem: _sha256(ruta) for ruta in rutas}

    detector = DetectorJPEG(cargar_pesos(pesos, config), config)
    ruta_control, cuadros_control, errores_control = ejecutar_run(
        detector,
        salida / "jpeg_sinteticos",
        salida / "un_proceso.jsonl",
        run_id="p506-real-un-proceso",
        sequence_id="sintetica",
        capture_ms=[0, 200],
    )
    if torch.get_num_threads() != 2:
        raise RuntimeError("la ruta de un proceso no mantuvo torch_threads=2")

    ruta_supervisada, cuadros_supervisados, errores_supervisados, fallo_reinicio = (
        ejecutar_run_supervisado(
            salida / "jpeg_sinteticos",
            salida / "supervisado.jsonl",
            run_id="p506-real-supervisado",
            config_ruta=RUTA_CONFIG_DETECTOR,
            pesos_ruta=pesos,
            sequence_id="sintetica",
            capture_ms=[0, 200],
        )
    )
    control = _leer_jsonl(ruta_control)
    supervisado = _leer_jsonl(ruta_supervisada)
    manifiesto = json.loads((salida / "p506-real-supervisado.infer-run.json").read_text())
    ready = [g for g in manifiesto["generaciones"] if g["estado"] == "ready"]

    for eventos in (control, supervisado):
        if len(eventos) != len(rutas) or validar_flujo(eventos):
            raise RuntimeError("cantidad o flujo de eventos A→B inválidos")
        if any(validar_evento(evento) for evento in eventos):
            raise RuntimeError("evento A→B v1 inválido")
        if [e["frame_id"] for e in eventos] != [ruta.stem for ruta in sorted(rutas)]:
            raise RuntimeError("frame_id u orden inesperados")
        if any((e["image_width"], e["image_height"]) != (640, 480) for e in eventos):
            raise RuntimeError("dimensiones originales incorrectas")
        if any(e["t_emit_ms"] < e["t_capture_ms"] for e in eventos):
            raise RuntimeError("tiempos no monotónicos")

    pares = list(zip(control, supervisado, strict=True))
    comparacion = [
        {
            "frame_id": a["frame_id"],
            "status_un_proceso": a["status"],
            "status_supervisado": b["status"],
            "detections_un_proceso": a["detections"],
            "detections_supervisado": b["detections"],
            "detecciones_iguales": a["detections"] == b["detections"],
        }
        for a, b in pares
    ]
    if any(a["status"] != b["status"] or a["detections"] != b["detections"] for a, b in pares):
        raise RuntimeError("las rutas produjeron estados o detecciones distintos")
    if cuadros_control != 2 or cuadros_supervisados != 2 or errores_control or errores_supervisados:
        raise RuntimeError("la inferencia funcional tuvo errores o perdió cuadros")
    if fallo_reinicio or manifiesto["cierre_limpio"] is not True or len(ready) != 1:
        raise RuntimeError("READY, persistencia o cierre del trabajador falló")
    if ready[0]["model_sha256"] != PESO_SHA256 or ready[0]["config_sha256"] != CONFIG_SHA256:
        raise RuntimeError("READY informó hashes incorrectos")
    if ready[0]["torch_threads"] != 2:
        raise RuntimeError("READY no confirmó dos hilos")

    resumen = {
        "tipo": "validacion_funcional_sin_benchmark",
        "checkpoint": {
            "archivo": pesos.name,
            "bytes": PESO_BYTES,
            "sha256": PESO_SHA256,
        },
        "config_sha256": config.config_sha256,
        "torch_threads_un_proceso": torch.get_num_threads(),
        "ready": ready[0],
        "cierre_limpio": manifiesto["cierre_limpio"],
        "jpeg_sinteticos_sha256": imagenes_sha,
        "conteos": {"un_proceso": cuadros_control, "supervisado": cuadros_supervisados},
        "comparacion": comparacion,
        "contrato_v1_valido": True,
    }
    with abrir_exclusivo(salida / "validacion.json") as evidencia:
        evidencia.write(json.dumps(resumen, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"ready": ready[0], "comparacion": comparacion}, ensure_ascii=False))


if __name__ == "__main__":
    main()
