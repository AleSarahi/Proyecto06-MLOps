"""Verifica límites de medición sin ejecutar series oficiales de rendimiento."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import torch

import infer.benchmark as bench
from contrato import validar_evento
from infer.config import RUTA_CONFIG_DETECTOR, cargar_config_detector
from infer.detector import ResultadoJPEG
from infer.plazos import PlazosInfer
from infer.trabajador import PredictorSupervisado, _desglosar_ready_ns


class DetectorFalso:
    def __init__(self):
        self.config = cargar_config_detector()
        self.cargado = SimpleNamespace(
            model_sha256=self.config.expected_model_sha256,
            config_sha256=self.config.config_sha256,
        )

    def calentar(self):
        torch.set_num_threads(2)

    def inferir(self, ruta, *, imagen=None):
        assert imagen is not None and Path(ruta).suffix == ".jpg"
        return ResultadoJPEG(
            imagen.shape[1],
            imagen.shape[0],
            (1, 3, 60, 80),
            (),
            0.0,
            self.cargado.model_sha256,
            self.config.config_sha256,
        )


def crear_detector_falso(_config: Path, _pesos: Path) -> DetectorFalso:
    return DetectorFalso()


def _jpeg(tmp_path: Path) -> Path:
    ruta = tmp_path / "imagen.jpg"
    assert cv2.imwrite(str(ruta), np.zeros((60, 80, 3), dtype=np.uint8))
    return ruta


def test_limites_del_control_y_solicitud_supervisada_son_deterministas(monkeypatch) -> None:
    reloj = [1_000_000_000]
    llamadas = []

    def evento(
        _detector, ruta, run_id, secuencia, indice, frame_id, captura, reloj_ms, edad, aviso
    ):
        llamadas.append((ruta, run_id, secuencia, indice, frame_id, captura, edad))
        assert reloj_ms() == 0
        aviso((80, 60))
        reloj[0] += 7_000_000
        return {"status": "ok", "detections": []}

    monkeypatch.setattr(bench, "_evento_cuadro", evento)
    plazos = PlazosInfer(500, 500)
    ruta = Path("imagen.jpg")
    duracion, control = bench.medir_control(
        object(), ruta, request_id=3, plazos=plazos, reloj_ns=lambda: reloj[0]
    )
    assert duracion == 7.0 and control["status"] == "ok"
    assert llamadas == [(ruta, "p506-benchmark", "independent", 3, "imagen", 0.0, 500)]

    class Supervisor:
        def solicitar(self, **kwargs):
            llamadas.append(kwargs)
            reloj[0] += 11_000_000
            return "result", {"status": "ok", "detections": []}, (80, 60)

    duracion, supervisado = bench.medir_supervisado(
        Supervisor(), ruta, request_id=4, plazos=plazos, reloj_ns=lambda: reloj[0]
    )
    assert duracion == 11.0 and supervisado == control
    assert llamadas[-1]["origen"] == pytest.approx(1.007)
    assert llamadas[-1]["captura"] == 0.0
    assert llamadas[-1]["request_id"] == 4
    assert llamadas[-1]["plazos"] is plazos


def test_fases_ready_suman_total_y_rechazan_reloj_inconsistente() -> None:
    tiempos = _desglosar_ready_ns((100, 200, 300, 500, 800, 1100))
    assert tiempos["duracion_ms"] == pytest.approx(0.001)
    assert sum(tiempos["fases_ms"].values()) - tiempos[
        "solapamiento_creacion_hijo_ms"
    ] == pytest.approx(tiempos["duracion_ms"])
    assert set(tiempos["fases_ms"]) == {
        "creacion_proceso",
        "arranque_hijo",
        "carga_verificacion",
        "calentamiento",
        "entrega_ready",
    }
    with pytest.raises(RuntimeError, match="monotónicas"):
        _desglosar_ready_ns((100, 300, 200, 150, 800, 1100))
    solapado = _desglosar_ready_ns((100, 300, 200, 500, 800, 1100))
    assert solapado["solapamiento_creacion_hijo_ms"] == pytest.approx(0.0001)
    assert sum(solapado["fases_ms"].values()) - solapado[
        "solapamiento_creacion_hijo_ms"
    ] == pytest.approx(solapado["duracion_ms"])


def test_misma_solicitud_en_ambas_rutas_y_ready_verificado(tmp_path: Path) -> None:
    ruta = _jpeg(tmp_path)
    plazos = PlazosInfer(500, 500)
    detector = DetectorFalso()
    detector.calentar()
    _, control = bench.medir_control(detector, ruta, request_id=1, plazos=plazos)
    predictor = PredictorSupervisado(
        RUTA_CONFIG_DETECTOR,
        tmp_path / "pesos-falsos",
        detector.config,
        fabrica=crear_detector_falso,
        inicio_guarda_s=10,
    )
    try:
        predictor.iniciar()
        _, supervisado = bench.medir_supervisado(predictor, ruta, request_id=1, plazos=plazos)
        ready = predictor.cronologia[-1]
    finally:
        predictor.close()
    assert control["status"] == supervisado["status"] == "ok"
    assert control["detections"] == supervisado["detections"] == []
    assert [control["frame_id"], supervisado["frame_id"]] == [ruta.stem] * 2
    assert all(validar_evento(e) == [] for e in (control, supervisado))
    assert ready["model_sha256"] == detector.cargado.model_sha256
    assert ready["config_sha256"] == detector.config.config_sha256
    assert ready["torch_threads"] == 2
    assert sum(ready["fases_ms"].values()) - ready[
        "solapamiento_creacion_hijo_ms"
    ] == pytest.approx(ready["duracion_ms"])
    assert predictor.cierre_limpio is True


def test_supervision_no_acepta_timeout_como_muestra_exitosa() -> None:
    class Supervisor:
        def solicitar(self, **_kwargs):
            return "timeout", None, None

    with pytest.raises(RuntimeError, match="timeout"):
        bench.medir_supervisado(
            Supervisor(), Path("imagen.jpg"), request_id=1, plazos=PlazosInfer(500, 500)
        )


def test_reinicio_mide_desde_detencion_hasta_ready_sin_perder_fases() -> None:
    reloj = [0]

    class Supervisor:
        def __init__(self):
            self.cronologia = []

        def detener(self):
            reloj[0] += 2_000_000
            return True

        def iniciar(self):
            reloj[0] += 7_000_000
            self.cronologia.append({"duracion_ms": 6.0, "estado": "ready"})

    muestra = bench.medir_reinicio(Supervisor(), reloj_ns=lambda: reloj[0])
    assert muestra["total_ms"] == 9.0
    assert muestra["detencion_ms"] == 2.0
    assert muestra["coordinacion_ms"] == 1.0
    assert muestra["ready"]["estado"] == "ready"
