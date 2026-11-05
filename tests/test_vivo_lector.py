"""P5-21: el lector del stream conserva solo el cuadro más nuevo y se reconecta."""

from __future__ import annotations

import io
import threading
from contextlib import contextmanager
from typing import Any

from vivo.lector import LectorStream, abrir_stream
from vivo_comun import SEPARADOR, esperar, jpeg_falso, servidor_mjpeg


def _flujo(*n: int, defectuoso: bool = False) -> bytes:
    cuerpo = b""
    for i in n:
        datos = jpeg_falso(i)
        largo = len(datos) + (7 if defectuoso else 0)
        cuerpo += SEPARADOR + b"Content-Length: %d\r\n\r\n" % largo + datos
    return cuerpo


class Fuente:
    """`abrir` que da un flujo distinto por conexión y, al agotarse, falla como una red caída."""

    def __init__(self, *flujos: bytes | Exception) -> None:
        self.flujos = list(flujos)
        self.aperturas = 0
        self.vivo = threading.Event()  # mientras esté activo, el último flujo no se cierra

    @contextmanager
    def __call__(self) -> Any:
        self.aperturas += 1
        if not self.flujos:
            raise OSError("sin más flujos")
        flujo = self.flujos.pop(0)
        if isinstance(flujo, Exception):
            raise flujo
        yield io.BytesIO(flujo)


def _lector(fuente: Fuente, reloj: Any = None) -> LectorStream:
    contador = iter(range(10_000))
    return LectorStream(
        fuente, reloj or (lambda: float(next(contador))), max_cuadro=1 << 20, reconexion_s=0.02
    )


def test_siempre_entrega_el_cuadro_mas_nuevo_y_cuenta_los_descartados() -> None:
    lector = _lector(Fuente(_flujo(1, 2, 3)))
    lector.iniciar()
    try:
        assert esperar(lambda: lector.recibidos == 3)
        cuadro = lector.siguiente(1)
        assert cuadro is not None and cuadro.n == 3 and cuadro.datos == jpeg_falso(3)
        assert lector.descartados == 2  # el 1 y el 2 nunca los tomó nadie
        assert lector.siguiente(0.05) is None  # el mismo cuadro no se entrega dos veces
    finally:
        lector.detener()


def test_un_cuadro_ya_tomado_no_cuenta_como_descartado() -> None:
    lector = _lector(Fuente(_flujo(1), _flujo(2)))
    lector.iniciar()
    try:
        assert lector.siguiente(2).n == 1
        assert lector.siguiente(2).n == 2
        assert lector.descartados == 0
    finally:
        lector.detener()


def test_t_capture_es_el_reloj_al_terminar_de_llegar_el_cuadro() -> None:
    tiempos = iter([10.0, 20.0, 30.0])
    lector = _lector(Fuente(_flujo(1, 2, 3)), lambda: next(tiempos))
    lector.iniciar()
    try:
        assert esperar(lambda: lector.recibidos == 3)
        assert lector.siguiente(1).t_capture_ms == 30.0
    finally:
        lector.detener()


def test_se_reconecta_cuando_el_stream_se_corta() -> None:
    fuente = Fuente(OSError("sin WiFi"), OSError("sin WiFi"), _flujo(1), _flujo(2))
    lector = _lector(fuente)
    lector.iniciar()
    try:
        assert lector.siguiente(2).n == 1
        assert lector.siguiente(2).n == 2
        assert lector.conexiones == 2 and fuente.aperturas >= 4
        assert esperar(lambda: not lector.conectado)
        assert lector.ultimo_error
    finally:
        lector.detener()


def test_un_stream_defectuoso_cuenta_como_desconexion_y_el_hilo_sigue() -> None:
    lector = _lector(Fuente(_flujo(1, defectuoso=True), _flujo(2)))
    lector.iniciar()
    try:
        cuadro = lector.siguiente(2)
        assert cuadro is not None and cuadro.datos == jpeg_falso(2)  # el malo no se entrega
    finally:
        lector.detener()


def test_detener_corta_la_espera() -> None:
    lector = _lector(Fuente())
    lector.iniciar()
    lector.detener()
    assert not lector._hilo.is_alive()
    assert lector.siguiente(0.01) is None


def test_abrir_stream_contra_un_servidor_http_real() -> None:
    with servidor_mjpeg(0.02) as servidor:
        lector = LectorStream(
            lambda: abrir_stream("127.0.0.1", servidor.puerto, "/stream", 1.0),
            lambda: 0.0,
            max_cuadro=1 << 20,
        )
        lector.iniciar()
        try:
            assert esperar(lambda: lector.recibidos >= 3)
            assert lector.siguiente(1).datos.startswith(b"\xff\xd8")
            assert lector.conectado
        finally:
            lector.detener()


def test_un_estado_http_distinto_de_200_es_un_error_de_conexion() -> None:
    with servidor_mjpeg() as servidor:
        servidor.cortar()  # responde 503
        lector = LectorStream(
            lambda: abrir_stream("127.0.0.1", servidor.puerto, "/stream", 1.0),
            lambda: 0.0,
            max_cuadro=1 << 20,
            reconexion_s=0.02,
        )
        lector.iniciar()
        try:
            assert esperar(lambda: lector.ultimo_error is not None)
            assert "503" in lector.ultimo_error and not lector.conectado
            assert lector.recibidos == 0
        finally:
            lector.detener()


def test_iniciar_dos_veces_no_lanza_un_segundo_hilo() -> None:
    fuente = Fuente(_flujo(1))
    lector = _lector(fuente)
    lector.iniciar()
    lector.iniciar()
    try:
        assert lector.siguiente(2).n == 1
    finally:
        lector.detener()
    lector.iniciar()  # ya detenido: no revive
    assert not lector._hilo.is_alive()
