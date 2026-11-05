"""P5-20: emisor de prueba. Manda órdenes a mano al carro, sin detector ni política.

Sirve para probar el firmware (y el carro simulado de P5-22) antes de conectar el lazo. Cada
datagrama enviado y cada respuesta se escriben en una bitácora JSONL opcional.

Al abrir una sesión nueva lo primero que se manda es un STOP (la placa solo acepta una sesión
nueva con STOP) y al cerrar se manda STOP otra vez, aunque sea por Ctrl+C o por un error.
"""

from __future__ import annotations

import json
import secrets
import socket
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .protocolo import (
    MAX_U32,
    PUERTO,
    Orden,
    Respuesta,
    codificar_orden,
    decodificar_respuesta,
)

VIGENCIA_MS = 400  # igual que validez_orden_ms de config/control/plazos.yaml
PERIODO_MS = 100  # igual que paso_reloj_ms
VELOCIDAD = 0.4  # velocidad_avance de config/control/politica.yaml
GIRO = 0.5  # giro de config/control/politica.yaml
STOPS_AL_CERRAR = 3  # UDP puede perder uno


def _ahora_ms() -> float:
    # perf_counter y no monotonic: en Windows monotonic avanza en saltos de ~15 ms y el rtt sale 0.
    return time.perf_counter() * 1000


@dataclass
class Recibida:
    respuesta: Respuesta
    t_pc_ms: float
    rtt_ms: float | None


class Emisor:
    def __init__(
        self,
        ip: str,
        puerto: int = PUERTO,
        bitacora: Path | str | None = None,
        sesion: int | None = None,
        reloj: Callable[[], float] = _ahora_ms,
    ) -> None:
        self.destino = (ip, puerto)
        self.sesion = sesion if sesion is not None else secrets.randbelow(MAX_U32) + 1
        self.seq = 0
        self.reloj = reloj
        self._enviados: dict[tuple[int, int], float] = {}
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._bitacora = None
        if bitacora is not None:
            # La ruta la elige quien corre `python -m carro --bitacora` (igual que en control).
            ruta = Path(bitacora)
            ruta.parent.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
            self._bitacora = ruta.open("w", encoding="utf-8", newline="\n")  # NOSONAR (S8707)
        self.stop()

    # -- envío -------------------------------------------------------------------------
    def orden(
        self, accion: str, velocidad: float = 0.0, giro: float = 0.0, vigencia_ms: int = VIGENCIA_MS
    ) -> Orden:
        """Siguiente orden de la sesión, con su número de secuencia."""
        self.seq += 1
        return Orden(self.sesion, self.seq, accion, velocidad, giro, vigencia_ms)

    def enviar(self, orden: Orden | bytes) -> bytes:
        """Manda una orden (o bytes crudos, para probar rechazos)."""
        datos = orden if isinstance(orden, bytes) else codificar_orden(orden)
        t = self.reloj()
        self._sock.sendto(datos, self.destino)
        if isinstance(orden, Orden):
            self._enviados[(orden.sesion, orden.seq)] = t
        self._anotar({"t_pc_ms": t, "tipo": "enviado", "datos": datos.decode("ascii", "replace")})
        return datos

    def stop(self) -> Orden:
        o = self.orden("STOP")
        self.enviar(o)
        return o

    # -- recepción ---------------------------------------------------------------------
    def recibir(self, espera_ms: float) -> list[Recibida]:
        """Junta las respuestas que lleguen durante `espera_ms`."""
        limite = self.reloj() + espera_ms
        recibidas: list[Recibida] = []
        while True:
            # Con espera 0 el socket queda sin bloqueo: se vacía lo que ya llegó y se sale.
            self._sock.settimeout(max(limite - self.reloj(), 0) / 1000)
            try:
                datos, _ = self._sock.recvfrom(256)
            except (TimeoutError, BlockingIOError):
                break
            except ConnectionResetError:  # Windows: ICMP "puerto inalcanzable"
                continue
            t = self.reloj()
            r = decodificar_respuesta(datos)
            registro: dict[str, Any] = {
                "t_pc_ms": t,
                "tipo": "recibido",
                "datos": datos.decode("ascii", "replace"),
            }
            if r is None:
                registro["error"] = "respuesta ilegible"
                self._anotar(registro)
                continue
            enviado = self._enviados.get((r.sesion, r.seq))
            rtt = t - enviado if enviado is not None and r.motivo != "VENCIDA" else None
            registro["rtt_ms"] = rtt
            self._anotar(registro)
            recibidas.append(Recibida(r, t, rtt))
        return recibidas

    # -- cierre ------------------------------------------------------------------------
    def cerrar(self) -> None:
        try:
            for _ in range(STOPS_AL_CERRAR):
                self.stop()
            self.recibir(50)
        finally:
            self._sock.close()
            if self._bitacora is not None:
                self._bitacora.close()

    def __enter__(self) -> Emisor:
        return self

    def __exit__(self, *_: object) -> None:
        self.cerrar()

    def _anotar(self, registro: dict[str, Any]) -> None:
        if self._bitacora is not None:
            registro["sesion"] = self.sesion
            self._bitacora.write(json.dumps(registro, ensure_ascii=False) + "\n")
            self._bitacora.flush()


