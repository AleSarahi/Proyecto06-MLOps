"""Configuración del lazo en vivo (`config/vivo.yaml`) revisada, sin IP ni credenciales."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[2]
RUTA_CONFIG_VIVO = RAIZ / "config" / "vivo.yaml"
VARIABLE_IP = "P5_CARRO_IP"  # la misma que usa `python -m carro`

_CLAVES = (
    "model_sha256",
    "config_sha256",
    "puerto_stream",
    "ruta_stream",
    "puerto_carro",
    "espera_stream_s",
    "reconexion_s",
    "max_cuadro_bytes",
    "sequence_id",
    "confirmacion",
    "tecla_emergencia",
    "tecla_rearme",
    "tecla_salida",
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_HOST = re.compile(r"[A-Za-z0-9._-]{1,253}")


class ErrorConfigVivo(ValueError):
    """`vivo.yaml` falta, no se puede leer o tiene valores fuera de rango."""


@dataclass(frozen=True)
class ConfigVivo:
    model_sha256: str
    config_sha256: str
    puerto_stream: int
    ruta_stream: str
    puerto_carro: int
    espera_stream_s: float
    reconexion_s: float
    max_cuadro_bytes: int
    sequence_id: str
    confirmacion: str
    tecla_emergencia: str
    tecla_rearme: str
    tecla_salida: str


def _numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _entero(valor: Any, minimo: int, maximo: int) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and minimo <= valor <= maximo


def validar_config_vivo(datos: Any) -> ConfigVivo:
    """Revisa un diccionario ya leído; lanza `ErrorConfigVivo` con todos los problemas juntos."""
    if not isinstance(datos, dict):
        raise ErrorConfigVivo("vivo.yaml debe ser un mapa clave: valor")
    faltan = [c for c in _CLAVES if c not in datos]
    sobran = sorted(set(datos) - set(_CLAVES))
    if faltan or sobran:
        raise ErrorConfigVivo(f"vivo.yaml: faltan claves {faltan}; claves desconocidas {sobran}")

    errores: list[str] = []
    for clave in ("model_sha256", "config_sha256"):
        if not (isinstance(datos[clave], str) and _SHA256.fullmatch(datos[clave])):
            errores.append(f"{clave}: debe ser un SHA-256 en hexadecimal minúscula")
    for clave in ("puerto_stream", "puerto_carro"):
        if not _entero(datos[clave], 1, 65535):
            errores.append(f"{clave}: debe ser un puerto entre 1 y 65535")
    if not (isinstance(datos["ruta_stream"], str) and datos["ruta_stream"].startswith("/")):
        errores.append("ruta_stream: debe ser una ruta que empieza con /")
    for clave in ("espera_stream_s", "reconexion_s"):
        if not (_numero(datos[clave]) and 0 < datos[clave] <= 60):
            errores.append(f"{clave}: se requiere 0 < valor <= 60")
    if not _entero(datos["max_cuadro_bytes"], 1024, 16 * 1024 * 1024):
        errores.append("max_cuadro_bytes: debe ser un entero entre 1 KiB y 16 MiB")
    if not (isinstance(datos["sequence_id"], str) and _ID.fullmatch(datos["sequence_id"])):
        errores.append("sequence_id: debe cumplir [A-Za-z0-9._-]{1,64}")
    if not (isinstance(datos["confirmacion"], str) and len(datos["confirmacion"]) >= 4):
        errores.append("confirmacion: debe ser una palabra de al menos 4 caracteres")
    teclas = [datos[c] for c in ("tecla_emergencia", "tecla_rearme", "tecla_salida")]
    if not all(isinstance(t, str) and len(t) == 1 and t.strip() for t in teclas):
        errores.append("las teclas deben ser un solo carácter visible")
    elif len({t.lower() for t in teclas}) != len(teclas):
        errores.append("las teclas de emergencia, rearme y salida deben ser distintas")
    if errores:
        raise ErrorConfigVivo("; ".join(errores))

    return ConfigVivo(
        model_sha256=datos["model_sha256"],
        config_sha256=datos["config_sha256"],
        puerto_stream=datos["puerto_stream"],
        ruta_stream=datos["ruta_stream"],
        puerto_carro=datos["puerto_carro"],
        espera_stream_s=float(datos["espera_stream_s"]),
        reconexion_s=float(datos["reconexion_s"]),
        max_cuadro_bytes=datos["max_cuadro_bytes"],
        sequence_id=datos["sequence_id"],
        confirmacion=datos["confirmacion"],
        tecla_emergencia=datos["tecla_emergencia"].lower(),
        tecla_rearme=datos["tecla_rearme"].lower(),
        tecla_salida=datos["tecla_salida"].lower(),
    )


def cargar_config_vivo(ruta: Path | str = RUTA_CONFIG_VIVO) -> ConfigVivo:
    """Lee `config/vivo.yaml` y lo revisa."""
    ruta = Path(ruta)
    try:
        # La ruta la elige quien corre `python -m vivo --config-vivo` (solo lectura).
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))  # NOSONAR (S8707)
    except OSError as exc:
        raise ErrorConfigVivo(f"no se pudo leer {ruta}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ErrorConfigVivo(f"{ruta} no es YAML válido: {exc}") from exc
    return validar_config_vivo(datos)


def resolver_ip(argumento: str | None, entorno: dict[str, str] | None = None) -> str | None:
    """La IP del carro: el argumento manda sobre la variable de entorno. `None` si no hay.

    Solo acepta nombres o direcciones con caracteres de host: nada de `http://`, rutas ni
    credenciales (`usuario@ip`).
    """
    entorno = os.environ if entorno is None else entorno
    ip = argumento or entorno.get(VARIABLE_IP) or None
    if ip is None:
        return None
    if _HOST.fullmatch(ip) is None:
        raise ErrorConfigVivo("la IP del carro debe ser una dirección o nombre de host, sin ruta")
    return ip
