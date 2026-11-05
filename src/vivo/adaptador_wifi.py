"""Adaptador del carro por WiFi (P5-21): el adaptador virtual de T02 más la orden por UDP.

Es el único archivo del lazo en vivo que conoce el protocolo del carro (`carro.protocolo`,
`docs/carro/protocolo.md`); si el protocolo cambia, se cambia aquí.

Hereda de `AdaptadorVirtual`, así que cada comando sigue quedando en `comandos.jsonl` con
`received`, `t_command_ms` y `valid_until_ms`, y el supervisor lo usa igual. Después de
registrarlo, lo manda al carro. Sin `emisor` es el **modo seco**: calcula y registra, no abre la
red ni manda nada.

Lo que sale al carro cumple las reglas de la placa antes de enviarse. Si un comando no se puede
codificar como orden (acción desconocida, `speed` o `steering` incoherentes con la acción, o
fuera de rango) no se manda ese: se manda un STOP y el motivo queda en `errores.jsonl`
(`orden_no_enviable`). Un fallo del socket también deja STOP registrado como error, nunca
silencio, y se reintenta el STOP en el cierre.

Las respuestas de la placa se leen sin bloquear después de cada envío y en cada tic, y quedan en
`respuestas.jsonl` con el `rtt_ms` de comando a respuesta, que pide la calibración (P5-23).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from carro.protocolo import TOPE_VIGENCIA_MS, Orden, Respuesta, codificar_orden, decodificar_orden
from control.adaptador_virtual import AdaptadorVirtual

NOMBRE_RESPUESTAS = "respuestas.jsonl"
NOMBRE_ERRORES = "errores.jsonl"


class Recibida(Protocol):
    respuesta: Respuesta
    t_pc_ms: float
    rtt_ms: float | None


class EmisorCarro(Protocol):
    """Lo que el adaptador usa de `carro.emisor.Emisor`; en las pruebas lo cumple un doble."""

    def orden(
        self, accion: str, velocidad: float = ..., giro: float = ..., vigencia_ms: int = ...
    ) -> Orden: ...
    def enviar(self, orden: Orden | bytes) -> bytes: ...
    def recibir(self, espera_ms: float) -> list[Recibida]: ...
    def cerrar(self) -> None: ...


class AdaptadorWifi(AdaptadorVirtual):
    def __init__(
        self,
        carpeta_salida: Path | str,
        validez_orden_ms: float,
        emisor: EmisorCarro | None = None,
    ) -> None:
        super().__init__(carpeta_salida, validez_orden_ms)
        self.emisor = emisor
        self.ruta_respuestas = self.carpeta_salida / NOMBRE_RESPUESTAS
        self.ruta_respuestas.write_text("", encoding="utf-8")  # NOSONAR (S8707)
        self.enviadas = 0
        self.rechazadas_por_la_placa = 0
        self.fallos_de_envio = 0
        self.rtts_ms: list[float] = []  # de orden a respuesta, solo las que contestan OK
        self._cerrado = False

    @property
    def seco(self) -> bool:
        return self.emisor is None

    def enviar(self, comando: dict[str, Any], ahora_ms: float) -> dict[str, Any]:
        registrado = super().enviar(comando, ahora_ms)
        if self.emisor is not None and not self._cerrado:
            self._mandar(registrado, ahora_ms)
        return registrado

    def revisar_respuestas(self) -> list[Recibida]:
        """Lee sin bloquear lo que contestó la placa y lo deja en `respuestas.jsonl`."""
        if self.emisor is None or self._cerrado:
            return []
        try:
            recibidas = self.emisor.recibir(0)
        except OSError as exc:
            self._error(0.0, "respuesta_no_leida", [f"{type(exc).__name__}: {exc}"])
            return []
        with self.ruta_respuestas.open("a", encoding="utf-8", newline="\n") as registro:
            for r in recibidas:
                rechazo = r.respuesta.motivo not in ("OK", "VENCIDA")
                self.rechazadas_por_la_placa += rechazo
                if r.rtt_ms is not None and r.respuesta.motivo == "OK":
                    self.rtts_ms.append(r.rtt_ms)
                registro.write(
                    json.dumps(
                        {
                            "t_pc_ms": r.t_pc_ms,
                            "rtt_ms": r.rtt_ms,
                            "sesion": r.respuesta.sesion,
                            "seq": r.respuesta.seq,
                            "motivo": r.respuesta.motivo,
                            "estado": r.respuesta.estado,
                            "pwm_izq": r.respuesta.pwm_izq,
                            "pwm_der": r.respuesta.pwm_der,
                            "t_placa_ms": r.respuesta.t_placa_ms,
                        },
                        allow_nan=False,
                    )
                    + "\n"
                )
        return recibidas

    def cerrar(self) -> None:
        """Después de esto no se manda nada más. El emisor deja tres STOP antes de cerrar."""
        if self._cerrado:
            return
        self._cerrado = True
        if self.emisor is None:
            return
        try:
            self.emisor.cerrar()
        except OSError as exc:
            self._error(0.0, "cierre_del_emisor", [f"{type(exc).__name__}: {exc}"])

    def _mandar(self, registrado: dict[str, Any], ahora_ms: float) -> None:
        assert self.emisor is not None
        motivo = _motivo_no_enviable(registrado)
        if motivo is None:
            orden = self.emisor.orden(
                registrado["action"],
                float(registrado["speed"]),
                float(registrado["steering"]),
                _vigencia_ms(registrado, ahora_ms),
            )
        else:
            self._error(ahora_ms, "orden_no_enviable", [motivo], registrado)
            orden = self.emisor.orden("STOP")
        try:
            self.emisor.enviar(orden)
            self.enviadas += 1
        except OSError as exc:
            # Si la red falló, la placa frena sola al vencer la orden (docs/carro/protocolo.md).
            self.fallos_de_envio += 1
            self._error(ahora_ms, "envio_fallido", [f"{type(exc).__name__}: {exc}"], registrado)
        self.revisar_respuestas()

    def _error(
        self,
        ahora_ms: float,
        motivo: str,
        errores: list[str],
        comando: dict[str, Any] | None = None,
    ) -> None:
        linea = {
            "run_id": comando.get("run_id") if comando else None,
            "frame_id": comando.get("frame_id") if comando else None,
            "t_ms": ahora_ms,
            "motivo": motivo,
            "errores": errores,
        }
        with (self.carpeta_salida / NOMBRE_ERRORES).open(
            "a", encoding="utf-8", newline="\n"
        ) as registro:
            registro.write(json.dumps(linea, ensure_ascii=False, allow_nan=False) + "\n")


def _vigencia_ms(comando: dict[str, Any], ahora_ms: float) -> int:
    """Lo que le queda a la orden desde que se manda: nunca más que `valid_until_ms`."""
    restante = comando["valid_until_ms"] - ahora_ms
    return max(1, min(TOPE_VIGENCIA_MS, int(restante)))


def _motivo_no_enviable(comando: dict[str, Any]) -> str | None:
    """Por qué la placa rechazaría este comando; `None` si la orden es válida."""
    try:
        orden = Orden(
            1,
            1,
            comando["action"],
            float(comando["speed"]),
            float(comando["steering"]),
            _vigencia_ms(comando, comando["t_command_ms"]),
        )
        _, motivo = decodificar_orden(codificar_orden(orden))
    except (KeyError, TypeError, ValueError) as exc:
        return f"comando ilegible: {type(exc).__name__}: {exc}"
    return None if motivo == "OK" else f"la placa respondería {motivo}"
