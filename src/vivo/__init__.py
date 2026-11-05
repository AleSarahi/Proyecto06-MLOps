"""Lazo en vivo del carro (P5-21): ESP32-CAM → detector → política → carro. Ver docs/vivo.md."""

from .adaptador_wifi import AdaptadorWifi
from .config import ConfigVivo, cargar_config_vivo, resolver_ip
from .corrida import CorridaVivo
from .lazo import LazoVivo
from .lector import CuadroVivo, LectorStream, abrir_stream

__all__ = [
    "AdaptadorWifi",
    "ConfigVivo",
    "CorridaVivo",
    "CuadroVivo",
    "LazoVivo",
    "LectorStream",
    "abrir_stream",
    "cargar_config_vivo",
    "resolver_ip",
]
