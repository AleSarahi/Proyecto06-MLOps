"""Comprobación obligatoria de energía antes de benchmarks P5-06 en Mac y Windows."""

from __future__ import annotations

import csv
import ctypes
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


class ErrorPreflight(RuntimeError):
    """El entorno de energía no permite iniciar una serie oficial."""


def _ejecutar(*argumentos: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argumentos, capture_output=True, text=True, check=False, timeout=5)


def _windows_power_status() -> tuple[int, int]:
    """GetSystemPowerStatus: ACLineStatus y SystemStatusFlag (ahorro)."""

    class SystemPowerStatus(ctypes.Structure):
        _fields_ = [
            ("ac_line_status", ctypes.c_ubyte),
            ("battery_flag", ctypes.c_ubyte),
            ("battery_life_percent", ctypes.c_ubyte),
            ("system_status_flag", ctypes.c_ubyte),
            ("battery_life_time", ctypes.c_uint32),
            ("battery_full_life_time", ctypes.c_uint32),
        ]

    estado = SystemPowerStatus()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not kernel32.GetSystemPowerStatus(ctypes.byref(estado)):
        raise OSError(ctypes.get_last_error(), "GetSystemPowerStatus falló")
    return estado.ac_line_status, estado.system_status_flag


def _consultar_mac(ejecutar: Callable[..., Any]) -> dict[str, Any]:
    fuente = "pmset -g ps; pmset -g (lowpowermode activo)"
    try:
        energia = ejecutar("pmset", "-g", "ps")
        ahorro = ejecutar("pmset", "-g")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "fuente": fuente,
            "alimentacion": "desconocida",
            "ahorro": "desconocido",
            "detalle": str(exc),
        }
    if energia.returncode != 0 or ahorro.returncode != 0:
        return {
            "fuente": fuente,
            "alimentacion": "desconocida",
            "ahorro": "desconocido",
            "detalle": f"pmset falló: ps={energia.returncode}, ajustes={ahorro.returncode}",
        }
    primera = energia.stdout.splitlines()[0].strip() if energia.stdout.splitlines() else ""
    alimentacion = {
        "Now drawing from 'AC Power'": "ac",
        "Now drawing from 'Battery Power'": "bateria",
    }.get(primera, "desconocida")
    valores = re.findall(r"(?m)^\s*lowpowermode\s+([01])\s*$", ahorro.stdout)
    modo = (
        {"0": "desactivado", "1": "activado"}.get(valores[0], "desconocido")
        if len(valores) == 1
        else "desconocido"
    )
    return {
        "fuente": fuente,
        "alimentacion": alimentacion,
        "ahorro": modo,
        "detalle": {"pmset_ps": primera, "lowpowermode": valores},
    }


def _consultar_windows(
    consultar_estado: Callable[[], tuple[int, int]], ejecutar: Callable[..., Any]
) -> dict[str, Any]:
    fuente = "GetSystemPowerStatus: ACLineStatus, SystemStatusFlag; tasklist /FO CSV /NH"
    try:
        ac, ahorro = consultar_estado()
    except (OSError, AttributeError, ValueError) as exc:
        return {
            "fuente": fuente,
            "alimentacion": "desconocida",
            "ahorro": "desconocido",
            "detalle": str(exc),
        }
    alimentacion = {0: "bateria", 1: "ac"}.get(ac, "desconocida")
    modo = {0: "desactivado", 1: "activado"}.get(ahorro, "desconocido")
    try:
        procesos = ejecutar("tasklist", "/FO", "CSV", "/NH")
    except (OSError, subprocess.TimeoutExpired) as exc:
        procesos = None
        detalle_procesos = str(exc)
    else:
        detalle_procesos = f"tasklist código {procesos.returncode}"
    bloqueantes: list[str] | None = None
    if procesos is not None and procesos.returncode == 0:
        nombres = {fila[0].casefold() for fila in csv.reader(procesos.stdout.splitlines()) if fila}
        bloqueantes = sorted(nombres & {"onedrive.exe", "code.exe", "code - insiders.exe"})
    return {
        "fuente": fuente,
        "alimentacion": alimentacion,
        "ahorro": modo,
        "procesos_bloqueantes": bloqueantes,
        "detalle": {
            "ac_line_status": ac,
            "system_status_flag": ahorro,
            "tasklist": detalle_procesos,
        },
    }


def consultar_preflight(
    *,
    sistema: str | None = None,
    ejecutar: Callable[..., Any] = _ejecutar,
    consultar_windows: Callable[[], tuple[int, int]] = _windows_power_status,
) -> dict[str, Any]:
    """Devuelve estado y fuente; desconocidos o consultas fallidas bloquean la serie."""
    sistema = sys.platform if sistema is None else sistema
    if sistema == "darwin":
        estado = _consultar_mac(ejecutar)
    elif sistema == "win32":
        estado = _consultar_windows(consultar_windows, ejecutar)
    else:
        estado = {"fuente": "no disponible", "alimentacion": "desconocida", "ahorro": "desconocido"}
    fallos = []
    if estado["alimentacion"] != "ac":
        fallos.append("se requiere alimentación AC verificada")
    if estado["ahorro"] != "desactivado":
        fallos.append("se requiere ahorro de energía desactivado y verificado")
    if sistema == "win32":
        if estado.get("procesos_bloqueantes") is None:
            fallos.append("no se pudo verificar OneDrive/VS Code")
        elif estado["procesos_bloqueantes"]:
            fallos.append("OneDrive/VS Code deben estar cerrados")
    return {"sistema": sistema, **estado, "aprobado": not fallos, "fallos": fallos}


def exigir_preflight(estado: dict[str, Any]) -> None:
    """Impide medir si cualquier condición obligatoria no está demostrada."""
    if not estado["aprobado"]:
        raise ErrorPreflight("; ".join(estado["fallos"]))


def guardar_y_exigir_preflight(ruta: Path, estado: dict[str, Any]) -> None:
    """Conserva también un rechazo antes de permitir que se prepare el predictor."""
    with Path(ruta).open("x", encoding="utf-8") as archivo:
        json.dump(estado, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")
    exigir_preflight(estado)
