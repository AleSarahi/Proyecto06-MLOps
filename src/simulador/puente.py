"""P5-22: puente mínimo PC → carro para la matriz de fallos. **No es el adaptador de P5-21.**

`AdaptadorPuente` hace todo lo que hace el `AdaptadorVirtual` de control (registra cada comando
en `comandos.jsonl`, con su vigencia) y además lo manda al carro por UDP con el emisor de P5-20.
Así la matriz prueba el supervisor y la política reales contra el carro simulado sin esperar al
lazo en vivo. Cuando P5-21 exista, la matriz se puede correr también con ese adaptador.

Si el carro deja de contestar, el puente lo anota en `avisos.jsonl` (`carro_sin_respuesta`) y
avisa una vez por hueco: la PC no puede frenar un carro que no la oye, así que lo que lo detiene
es su paro automático.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from control import AdaptadorVirtual

from . import formato

NOMBRE_AVISOS = "avisos.jsonl"
ESPERA_RESPUESTA_MS = 150  # más de un ciclo de 100 ms sin respuesta ya es un aviso


class AdaptadorPuente(AdaptadorVirtual):
    def __init__(
        self,
        carpeta_salida: Path | str,
        validez_orden_ms: float,
        ip: str,
        puerto: int = formato.PUERTO,
        espera_respuesta_ms: float = ESPERA_RESPUESTA_MS,
        al_avisar: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(carpeta_salida, validez_orden_ms)
        self.espera_respuesta_ms = espera_respuesta_ms
        self._al_avisar = al_avisar
        self.ruta_avisos = self.carpeta_salida / NOMBRE_AVISOS
        self.ruta_avisos.write_text("", encoding="utf-8")  # NOSONAR (S8707)
        # Sin pendientes: el emisor manda su STOP inicial al crearse.
        self._emisor = formato.Emisor(ip, puerto)
        self._sin_respuesta_desde: float | None = None
        self._avisado = False
        self._cerrado = False
        self.ultima_respuesta: Any = None

    def enviar(self, comando: dict[str, Any], ahora_ms: float) -> dict[str, Any]:
        registrado = super().enviar(comando, ahora_ms)
        if self._cerrado:
            return registrado
        orden = formato.orden_de_comando(self._emisor, registrado, int(self.validez_orden_ms))
        self._emisor.enviar(orden)
        if self._sin_respuesta_desde is None:
            self._sin_respuesta_desde = ahora_ms
        self.revisar(ahora_ms)
        return registrado

    def revisar(self, ahora_ms: float) -> None:
        """Lee las respuestas que ya llegaron y avisa si el carro lleva rato sin contestar."""
        if self._cerrado:
            return
        recibidas = self._emisor.recibir(0)
        if recibidas:
            self.ultima_respuesta = recibidas[-1].respuesta
            self._sin_respuesta_desde = None
            if self._avisado:
                self._avisar(ahora_ms, "carro_responde_otra_vez", None)
            self._avisado = False
            return
        desde = self._sin_respuesta_desde
        if desde is None or self._avisado or ahora_ms - desde < self.espera_respuesta_ms:
            return
        self._avisado = True
        self._avisar(ahora_ms, "carro_sin_respuesta", ahora_ms - desde)

    def cerrar(self) -> None:
        """Manda los STOP de cierre del emisor y suelta el socket."""
        if not self._cerrado:
            self._cerrado = True
            self._emisor.cerrar()

    def _avisar(self, ahora_ms: float, motivo: str, sin_respuesta_ms: float | None) -> None:
        aviso = {"t_ms": ahora_ms, "motivo": motivo, "sin_respuesta_ms": sin_respuesta_ms}
        with self.ruta_avisos.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(aviso, ensure_ascii=False) + "\n")
        if self._al_avisar is not None:
            self._al_avisar(aviso)
