"""Benchmark emparejado P5-06. Ejecutar solo cuando se autoricen las series oficiales."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
import torch

from contrato import validar_evento
from infer.benchmark import medir_control, medir_reinicio, medir_supervisado
from infer.config import RUTA_CONFIG_DETECTOR, cargar_config_detector
from infer.detector import DetectorJPEG
from infer.pesos import cargar_pesos
from infer.plazos import cargar_plazos_infer_con_hash
from infer.preflight import consultar_preflight, exigir_preflight, guardar_y_exigir_preflight
from infer.trabajador import PredictorSupervisado

RAIZ = Path(__file__).resolve().parents[1]
IMAGEN = RAIZ / "docs/carro/objeto_taza_centro_cerca.jpg"
REFERENCIA = RAIZ / "resultados/p5-05-aceptacion-2h-a.jsonl"
MODELO_SHA256 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
CONFIG_SHA256 = "6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08"
IMAGEN_SHA256 = "670fec5473ceda61b5a6283711596d610d75577dfb1bc9d5ffc8de52c1e9cbcc"


def _sha256(ruta: Path) -> str:
    with ruta.open("rb") as archivo:
        return hashlib.file_digest(archivo, "sha256").hexdigest()


def _stats(muestras: list[float]) -> dict[str, float]:
    return {
        "media": statistics.mean(muestras),
        "p50": statistics.median(muestras),
        "p95_lineal": float(np.percentile(muestras, 95, method="linear")),
        "min": min(muestras),
        "max": max(muestras),
    }


def _ram_bytes() -> int | None:
    if sys.platform == "darwin":
        respuesta = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=False
        )
        return int(respuesta.stdout.strip()) if respuesta.returncode == 0 else None
    if sys.platform == "win32":

        class Memoria(ctypes.Structure):
            _fields_ = [
                ("longitud", ctypes.c_ulong),
                ("carga", ctypes.c_ulong),
                ("total_fisica", ctypes.c_ulonglong),
                ("libre_fisica", ctypes.c_ulonglong),
                ("total_pagina", ctypes.c_ulonglong),
                ("libre_pagina", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("libre_virtual", ctypes.c_ulonglong),
                ("libre_virtual_ext", ctypes.c_ulonglong),
            ]

        memoria = Memoria()
        memoria.longitud = ctypes.sizeof(Memoria)
        return (
            memoria.total_fisica
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memoria))
            else None
        )
    if hasattr(os, "sysconf"):
        try:
            return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError):
            return None
    return None


def _carga_sistema() -> tuple[float, float, float] | None:
    return os.getloadavg() if hasattr(os, "getloadavg") else None


def _condicion_serie() -> dict:
    return {
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "carga_sistema": _carga_sistema(),
        "preflight": consultar_preflight(),
    }


def _registrar_condicion(condiciones: dict, clave: str) -> None:
    condiciones[clave] = _condicion_serie()
    exigir_preflight(condiciones[clave]["preflight"])


def _comparar(evento: dict, referencia: dict) -> None:
    if validar_evento(evento):
        raise RuntimeError("evento producido durante benchmark no cumple A→B v1")
    for campo in ("status", "image_width", "image_height", "detections"):
        if evento[campo] != referencia[campo]:
            raise RuntimeError(f"diferencia de detecciones o estado en {campo}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--responsable", required=True)
    args = parser.parse_args()

    pesos = args.weights.absolute()
    salida = args.output.absolute()
    config = cargar_config_detector()
    plazos, plazos_sha256 = cargar_plazos_infer_con_hash()
    if pesos.is_symlink() or pesos.stat().st_size != 5_613_764 or _sha256(pesos) != MODELO_SHA256:
        raise RuntimeError("checkpoint distinto al aprobado")
    if config.config_sha256 != CONFIG_SHA256 or config.expected_model_sha256 != MODELO_SHA256:
        raise RuntimeError("configuración efectiva distinta a P5-05")
    if config.torch_threads != 2 or _sha256(IMAGEN) != IMAGEN_SHA256:
        raise RuntimeError("hilos o JPEG distintos a P5-05")
    referencia = next(
        json.loads(linea)
        for linea in REFERENCIA.read_text(encoding="utf-8").splitlines()
        if json.loads(linea)["frame_id"] == "ensayo-0012"
    )
    salida.parent.mkdir(parents=True, exist_ok=True)
    preflight_ruta = salida.with_name(salida.stem + ".preflight.json")
    if salida.exists() or preflight_ruta.exists():
        raise FileExistsError(f"no se sobrescribe evidencia: {salida} o {preflight_ruta}")
    preflight = consultar_preflight()
    guardar_y_exigir_preflight(preflight_ruta, preflight)
    carga_inicial = _carga_sistema()

    # Pares intercalados control→supervisado; reinicios después y por separado.
    detector = DetectorJPEG(cargar_pesos(pesos, config), config)
    detector.calentar()
    if torch.get_num_threads() != 2:
        raise RuntimeError("control sin dos hilos efectivos")
    control: list[float] = []
    control_excluidos: list[float] = []
    supervisado: list[float] = []
    supervisado_excluidos: list[float] = []
    reinicios_excluidos: list[dict] = []
    reinicios_medidos: list[dict] = []
    predictor: PredictorSupervisado | None = None
    fase = "latencia"
    indice_actual = 0
    condiciones: dict[str, dict] = {}
    try:
        predictor = PredictorSupervisado(RUTA_CONFIG_DETECTOR, pesos, config)
        predictor.iniciar()
        _registrar_condicion(condiciones, "latencia_intercalada_inicio")
        for indice in range(1, 61):
            fase = "latencia_control"
            indice_actual = indice
            duracion, evento = medir_control(detector, IMAGEN, request_id=indice, plazos=plazos)
            _comparar(evento, referencia)
            (control_excluidos if indice <= 10 else control).append(duracion)
            fase = "latencia_supervisado"
            duracion, evento = medir_supervisado(
                predictor, IMAGEN, request_id=indice, plazos=plazos
            )
            _comparar(evento, referencia)
            (supervisado_excluidos if indice <= 10 else supervisado).append(duracion)
        _registrar_condicion(condiciones, "latencia_intercalada_fin")
        fase = "reinicio"
        _registrar_condicion(condiciones, "reinicio_inicio")
        for indice in range(60):
            indice_actual = indice + 1
            muestra = medir_reinicio(predictor)
            (reinicios_excluidos if indice < 10 else reinicios_medidos).append(muestra)
        _registrar_condicion(condiciones, "reinicio_fin")
    except Exception as exc:
        with salida.open("x", encoding="utf-8") as archivo:
            json.dump(
                {
                    "tipo": "benchmark_p5_06_incompleto",
                    "fase": fase,
                    "indice": indice_actual,
                    "fallo": f"{type(exc).__name__}: {exc}",
                    "muestras_ms": {"control": control, "supervisado": supervisado},
                    "calentamientos_excluidos_ms": {
                        "control": control_excluidos,
                        "supervisado": supervisado_excluidos,
                    },
                    "reinicios_excluidos": reinicios_excluidos,
                    "reinicios_medidos": reinicios_medidos,
                    "condiciones_series": condiciones,
                    "checkpoint_sha256": MODELO_SHA256,
                    "config_sha256": CONFIG_SHA256,
                    "imagen_sha256": IMAGEN_SHA256,
                },
                archivo,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            archivo.write("\n")
        raise
    finally:
        if predictor is not None:
            predictor.close()

    control_stats = _stats(control)
    supervisado_stats = _stats(supervisado)
    reinicio_stats = _stats([m["total_ms"] for m in reinicios_medidos])
    fases_reinicio = (
        "detencion_ms",
        "coordinacion_ms",
        "creacion_proceso",
        "arranque_hijo",
        "carga_verificacion",
        "calentamiento",
        "entrega_ready",
        "solapamiento_creacion_hijo_ms",
    )
    reinicio_fases_stats = {
        fase: _stats(
            [
                muestra[fase]
                if fase in {"detencion_ms", "coordinacion_ms"}
                else muestra["ready"].get(fase, muestra["ready"]["fases_ms"].get(fase))
                for muestra in reinicios_medidos
            ]
        )
        for fase in fases_reinicio
    }
    diferencia_ms = {q: supervisado_stats[q] - control_stats[q] for q in ("p50", "p95_lineal")}
    datos = {
        "tipo": "benchmark_p5_06",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "responsable": args.responsable,
        "host": {
            "os": platform.platform(),
            "arquitectura": platform.machine(),
            "cpu": platform.processor(),
            "ram_bytes": _ram_bytes(),
            "python": platform.python_version(),
            "modo_energia": preflight["alimentacion"],
            "preflight": preflight,
            "carga_sistema_inicio": carga_inicial,
            "carga_sistema_fin": _carga_sistema(),
        },
        "comando": sys.argv,
        "condiciones_series": condiciones,
        "runtime": {
            nombre: version(nombre)
            for nombre in ("ultralytics", "torch", "torchvision", "opencv-python", "numpy")
        },
        "checkpoint_sha256": MODELO_SHA256,
        "config_sha256": CONFIG_SHA256,
        "plazos_sha256": plazos_sha256,
        "torch_threads": 2,
        "imagen": str(IMAGEN.relative_to(RAIZ)),
        "imagen_sha256": IMAGEN_SHA256,
        "referencia": str(REFERENCIA.relative_to(RAIZ)),
        "procedimiento": {
            "orden": "10 pares control→supervisado excluidos, 50 pares medidos; reinicios aparte",
            "calentamiento_sintetico": 1,
            "solicitudes_jpeg_excluidas_por_ruta": 10,
            "solicitudes_medidas_por_ruta": 50,
            "reinicios_excluidos": 10,
            "reinicios_medidos": 50,
            "reloj": "time.monotonic_ns",
            "percentil": "numpy.percentile(method=linear)",
            "control": "antes de _evento_cuadro hasta retorno validado, sin IPC",
            "supervisado": "antes de solicitar hasta recibir respuesta completa validada",
            "reinicio": "antes de detener hasta READY verificado",
        },
        "muestras_ms": {"control": control, "supervisado": supervisado},
        "solicitudes_sobre_500_ms": {
            "control": sum(ms > plazos.detector_timeout_ms for ms in control),
            "supervisado": sum(ms > plazos.detector_timeout_ms for ms in supervisado),
        },
        "calentamientos_excluidos_ms": {
            "control": control_excluidos,
            "supervisado": supervisado_excluidos,
        },
        "stats_ms": {
            "control": control_stats,
            "supervisado": supervisado_stats,
            "reinicio": reinicio_stats,
            "fases_reinicio": reinicio_fases_stats,
        },
        "coste_supervision_ipc": {
            "diferencia_ms": diferencia_ms,
            "diferencia_porcentual": {
                q: diferencia_ms[q] / control_stats[q] * 100 for q in diferencia_ms
            },
        },
        "reinicios_excluidos": reinicios_excluidos,
        "reinicios_medidos": reinicios_medidos,
        "detecciones": referencia["detections"],
        "paridad_detecciones": {
            "control_vs_p5_05": "60 de 60 solicitudes iguales en estado, dimensiones y detecciones",
            "supervisado_vs_p5_05": (
                "60 de 60 solicitudes iguales en estado, dimensiones y detecciones"
            ),
            "criterio": "igualdad exacta en mismo host y runtime",
        },
        "desviaciones": [],
    }
    with salida.open("x", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2, allow_nan=False)
        archivo.write("\n")
    print(json.dumps(datos["stats_ms"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
