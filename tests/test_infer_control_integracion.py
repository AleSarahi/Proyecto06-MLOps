"""Recorridos A→B de C8/C9 con JPEG sintéticos y política real de B.

Para guardar los JSONL observados: P5_06_EVIDENCIA_DIR=<ruta> pytest -q \
    tests/test_infer_control_integracion.py
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from contrato import validar_comando, validar_evento, validar_flujo
from control.__main__ import CARPETA_CONFIG, cargar_plazos
from control.adaptador_virtual import AdaptadorVirtual
from control.config import cargar_config_politica
from control.politica import decidir
from control.supervisor import Supervisor
from infer.config import cargar_config_detector
from infer.detector import ErrorSalidaInvalida, ResultadoJPEG
from infer.eventos import ejecutar_run
from infer.pesos import ModeloCargado


def _jsonl(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def _jpeg(ruta: Path) -> None:
    assert cv2.imwrite(str(ruta), np.zeros((60, 80, 3), dtype=np.uint8))


class DetectorDeIntegracion:
    """Sustituye solo la predicción; la decodificación y publicación son las de A."""

    def __init__(self, fallo: str | None, reloj_ms: list[float]):
        self.config = cargar_config_detector()
        self.cargado = ModeloCargado(object(), "a" * 64, self.config.config_sha256)
        self.fallo = fallo
        self.reloj_ms = reloj_ms

    def calentar(self) -> None:
        pass

    def inferir(self, ruta: Path, *, imagen: np.ndarray | None = None) -> ResultadoJPEG:
        assert imagen is not None
        if ruta.stem == "b_fallo":
            if self.fallo == "detector_exception":
                raise RuntimeError("fallo de prueba del predictor")
            if self.fallo == "invalid_output":
                raise ErrorSalidaInvalida("salida de prueba inválida")
            if self.fallo == "stale":
                self.reloj_ms[0] += 501
        return ResultadoJPEG(
            width=imagen.shape[1],
            height=imagen.shape[0],
            tensor_shape=(1, 3, 60, 80),
            detections=(),
            elapsed_ms=0,
            model_sha256=self.cargado.model_sha256,
            config_sha256=self.config.config_sha256,
        )


def _recorrido(tmp_path: Path, fallo: str | None) -> tuple[list[dict], Supervisor, Path, Path]:
    entrada = tmp_path / "jpeg"
    entrada.mkdir()
    _jpeg(entrada / "a_libre.jpg")
    if fallo == "unreadable_image":
        (entrada / "b_fallo.jpg").write_bytes(b"")
    elif fallo is not None:
        nombre = "b_ok_tardio.jpg" if fallo == "ok_tardio" else "b_fallo.jpg"
        _jpeg(entrada / nombre)

    reloj_ms = [0.0]

    def dormir(segundos: float) -> None:
        reloj_ms[0] += segundos * 1000

    detector = DetectorDeIntegracion(fallo, reloj_ms)
    percepcion = tmp_path / "percepcion.jsonl"
    if fallo is None:
        origen = entrada / "a_libre.jpg"
        capturas = [0]
    else:
        origen = entrada
        capturas = [0, 200]
    _, cantidad, errores = ejecutar_run(
        detector,
        origen,
        percepcion,
        run_id=f"p506-{fallo or 'libre'}",
        sequence_id="integracion",
        capture_ms=capturas,
        reloj=lambda: reloj_ms[0] / 1000,
        dormir=dormir,
    )
    eventos = _jsonl(percepcion)
    assert cantidad == len(eventos)
    assert errores == (
        1 if fallo in {"unreadable_image", "detector_exception", "invalid_output"} else 0
    )
    assert validar_flujo(eventos) == []
    assert all(validar_evento(evento) == [] for evento in eventos)

    plazos = cargar_plazos(CARPETA_CONFIG / "plazos.yaml")
    salida_b = tmp_path / "control"
    supervisor = Supervisor(
        decidir,
        AdaptadorVirtual(salida_b, plazos["validez_orden_ms"]),
        plazos,
        cargar_config_politica(),
    )
    return eventos, supervisor, percepcion, salida_b


def _evidencia(
    nombre: str,
    percepcion: Path,
    salida_b: Path,
    registros: list[dict],
) -> None:
    destino_raiz = os.environ.get("P5_06_EVIDENCIA_DIR")
    if destino_raiz is None:
        return
    destino = Path(destino_raiz) / nombre
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(percepcion, destino / "percepcion.jsonl")
    for archivo in ("comandos.jsonl", "errores.jsonl"):
        shutil.copyfile(salida_b / archivo, destino / archivo)
    (destino / "resultado.json").write_text(
        json.dumps(registros, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("fallo", "status", "codigo", "motivo"),
    [
        ("unreadable_image", "error", "unreadable_image", "error_detector:unreadable_image"),
        ("detector_exception", "error", "detector_exception", "error_detector:detector_exception"),
        ("invalid_output", "error", "invalid_output", "error_detector:invalid_output"),
        ("stale", "stale", None, "stale"),
    ],
)
def test_evento_real_de_a_detiene_orden_activa_de_b(
    tmp_path: Path, fallo: str, status: str, codigo: str | None, motivo: str
) -> None:
    eventos, supervisor, percepcion, salida_b = _recorrido(tmp_path, fallo)
    libre, afectado = eventos
    comando_libre = supervisor.procesar_evento(libre, libre["t_emit_ms"])
    comando = supervisor.procesar_evento(afectado, afectado["t_emit_ms"])
    errores = _jsonl(salida_b / "errores.jsonl")

    assert comando_libre["action"] == "AVANZAR"
    assert afectado["status"] == status
    assert afectado.get("error", {}).get("code") == codigo
    assert afectado["detections"] == []
    assert comando["action"] == "STOP"
    assert comando["reason"] == motivo
    assert comando["frame_id"] == afectado["frame_id"]
    assert comando["state_before"] == "AVANZANDO"
    assert all(validar_comando(c) == [] for c in (comando_libre, comando))
    assert len(errores) == 1
    assert errores[0]["motivo"] == motivo
    assert errores[0]["frame_id"] == afectado["frame_id"]
    assert _jsonl(salida_b / "comandos.jsonl") == [comando_libre, comando]

    _evidencia(
        fallo,
        percepcion,
        salida_b,
        [
            {
                "frame_id": afectado["frame_id"],
                "evento_a": afectado,
                "error_code": codigo,
                "esperado": {"action": "STOP", "reason": motivo},
                "observado": comando,
                "error_b": errores[0],
            }
        ],
    )


def test_b_rechaza_ok_que_envejece_despues_de_emitirlo_a(tmp_path: Path) -> None:
    eventos, supervisor, percepcion, salida_b = _recorrido(tmp_path, "ok_tardio")
    libre, tardio = eventos
    comando_libre = supervisor.procesar_evento(libre, libre["t_emit_ms"])
    recibido_ms = tardio["t_emit_ms"] + supervisor.plazos["max_frame_age_ms"] + 1
    comando = supervisor.procesar_evento(tardio, recibido_ms)
    errores = _jsonl(salida_b / "errores.jsonl")

    assert comando_libre["action"] == "AVANZAR"
    assert tardio["status"] == "ok"
    assert tardio["detections"] == []
    assert "error" not in tardio
    assert (
        tardio["t_emit_ms"] - tardio["t_capture_ms"] <= supervisor.plazos["max_frame_age_ms"]
    )  # A publicó un cuadro fresco.
    assert recibido_ms - tardio["t_capture_ms"] > supervisor.plazos["max_frame_age_ms"]
    assert validar_evento(tardio) == []
    assert comando["action"] == "STOP"
    assert comando["reason"] == "cuadro_viejo"
    assert comando["event"] == "frame"
    assert comando["frame_id"] == tardio["frame_id"]
    assert comando["state_before"] == "AVANZANDO"
    assert comando["t_command_ms"] == recibido_ms
    assert validar_comando(comando) == []
    assert len(errores) == 1
    assert errores[0]["motivo"] == "cuadro_viejo"
    assert errores[0]["frame_id"] == tardio["frame_id"]
    assert "edad del cuadro" in errores[0]["errores"][0]
    assert _jsonl(salida_b / "comandos.jsonl") == [comando_libre, comando]

    _evidencia(
        "ok_envejecido_en_transporte",
        percepcion,
        salida_b,
        [
            {
                "frame_id": tardio["frame_id"],
                "evento_a": tardio,
                "t_recibido_ms": recibido_ms,
                "edad_al_emitir_ms": tardio["t_emit_ms"] - tardio["t_capture_ms"],
                "edad_al_recibir_ms": recibido_ms - tardio["t_capture_ms"],
                "error_code": None,
                "esperado": {"action": "STOP", "reason": "cuadro_viejo"},
                "observado": comando,
                "error_b": errores[0],
            }
        ],
    )


def test_cuadro_vacio_inicial_y_ausencia_posterior_detiene_por_watchdog(tmp_path: Path) -> None:
    eventos, supervisor, percepcion, salida_b = _recorrido(tmp_path, None)
    libre = eventos[0]
    comando_libre = supervisor.procesar_evento(libre, libre["t_emit_ms"])
    plazos = supervisor.plazos
    ahora = libre["t_emit_ms"] + plazos["watchdog_ms"] + 1
    comando_reloj = supervisor.tick(ahora)
    errores = _jsonl(salida_b / "errores.jsonl")

    assert libre["status"] == "ok" and libre["detections"] == []
    assert comando_libre["action"] == "AVANZAR"  # Política real desde DETENIDO.
    assert comando_reloj is not None
    assert comando_reloj["action"] == "STOP"
    assert comando_reloj["event"] == "clock"
    assert comando_reloj["frame_id"] is None
    assert comando_reloj["reason"] == "watchdog_vencido"
    assert supervisor.tick(ahora + 1) is None
    assert all(validar_comando(c) == [] for c in (comando_libre, comando_reloj))
    assert len(errores) == 1
    assert errores[0]["motivo"] == "watchdog_vencido"
    assert errores[0]["frame_id"] is None
    assert _jsonl(salida_b / "comandos.jsonl") == [comando_libre, comando_reloj]

    _evidencia(
        "sin_cuadro",
        percepcion,
        salida_b,
        [
            {
                "frame_id": libre["frame_id"],
                "evento_a": libre,
                "error_code": None,
                "esperado": {"action": "AVANZAR"},
                "observado": comando_libre,
            },
            {
                "frame_id": None,
                "evento_a": None,
                "error_code": "watchdog_vencido",
                "esperado": {"action": "STOP", "reason": "watchdog_vencido"},
                "observado": comando_reloj,
                "error_b": errores[0],
            },
        ],
    )


def test_ausencia_con_tics_periodicos_detiene_al_vencer_la_orden(tmp_path: Path) -> None:
    eventos, supervisor, percepcion, salida_b = _recorrido(tmp_path, None)
    libre = eventos[0]
    comando_libre = supervisor.procesar_evento(libre, libre["t_emit_ms"])
    plazos = supervisor.plazos
    paso = plazos["paso_reloj_ms"]
    t = libre["t_emit_ms"] + paso
    comandos_reloj = []
    while t <= libre["t_emit_ms"] + plazos["watchdog_ms"] + paso:
        comando = supervisor.tick(t)
        if comando is not None:
            comandos_reloj.append(comando)
        t += paso

    assert comando_libre["action"] == "AVANZAR"
    assert len(comandos_reloj) == 1
    detenido = comandos_reloj[0]
    assert detenido["action"] == "STOP"
    assert detenido["event"] == "clock"
    assert detenido["frame_id"] is None
    assert detenido["reason"] == "orden_vencida"
    assert detenido["t_command_ms"] == 500
    assert validar_comando(detenido) == []
    errores = _jsonl(salida_b / "errores.jsonl")
    assert len(errores) == 1 and errores[0]["motivo"] == "orden_vencida"
    assert _jsonl(salida_b / "comandos.jsonl") == [comando_libre, detenido]

    _evidencia(
        "sin_cuadro_tics_periodicos",
        percepcion,
        salida_b,
        [
            {
                "frame_id": libre["frame_id"],
                "evento_a": libre,
                "error_code": None,
                "esperado": {"action": "AVANZAR"},
                "observado": comando_libre,
            },
            {
                "frame_id": None,
                "evento_a": None,
                "error_code": "orden_vencida",
                "esperado": {"action": "STOP", "reason": "orden_vencida"},
                "observado": detenido,
                "error_b": errores[0],
            },
        ],
    )
