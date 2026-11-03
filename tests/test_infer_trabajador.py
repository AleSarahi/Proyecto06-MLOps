"""Pruebas del proceso spawn con JPEG sintéticos; no cargan pesos reales."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import torch

import infer.__main__ as cli_infer
from contrato import validar_evento, validar_flujo
from control.__main__ import CARPETA_CONFIG, cargar_plazos
from control.adaptador_virtual import AdaptadorVirtual
from control.config import cargar_config_politica
from control.politica import decidir
from control.supervisor import Supervisor
from infer.config import RUTA_CONFIG_DETECTOR, cargar_config_detector
from infer.detector import ErrorSalidaInvalida, ResultadoJPEG
from infer.eventos import _evento_cuadro
from infer.reloj import leer_reloj_s
from infer.trabajador import PredictorSupervisado, ejecutar_run_supervisado


class PredictorFalso:
    def __init__(self, config, modo: dict, generacion: int, ruta_estado: Path):
        self.config = config
        self.cargado = SimpleNamespace(
            model_sha256=(
                "f" * 64
                if modo.get("hash_erroneo") and generacion == 2
                else config.expected_model_sha256
            ),
            config_sha256=(
                "f" * 64 if modo.get("config_erronea") and generacion == 2 else config.config_sha256
            ),
        )
        self.modo = modo
        self.generacion = generacion
        self.ruta_estado = ruta_estado

    def calentar(self) -> None:
        torch.set_num_threads(1 if self.modo.get("hilos_erroneos") and self.generacion == 2 else 2)

    def inferir(self, ruta: Path, *, imagen: np.ndarray | None = None) -> ResultadoJPEG:
        assert imagen is not None
        with self.ruta_estado.with_suffix(".llamadas").open("a", encoding="utf-8") as registro:
            registro.write(f"{self.generacion}:{ruta.stem}\n")
        if self.modo.get("bloquear") and self.generacion == 1:
            time.sleep(3)
        if self.modo.get("demorar_inferencia"):
            time.sleep(0.2)
        if self.modo.get("error"):
            raise RuntimeError("error simulado")
        if self.modo.get("salida_invalida"):
            raise ErrorSalidaInvalida("salida inválida simulada")
        return ResultadoJPEG(
            imagen.shape[1],
            imagen.shape[0],
            (1, 3, 60, 80),
            (),
            0,
            self.cargado.model_sha256,
            self.config.config_sha256,
        )


def crear_predictor_falso(_config_ruta: Path, ruta_estado: Path) -> PredictorFalso:
    modo = json.loads(ruta_estado.read_text(encoding="utf-8"))
    contador = ruta_estado.with_suffix(".contador")
    generacion = int(contador.read_text(encoding="utf-8")) + 1 if contador.exists() else 1
    contador.write_text(str(generacion), encoding="utf-8")
    if modo.get("fallar_reinicio") and generacion == 2:
        raise RuntimeError("reinicio simulado fallido")
    if modo.get("demorar_reinicio") and generacion == 2:
        time.sleep(0.6)
    return PredictorFalso(cargar_config_detector(), modo, generacion, ruta_estado)


def _jpeg(ruta: Path) -> None:
    assert cv2.imwrite(str(ruta), np.zeros((60, 80, 3), dtype=np.uint8))


def _eventos(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def _run(
    tmp_path: Path,
    nombres: list[str],
    capturas: list[float],
    modo: dict,
    *,
    ilegibles: set[str] | None = None,
):
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    for nombre in nombres:
        ruta = entrada / f"{nombre}.jpg"
        if nombre in (ilegibles or set()):
            ruta.write_bytes(b"")
        else:
            _jpeg(ruta)
    estado = tmp_path / "estado.json"
    estado.write_text(json.dumps(modo), encoding="utf-8")
    salida = tmp_path / "eventos.jsonl"
    resultado = ejecutar_run_supervisado(
        entrada,
        salida,
        run_id="worker-test",
        config_ruta=RUTA_CONFIG_DETECTOR,
        pesos_ruta=estado,
        sequence_id="sintetica",
        capture_ms=capturas,
        fabrica=crear_predictor_falso,
        inicio_guarda_s=10,
    )
    eventos = _eventos(salida)
    assert len(eventos) == len(nombres)
    assert validar_flujo(eventos) == []
    assert all(validar_evento(evento) == [] for evento in eventos)
    return resultado, eventos, estado


def test_inferencia_normal_y_manifiesto_de_plazos(tmp_path: Path) -> None:
    resultado, eventos, estado = _run(tmp_path, ["a"], [0], {})
    assert resultado[1:] == (1, 0, False)
    assert eventos[0]["status"] == "ok" and eventos[0]["detections"] == []
    assert estado.with_suffix(".llamadas").read_text() == "1:a\n"
    manifiesto = json.loads((tmp_path / "worker-test.infer-run.json").read_text())
    plazos = (CARPETA_CONFIG / "plazos.yaml").read_bytes()
    assert manifiesto["plazos"] == {
        "detector_timeout_ms": 500,
        "max_frame_age_ms": 500,
        "plazos_sha256": hashlib.sha256(plazos).hexdigest(),
    }
    assert manifiesto["config_sha256"] == cargar_config_detector().config_sha256
    assert manifiesto["reloj"]["nombre"] == "perf_counter"
    assert manifiesto["reloj"]["resolucion_reportada_s"] > 0
    assert (
        manifiesto["percepcion"]["sha256"]
        == hashlib.sha256((tmp_path / "eventos.jsonl").read_bytes()).hexdigest()
    )
    assert manifiesto["generaciones"][0]["estado"] == "ready"
    assert (
        manifiesto["generaciones"][0]["model_sha256"]
        == cargar_config_detector().expected_model_sha256
    )
    assert manifiesto["generaciones"][0]["config_sha256"] == cargar_config_detector().config_sha256
    assert manifiesto["generaciones"][0]["torch_threads"] == 2
    assert manifiesto["cierre_limpio"] is True


def test_salida_existente_no_se_sobrescribe(tmp_path: Path) -> None:
    _, _, estado = _run(tmp_path, ["a"], [0], {})
    jsonl = tmp_path / "eventos.jsonl"
    manifiesto = tmp_path / "worker-test.infer-run.json"
    contenido_jsonl = jsonl.read_bytes()
    contenido_manifiesto = manifiesto.read_bytes()
    with pytest.raises(FileExistsError):
        ejecutar_run_supervisado(
            tmp_path / "entrada",
            jsonl,
            run_id="worker-test",
            config_ruta=RUTA_CONFIG_DETECTOR,
            pesos_ruta=estado,
            sequence_id="sintetica",
            capture_ms=[0],
            fabrica=crear_predictor_falso,
        )
    assert jsonl.read_bytes() == contenido_jsonl
    assert manifiesto.read_bytes() == contenido_manifiesto


def test_timeout_real_reinicia_y_cuadro_viejo_no_se_infiere(tmp_path: Path) -> None:
    resultado, eventos, estado = _run(
        tmp_path, ["a", "b"], [0, 200], {"bloquear": True, "demorar_reinicio": True}
    )
    assert resultado[1:] == (2, 1, False)
    assert [e["status"] for e in eventos] == ["error", "stale"]
    assert eventos[0]["error"]["code"] == "detector_timeout"
    assert (eventos[0]["image_width"], eventos[0]["image_height"]) == (80, 60)
    assert (eventos[1]["image_width"], eventos[1]["image_height"]) == (80, 60)
    assert "error" not in eventos[1]
    assert estado.with_suffix(".llamadas").read_text() == "1:a\n"
    manifiesto = json.loads((tmp_path / "worker-test.infer-run.json").read_text())
    assert [g["estado"] for g in manifiesto["generaciones"]] == ["ready", "timeout", "ready"]


def test_timeout_se_publica_antes_del_reinicio_y_traza_el_flush(tmp_path: Path) -> None:
    entrada = tmp_path / "a.jpg"
    _jpeg(entrada)
    estado = tmp_path / "estado.json"
    estado.write_text(json.dumps({"bloquear": True, "demorar_reinicio": True}))
    trazas: list[dict] = []
    salida = tmp_path / "eventos.jsonl"
    resultado = ejecutar_run_supervisado(
        entrada,
        salida,
        run_id="antes-ready",
        config_ruta=RUTA_CONFIG_DETECTOR,
        pesos_ruta=estado,
        fabrica=crear_predictor_falso,
        inicio_guarda_s=10,
        trazas=trazas,
    )
    assert resultado[1:] == (1, 1, False)
    assert len(trazas) == 1
    traza = trazas[0]
    assert traza["status"] == "error" and traza["error_code"] == "detector_timeout"
    assert traza["reinicio_ok"] is True
    assert traza["publicado_monotonic_s"] >= traza["inicio_monotonic_s"]
    assert 500 <= traza["duracion_publicacion_ms"] <= 600
    assert _eventos(salida)[0]["error"]["code"] == "detector_timeout"
    manifiesto = json.loads((tmp_path / "antes-ready.infer-run.json").read_text())
    assert manifiesto["generaciones"][-1]["estado"] == "ready"
    assert manifiesto["generaciones"][-2]["reinicio_ms"] >= 600
    assert manifiesto["reloj"]["nombre"] == "perf_counter"


@pytest.mark.parametrize("operacion", ["write", "flush"])
def test_escritura_fallida_no_se_declara_publicacion_ni_inicia_reinicio(
    tmp_path: Path, monkeypatch, operacion: str
) -> None:
    import infer.trabajador as modulo

    entrada = tmp_path / "a.jpg"
    _jpeg(entrada)
    estado = tmp_path / "estado.json"
    estado.write_text(json.dumps({"bloquear": True}))
    trazas: list[dict] = []
    abrir_original = modulo.abrir_exclusivo

    class ArchivoConFallo:
        def __init__(self, archivo):
            self.archivo = archivo

        def __enter__(self):
            self.archivo.__enter__()
            return self

        def __exit__(self, *args):
            return self.archivo.__exit__(*args)

        def write(self, texto):
            if operacion == "write":
                raise OSError("write simulado fallido")
            return self.archivo.write(texto)

        def flush(self):
            if operacion == "flush":
                raise OSError("flush simulado fallido")
            return self.archivo.flush()

    def abrir(ruta, *, lectura=False):
        archivo = abrir_original(ruta, lectura=lectura)
        return ArchivoConFallo(archivo) if lectura else archivo

    monkeypatch.setattr(modulo, "abrir_exclusivo", abrir)
    with pytest.raises(OSError, match=f"{operacion} simulado"):
        ejecutar_run_supervisado(
            entrada,
            tmp_path / "eventos.jsonl",
            run_id="flush-fallido",
            config_ruta=RUTA_CONFIG_DETECTOR,
            pesos_ruta=estado,
            fabrica=crear_predictor_falso,
            inicio_guarda_s=10,
            trazas=trazas,
        )
    assert len(trazas) == 1 and trazas[0]["publicado_monotonic_s"] is None
    assert estado.with_suffix(".contador").read_text() == "1"


def test_trazas_opcionales_no_cambian_eventos(tmp_path: Path) -> None:
    for nombre, trazas in (("sin", None), ("con", [])):
        carpeta = tmp_path / nombre
        carpeta.mkdir()
        entrada = carpeta / "a.jpg"
        _jpeg(entrada)
        estado = carpeta / "estado.json"
        estado.write_text("{}")
        ejecutar_run_supervisado(
            entrada,
            carpeta / "eventos.jsonl",
            run_id=nombre,
            config_ruta=RUTA_CONFIG_DETECTOR,
            pesos_ruta=estado,
            fabrica=crear_predictor_falso,
            inicio_guarda_s=10,
            trazas=trazas,
        )
    a = _eventos(tmp_path / "sin" / "eventos.jsonl")[0]
    b = _eventos(tmp_path / "con" / "eventos.jsonl")[0]
    for campo in (
        "status",
        "detections",
        "image_width",
        "image_height",
        "model_sha256",
        "config_sha256",
    ):
        assert a[campo] == b[campo]
    assert a["frame_id"] == b["frame_id"] == "a"
    assert validar_evento(a) == validar_evento(b) == []


def test_reinicio_fallido_publica_todos_los_pendientes(tmp_path: Path) -> None:
    resultado, eventos, estado = _run(
        tmp_path, ["a", "b", "c"], [0, 200, 400], {"bloquear": True, "fallar_reinicio": True}
    )
    assert resultado[1:] == (3, 3, True)
    assert [e["frame_id"] for e in eventos] == ["a", "b", "c"]
    assert [e["error"]["code"] for e in eventos] == [
        "detector_timeout",
        "detector_exception",
        "detector_exception",
    ]
    assert estado.with_suffix(".llamadas").read_text() == "1:a\n"


def test_cli_sale_no_cero_despues_de_publicar_pendientes(tmp_path: Path, monkeypatch) -> None:
    resultado, eventos, _ = _run(
        tmp_path, ["a", "b"], [0, 200], {"bloquear": True, "fallar_reinicio": True}
    )
    assert len(eventos) == 2 and resultado[3] is True
    monkeypatch.setattr(cli_infer, "ejecutar_run_supervisado", lambda *_a, **_kw: resultado)
    codigo = cli_infer.main(
        [
            "--input",
            str(tmp_path / "entrada"),
            "--weights",
            str(tmp_path / "estado.json"),
            "--output",
            str(tmp_path / "eventos.jsonl"),
            "--run-id",
            "worker-test",
        ]
    )
    assert codigo != 0


def test_ilegible_tras_reinicio_prevalece_sobre_stale(tmp_path: Path) -> None:
    resultado, eventos, estado = _run(
        tmp_path,
        ["a", "b"],
        [0, 200],
        {"bloquear": True, "demorar_reinicio": True},
        ilegibles={"b"},
    )
    assert resultado[1:] == (2, 2, False)
    assert [e["error"]["code"] for e in eventos] == ["detector_timeout", "unreadable_image"]
    assert eventos[1]["t_emit_ms"] - eventos[1]["t_capture_ms"] > 500
    assert estado.with_suffix(".llamadas").read_text() == "1:a\n"


@pytest.mark.parametrize(
    "modo", [{"hash_erroneo": True}, {"config_erronea": True}, {"hilos_erroneos": True}]
)
def test_reinicio_rechaza_hash_o_hilos_invalidos(tmp_path: Path, modo: dict) -> None:
    resultado, eventos, _ = _run(tmp_path, ["a", "b"], [0, 200], {"bloquear": True, **modo})
    assert resultado[3] is True
    assert [e["error"]["code"] for e in eventos] == ["detector_timeout", "detector_exception"]


def test_error_del_predictor_llega_a_b_como_stop(tmp_path: Path) -> None:
    resultado, eventos, _ = _run(tmp_path, ["a"], [0], {"salida_invalida": True})
    assert resultado[2] == 1 and eventos[0]["error"]["code"] == "invalid_output"
    plazos = cargar_plazos(CARPETA_CONFIG / "plazos.yaml")
    supervisor = Supervisor(
        decidir,
        AdaptadorVirtual(tmp_path / "control", plazos["validez_orden_ms"]),
        plazos,
        cargar_config_politica(),
    )
    comando = supervisor.procesar_evento(eventos[0], eventos[0]["t_emit_ms"])
    assert comando["action"] == "STOP" and comando["reason"] == "error_detector:invalid_output"


def test_timeout_llega_a_b_como_stop(tmp_path: Path) -> None:
    _, eventos, _ = _run(tmp_path, ["a"], [0], {"bloquear": True})
    assert eventos[0]["error"]["code"] == "detector_timeout"
    plazos = cargar_plazos(CARPETA_CONFIG / "plazos.yaml")
    carpeta = tmp_path / "control"
    supervisor = Supervisor(
        decidir,
        AdaptadorVirtual(carpeta, plazos["validez_orden_ms"]),
        plazos,
        cargar_config_politica(),
    )
    comando = supervisor.procesar_evento(eventos[0], eventos[0]["t_emit_ms"])
    assert comando["action"] == "STOP"
    assert comando["reason"] == "error_detector:detector_timeout"
    assert comando["frame_id"] == "a"
    assert _eventos(carpeta / "errores.jsonl")[0]["motivo"] == comando["reason"]


@pytest.mark.parametrize(
    ("fallar", "estado"),
    [
        (True, "error"),
        (False, "stale"),
    ],
)
def test_prioridad_error_y_stale_durante_inferencia(
    tmp_path: Path, fallar: bool, estado: str
) -> None:
    ruta = tmp_path / "a.jpg"
    _jpeg(ruta)
    config = cargar_config_detector()
    reloj_ms = [400]

    class Detector:
        cargado = SimpleNamespace(model_sha256=config.expected_model_sha256)

        def inferir(self, _ruta, *, imagen=None):
            reloj_ms[0] = 600
            if fallar:
                raise RuntimeError("fallo después de envejecer")
            return ResultadoJPEG(
                imagen.shape[1],
                imagen.shape[0],
                (1, 3, 60, 80),
                (),
                0,
                self.cargado.model_sha256,
                config.config_sha256,
            )

    detector = Detector()
    detector.config = config
    evento = _evento_cuadro(detector, ruta, "r", "s", 1, "a", 0, lambda: reloj_ms[0], 500)
    assert evento["status"] == estado
    if fallar:
        assert evento["error"]["code"] == "detector_exception"
    else:
        assert "error" not in evento and evento["detections"] == []


@pytest.mark.parametrize(
    ("envio_s", "estado"),
    [(0.499, "result"), (0.5, "result"), (0.501, "timeout")],
)
def test_plazo_incluye_envio_y_respeta_limite_exacto(tmp_path: Path, envio_s: float, estado: str):
    reloj = [0.0]

    class Solicitudes:
        def put_nowait(self, _mensaje):
            reloj[0] += envio_s

    class Respuestas:
        def get(self, timeout):
            return (1, 1, "result", {"run_id": "r", "frame_id": "a"})

    predictor = object.__new__(PredictorSupervisado)
    predictor.generacion = 1
    predictor.solicitudes = Solicitudes()
    predictor.respuestas = Respuestas()
    predictor.proceso = None
    predictor.reloj = lambda: reloj[0]
    predictor.trazas = []
    clase, evento, _ = predictor.solicitar(
        request_id=1,
        ruta=tmp_path / "a.jpg",
        run_id="r",
        secuencia="s",
        indice=1,
        frame_id="a",
        captura=0,
        origen=0,
        plazos=SimpleNamespace(detector_timeout_ms=500, max_frame_age_ms=500),
    )
    assert clase == estado
    assert (evento is not None) == (estado == "result")
    assert predictor.trazas[0]["inicio_monotonic_s"] == 0.0
    assert predictor.trazas[0]["publicado_monotonic_s"] is None


@pytest.mark.parametrize(("recepcion_s", "estado"), [(0.3, "result"), (0.301, "timeout")])
def test_plazo_incluye_respuesta_completa(tmp_path: Path, recepcion_s: float, estado: str) -> None:
    reloj = [0.0]

    class Solicitudes:
        def put_nowait(self, _mensaje):
            reloj[0] += 0.2

    class Respuestas:
        def get(self, timeout):
            assert timeout >= 0
            reloj[0] += recepcion_s
            return (1, 1, "result", {"run_id": "r", "frame_id": "a"})

    predictor = object.__new__(PredictorSupervisado)
    predictor.generacion = 1
    predictor.solicitudes = Solicitudes()
    predictor.respuestas = Respuestas()
    predictor.proceso = None
    predictor.reloj = lambda: reloj[0]
    predictor.trazas = []
    clase, evento, _ = predictor.solicitar(
        request_id=1,
        ruta=tmp_path / "a.jpg",
        run_id="r",
        secuencia="s",
        indice=1,
        frame_id="a",
        captura=0,
        origen=0,
        plazos=SimpleNamespace(detector_timeout_ms=500, max_frame_age_ms=500),
    )
    assert clase == estado
    assert (evento is not None) == (estado == "result")
    assert predictor.trazas[0]["inicio_monotonic_s"] == 0.0


def test_reinicio_exitoso_acepta_cuadro_nuevo_vigente(tmp_path: Path) -> None:
    ruta = tmp_path / "a.jpg"
    _jpeg(ruta)
    control = tmp_path / "estado.json"
    control.write_text(json.dumps({"bloquear": True}), encoding="utf-8")
    config = cargar_config_detector()
    predictor = PredictorSupervisado(
        RUTA_CONFIG_DETECTOR, control, config, fabrica=crear_predictor_falso, inicio_guarda_s=10
    )
    plazos = SimpleNamespace(detector_timeout_ms=500, max_frame_age_ms=500)
    try:
        predictor.iniciar()
        primero = predictor.solicitar(
            request_id=1,
            ruta=ruta,
            run_id="r",
            secuencia="s",
            indice=1,
            frame_id="a",
            captura=0,
            origen=leer_reloj_s(),
            plazos=plazos,
        )
        assert primero[0] == "timeout"
        assert predictor.detener()
        predictor.iniciar()
        segundo = predictor.solicitar(
            request_id=2,
            ruta=ruta,
            run_id="r",
            secuencia="s",
            indice=2,
            frame_id="b",
            captura=0,
            origen=leer_reloj_s(),
            plazos=plazos,
        )
    finally:
        predictor.detener()
    assert segundo[0] == "result" and segundo[1]["status"] == "ok"


def test_respuesta_duplicada_de_generacion_anterior_se_descarta(tmp_path: Path) -> None:
    class Solicitudes:
        def put_nowait(self, _mensaje):
            pass

    class Respuestas:
        def __init__(self):
            self.mensajes = [
                (1, 1, "result", {"frame_id": "viejo"}),
                (2, 1, "result", {"frame_id": "duplicado"}),
                (2, 2, "result", {"run_id": "r", "frame_id": "nuevo"}),
            ]

        def get(self, timeout):
            return self.mensajes.pop(0)

    predictor = object.__new__(PredictorSupervisado)
    predictor.generacion = 2
    predictor.solicitudes = Solicitudes()
    predictor.respuestas = Respuestas()
    predictor.proceso = None
    predictor.reloj = leer_reloj_s
    clase, evento, _ = predictor.solicitar(
        request_id=2,
        ruta=tmp_path / "a.jpg",
        run_id="r",
        secuencia="s",
        indice=2,
        frame_id="nuevo",
        captura=0,
        origen=leer_reloj_s(),
        plazos=SimpleNamespace(detector_timeout_ms=500, max_frame_age_ms=500),
    )
    assert clase == "result" and evento == {"run_id": "r", "frame_id": "nuevo"}
