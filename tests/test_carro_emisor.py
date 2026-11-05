"""P5-20: emisor de prueba contra una placa falsa en localhost (UDP real, sin carro)."""

from __future__ import annotations

import functools
import json
import socket
import threading
import time
from contextlib import contextmanager

import pytest

import carro.__main__ as cli
from carro.emisor import PRUEBAS, Emisor, detener, sostener
from carro.protocolo import Placa, Respuesta, codificar_respuesta


@contextmanager
def placa_falsa(callar_despues: int | None = None):
    """`Placa` tras un socket UDP. Con `callar_despues=n` deja de contestar tras n datagramas."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.005)
    placa = Placa()
    fin = threading.Event()
    estado = {"ultimo": None, "recibidos": 0}

    def ciclo():
        while not fin.is_set():
            ahora = time.monotonic() * 1000
            try:
                datos, origen = sock.recvfrom(256)
            except (TimeoutError, ConnectionResetError):
                pass
            else:
                estado["recibidos"] += 1
                r = placa.recibir(datos, ahora)
                estado["ultimo"] = origen
                if callar_despues is None or estado["recibidos"] <= callar_despues:
                    sock.sendto(codificar_respuesta(r), origen)
            aviso = placa.tick(time.monotonic() * 1000)
            if aviso is not None and estado["ultimo"] is not None:
                sock.sendto(codificar_respuesta(aviso), estado["ultimo"])

    hilo = threading.Thread(target=ciclo, daemon=True)
    hilo.start()
    try:
        yield sock.getsockname()[1], placa
    finally:
        fin.set()
        hilo.join(1)
        sock.close()


def test_arranca_con_stop_y_cierra_con_stop(tmp_path):
    bitacora = tmp_path / "b.jsonl"
    with placa_falsa() as (puerto, placa), Emisor("127.0.0.1", puerto, bitacora) as em:
        recibidas = sostener(em, "AVANZAR", 0.4, 0.0, 300)
        assert recibidas
        assert all(r.respuesta.motivo == "OK" for r in recibidas)
        assert any(r.respuesta.estado == "MOVIENDO" for r in recibidas)
        assert all(r.rtt_ms is not None and r.rtt_ms >= 0 for r in recibidas)
    time.sleep(0.05)
    assert placa.estado == "DETENIDO"
    lineas = [json.loads(x) for x in bitacora.read_text(encoding="utf-8").splitlines()]
    enviados = [x["datos"] for x in lineas if x["tipo"] == "enviado"]
    assert ",STOP," in enviados[0]
    assert all(",STOP," in x for x in enviados[-3:])
    assert {x["sesion"] for x in lineas} == {em.sesion}


@pytest.mark.parametrize("nombre", sorted(set(PRUEBAS) - {"corte"}))
def test_pruebas_de_rechazo_pasan_contra_la_placa_falsa(nombre):
    with placa_falsa() as (puerto, placa), Emisor("127.0.0.1", puerto) as em:
        res = PRUEBAS[nombre](em, mover_ms=250)
        assert res.pasa, res.detalle
        assert placa.estado == "DETENIDO"


def test_prueba_corte_mide_el_paro_automatico():
    with placa_falsa() as (puerto, _), Emisor("127.0.0.1", puerto) as em:
        res = PRUEBAS["corte"](em, mover_ms=300)
    assert res.pasa, res.detalle
    assert "VENCIDA" in res.detalle


def test_prueba_falla_si_la_placa_no_contesta():
    with placa_falsa(callar_despues=0) as (puerto, _), Emisor("127.0.0.1", puerto) as em:
        res = PRUEBAS["repetida"](em, mover_ms=200)
    assert not res.pasa
    assert "MOVIENDO" in res.detalle


def test_cierra_con_stop_aunque_haya_excepcion():
    with placa_falsa() as (puerto, placa):
        with pytest.raises(KeyboardInterrupt), Emisor("127.0.0.1", puerto) as em:
            sostener(em, "AVANZAR", 0.4, 0.0, 200)
            raise KeyboardInterrupt
        time.sleep(0.05)
        assert placa.estado == "DETENIDO"


def test_cli_modo_seco_no_abre_la_red(capsys, monkeypatch):
    def prohibido(*_a, **_k):
        raise AssertionError("modo seco no debe abrir sockets")

    monkeypatch.setattr(socket, "socket", prohibido)
    assert cli.main(["--ip", "10.0.0.1", "orden", "GIRAR_IZQ", "--durante-ms", "500"]) == 0
    salida = capsys.readouterr().out
    assert "modo seco" in salida
    assert "P5C1,1,2,GIRAR_IZQ,0.400,-0.500,400" in salida
    assert cli.main(["prueba", "corte"]) == 2


def test_cli_sin_ip(monkeypatch, capsys):
    monkeypatch.delenv("P5_CARRO_IP", raising=False)
    assert cli.main(["stop"]) == 2
    assert "falta la IP" in capsys.readouterr().err


def test_cli_prueba_contra_la_placa_falsa(capsys, monkeypatch):
    import carro.emisor as emisor

    rapidas = {k: functools.partial(f, mover_ms=200) for k, f in PRUEBAS.items()}
    monkeypatch.setattr(cli, "PRUEBAS", rapidas)
    monkeypatch.setattr(emisor, "PRUEBAS", rapidas)
    with placa_falsa() as (puerto, _):
        codigo = cli.main(
            ["--ip", "127.0.0.1", "--puerto", str(puerto), "--enviar", "prueba", "todas"]
        )
    salida = capsys.readouterr().out
    assert codigo == 0, salida
    assert salida.count("PASA ") == len(PRUEBAS)


def test_sesiones_crecen_aunque_el_reloj_no_avance():
    from carro import emisor

    a = emisor.nueva_sesion(lambda: 1_800_000_000)
    b = emisor.nueva_sesion(lambda: 1_800_000_000)
    c = emisor.nueva_sesion(lambda: 1_700_000_000)  # reloj hacia atrás
    assert a < b < c


def _par_falso():
    """Socket que hace de "carro" sin contestar solo, para mandar respuestas a mano."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    return s


