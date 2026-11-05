"""Único punto del simulador que conoce el protocolo PC → carro (docs/carro/protocolo.md).

El resto de `simulador` importa de aquí y no de `carro.protocolo`. Si el protocolo sube de
versión, solo se toca este archivo. Las reglas (sesión, secuencia, rangos, paro automático,
techo de PWM) son las de `Placa`, el modelo de referencia del firmware: el simulador no las
repite, las envuelve en un socket.
"""

from __future__ import annotations

from carro.protocolo import (
    MINIMO_PWM,
    PUERTO,
    TECHO_PWM,
    TOPE_VIGENCIA_MS,
    Placa,
    Respuesta,
    codificar_respuesta,
)

__all__ = [
    "MINIMO_PWM",
    "PUERTO",
    "TECHO_PWM",
    "TOPE_VIGENCIA_MS",
    "Placa",
    "Respuesta",
    "codificar_respuesta",
    "frenar",
]


def frenar(placa: Placa) -> None:
    """Apaga los motores como al perder el WiFi (`WiFi.status() != WL_CONNECTED`).

    El protocolo pide frenar de inmediato en ese caso, pero `Placa` no lo modela porque no
    tiene red. Es la única regla del firmware que el simulador agrega por fuera.
    """
    placa._frenar()
