"""P5-21: el lazo en vivo completo con un stream HTTP local, un detector falso y, a veces, una
placa falsa por UDP. Sin cámara, sin carro y sin pesos."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from carro.emisor import Emisor
from contrato import validar_comando, validar_evento, validar_flujo
from test_carro_emisor import placa_falsa
from vivo.config import cargar_config_vivo
from vivo.corrida import CorridaVivo
from vivo.lazo import LazoVivo
from vivo.lector import LectorStream, abrir_stream
from vivo_comun import (
    ColaTeclas,
    DetectorFalso,
    ServidorMjpeg,
    esperar,
    plazos,
    politica,
    servidor_mjpeg,
)

VIVO = cargar_config_vivo()


def _jsonl(ruta: Path) -> list[dict]:
    texto = ruta.read_text(encoding="utf-8")
    return [json.loads(linea) for linea in texto.splitlines() if linea.strip()]


class Armado:
    def __init__(
        self,
        tmp_path: Path,
        servidor: ServidorMjpeg,
        detector: DetectorFalso,
        *,
        emisor: Emisor | None = None,
        duracion_s: float | None = None,
        con_teclas: bool = False,
    ) -> None:
        self.salida = tmp_path / "run"
        self.salida.mkdir()
        self.lineas: list[str] = []
        self.detector = detector
        self.teclas = ColaTeclas() if con_teclas else None
        self.corrida = CorridaVivo(self.salida, plazos(), politica(), detector.ahora_ms, emisor)
        self.lector = LectorStream(
            lambda: abrir_stream("127.0.0.1", servidor.puerto, "/stream", 1.0),
            detector.ahora_ms,
            max_cuadro=VIVO.max_cuadro_bytes,
            reconexion_s=0.05,
        )
        self.lazo = LazoVivo(
            self.corrida,
            self.lector,
            detector,
            VIVO,
            plazos()["paso_reloj_ms"],
            self.salida / "_cuadros",
            teclas=self.teclas,
            imprimir=self.lineas.append,
            duracion_s=duracion_s,
        )
        self.codigo: int | None = None
        self._hilo = threading.Thread(target=self._correr, daemon=True)

    def _correr(self) -> None:
        self.codigo = self.lazo.correr()

    def iniciar(self) -> None:
        self._hilo.start()  # el lazo arranca el lector, como en `python -m vivo`

    def terminar(self, limite_s: float = 5.0) -> int:
        self._hilo.join(limite_s)
        assert not self._hilo.is_alive(), "el lazo no cerró"
        assert self.codigo is not None
        return self.codigo

    def comandos(self) -> list[dict]:
        return _jsonl(self.salida / "comandos.jsonl")

    def acciones(self) -> list[str]:
        return [c["action"] for c in self.comandos()]


def _stop_por(armado: Armado, motivos: tuple[str, ...]) -> bool:
    return any(c["action"] == "STOP" and c["reason"] in motivos for c in armado.comandos())


def test_modo_seco_registra_todo_y_no_manda_nada(tmp_path: Path) -> None:
    with servidor_mjpeg(0.05) as servidor:
        armado = Armado(tmp_path, servidor, DetectorFalso(), duracion_s=1.0)
        armado.iniciar()
        assert armado.terminar() == 0

    assert armado.lazo.seco
    comandos = armado.comandos()
    assert "AVANZAR" in [c["action"] for c in comandos]
    assert comandos[-1]["action"] == "STOP" and comandos[-1]["reason"] == "cierre"
    # Los comandos cumplen el contrato de comando y los eventos el de percepción.
    assert all(validar_comando(c) == [] for c in comandos)
    eventos = _jsonl(armado.salida / "detecciones.jsonl")
    assert eventos and all(validar_evento(e) == [] for e in eventos)
    assert validar_flujo(eventos) == []
    assert (armado.salida / "errores.jsonl").read_text(encoding="utf-8") == ""
    assert (armado.salida / "respuestas.jsonl").read_text(encoding="utf-8") == ""
    assert any(linea.startswith("[SECO ]") and "AVANZAR" in linea for linea in armado.lineas)

    resumen = json.loads((armado.salida / "vivo.json").read_text(encoding="utf-8"))
    assert resumen["modo"] == "seco"
    assert resumen["cierre"] == {"motivo": "duracion", "error": None, "predictor_limpio": True}
    assert resumen["carro"]["enviadas"] == 0
    assert resumen["cuadros"]["atendidos"] == len(eventos)
    assert resumen["latencia_cuadro_a_comando_ms"]["p95"] < 500
    assert resumen["detector"]["model_sha256"] == armado.detector.model_sha256
    assert armado.detector.cerrado


def test_con_placa_manda_ordenes_y_la_deja_detenida(tmp_path: Path) -> None:
    with placa_falsa() as (puerto, placa), servidor_mjpeg(0.05) as servidor:
        picos = {"pwm": 0}
        vigilante_activo = threading.Event()

        def vigilar() -> None:
            while not vigilante_activo.is_set():
                picos["pwm"] = max(picos["pwm"], placa.pwm_izq, placa.pwm_der)
                vigilante_activo.wait(0.005)

        hilo = threading.Thread(target=vigilar, daemon=True)
        hilo.start()
        emisor = Emisor("127.0.0.1", puerto, tmp_path / "carro.jsonl")
        armado = Armado(tmp_path, servidor, DetectorFalso(), emisor=emisor, duracion_s=1.0)
        armado.iniciar()
        assert armado.terminar() == 0
        vigilante_activo.set()
        hilo.join(1)

        assert picos["pwm"] > 0, "la placa nunca recibió una orden de movimiento"
        assert placa.estado == "DETENIDO"

    assert not armado.lazo.seco
    respuestas = _jsonl(armado.salida / "respuestas.jsonl")
    assert respuestas and {r["motivo"] for r in respuestas} <= {"OK", "VENCIDA"}
    resumen = json.loads((armado.salida / "vivo.json").read_text(encoding="utf-8"))
    assert resumen["modo"] == "motores"
    assert resumen["carro"]["enviadas"] > 0
    assert resumen["carro"]["rechazadas_por_la_placa"] == 0
    assert resumen["carro"]["rtt_comando_a_respuesta_ms"]["n"] > 0
    bitacora = _jsonl(tmp_path / "carro.jsonl")
    enviados = [b["datos"].split(",")[3] for b in bitacora if b["tipo"] == "enviado"]
    assert enviados[0] == "STOP"  # la sesión arranca con STOP
    assert "AVANZAR" in enviados
    assert enviados[-3:] == ["STOP"] * 3  # y cierra con tres STOP


def test_camara_desconectada_da_stop(tmp_path: Path) -> None:
    with placa_falsa() as (puerto, placa), servidor_mjpeg(0.05) as servidor:
        emisor = Emisor("127.0.0.1", puerto)
        armado = Armado(tmp_path, servidor, DetectorFalso(), emisor=emisor, con_teclas=True)
        armado.iniciar()
        assert esperar(lambda: "AVANZAR" in armado.acciones())
        servidor.cortar()
        # La orden vale 400 ms y el watchdog 600: el que llegue primero deja el STOP de reloj.
        assert esperar(lambda: _stop_por(armado, ("orden_vencida", "watchdog_vencido")), 3)
        assert esperar(lambda: placa.estado == "DETENIDO", 1)
        assert any("cámara sin stream" in linea for linea in armado.lineas)
        armado.teclas.poner(VIVO.tecla_salida)
        assert armado.terminar() == 0
    stop = next(
        c for c in armado.comandos() if c["reason"] in ("orden_vencida", "watchdog_vencido")
    )
    assert stop["event"] == "clock" and stop["frame_id"] is None


def test_la_camara_vuelve_y_el_carro_reanuda(tmp_path: Path) -> None:
    with servidor_mjpeg(0.05) as servidor:
        armado = Armado(tmp_path, servidor, DetectorFalso(), con_teclas=True)
        armado.iniciar()
        assert esperar(lambda: "AVANZAR" in armado.acciones())
        servidor.cortar()
        assert esperar(lambda: _stop_por(armado, ("orden_vencida", "watchdog_vencido")), 3)
        antes = armado.acciones().count("AVANZAR")
        servidor.reanudar()
        assert esperar(lambda: armado.acciones().count("AVANZAR") > antes, 5)
        armado.teclas.poner(VIVO.tecla_salida)
        assert armado.terminar() == 0
    assert armado.lector.conexiones >= 2


def test_detector_muerto_da_stop(tmp_path: Path) -> None:
    with servidor_mjpeg(0.05) as servidor:
        detector = DetectorFalso()
        armado = Armado(tmp_path, servidor, detector, con_teclas=True)
        armado.iniciar()
        assert esperar(lambda: "AVANZAR" in armado.acciones())
        detector.modo = "error"
        assert esperar(lambda: _stop_por(armado, ("error_detector:detector_exception",)), 3)
        armado.teclas.poner(VIVO.tecla_salida)
        assert armado.terminar() == 0
    assert armado.corrida.por_estado["error"] > 0
    errores = _jsonl(armado.salida / "errores.jsonl")
    assert any(e["motivo"] == "error_detector:detector_exception" for e in errores)


def test_obstaculo_al_centro_no_avanza(tmp_path: Path) -> None:
    with servidor_mjpeg(0.05) as servidor:
        armado = Armado(tmp_path, servidor, DetectorFalso("obstaculo"), duracion_s=0.6)
        armado.iniciar()
        assert armado.terminar() == 0
    assert "AVANZAR" not in armado.acciones()


def test_emergencia_por_tecla_enclava_y_el_rearme_la_quita(tmp_path: Path) -> None:
    with servidor_mjpeg(0.05) as servidor:
        armado = Armado(tmp_path, servidor, DetectorFalso(), con_teclas=True)
        armado.iniciar()
        assert esperar(lambda: "AVANZAR" in armado.acciones())
        armado.teclas.poner(VIVO.tecla_emergencia)
        assert esperar(lambda: _stop_por(armado, ("emergencia",)))
        assert esperar(lambda: _stop_por(armado, ("emergencia_activa",)))
        # Mientras dura la emergencia ningún cuadro libre mueve el carro.
        n = len(armado.comandos())
        assert esperar(lambda: len(armado.comandos()) > n + 3)
        assert armado.acciones()[n:] == ["STOP"] * (len(armado.acciones()) - n)
        armado.teclas.poner(VIVO.tecla_rearme)
        assert esperar(lambda: _stop_por(armado, ("rearmado",)))
        assert esperar(lambda: armado.acciones()[-1] == "AVANZAR")
        armado.teclas.poner(VIVO.tecla_salida)
        assert armado.terminar() == 0
    assert any("EMERGENCIA" in linea for linea in armado.lineas)


def test_excepcion_manda_stop_antes_de_salir(tmp_path: Path) -> None:
    with placa_falsa() as (puerto, placa), servidor_mjpeg(0.05) as servidor:
        emisor = Emisor("127.0.0.1", puerto)
        detector = DetectorFalso()
        armado = Armado(tmp_path, servidor, detector, emisor=emisor)
        armado.iniciar()
        assert esperar(lambda: "AVANZAR" in armado.acciones())
        detector.modo = "explotar"
        assert armado.terminar() == 1
        assert placa.estado == "DETENIDO"
    ultimo = armado.comandos()[-1]
    assert ultimo["action"] == "STOP" and ultimo["reason"] == "cierre"
    resumen = json.loads((armado.salida / "vivo.json").read_text(encoding="utf-8"))
    assert resumen["cierre"]["motivo"] == "error:RuntimeError"
    assert "detector roto" in resumen["cierre"]["error"]
    assert armado.detector.cerrado
    assert any(linea.startswith("FALLO") for linea in armado.lineas)


def test_ctrl_c_en_el_lazo_cierra_con_stop(tmp_path: Path) -> None:
    class Interrumpido(DetectorFalso):
        def evento(self, ruta: Path, frame_id: str, captura_ms: float) -> dict:
            if len(self.vistos) >= 3:
                raise KeyboardInterrupt
            return super().evento(ruta, frame_id, captura_ms)

    with servidor_mjpeg(0.05) as servidor:
        armado = Armado(tmp_path, servidor, Interrumpido())
        armado.iniciar()
        assert armado.terminar() == 0
    assert armado.comandos()[-1]["reason"] == "cierre"
    resumen = json.loads((armado.salida / "vivo.json").read_text(encoding="utf-8"))
    assert resumen["cierre"]["motivo"] == "ctrl_c"


def test_un_detector_lento_descarta_cuadros_viejos_y_no_acumula_latencia(tmp_path: Path) -> None:
    """El detector tarda 4 veces el periodo entre cuadros: se atienden los más nuevos."""
    with servidor_mjpeg(0.025) as servidor:
        detector = DetectorFalso(demora_s=0.1)
        armado = Armado(tmp_path, servidor, detector, duracion_s=1.5)
        armado.iniciar()
        assert armado.terminar() == 0
    assert armado.lector.descartados > 0
    assert armado.lector.recibidos > len(detector.vistos)
    # Cada cuadro atendido era el más nuevo al tomarlo: la latencia no crece con el tiempo.
    assert max(armado.corrida.latencias_ms) < 400
    ids = [int(f[1:]) for f in detector.vistos]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


@pytest.mark.parametrize("tecla", ["x", "1", " "])
def test_otras_teclas_se_ignoran(tmp_path: Path, tecla: str) -> None:
    with servidor_mjpeg(0.05) as servidor:
        armado = Armado(tmp_path, servidor, DetectorFalso(), con_teclas=True, duracion_s=0.5)
        armado.iniciar()
        armado.teclas.poner(tecla)
        assert armado.terminar() == 0
    assert "emergencia" not in [c["reason"] for c in armado.comandos()]


def test_la_linea_por_cuadro_cabe_en_la_terminal() -> None:
    from vivo.lazo import MAX_MOTIVO, linea_de_cuadro

    comando = {
        "frame_id": "F000012",
        "action": "GIRAR_IZQ",
        "speed": 0.4,
        "steering": -0.5,
        "t_command_ms": 1060.0,
        "reason": "Obstáculo en el centro; la izquierda está libre: gira hacia allá. " * 3,
    }
    linea = linea_de_cuadro(comando, {"t_capture_ms": 1000.0, "status": "ok"}, seco=False)
    assert linea.startswith("[CARRO] F000012 GIRAR_IZQ v=0.40 g=-0.50 lat=  60 ms ok")
    assert linea.endswith("…") and len(linea) < 100 + MAX_MOTIVO
    corta = linea_de_cuadro(
        {**comando, "reason": "cierre"}, {"t_capture_ms": 0, "status": "ok"}, True
    )
    assert corta.startswith("[SECO ]") and corta.endswith("ok    cierre")
