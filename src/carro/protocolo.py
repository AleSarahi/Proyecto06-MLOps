"""P5-20: protocolo de órdenes PC → carro, versión 1 (ver docs/carro/protocolo.md).

Una orden es una línea ASCII por datagrama UDP:

    P5C1,<sesion>,<seq>,<accion>,<velocidad>,<giro>,<vigencia_ms>

y la placa contesta cada datagrama con:

    P5R1,<sesion>,<seq>,<motivo>,<estado>,<pwm_izq>,<pwm_der>,<t_placa_ms>

`Placa` es el modelo de referencia de las reglas del firmware: sin red ni hardware y con el
reloj como argumento. El firmware las repite en C++ y el carro simulado (P5-22) puede envolver
esta clase en un socket. Si el documento y este archivo difieren, se corrige uno de los dos en
el mismo PR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

VERSION_ORDEN = "P5C1"
VERSION_RESPUESTA = "P5R1"
PUERTO = 4210
MAX_BYTES = 96
TOPE_VIGENCIA_MS = 500
MAX_U32 = 2**32 - 1

ACCIONES = ("AVANZAR", "GIRAR_IZQ", "GIRAR_DER", "STOP")
MOTIVOS = ("OK", "MAL_FORMADA", "FUERA_RANGO", "INCONSISTENTE", "SESION", "SEQ_VIEJA", "VENCIDA")
ESTADOS = ("MOVIENDO", "DETENIDO")

# Valores por omisión del firmware (0 a 255, PWM de 8 bits). Se calibran en la fase 2 y la
# tabla de parámetros de docs/carro/protocolo.md guarda los medidos.
TECHO_PWM = 160
MINIMO_PWM = 90

_NUM = r"-?\d(?:\.\d{1,3})?"
_ORDEN_RE = re.compile(
    rf"P5C1,(\d{{1,10}}),(\d{{1,10}}),([A-Z_]{{1,12}}),({_NUM}),({_NUM}),(\d{{1,5}})\n?"
)
_RESPUESTA_RE = re.compile(
    r"P5R1,(\d{1,10}),(\d{1,10}),([A-Z_]{1,16}),([A-Z]{1,10}),(-?\d{1,3}),(-?\d{1,3}),(\d{1,10})\n?"
)


@dataclass(frozen=True)
class Orden:
    sesion: int
    seq: int
    accion: str
    velocidad: float
    giro: float
    vigencia_ms: int


@dataclass(frozen=True)
class Respuesta:
    sesion: int
    seq: int
    motivo: str
    estado: str
    pwm_izq: int
    pwm_der: int
    t_placa_ms: int


def codificar_orden(orden: Orden) -> bytes:
    """Línea de la orden. No valida: sirve también para mandar órdenes malas a propósito."""
    giro = 0.0 if orden.giro == 0 else orden.giro  # evita "-0.000"
    return (
        f"{VERSION_ORDEN},{orden.sesion},{orden.seq},{orden.accion},"
        f"{orden.velocidad:.3f},{giro:.3f},{orden.vigencia_ms}"
    ).encode("ascii")


def decodificar_orden(datos: bytes) -> tuple[Orden | None, str]:
    """Lee y valida una orden. Devuelve `(orden, "OK")` o `(orden o None, motivo del rechazo)`."""
    if len(datos) > MAX_BYTES:
        return None, "MAL_FORMADA"
    try:
        texto = datos.decode("ascii")
    except UnicodeDecodeError:
        return None, "MAL_FORMADA"
    m = _ORDEN_RE.fullmatch(texto)
    if m is None or m.group(3) not in ACCIONES:
        return None, "MAL_FORMADA"
    orden = Orden(
        sesion=int(m.group(1)),
        seq=int(m.group(2)),
        accion=m.group(3),
        velocidad=float(m.group(4)),
        giro=float(m.group(5)),
        vigencia_ms=int(m.group(6)),
    )
    if not (
        1 <= orden.sesion <= MAX_U32
        and 1 <= orden.seq <= MAX_U32
        and 0 <= orden.velocidad <= 1
        and -1 <= orden.giro <= 1
        and 1 <= orden.vigencia_ms <= TOPE_VIGENCIA_MS
    ):
        return orden, "FUERA_RANGO"
    if not _coherente(orden):
        return orden, "INCONSISTENTE"
    return orden, "OK"


def _coherente(orden: Orden) -> bool:
    v, g = orden.velocidad, orden.giro
    if orden.accion == "STOP":
        return v == 0 and g == 0
    if v <= 0:
        return False
    if orden.accion == "AVANZAR":
        return g == 0
    if orden.accion == "GIRAR_IZQ":
        return g < 0
    return g > 0  # GIRAR_DER


def codificar_respuesta(r: Respuesta) -> bytes:
    return (
        f"{VERSION_RESPUESTA},{r.sesion},{r.seq},{r.motivo},{r.estado},"
        f"{r.pwm_izq},{r.pwm_der},{r.t_placa_ms}"
    ).encode("ascii")


def decodificar_respuesta(datos: bytes) -> Respuesta | None:
    """Lee una respuesta de la placa; `None` si no sigue el formato."""
    try:
        m = _RESPUESTA_RE.fullmatch(datos.decode("ascii"))
    except UnicodeDecodeError:
        return None
    if m is None or m.group(3) not in MOTIVOS or m.group(4) not in ESTADOS:
        return None
    return Respuesta(
        sesion=int(m.group(1)),
        seq=int(m.group(2)),
        motivo=m.group(3),
        estado=m.group(4),
        pwm_izq=int(m.group(5)),
        pwm_der=int(m.group(6)),
        t_placa_ms=int(m.group(7)),
    )


def lados(velocidad: float, giro: float) -> tuple[float, float]:
    """Fracción de 0 a 1 para cada lado. Giro negativo = izquierda: el lado izquierdo frena."""
    izq = velocidad * (1 + giro) if giro < 0 else velocidad
    der = velocidad * (1 - giro) if giro > 0 else velocidad
    return izq, der


def a_pwm(fraccion: float, techo: int = TECHO_PWM, minimo: int = MINIMO_PWM) -> int:
    """0 queda en 0; cualquier otro valor arranca en la zona muerta y llega al techo con 1."""
    if fraccion <= 0:
        return 0
    return round(minimo + min(fraccion, 1.0) * (techo - minimo))


class Placa:
    """Reglas del firmware sin hardware: qué hace con cada datagrama y cuándo frena sola."""

    def __init__(self, techo: int = TECHO_PWM, minimo: int = MINIMO_PWM) -> None:
        self.techo = techo
        self.minimo = minimo
        self.sesion = 0  # 0 = ninguna; la primera orden aceptada tiene que ser STOP
        self.ultima_seq = 0
        self.vence_ms: float | None = None
        self.pwm_izq = 0
        self.pwm_der = 0

    @property
    def estado(self) -> str:
        return "MOVIENDO" if (self.pwm_izq or self.pwm_der) else "DETENIDO"

    def _frenar(self) -> None:
        self.pwm_izq = self.pwm_der = 0
        self.vence_ms = None

    def _respuesta(self, sesion: int, seq: int, motivo: str, ahora_ms: float) -> Respuesta:
        return Respuesta(
            sesion, seq, motivo, self.estado, self.pwm_izq, self.pwm_der, int(ahora_ms)
        )

    def recibir(self, datos: bytes, ahora_ms: float) -> Respuesta:
        """Aplica un datagrama. Todo rechazo frena los motores."""
        orden, motivo = decodificar_orden(datos)
        if motivo == "OK" and orden is not None:
            if orden.sesion != self.sesion:
                if orden.accion != "STOP":
                    motivo = "SESION"
                else:
                    self.sesion, self.ultima_seq = orden.sesion, 0
            if motivo == "OK" and orden.seq <= self.ultima_seq:
                motivo = "SEQ_VIEJA"
        if motivo != "OK" or orden is None:
            self._frenar()
            sesion, seq = (orden.sesion, orden.seq) if orden is not None else (0, 0)
            return self._respuesta(sesion, seq, motivo, ahora_ms)

        self.ultima_seq = orden.seq
        if orden.accion == "STOP":
            self._frenar()
        else:
            izq, der = lados(orden.velocidad, orden.giro)
            self.pwm_izq = a_pwm(izq, self.techo, self.minimo)
            self.pwm_der = a_pwm(der, self.techo, self.minimo)
            self.vence_ms = ahora_ms + min(orden.vigencia_ms, TOPE_VIGENCIA_MS)
        return self._respuesta(orden.sesion, orden.seq, "OK", ahora_ms)

    def tick(self, ahora_ms: float) -> Respuesta | None:
        """Paro automático: si la orden venció, frena y devuelve el aviso VENCIDA."""
        if self.vence_ms is not None and ahora_ms >= self.vence_ms:
            self._frenar()
            return self._respuesta(self.sesion, self.ultima_seq, "VENCIDA", ahora_ms)
        return None
