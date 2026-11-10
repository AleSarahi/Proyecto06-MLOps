"""Dos umbrales y tres zonas de confianza (issue #11).

Interpretación obligatoria (rúbrica R3):
- s < inferior               -> "baja"     (baja confianza)
- inferior <= s < superior   -> "duda"
- s >= superior              -> "aceptada" (aceptada por la política; no afirma que sea correcta)

Los frames sin candidatas ("sin_detecciones") y los fallos de inferencia ("error") son estados
aparte: no reciben zona ni una confianza artificial de 0.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

BAJA, DUDA, ACEPTADA = "baja", "duda", "aceptada"
OK, SIN_DETECCIONES, ERROR = "ok", "sin_detecciones", "error"


def zona(score: float, inferior: float, superior: float) -> str:
    if not 0 <= inferior < superior <= 1:
        raise ValueError("se requiere 0 <= inferior < superior <= 1")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ValueError(f"score inválido: {score!r}")
    if not 0 <= score <= 1:
        raise ValueError(f"score fuera de [0, 1]: {score}")
    if score < inferior:
        return BAJA
    if score < superior:
        return DUDA
    return ACEPTADA


def zona_frame(scores: Iterable[float], inferior: float, superior: float) -> str | None:
    """Zona del frame = zona de su candidata de mayor score; None si no hay candidatas."""
    scores = list(scores)
    if not scores:
        return None
    return zona(max(scores), inferior, superior)


def conteo(zonas: Iterable[str]) -> dict[str, int]:
    resultado = {BAJA: 0, DUDA: 0, ACEPTADA: 0}
    for z in zonas:
        resultado[z] += 1
    return resultado
