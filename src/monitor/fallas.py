"""Fallas inyectadas en el detector para los escenarios S3 y S4 (extras, issue #37).

`DetectorConFallas` envuelve al detector real de YOLO11n. Para los frames cuya posición (ms del
segmento) cae en un intervalo configurado:

- `errores`: la llamada al modelo lanza una excepción, como un fallo del runtime. `Inferidor` la
  convierte en un evento `status: error` con `code: detector_exception`. No se inventa ninguna
  detección: el frame simplemente no se infiere.
- `lentitud`: antes de la llamada real se agrega una demora fija (contención de CPU simulada). El
  modelo infiere igual; solo tarda más, la cola crece y los frames atrasados más de
  `atraso_max_ms` se descartan por saturación, como en un stream que no espera.

Fuera de los intervalos el detector es exactamente el real. La inyección queda declarada en
`run.json → modelo.inyeccion`.
"""

from __future__ import annotations

import time
from typing import Any


def _intervalos(cortes: list[tuple[float, float]]) -> list[list[float]]:
    return [[a / 1000, b / 1000] for a, b in cortes]


class DetectorConFallas:
    def __init__(
        self,
        interno: Any,
        inferidor: Any,
        *,
        inicio_ms: float,
        errores: list[tuple[float, float]] | None = None,
        lentitud: list[tuple[float, float]] | None = None,
        lentitud_ms: float = 0.0,
    ):
        self.interno = interno
        self.inferidor = inferidor
        self.inicio_ms = inicio_ms
        self.errores = errores or []
        self.lentitud = lentitud or []
        self.lentitud_ms = lentitud_ms

    def calentar(self) -> None:
        self.interno.calentar()

    def descripcion(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "nota": "fallas inyectadas a propósito; fuera de ellas el detector es el real"
        }
        if self.errores:
            d["errores_s"] = _intervalos(self.errores)
        if self.lentitud:
            d["lentitud_s"] = _intervalos(self.lentitud)
            d["lentitud_ms_por_frame"] = self.lentitud_ms
        return d

    def _en(self, intervalos: list[tuple[float, float]]) -> bool:
        pos = getattr(self.inferidor, "posicion_ms", None)
        if pos is None:
            return False
        rel = pos - self.inicio_ms
        return any(a <= rel < b for a, b in intervalos)

    def inferir(self, ruta: Any, *, imagen: Any) -> Any:
        if self._en(self.errores):
            raise RuntimeError("fallo inyectado: el runtime del modelo no respondió")
        if self._en(self.lentitud):
            time.sleep(self.lentitud_ms / 1000)
        return self.interno.inferir(ruta, imagen=imagen)
