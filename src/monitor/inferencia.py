"""Inferencia real con YOLO11n para el Proyecto 6 (issue #6).

Reutiliza la carga verificada por SHA-256 y el detector validado de P5 (`src/infer/`). Cambia solo
la configuración: config/p6/detector.json con las clases COCO del video (persona, bicicleta, auto,
moto, autobús, camión) y un piso de salida de 0.10, por debajo del umbral inferior, para que la zona
de baja confianza se pueda observar. El NMS (IoU 0.7) y el preprocesamiento son los de P5.

El tiempo de inferencia se mide con `time.perf_counter` alrededor de la llamada al modelo, separado
de la lectura del frame, de la captura y de la persistencia.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from infer.config import cargar_config_detector
from infer.detector import DetectorJPEG, ErrorSalidaInvalida
from infer.pesos import cargar_pesos


@dataclass(frozen=True)
class Salida:
    status: str  # ok | sin_detecciones | error
    detecciones: list[dict[str, Any]]
    inicio_ms: float | None
    fin_ms: float | None
    error: dict[str, str] | None


class Inferidor:
    def __init__(self, ruta_config_detector: Path, reloj_ms):
        self.config = cargar_config_detector(ruta_config_detector, clases_aprobadas=set(range(80)))
        self.cargado = cargar_pesos(self.config.weights_path, self.config)
        self.detector = DetectorJPEG(self.cargado, self.config)
        self.detector.calentar()
        self.nombres = dict(self.cargado.modelo.names)
        self.reloj_ms = reloj_ms

    @property
    def model_ref(self) -> str:
        return self.cargado.model_sha256

    @property
    def detector_config_sha256(self) -> str:
        return self.config.config_sha256

    def ficha(self) -> dict[str, Any]:
        return {
            "model_ref": self.model_ref,
            "detector_config_sha256": self.detector_config_sha256,
            "pesos": str(self.config.weights_path),
            "efectiva": self.config.effective,
            "clases": {
                str(c): self.nombres[c] for c in self.config.effective["postprocess"]["class_ids"]
            },
        }

    def inferir(self, imagen: np.ndarray) -> Salida:
        inicio = self.reloj_ms()
        try:
            r = self.detector.inferir(None, imagen=imagen)
        except ErrorSalidaInvalida as exc:
            return Salida(
                "error",
                [],
                inicio,
                self.reloj_ms(),
                {"code": "invalid_output", "message": str(exc)},
            )
        except Exception as exc:
            return Salida(
                "error",
                [],
                inicio,
                self.reloj_ms(),
                {"code": "detector_exception", "message": f"{type(exc).__name__}: {exc}"},
            )
        fin = self.reloj_ms()
        dets = [
            {
                "class_id": d.class_id,
                "class_name": self.nombres.get(d.class_id, str(d.class_id)),
                "score": round(float(d.confidence), 6),
                "bbox": [round(float(x), 2) for x in d.bbox],
            }
            for d in r.detections
        ]
        return Salida("ok" if dets else "sin_detecciones", dets, inicio, fin, None)


def reloj_monotonico():
    """Reloj de la corrida en ms desde su creación (perf_counter)."""
    t0 = time.perf_counter()
    return lambda: (time.perf_counter() - t0) * 1000.0