def test_respuesta_de_otro_origen_se_ignora(tmp_path):
    carro, intruso = _par_falso(), _par_falso()
    bitacora = tmp_path / "b.jsonl"
    try:
        with Emisor("127.0.0.1", carro.getsockname()[1], bitacora) as em:
            mio = ("127.0.0.1", em._sock.getsockname()[1])
            r = codificar_respuesta(Respuesta(em.sesion, 1, "OK", "DETENIDO", 0, 0, 5))
            intruso.sendto(r, mio)
            assert em.recibir(100) == []
            carro.sendto(r, mio)
            (buena,) = em.recibir(100)
            assert buena.rtt_ms is not None
    finally:
        carro.close()
        intruso.close()
    ajenas = [json.loads(x) for x in bitacora.read_text(encoding="utf-8").splitlines()]
    assert [x["motivo"] for x in ajenas if x["tipo"] == "ajena"] == ["otro origen"]


def test_respuesta_que_no_corresponde_se_ignora():
    carro = _par_falso()
    try:
        with Emisor("127.0.0.1", carro.getsockname()[1]) as em:
            mio = ("127.0.0.1", em._sock.getsockname()[1])
            otras = [
                Respuesta(em.sesion, 999, "OK", "DETENIDO", 0, 0, 5),  # seq no enviada
                Respuesta(em.sesion + 1, 1, "OK", "DETENIDO", 0, 0, 5),  # otra sesión
                Respuesta(em.sesion + 1, 1, "VENCIDA", "DETENIDO", 0, 0, 5),
            ]
            for r in otras:
                carro.sendto(codificar_respuesta(r), mio)
            carro.sendto(b"P5R1,1,1,OK,MOVIENDO,0,0,5", mio)  # incoherente
            assert em.recibir(100) == []
            validas = [
                Respuesta(0, 0, "MAL_FORMADA", "DETENIDO", 0, 0, 5),
                Respuesta(em.sesion, 1, "VENCIDA", "DETENIDO", 0, 0, 5),
            ]
            for r in validas:
                carro.sendto(codificar_respuesta(r), mio)
            recibidas = em.recibir(100)
            assert [x.respuesta.motivo for x in recibidas] == ["MAL_FORMADA", "VENCIDA"]
            assert all(x.rtt_ms is None for x in recibidas)
    finally:
        carro.close()


def test_detener_manda_stop_en_cada_periodo():
    with placa_falsa() as (puerto, placa), Emisor("127.0.0.1", puerto) as em:
        recibidas = detener(em, 350)
        assert len(recibidas) >= 3
        assert all(r.respuesta.estado == "DETENIDO" for r in recibidas)
        assert placa.ultima_seq == em.seq
