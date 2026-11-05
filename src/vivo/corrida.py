"""Corrida en vivo: la `Corrida` de T14 con reloj real, un cerrojo y el adaptador del carro.

`control.__main__.Corrida` ya hace lo que hace falta con cada decisión: llama al supervisor y a la
política, valida el comando contra el contrato y deja `detecciones.jsonl`, `decisiones.jsonl`,
`comandos.jsonl` y `errores.jsonl`. Aquí solo cambian dos cosas:

- El reloj. En reproducción el reloj es el `t_emit_ms` de cada evento. En vivo es el reloj
  monotónico del run (`infer.reloj`, el mismo de `t_capture_ms` y `t_emit_ms`), y se lee **dentro
  del cerrojo** para que dos hilos nunca le pasen al supervisor un `ahora_ms` que retrocede.
- El adaptador. En lugar del virtual se usa `AdaptadorWifi`, que además manda la orden al carro.

Dos hilos llaman a esta clase: el lazo principal (un cuadro por vez) y el hilo del reloj (el tic
del watchdog cada `paso_reloj_ms`), más el de las teclas (emergencia y rearme). Todo pasa por
`self.cerrojo`.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from control.__main__ import Corrida
from control.politica import decidir
from control.supervisor import Politica, Supervisor

from .adaptador_wifi import AdaptadorWifi, EmisorCarro


class CorridaVivo(Corrida):
    def __init__(
        self,
        salida: Path,
        plazos: dict[str, Any],
        config_politica: Any,
        reloj_ms: Callable[[], float],
        emisor: EmisorCarro | None = None,
        politica: Politica = decidir,
    ) -> None:
        super().__init__(salida, plazos, config_politica, politica)
        self.reloj_ms = reloj_ms
        self.cerrojo = threading.RLock()
        # Se reemplaza el adaptador virtual que armó `Corrida` por el del carro (mismo archivo
        # `comandos.jsonl`) y el supervisor que lo usa.
        self.adaptador = AdaptadorWifi(self.salida, plazos["validez_orden_ms"], emisor)
        self.supervisor = Supervisor(self.politica, self.adaptador, plazos, config_politica)
        # Latencia de cuadro a comando: t_command_ms - t_capture_ms, por cada cuadro atendido.
        self.latencias_ms: list[float] = []
        self.por_estado = {"ok": 0, "stale": 0, "error": 0}
        self.por_accion: dict[str, int] = {}

    def cuadro_vivo(self, evento: dict[str, Any]) -> dict[str, Any]:
        """Un evento del detector: el supervisor decide y el adaptador manda la orden."""
        with self.cerrojo:
            self.ahora_ms = self.reloj_ms()
            self.eventos += 1
            _anexar(self.ruta_detecciones, evento)
            self.por_estado[evento["status"]] += 1
            # Antes de decidir, el watchdog y la vigencia de la orden anterior (igual que T14).
            self._registrar(self.supervisor.tick(self.ahora_ms), None)
            self.politica.propuesta = None
            comando = self.supervisor.procesar_evento(evento, self.ahora_ms)
            self._registrar(comando, self.politica.propuesta)
            self.latencias_ms.append(comando["t_command_ms"] - evento["t_capture_ms"])
            return comando

    def tic(self) -> dict[str, Any] | None:
        """El watchdog. Devuelve el STOP de reloj si lo mandó."""
        with self.cerrojo:
            self.ahora_ms = self.reloj_ms()
            comando = self.supervisor.tick(self.ahora_ms)
            self._registrar(comando, None)
            self.adaptador.revisar_respuestas()
            return comando

    def emergencia_vivo(self) -> dict[str, Any]:
        with self.cerrojo:
            return self._accion_vivo("emergencia", self.supervisor.emergencia)

    def rearmar_vivo(self) -> dict[str, Any] | None:
        """`None` si no había emergencia. Si no se pudo rearmar, el comando es un STOP."""
        with self.cerrojo:
            return self._accion_vivo("rearmar", self.supervisor.rearmar)

    def cerrar_vivo(self) -> dict[str, Any] | None:
        """STOP final del supervisor y cierre del carro (tres STOP más). Se puede repetir."""
        with self.cerrojo:
            try:
                self.cerrar()
            finally:
                self.adaptador.cerrar()
            return self.adaptador.activo

    def _accion_vivo(
        self, nombre: str, accion: Callable[[float], dict[str, Any] | None]
    ) -> dict[str, Any] | None:
        self.ahora_ms = self.reloj_ms()
        posicion = self.comandos
        self.politica.propuesta = None
        comando = accion(self.ahora_ms)
        self._registrar(comando, self.politica.propuesta)
        self._anotar(nombre, posicion, comando)
        return comando

    def _registrar(self, comando: dict[str, Any] | None, propuesta: dict[str, Any] | None) -> None:
        super()._registrar(comando, propuesta)
        if comando is not None:
            self.por_accion[comando["action"]] = self.por_accion.get(comando["action"], 0) + 1


def _anexar(ruta: Path, linea: Any) -> None:
    with ruta.open("a", encoding="utf-8", newline="\n") as registro:
        registro.write(json.dumps(linea, ensure_ascii=False, allow_nan=False) + "\n")
