"""P5-21: el adaptador del carro por WiFi. Sin red, con un emisor de mentira, y una vez con el
emisor real contra la placa de referencia en localhost."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from carro.emisor import Emisor
from carro.protocolo import Orden, Respuesta
from contrato import validar_comando
from control.adaptador_virtual import AdaptadorVirtual
from test_carro_emisor import placa_falsa
from vivo.adaptador_wifi import AdaptadorWifi


def _comando(accion: str = "AVANZAR", speed: float = 0.4, steering: float = 0.0) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "run_id": "r1",
        "frame_id": "F000001",
        "event": "frame",
        "state_before": "DETENIDO",
        "state_after": "AVANZANDO",
        "action": accion,
        "reason": "prueba",
        "speed": speed,
        "steering": steering,
        "t_decision_ms": 1000.0,
    }


class EmisorFalso:
    """Guarda lo que se le pide mandar y contesta lo que se le pida."""

    def __init__(self) -> None:
        self.seq = 0
        self.mandadas: list[Orden] = []
        self.cerrado = 0
        self.respuestas: list[Any] = []
        self.fallar_envio = False

    def orden(
        self, accion: str, velocidad: float = 0.0, giro: float = 0.0, vigencia_ms: int = 400
    ) -> Orden:
        self.seq += 1
        return Orden(7, self.seq, accion, velocidad, giro, vigencia_ms)

    def enviar(self, orden: Orden | bytes) -> bytes:
        if self.fallar_envio:
            raise OSError("red caída")
        assert isinstance(orden, Orden)
        self.mandadas.append(orden)
        return b""

    def recibir(self, _espera_ms: float) -> list[Any]:
        salida, self.respuestas = self.respuestas, []
        return salida

    def cerrar(self) -> None:
        self.cerrado += 1


def _jsonl(ruta: Path) -> list[dict]:
    texto = ruta.read_text(encoding="utf-8")
    return [json.loads(linea) for linea in texto.splitlines() if linea.strip()]


def test_hereda_del_adaptador_virtual_y_registra_igual(tmp_path: Path) -> None:
    wifi = AdaptadorWifi(tmp_path / "a", 400)
    virtual = AdaptadorVirtual(tmp_path / "b", 400)
    assert isinstance(wifi, AdaptadorVirtual)
    assert wifi.enviar(_comando(), 1100.0) == virtual.enviar(_comando(), 1100.0)
    assert (tmp_path / "a" / "comandos.jsonl").read_text() == (
        tmp_path / "b" / "comandos.jsonl"
    ).read_text()
    assert validar_comando(_jsonl(tmp_path / "a" / "comandos.jsonl")[0]) == []


def test_modo_seco_no_manda_nada(tmp_path: Path) -> None:
    wifi = AdaptadorWifi(tmp_path, 400)
    assert wifi.seco
    wifi.enviar(_comando(), 1100.0)
    assert wifi.enviadas == 0 and wifi.revisar_respuestas() == []
    wifi.cerrar()
    wifi.cerrar()  # repetido no falla


def test_cada_comando_sale_como_su_orden(tmp_path: Path) -> None:
    emisor = EmisorFalso()
    wifi = AdaptadorWifi(tmp_path, 400, emisor)
    wifi.enviar(_comando("AVANZAR", 0.4, 0.0), 1100.0)
    wifi.enviar(_comando("GIRAR_IZQ", 0.4, -0.5), 1200.0)
    wifi.enviar(_comando("GIRAR_DER", 0.4, 0.5), 1300.0)
    wifi.enviar(_comando("STOP", 0.0, 0.0), 1400.0)
    assert [(o.accion, o.velocidad, o.giro, o.vigencia_ms) for o in emisor.mandadas] == [
        ("AVANZAR", 0.4, 0.0, 400),
        ("GIRAR_IZQ", 0.4, -0.5, 400),
        ("GIRAR_DER", 0.4, 0.5, 400),
        ("STOP", 0.0, 0.0, 400),
    ]
    assert wifi.enviadas == 4
    assert [c["action"] for c in _jsonl(tmp_path / "comandos.jsonl")] == [
        "AVANZAR",
        "GIRAR_IZQ",
        "GIRAR_DER",
        "STOP",
    ]


def test_la_placa_nunca_obedece_mas_que_el_comando(tmp_path: Path) -> None:
    """valid_until_ms = t_command_ms + 400: la vigencia que viaja no pasa de ahí ni de 500."""
    emisor = EmisorFalso()
    wifi = AdaptadorWifi(
        tmp_path, 900, emisor
    )  # un plazo mal puesto no rebasa el tope del protocolo
    wifi.enviar(_comando(), 1100.0)
    assert emisor.mandadas[0].vigencia_ms == 500


@pytest.mark.parametrize(
    ("accion", "speed", "steering"),
    [
        ("AVANZAR", 0.4, 0.5),  # AVANZAR con giro
        ("GIRAR_IZQ", 0.4, 0.5),  # izquierda con giro a la derecha
        ("GIRAR_DER", 0.0, 0.5),  # girar sin velocidad
        ("AVANZAR", 1.5, 0.0),  # fuera de rango
        ("VOLAR", 0.4, 0.0),
    ],
)
def test_un_comando_que_la_placa_rechazaria_se_manda_como_stop(
    tmp_path: Path, accion: str, speed: float, steering: float
) -> None:
    emisor = EmisorFalso()
    wifi = AdaptadorWifi(tmp_path, 400, emisor)
    wifi.enviar({**_comando(), "action": accion, "speed": speed, "steering": steering}, 1100.0)
    assert [o.accion for o in emisor.mandadas] == ["STOP"]
    errores = _jsonl(tmp_path / "errores.jsonl")
    assert errores[0]["motivo"] == "orden_no_enviable" and errores[0]["frame_id"] == "F000001"


def test_un_fallo_de_red_queda_en_errores_y_no_tumba_al_lazo(tmp_path: Path) -> None:
    emisor = EmisorFalso()
    emisor.fallar_envio = True
    wifi = AdaptadorWifi(tmp_path, 400, emisor)
    wifi.enviar(_comando(), 1100.0)
    assert wifi.fallos_de_envio == 1 and wifi.enviadas == 0
    assert _jsonl(tmp_path / "errores.jsonl")[0]["motivo"] == "envio_fallido"
    assert len(_jsonl(tmp_path / "comandos.jsonl")) == 1  # el comando sí quedó registrado


def test_las_respuestas_de_la_placa_quedan_registradas(tmp_path: Path) -> None:
    emisor = EmisorFalso()
    wifi = AdaptadorWifi(tmp_path, 400, emisor)
    emisor.respuestas = [
        SimpleNamespace(
            respuesta=Respuesta(7, 1, "OK", "MOVIENDO", 110, 110, 5000), t_pc_ms=1110.0, rtt_ms=9.5
        ),
        SimpleNamespace(
            respuesta=Respuesta(7, 2, "SEQ_VIEJA", "DETENIDO", 0, 0, 5100),
            t_pc_ms=1120.0,
            rtt_ms=3.0,
        ),
    ]
    wifi.revisar_respuestas()
    lineas = _jsonl(tmp_path / "respuestas.jsonl")
    assert [(r["motivo"], r["rtt_ms"]) for r in lineas] == [("OK", 9.5), ("SEQ_VIEJA", 3.0)]
    assert wifi.rechazadas_por_la_placa == 1
    assert wifi.rtts_ms == [9.5]  # solo cuentan las órdenes aceptadas


def test_cerrar_cierra_el_emisor_una_vez_y_ya_no_se_manda(tmp_path: Path) -> None:
    emisor = EmisorFalso()
    wifi = AdaptadorWifi(tmp_path, 400, emisor)
    wifi.cerrar()
    wifi.cerrar()
    wifi.enviar(_comando(), 1100.0)
    assert emisor.cerrado == 1 and emisor.mandadas == []
    assert len(_jsonl(tmp_path / "comandos.jsonl")) == 1  # el registro sigue


def test_con_la_placa_de_referencia(tmp_path: Path) -> None:
    with placa_falsa() as (puerto, placa):
        emisor = Emisor("127.0.0.1", puerto)
        wifi = AdaptadorWifi(tmp_path, 400, emisor)
        wifi.enviar(_comando("AVANZAR", 0.4, 0.0), 1100.0)
        for _ in range(100):  # la respuesta llega por UDP: se espera sin bloquear
            wifi.revisar_respuestas()
            if wifi.rtts_ms:
                break
            emisor.recibir(5)
        assert placa.estado == "MOVIENDO"
        wifi.enviar(_comando("STOP", 0.0, 0.0), 1200.0)
        wifi.cerrar()
        assert placa.estado == "DETENIDO"
    assert wifi.enviadas == 2 and wifi.rtts_ms and wifi.rechazadas_por_la_placa == 0


def test_un_stop_siempre_sale_con_velocidad_y_giro_cero(tmp_path: Path) -> None:
    """El adaptador virtual normaliza el STOP; la orden que viaja es coherente con la placa."""
    emisor = EmisorFalso()
    wifi = AdaptadorWifi(tmp_path, 400, emisor)
    wifi.enviar(_comando("STOP", 0.4, 0.3), 1100.0)
    assert [(o.accion, o.velocidad, o.giro) for o in emisor.mandadas] == [("STOP", 0.0, 0.0)]
    assert not (tmp_path / "errores.jsonl").exists()