def sostener(
    em: Emisor,
    accion: str,
    velocidad: float,
    giro: float,
    durante_ms: float,
    periodo_ms: float = PERIODO_MS,
    vigencia_ms: int = VIGENCIA_MS,
    al_recibir: Callable[[Recibida], None] | None = None,
) -> list[Recibida]:
    """Repite la misma orden cada `periodo_ms` durante `durante_ms` (como el tick del lazo)."""
    recibidas: list[Recibida] = []
    fin = em.reloj() + durante_ms
    while em.reloj() < fin:
        siguiente = em.reloj() + periodo_ms
        em.enviar(em.orden(accion, velocidad, giro, vigencia_ms))
        nuevas = em.recibir(max(siguiente - em.reloj(), 0))
        if al_recibir is not None:
            for r in nuevas:
                al_recibir(r)
        recibidas += nuevas
    return recibidas


# -- pruebas de rechazo y de paro automático ---------------------------------------------
@dataclass
class Resultado:
    nombre: str
    pasa: bool
    detalle: str
    respuestas: list[dict[str, Any]] = field(default_factory=list)


def _arrancar(em: Emisor, mover_ms: float) -> list[Recibida]:
    return sostener(em, "AVANZAR", VELOCIDAD, 0.0, mover_ms)


def _rechazo(
    em: Emisor, nombre: str, datos: _OrdenDiferida | bytes, motivo: str, mover_ms: float
) -> Resultado:
    """Pone el carro en movimiento, manda un datagrama malo y espera rechazo y freno."""
    previas = _arrancar(em, mover_ms)
    if not any(r.respuesta.estado == "MOVIENDO" for r in previas):
        return Resultado(nombre, False, "la placa no llegó a MOVIENDO antes de la prueba")
    em.enviar(datos.armar() if isinstance(datos, _OrdenDiferida) else datos)
    resp = [r.respuesta for r in em.recibir(300)]
    buena = [r for r in resp if r.motivo == motivo and r.estado == "DETENIDO"]
    detalle = f"esperado {motivo}/DETENIDO; recibido " + (
        ", ".join(f"{r.motivo}/{r.estado}" for r in resp) or "nada"
    )
    return Resultado(nombre, bool(buena), detalle, [asdict(r) for r in resp])


def prueba_corte(em: Emisor, mover_ms: float = 1000) -> Resultado:
    """Mueve y deja de mandar sin STOP: la placa debe frenar sola y avisar VENCIDA."""
    previas = _arrancar(em, mover_ms)
    if not any(r.respuesta.estado == "MOVIENDO" for r in previas):
        return Resultado("corte", False, "la placa no llegó a MOVIENDO antes del corte")
    t_ultimo = max(em._enviados.values())
    for r in em.recibir(1500):
        if r.respuesta.motivo == "VENCIDA":
            tras = r.t_pc_ms - t_ultimo
            return Resultado(
                "corte",
                tras <= 600,
                f"VENCIDA a {tras:.0f} ms de la última orden (vigencia {VIGENCIA_MS}, límite 600)",
                [asdict(r.respuesta)],
            )
    return Resultado("corte", False, "no llegó el aviso VENCIDA en 1500 ms")


class _OrdenDiferida:
    """Orden que se arma justo antes de mandarla, con la secuencia que haya en ese momento."""

    def __init__(self, armar: Callable[[], Orden]) -> None:
        self.armar = armar


def prueba_repetida(em: Emisor, mover_ms: float = 300) -> Resultado:
    """Repite el número de secuencia de la última orden aceptada."""
    o = _OrdenDiferida(lambda: Orden(em.sesion, em.seq, "AVANZAR", VELOCIDAD, 0.0, VIGENCIA_MS))
    return _rechazo(em, "repetida", o, "SEQ_VIEJA", mover_ms)


def prueba_vieja(em: Emisor, mover_ms: float = 300) -> Resultado:
    """Manda una secuencia anterior a la última aceptada (llegó tarde o fuera de orden)."""
    o = _OrdenDiferida(
        lambda: Orden(em.sesion, max(em.seq - 3, 1), "AVANZAR", VELOCIDAD, 0.0, VIGENCIA_MS)
    )
    return _rechazo(em, "vieja", o, "SEQ_VIEJA", mover_ms)


def prueba_mal_formada(em: Emisor, mover_ms: float = 300) -> Resultado:
    return _rechazo(em, "mal_formada", b"P5C1,basura", "MAL_FORMADA", mover_ms)


def prueba_fuera_rango(em: Emisor, mover_ms: float = 300) -> Resultado:
    o = _OrdenDiferida(lambda: em.orden("AVANZAR", 1.5))
    return _rechazo(em, "fuera_rango", o, "FUERA_RANGO", mover_ms)


def prueba_inconsistente(em: Emisor, mover_ms: float = 300) -> Resultado:
    o = _OrdenDiferida(lambda: em.orden("AVANZAR", VELOCIDAD, GIRO))  # AVANZAR con giro
    return _rechazo(em, "inconsistente", o, "INCONSISTENTE", mover_ms)


def prueba_sesion_ajena(em: Emisor, mover_ms: float = 300) -> Resultado:
    """AVANZAR de otra sesión (otro emisor, o uno viejo que sigue vivo)."""
    o = _OrdenDiferida(
        lambda: Orden(em.sesion % MAX_U32 + 1, em.seq + 1, "AVANZAR", VELOCIDAD, 0.0, VIGENCIA_MS)
    )
    return _rechazo(em, "sesion_ajena", o, "SESION", mover_ms)


PRUEBAS: dict[str, Callable[..., Resultado]] = {
    "corte": prueba_corte,
    "repetida": prueba_repetida,
    "vieja": prueba_vieja,
    "mal_formada": prueba_mal_formada,
    "fuera_rango": prueba_fuera_rango,
    "inconsistente": prueba_inconsistente,
    "sesion_ajena": prueba_sesion_ajena,
}
