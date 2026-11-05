"""Teclas sueltas de la terminal para el paro de emergencia (sin Enter).

`Teclado` se usa como contexto: en macOS y Linux pone la terminal en modo `cbreak` y la restaura
al salir (Ctrl+C sigue funcionando); en Windows usa `msvcrt`. Si la entrada no es una terminal
(un pipe, una tarea programada) `disponible` es `False` y `tecla` solo espera: ahí no hay paro
por tecla y el lazo en vivo no deja mandar a motores (ver `__main__`).

`tecla(espera_s)` devuelve la tecla en minúscula o `None` si no se pulsó ninguna en ese tiempo.
"""

from __future__ import annotations

import os
import sys
import time
from types import TracebackType
from typing import Any


class Teclado:
    def __init__(self, entrada: Any = None) -> None:
        self._entrada = sys.stdin if entrada is None else entrada
        self._ajustes: Any = None
        self._windows = sys.platform == "win32"
        try:
            self.disponible = bool(self._entrada.isatty())
        except (AttributeError, ValueError):
            self.disponible = False

    def __enter__(self) -> Teclado:
        if self.disponible and not self._windows:
            import termios
            import tty

            descriptor = self._entrada.fileno()
            self._ajustes = termios.tcgetattr(descriptor)
            tty.setcbreak(descriptor)
        return self

    def __exit__(
        self,
        _tipo: type[BaseException] | None,
        _valor: BaseException | None,
        _traza: TracebackType | None,
    ) -> None:
        if self._ajustes is not None:
            import termios

            termios.tcsetattr(self._entrada.fileno(), termios.TCSADRAIN, self._ajustes)
            self._ajustes = None

    def tecla(self, espera_s: float) -> str | None:
        if not self.disponible:
            time.sleep(espera_s)
            return None
        if self._windows:
            return self._tecla_windows(espera_s)
        import select

        listos, _, _ = select.select([self._entrada], [], [], espera_s)
        if not listos:
            return None
        # os.read y no read(1): el búfer de stdin podría guardar teclas que select no ve.
        caracter = os.read(self._entrada.fileno(), 1).decode("utf-8", errors="ignore")
        return caracter.lower() if caracter else None

    @staticmethod
    def _tecla_windows(espera_s: float) -> str | None:
        import msvcrt

        limite = time.monotonic() + espera_s
        while True:
            if msvcrt.kbhit():
                caracter = msvcrt.getwch()
                if caracter in ("\x00", "\xe0"):  # tecla especial: el segundo código se descarta
                    msvcrt.getwch()
                    return None
                return caracter.lower()
            if time.monotonic() >= limite:
                return None
            time.sleep(0.01)
