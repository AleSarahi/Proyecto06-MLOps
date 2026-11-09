"""Proyecto 6 · humo con YOLO11n real sobre frames del respaldo (issue #6).

Se salta si los pesos no están (el CI no los baja): `uv run python -m infer.descarga`.
"""

from __future__ import annotations

import pytest

from monitor import config as cfgmod
from monitor.fuente import FuenteFrames
from monitor.inferencia import Inferidor, reloj_monotonico
from monitor.video import DIR_FRAMES

cfg = cfgmod.cargar()
PESOS = cfgmod.RAIZ / "modelo" / "descargas" / "yolo11n.pt"
pytestmark = pytest.mark.skipif(not PESOS.is_file(), reason="faltan los pesos de YOLO11n")


def test_inferencia_real_atribuible_y_zona_baja_observable():
    reloj = reloj_monotonico()
    inf = Inferidor(cfg.detector_ruta, reloj)
    assert inf.model_ref == "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
    assert inf.detector_config_sha256 == cfg.detector_config_sha256
    frames = list(FuenteFrames(DIR_FRAMES / "c2", velocidad=0, reloj_ms=reloj))[:3]
    salidas = [inf.inferir(f.imagen) for f in frames]
    scores = [d["score"] for s in salidas for d in s.detecciones]
    assert all(s.status in {"ok", "sin_detecciones"} for s in salidas)
    assert all(s.fin_ms >= s.inicio_ms for s in salidas)
    clases = set(cfgmod.leer_yaml(cfgmod.RUTA_MONITOREO) and [0, 1, 2, 3, 5, 7])
    assert {d["class_id"] for s in salidas for d in s.detecciones} <= clases
    # Con el piso de 0.10 se observan candidatas bajo el umbral inferior (zona baja).
    assert any(s < cfg.inferior for s in scores)
    assert all(s >= 0.10 for s in scores)
