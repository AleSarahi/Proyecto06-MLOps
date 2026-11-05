"""P5-21: `DetectorEnVivo`, la entrada por cuadro del predictor supervisado, con el predictor falso
de las pruebas de P5-06 (proceso `spawn` real, sin pesos)."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from contrato import validar_evento, validar_flujo
from infer.config import RUTA_CONFIG_DETECTOR
from infer.cuadro import DetectorEnVivo
from infer.eventos import ErrorRunInfer
from test_infer_trabajador import crear_predictor_falso

MODELO_CALIFICADO = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
CONFIG_CALIFICADA = "6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08"


def _jpeg(ruta: Path, valido: bool = True) -> Path:
    if valido:
        assert cv2.imwrite(str(ruta), np.zeros((60, 80, 3), dtype=np.uint8))
    else:
        ruta.write_bytes(b"")
    return ruta


def _detector(tmp_path: Path, modo: dict | None = None, **kwargs) -> DetectorEnVivo:
    estado = tmp_path / "estado.json"
    estado.write_text(json.dumps(modo or {}), encoding="utf-8")
    return DetectorEnVivo(
        RUTA_CONFIG_DETECTOR,
        estado,
        run_id="vivo-test",
        fabrica=crear_predictor_falso,
        inicio_guarda_s=10,
        **kwargs,
    )


def test_los_hashes_son_los_calificados(tmp_path: Path) -> None:
    detector = _detector(tmp_path)
    assert detector.model_sha256 == MODELO_CALIFICADO
    assert detector.config_sha256 == CONFIG_CALIFICADA


def test_un_cuadro_bueno_da_un_evento_ok_del_contrato(tmp_path: Path) -> None:
    detector = _detector(tmp_path)
    detector.iniciar()
    try:
        captura = detector.ahora_ms()
        evento = detector.evento(_jpeg(tmp_path / "a.jpg"), "F000001", captura)
    finally:
        assert detector.cerrar()
    assert validar_evento(evento) == []
    assert evento["status"] == "ok"
    assert (evento["run_id"], evento["sequence_id"], evento["frame_id"]) == (
        "vivo-test",
        "vivo",
        "F000001",
    )
    assert evento["model_sha256"] == MODELO_CALIFICADO
    assert evento["config_sha256"] == CONFIG_CALIFICADA
    assert evento["t_capture_ms"] == captura <= evento["t_emit_ms"]
    assert (evento["image_width"], evento["image_height"]) == (80, 60)


def test_varios_cuadros_forman_un_flujo_valido(tmp_path: Path) -> None:
    detector = _detector(tmp_path)
    detector.iniciar()
    try:
        eventos = [
            detector.evento(_jpeg(tmp_path / f"{n}.jpg"), f"F{n:06d}", detector.ahora_ms())
            for n in range(1, 4)
        ]
    finally:
        detector.cerrar()
    assert validar_flujo(eventos) == []
    assert [e["status"] for e in eventos] == ["ok"] * 3


def test_un_jpeg_ilegible_es_un_evento_de_error_y_no_reinicia(tmp_path: Path) -> None:
    detector = _detector(tmp_path)
    detector.iniciar()
    try:
        evento = detector.evento(_jpeg(tmp_path / "a.jpg", False), "F000001", detector.ahora_ms())
        siguiente = detector.evento(_jpeg(tmp_path / "b.jpg"), "F000002", detector.ahora_ms())
    finally:
        detector.cerrar()
    assert evento["status"] == "error" and evento["error"]["code"] == "unreadable_image"
    assert validar_evento(evento) == []
    assert siguiente["status"] == "ok"
    assert detector.reinicios == 0


def test_un_cuadro_viejo_sale_como_stale(tmp_path: Path) -> None:
    detector = _detector(tmp_path)
    detector.iniciar()
    try:
        viejo = detector.ahora_ms() - 2 * detector.plazos.max_frame_age_ms
        evento = detector.evento(_jpeg(tmp_path / "a.jpg"), "F000001", viejo)
    finally:
        detector.cerrar()
    assert evento["status"] == "stale" and evento["detections"] == []
    assert validar_evento(evento) == []


def test_un_timeout_da_error_reinicia_y_el_siguiente_cuadro_sale_ok(tmp_path: Path) -> None:
    detector = _detector(tmp_path, {"bloquear": True})  # la generación 1 se cuelga 3 s
    detector.iniciar()
    try:
        colgado = detector.evento(_jpeg(tmp_path / "a.jpg"), "F000001", detector.ahora_ms())
        assert colgado["status"] == "error" and colgado["error"]["code"] == "detector_timeout"
        assert detector.reinicios == 1 and detector.disponible
        despues = detector.evento(_jpeg(tmp_path / "b.jpg"), "F000002", detector.ahora_ms())
    finally:
        assert detector.cerrar()
    assert despues["status"] == "ok"
    assert validar_flujo([colgado, despues]) == []


def test_si_el_reinicio_falla_cada_cuadro_es_un_error_del_detector(tmp_path: Path) -> None:
    detector = _detector(tmp_path, {"bloquear": True, "fallar_reinicio": True})
    detector.iniciar()
    try:
        primero = detector.evento(_jpeg(tmp_path / "a.jpg"), "F000001", detector.ahora_ms())
        assert not detector.disponible
        siguientes = [
            detector.evento(_jpeg(tmp_path / f"{n}.jpg"), f"F{n:06d}", detector.ahora_ms())
            for n in (2, 3)
        ]
    finally:
        detector.cerrar()
    assert primero["error"]["code"] == "detector_timeout"
    assert [e["status"] for e in siguientes] == ["error", "error"]
    assert {e["error"]["code"] for e in siguientes} == {"detector_exception"}
    assert all(validar_evento(e) == [] for e in siguientes)


def test_un_error_del_predictor_es_detector_exception_y_reinicia(tmp_path: Path) -> None:
    detector = _detector(tmp_path, {"error": True})
    detector.iniciar()
    try:
        evento = detector.evento(_jpeg(tmp_path / "a.jpg"), "F000001", detector.ahora_ms())
    finally:
        detector.cerrar()
    assert evento["status"] == "error" and evento["error"]["code"] == "detector_exception"
    assert validar_evento(evento) == []


@pytest.mark.parametrize("frame_id", ["", "con espacio", "a" * 65, "ñ"])
def test_un_frame_id_fuera_del_contrato_se_rechaza(tmp_path: Path, frame_id: str) -> None:
    detector = _detector(tmp_path)
    detector.iniciar()
    try:
        with pytest.raises(ErrorRunInfer, match="frame_id"):
            detector.evento(_jpeg(tmp_path / "a.jpg"), frame_id, 0.0)
    finally:
        detector.cerrar()


@pytest.mark.parametrize("campo", ["run_id", "sequence_id"])
def test_los_ids_del_run_se_validan_al_crear(tmp_path: Path, campo: str) -> None:
    estado = tmp_path / "estado.json"
    estado.write_text("{}", encoding="utf-8")
    ids = {"run_id": "vivo-test", "sequence_id": "vivo", campo: "mal id"}
    with pytest.raises(ErrorRunInfer, match=campo):
        DetectorEnVivo(
            RUTA_CONFIG_DETECTOR, estado, fabrica=crear_predictor_falso, inicio_guarda_s=10, **ids
        )


def test_no_se_pide_un_evento_despues_de_cerrar(tmp_path: Path) -> None:
    detector = _detector(tmp_path)
    detector.iniciar()
    assert detector.cerrar()
    with pytest.raises(ErrorRunInfer, match="cerrado"):
        detector.evento(_jpeg(tmp_path / "a.jpg"), "F000001", 0.0)


def test_los_pesos_reales_se_verifican_antes_de_arrancar(tmp_path: Path) -> None:
    """Con la fábrica real, un checkpoint falso no llega a arrancar el proceso."""
    falso = tmp_path / "yolo11n.pt"
    falso.write_bytes(b"no soy un checkpoint")
    detector = DetectorEnVivo(RUTA_CONFIG_DETECTOR, falso, run_id="vivo-test")
    with pytest.raises(ErrorRunInfer, match="checkpoint local inválido"):
        detector.iniciar()
    detector.cerrar()
