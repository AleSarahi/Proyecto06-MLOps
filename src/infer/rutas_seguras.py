"""Operaciones de archivo para salidas locales elegidas por el operador."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TextIO

from .pesos import _abrir_checkpoint


def directorio_evidencia(ruta: Path, *, raiz_restringida: Path | None = None) -> Path:
    """Crea un directorio nuevo; opcionalmente limita entradas no confiables a una raíz."""
    destino = Path(ruta)
    if raiz_restringida is not None:
        raiz = Path(raiz_restringida).resolve(strict=True)
        destino = destino.resolve(strict=False)
        if not destino.is_relative_to(raiz) or destino == raiz:
            raise ValueError("el directorio de salida está fuera de la raíz autorizada")
    destino.mkdir(parents=True, exist_ok=False)
    return destino


def abrir_exclusivo(ruta: Path, *, lectura: bool = False) -> TextIO:
    """Crea un archivo nuevo sin seguir un enlace simbólico final."""
    flags = os.O_CREAT | os.O_EXCL | (os.O_RDWR if lectura else os.O_WRONLY)
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(ruta, flags, 0o666)  # Misma política de permisos que Path.open.
    try:
        return os.fdopen(descriptor, "w+" if lectura else "w", encoding="utf-8", newline="\n")
    except BaseException:
        os.close(descriptor)
        raise


def verificar_checkpoint(
    ruta: Path, sha256_esperado: str, *, bytes_esperados: int | None = None
) -> None:
    """Comprueba tamaño y hash sobre el descriptor regular abierto de forma segura."""
    with _abrir_checkpoint(Path(ruta)) as archivo:
        if bytes_esperados is not None and os.fstat(archivo.fileno()).st_size != bytes_esperados:
            raise ValueError("tamaño del checkpoint distinto al aprobado")
        if hashlib.file_digest(archivo, "sha256").hexdigest() != sha256_esperado:
            raise ValueError("SHA-256 del checkpoint no coincide con la configuración")
