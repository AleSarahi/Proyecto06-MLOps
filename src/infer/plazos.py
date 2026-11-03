"""Plazos compartidos que usa el detector, fuera de config_sha256."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import RAIZ

RUTA_PLAZOS = RAIZ / "config" / "control" / "plazos.yaml"
_CLAVES = ("detector_timeout_ms", "max_frame_age_ms")


class ErrorPlazosInfer(ValueError):
    """Faltan plazos compartidos o tienen valores incompatibles con infer."""


@dataclass(frozen=True)
class PlazosInfer:
    detector_timeout_ms: float
    max_frame_age_ms: float


def validar_plazos_infer(datos: Any) -> PlazosInfer:
    """Acepta los demás plazos de B, pero exige dos números positivos y finitos."""
    if not isinstance(datos, dict):
        raise ErrorPlazosInfer("plazos.yaml debe ser un mapa clave: valor")
    faltan = [clave for clave in _CLAVES if clave not in datos]
    if faltan:
        raise ErrorPlazosInfer(f"plazos.yaml: faltan claves {faltan}")
    valores = {}
    for clave in _CLAVES:
        valor = datos[clave]
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErrorPlazosInfer(f"plazos.yaml: {clave} debe ser un número finito > 0")
        try:
            numero = float(valor)
        except (OverflowError, ValueError) as exc:
            raise ErrorPlazosInfer(f"plazos.yaml: {clave} debe ser un número finito > 0") from exc
        if not math.isfinite(numero) or numero <= 0:
            raise ErrorPlazosInfer(f"plazos.yaml: {clave} debe ser un número finito > 0")
        valores[clave] = numero
    if valores["detector_timeout_ms"] > valores["max_frame_age_ms"]:
        raise ErrorPlazosInfer("detector_timeout_ms no puede superar max_frame_age_ms")
    return PlazosInfer(**valores)


def cargar_plazos_infer(ruta: str | Path = RUTA_PLAZOS) -> PlazosInfer:
    """Lee el YAML compartido; nunca agrega sus plazos al hash del detector."""
    return cargar_plazos_infer_con_hash(ruta)[0]


def cargar_plazos_infer_con_hash(ruta: str | Path = RUTA_PLAZOS) -> tuple[PlazosInfer, str]:
    """Valida y calcula SHA-256 de los mismos bytes YAML aplicados al run."""
    ruta = Path(ruta)
    try:
        contenido = ruta.read_bytes()
        datos = yaml.safe_load(contenido.decode("utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ErrorPlazosInfer(f"no se pudo leer plazos.yaml: {exc}") from exc
    return validar_plazos_infer(datos), hashlib.sha256(contenido).hexdigest()
