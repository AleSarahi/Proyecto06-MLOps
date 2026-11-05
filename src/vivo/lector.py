"""Lectura continua del stream: siempre el cuadro más nuevo, los viejos se descartan.

Un hilo lee el stream con `captura.leer_partes` y deja cada JPEG en un solo casillero. Si el
detector todavía no tomó el anterior, el nuevo lo reemplaza y se cuenta como descartado: la cola
no crece y la latencia tampoco, aunque el detector tarde más que el periodo entre cuadros.

`t_capture_ms` es el instante en que terminó de llegar el JPEG, en el reloj del run. El hilo se
reconecta solo si el stream se corta (cámara apagada, WiFi caído); mientras no llegan cuadros, el
watchdog de `control` es quien frena. Un stream defectuoso (encabezado ilegible, cuerpo que no
mide lo anunciado) cuenta como desconexión.

Sin el hilo, `leer_partes` en un `for` también sirve: todo lo que toca la red entra por `abrir`,
una función que devuelve un contexto con los bytes del stream, así que se prueba sin cámara.
"""

from __future__ import annotations

import http.client
import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import BinaryIO

from captura import StreamDefectuoso, leer_partes

Abrir = Callable[[], AbstractContextManager[BinaryIO]]


@dataclass(frozen=True)
class CuadroVivo:
    n: int  # 1, 2, 3...: el orden de llegada, incluidos los descartados
    datos: bytes
    t_capture_ms: float


@contextmanager
def abrir_stream(ip: str, puerto: int, ruta: str, espera_s: float) -> Iterator[BinaryIO]:
    """Conecta al stream de la ESP32-CAM. `espera_s` es el tope sin recibir bytes."""
    # La IP es de la red local del carro y la da quien corre el comando; el firmware solo habla
    # http.
    conexion = http.client.HTTPConnection(ip, puerto, timeout=espera_s)  # NOSONAR (S5332)
    try:
        conexion.request("GET", ruta)
        respuesta = conexion.getresponse()
        if respuesta.status != 200:
            raise OSError(f"el stream contestó {respuesta.status} {respuesta.reason}")
        yield respuesta
    finally:
        conexion.close()


class LectorStream:
    """Hilo que mantiene `ultimo` con el JPEG más nuevo del stream."""

    def __init__(
        self,
        abrir: Abrir,
        reloj_ms: Callable[[], float],
        *,
        max_cuadro: int,
        reconexion_s: float = 1.0,
    ) -> None:
        self._abrir = abrir
        self._reloj_ms = reloj_ms
        self._max_cuadro = max_cuadro
        self._reconexion_s = reconexion_s
        self._cond = threading.Condition()
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._correr, name="lector-stream", daemon=True)
        self._ultimo: CuadroVivo | None = None
        self._entregado = 0
        self._recibidos = 0
        self.descartados = 0
        self.conectado = False
        self.conexiones = 0
        self.ultimo_error: str | None = None

    @property
    def recibidos(self) -> int:
        return self._recibidos

    def iniciar(self) -> None:
        """Arranca el hilo; si ya corre, no hace nada."""
        if not self._hilo.is_alive() and not self._parar.is_set():
            self._hilo.start()

    def detener(self) -> None:
        self._parar.set()
        with self._cond:
            self._cond.notify_all()
        if self._hilo.is_alive():
            self._hilo.join(timeout=3)

    def siguiente(self, espera_s: float) -> CuadroVivo | None:
        """El cuadro más nuevo que no se ha entregado; `None` si no llega ninguno en `espera_s`."""
        with self._cond:
            self._cond.wait_for(
                lambda: (
                    self._parar.is_set()
                    or (self._ultimo is not None and self._ultimo.n > self._entregado)
                ),
                timeout=espera_s,
            )
            if self._ultimo is None or self._ultimo.n <= self._entregado:
                return None
            self._entregado = self._ultimo.n
            return self._ultimo

    def _publicar(self, datos: bytes) -> None:
        t_ms = self._reloj_ms()
        with self._cond:
            self._recibidos += 1
            if self._ultimo is not None and self._ultimo.n > self._entregado:
                self.descartados += 1  # el detector no alcanzó a tomar el anterior
            self._ultimo = CuadroVivo(self._recibidos, datos, t_ms)
            self._cond.notify_all()

    def _correr(self) -> None:
        while not self._parar.is_set():
            try:
                with self._abrir() as flujo:
                    self.conectado = True
                    self.conexiones += 1
                    self.ultimo_error = None
                    for datos in leer_partes(flujo, self._max_cuadro):
                        if self._parar.is_set():
                            return
                        self._publicar(datos)
                self.ultimo_error = "el stream terminó"
            except (OSError, http.client.HTTPException, StreamDefectuoso) as exc:
                self.ultimo_error = str(exc) or type(exc).__name__
            except Exception as exc:  # un fallo raro no debe matar al hilo en silencio
                self.ultimo_error = f"{type(exc).__name__}: {exc}"
            finally:
                self.conectado = False
            self._parar.wait(self._reconexion_s)
