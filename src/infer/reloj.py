"""Reloj de alta resolución común al publicador, trabajador y benchmark de P5-06."""

from __future__ import annotations

import time
from typing import Any


def leer_reloj_s() -> float:
    """Instante del reloj de rendimiento, en segundos, comparable entre procesos."""
    return time.perf_counter()


def leer_reloj_ns() -> int:
    """El mismo reloj en nanosegundos, sin redondeo previo a coma flotante."""
    return time.perf_counter_ns()


def descripcion_reloj() -> dict[str, Any]:
    """Características reportadas por Python; no son una resolución medida."""
    info = time.get_clock_info("perf_counter")
    return {
        "nombre": "perf_counter",
        "implementacion": info.implementation,
        "resolucion_reportada_s": info.resolution,
    }
