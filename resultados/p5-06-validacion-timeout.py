"""Evidencia funcional de timeout y recuperación con trabajador simulado (spawn).

No mide la latencia normal ni sustituye la validación con el checkpoint real.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
import torch

import infer.__main__ as cli_infer
from contrato import validar_evento, validar_flujo
from infer.config import RUTA_CONFIG_DETECTOR, cargar_config_detector
from infer.detector import ResultadoJPEG
from infer.rutas_seguras import abrir_exclusivo, directorio_evidencia
from infer.trabajador import ejecutar_run_supervisado


class DetectorBloqueado:
    def __init__(self) -> None:
        self.config = cargar_config_detector()
        self.cargado = SimpleNamespace(
            model_sha256=self.config.expected_model_sha256,
            config_sha256=self.config.config_sha256,
        )

    def calentar(self) -> None:
        torch.set_num_threads(2)

    def inferir(self, ruta: Path, *, imagen: np.ndarray | None = None) -> ResultadoJPEG:
        time.sleep(3)  # El supervisor debe terminar el hijo antes de que responda.
        assert imagen is not None
        return ResultadoJPEG(
            imagen.shape[1],
            imagen.shape[0],
            (1, 3, imagen.shape[1] - 1, imagen.shape[0] - 1),
            (),
            0,
            self.cargado.model_sha256,
            self.config.config_sha256,
        )


def crear_detector_bloqueado(_config: Path, control: Path) -> DetectorBloqueado:
    datos = json.loads(control.read_text(encoding="utf-8"))
    contador = control.with_suffix(".contador")
    generacion = int(contador.read_text(encoding="utf-8")) + 1 if contador.exists() else 1
    contador.write_text(str(generacion), encoding="utf-8")
    if datos["fallar_reinicio"] and generacion == 2:
        raise RuntimeError("fallo de reinicio inyectado por validación")
    return DetectorBloqueado()


def _leer_jsonl(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def _intento(salida: Path, indice: int, *, terminal: bool) -> dict:
    run_id = f"timeout-{indice:04d}"
    entrada = salida / f"cuadro-{indice:04d}.jpg"
    if not cv2.imwrite(str(entrada), np.zeros((60, 80, 3), dtype=np.uint8)):
        raise RuntimeError("no se pudo crear JPEG sintético")
    if terminal:
        pendientes = [salida / f"pendiente-{n:04d}.jpg" for n in range(2)]
        for pendiente in pendientes:
            if not cv2.imwrite(str(pendiente), np.zeros((60, 80, 3), dtype=np.uint8)):
                raise RuntimeError("no se pudo crear JPEG pendiente")
        carpeta = salida / f"entrada-{indice:04d}"
        carpeta.mkdir()
        entrada.rename(carpeta / entrada.name)
        for pendiente in pendientes:
            pendiente.rename(carpeta / pendiente.name)
        entrada = carpeta
        capturas = [0, 200, 400]
    else:
        capturas = None
    control = salida / f"control-{indice:04d}.json"
    control.write_text(json.dumps({"fallar_reinicio": terminal}), encoding="utf-8")
    trazas: list[dict] = []
    jsonl, cuadros, errores, fallo = ejecutar_run_supervisado(
        entrada,
        salida / f"{run_id}.jsonl",
        run_id=run_id,
        config_ruta=RUTA_CONFIG_DETECTOR,
        pesos_ruta=control,
        sequence_id="sintetica" if terminal else None,
        capture_ms=capturas,
        fabrica=crear_detector_bloqueado,
        inicio_guarda_s=30,
        trazas=trazas,
    )
    eventos = _leer_jsonl(jsonl)
    manifiesto = json.loads((salida / f"{run_id}.infer-run.json").read_text(encoding="utf-8"))
    ready = [g for g in manifiesto["generaciones"] if g["estado"] == "ready"]
    config = cargar_config_detector()
    codigo_cli = None
    if terminal:
        with patch.object(
            cli_infer,
            "ejecutar_run_supervisado",
            return_value=(jsonl, cuadros, errores, fallo),
        ):
            codigo_cli = cli_infer.main(
                [
                    "--input",
                    str(entrada),
                    "--weights",
                    str(control),
                    "--output",
                    str(jsonl),
                    "--run-id",
                    run_id,
                ]
            )
    esperado = (
        ["detector_timeout", "detector_exception", "detector_exception"]
        if terminal
        else ["detector_timeout"]
    )
    codigos = [e.get("error", {}).get("code") for e in eventos]
    valido = (
        cuadros == len(esperado)
        and errores == len(esperado)
        and codigos == esperado
        and not validar_flujo(eventos)
        and all(not validar_evento(e) for e in eventos)
        and len({e["frame_id"] for e in eventos}) == len(eventos)
        and fallo is terminal
        and len(ready) == (1 if terminal else 2)
        and all(
            g["model_sha256"] == config.expected_model_sha256
            and g["config_sha256"] == config.config_sha256
            and g["torch_threads"] == 2
            for g in ready
        )
        and len(trazas) == 1
        and trazas[0]["publicado_monotonic_s"] is not None
        and trazas[0]["reinicio_ok"] is (not terminal)
        and (not terminal or codigo_cli != 0)
    )
    return {
        "run_id": run_id,
        "jsonl": jsonl.name,
        "manifiesto": f"{run_id}.infer-run.json",
        "frame_ids": [e["frame_id"] for e in eventos],
        "codigos": codigos,
        "ready": ready,
        "trazas": trazas,
        "duracion_publicacion_en_intervalo": 500 <= trazas[0]["duracion_publicacion_ms"] <= 600,
        "funcional_valido": valido,
        "fallo_terminal": fallo,
        "codigo_cli_con_resultado_inyectado": codigo_cli,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--intentos", type=int, default=50)
    parser.add_argument("--terminal", action="store_true")
    args = parser.parse_args()
    if args.intentos < 1 or (args.terminal and args.intentos != 1):
        parser.error("--intentos debe ser positivo y --terminal exige un intento")
    salida = directorio_evidencia(args.output)
    resultados = []
    with abrir_exclusivo(salida / "muestras.jsonl") as muestras:
        for indice in range(1, args.intentos + 1):
            try:
                resultado = _intento(salida, indice, terminal=args.terminal)
            except Exception as exc:
                resultado = {"intento": indice, "fallo": f"{type(exc).__name__}: {exc}"}
                muestras.write(json.dumps(resultado, ensure_ascii=False) + "\n")
                muestras.flush()
                raise
            resultados.append(resultado)
            muestras.write(json.dumps(resultado, ensure_ascii=False) + "\n")
            muestras.flush()
            if not resultado["funcional_valido"]:
                break
    resumen = {
        "tipo": "validacion_timeout_simulado",
        "intentos_solicitados": args.intentos,
        "intentos_completados": len(resultados),
        "recuperaciones_correctas": sum(r["trazas"][0]["reinicio_ok"] is True for r in resultados),
        "publicaciones_500_600_ms": sum(r["duracion_publicacion_en_intervalo"] for r in resultados),
        "funcional_valido": all(r["funcional_valido"] for r in resultados),
        "terminal": args.terminal,
        "simulado": True,
    }
    with abrir_exclusivo(salida / "resumen.json") as archivo:
        archivo.write(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(resumen, ensure_ascii=False))
    return (
        0
        if resumen["funcional_valido"]
        and (args.terminal or resumen["recuperaciones_correctas"] == args.intentos)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
