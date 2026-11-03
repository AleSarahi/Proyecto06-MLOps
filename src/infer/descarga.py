"""Descarga y verificación de los pesos de YOLO11n (P5-07): ``python -m infer.descarga``.

Un solo comando, con red y una sola vez, deja ``yolo11n.pt`` donde lo espera
``config/detector.json`` (``modelo/descargas/``, fuera de Git) y comprueba su
tamaño y su SHA-256 antes de darlo por bueno. Si el archivo ya está y coincide, no
vuelve a descargar. La ruta final nunca recibe bytes sin verificar: se escriben en
un temporal de la misma carpeta y se mueven solo si coinciden.

La fuente no se puede cambiar: solo vale la release oficial. Sin acceso a ella, el
archivo se copia a mano a ``modelo/descargas/`` y el comando lo verifica sin red.
``--destino`` es una ruta que elige quien corre el comando; las lecturas y escrituras
con ella llevan ``NOSONAR (S8707)``, como en ``python -m bench``.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from .config import RUTA_CONFIG_DETECTOR, cargar_config_detector

# Release oficial que usaron P5-04 y P5-05 (modelo/DECISION.md). El SHA-256 no se
# repite aquí: sale de config/detector.json, que ya lo fija.
URL_PESOS = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"
TAMANO_BYTES = 5_613_764

_BLOQUE = 1024 * 1024
_TIEMPO_LIMITE_S = 60


class ErrorDescarga(RuntimeError):
    """La descarga falló o los bytes no son los del checkpoint de P5-04."""


def sha256_de(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:  # NOSONAR (S8707)
        for bloque in iter(lambda: archivo.read(_BLOQUE), b""):
            digest.update(bloque)
    return digest.hexdigest()


def descargar_pesos(url: str, destino: Path, sha256: str, tamano: int) -> bool:
    """Deja en ``destino`` el archivo con ese tamaño y SHA-256; True si lo descargó.

    Un ``destino`` que ya existe se verifica y no se toca: si es otro archivo es un
    error, no algo que se sobrescriba en silencio.
    """
    if destino.exists():  # NOSONAR (S8707)
        actual = sha256_de(destino)
        if actual != sha256:
            raise ErrorDescarga(
                f"{destino} ya existe y su SHA-256 no coincide (esperado {sha256}, "
                f"obtenido {actual}); bórralo y vuelve a correr el comando"
            )
        return False

    carpeta = destino.parent
    carpeta.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
    descriptor, nombre = tempfile.mkstemp(  # NOSONAR (S8707)
        prefix=".yolo11n-", suffix=".parcial", dir=carpeta
    )
    temporal = Path(nombre)
    try:
        digest = hashlib.sha256()
        leidos = 0
        with (
            os.fdopen(descriptor, "wb") as salida,
            urllib.request.urlopen(url, timeout=_TIEMPO_LIMITE_S) as respuesta,
        ):
            for bloque in iter(lambda: respuesta.read(_BLOQUE), b""):
                leidos += len(bloque)
                if leidos > tamano:
                    raise ErrorDescarga(f"la descarga pasa de {tamano} B: no es el checkpoint")
                digest.update(bloque)
                salida.write(bloque)
            salida.flush()
            os.fsync(salida.fileno())
        if leidos != tamano:
            raise ErrorDescarga(f"se descargaron {leidos} B y se esperaban {tamano} B")
        actual = digest.hexdigest()
        if actual != sha256:
            raise ErrorDescarga(f"SHA-256 no coincide: esperado {sha256}, obtenido {actual}")
        os.replace(temporal, destino)  # NOSONAR (S8707)
    except BaseException:
        temporal.unlink(missing_ok=True)  # NOSONAR (S8707)
        raise
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m infer.descarga", description=__doc__)
    parser.add_argument("--config", type=Path, default=RUTA_CONFIG_DETECTOR)
    parser.add_argument(
        "--destino", type=Path, help="ruta del .pt (por omisión, artifacts.weights_path)"
    )
    args = parser.parse_args(argv)
    try:
        config = cargar_config_detector(args.config)
        destino = args.destino or config.weights_path
        descargo = descargar_pesos(URL_PESOS, destino, config.expected_model_sha256, TAMANO_BYTES)
    except Exception as exc:
        print(f"infer.descarga: {exc}", file=sys.stderr)
        return 2
    estado = "descargado" if descargo else "ya estaba"
    print(f"{destino}: {estado}, {TAMANO_BYTES} B, SHA-256 {config.expected_model_sha256} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
