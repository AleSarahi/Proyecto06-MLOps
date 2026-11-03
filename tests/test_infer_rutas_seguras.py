"""Rutas locales de P5-06: checkpoint verificado y salidas nuevas."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from infer.rutas_seguras import abrir_exclusivo, directorio_evidencia, verificar_checkpoint


def test_checkpoint_regular_con_hash_y_tamano(tmp_path: Path) -> None:
    pesos = tmp_path / "modelo.pt"
    contenido = b"pesos de prueba"
    pesos.write_bytes(contenido)
    verificar_checkpoint(
        pesos, hashlib.sha256(contenido).hexdigest(), bytes_esperados=len(contenido)
    )


@pytest.mark.parametrize("caso", ["ausente", "directorio", "tamano", "hash"])
def test_checkpoint_invalido(tmp_path: Path, caso: str) -> None:
    pesos = tmp_path / "modelo.pt"
    if caso == "directorio":
        pesos.mkdir()
    elif caso != "ausente":
        pesos.write_bytes(b"contenido")
    with pytest.raises((OSError, ValueError, RuntimeError)):
        verificar_checkpoint(pesos, "0" * 64, bytes_esperados=1 if caso == "tamano" else None)


def test_checkpoint_symlink_rechazado(tmp_path: Path) -> None:
    real = tmp_path / "real.pt"
    real.write_bytes(b"contenido")
    enlace = tmp_path / "enlace.pt"
    try:
        enlace.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("el sistema no permite crear enlaces simbólicos")
    with pytest.raises(RuntimeError, match="enlace simbólico"):
        verificar_checkpoint(enlace, hashlib.sha256(b"contenido").hexdigest())


@pytest.mark.skipif(os.name == "nt" or not hasattr(os, "mkfifo"), reason="FIFO POSIX")
def test_checkpoint_fifo_rechazado_sin_bloqueo(tmp_path: Path) -> None:
    fifo = tmp_path / "tuberia.pt"
    os.mkfifo(fifo)
    with pytest.raises(RuntimeError, match="archivo regular"):
        verificar_checkpoint(fifo, "0" * 64)


def test_directorio_evidencia_externo_y_sin_sobrescritura(tmp_path: Path) -> None:
    externo = tmp_path / "fuera-del-repositorio" / "evidencia"
    assert directorio_evidencia(externo) == externo
    with pytest.raises(FileExistsError):
        directorio_evidencia(externo)


def test_directorio_evidencia_con_raiz_restringida(tmp_path: Path) -> None:
    raiz = tmp_path / "permitida"
    raiz.mkdir()
    destino = raiz / "run"
    assert directorio_evidencia(destino, raiz_restringida=raiz) == destino
    with pytest.raises(ValueError, match="fuera de la raíz"):
        directorio_evidencia(tmp_path / "otra" / "run", raiz_restringida=raiz)
    with pytest.raises(ValueError, match="fuera de la raíz"):
        directorio_evidencia(raiz / ".." / "escape", raiz_restringida=raiz)


def test_directorio_evidencia_rechaza_symlink_fuera_de_raiz(tmp_path: Path) -> None:
    raiz = tmp_path / "permitida"
    raiz.mkdir()
    enlace = raiz / "enlace"
    try:
        enlace.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("el sistema no permite crear enlaces simbólicos")
    with pytest.raises(ValueError, match="fuera de la raíz"):
        directorio_evidencia(enlace / "run", raiz_restringida=raiz)


def test_archivo_exclusivo_no_sobrescribe_ni_sigue_symlink(tmp_path: Path) -> None:
    archivo = tmp_path / "evento.jsonl"
    with abrir_exclusivo(archivo, lectura=True) as salida:
        salida.write('{"status":"ok"}\n')
        salida.flush()
        salida.buffer.seek(0)
        assert (
            hashlib.file_digest(salida.buffer, "sha256").hexdigest()
            == hashlib.sha256(archivo.read_bytes()).hexdigest()
        )
    with pytest.raises(FileExistsError):
        abrir_exclusivo(archivo)
    assert archivo.read_text() == '{"status":"ok"}\n'
    enlace = tmp_path / "enlace.jsonl"
    try:
        enlace.symlink_to(archivo)
    except (OSError, NotImplementedError):
        pytest.skip("el sistema no permite crear enlaces simbólicos")
    with pytest.raises(FileExistsError):
        abrir_exclusivo(enlace)
