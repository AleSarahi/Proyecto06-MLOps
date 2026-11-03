"""Descarga de pesos (P5-07): verificación antes de mover, sin red y sin pisar archivos."""

from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

import pytest

from infer import descarga
from infer.config import RAIZ, cargar_config_detector

CONTENIDO = b"checkpoint de prueba, no un modelo"
SHA = hashlib.sha256(CONTENIDO).hexdigest()


def _fuente(tmp_path: Path, contenido: bytes = CONTENIDO) -> str:
    """URL file:// local: la misma ruta de urllib que la release, sin red."""
    origen = tmp_path / "fuente" / "yolo11n.pt"
    origen.parent.mkdir()
    origen.write_bytes(contenido)
    return origen.as_uri()


def _sin_temporales(carpeta: Path) -> bool:
    return not list(carpeta.glob("*.parcial"))


def test_descarga_a_carpeta_vacia_deja_solo_el_archivo_verificado(tmp_path: Path):
    destino = tmp_path / "modelo" / "descargas" / "yolo11n.pt"

    assert descarga.descargar_pesos(_fuente(tmp_path), destino, SHA, len(CONTENIDO)) is True

    assert destino.read_bytes() == CONTENIDO
    assert _sin_temporales(destino.parent)


def test_archivo_que_ya_coincide_no_se_vuelve_a_descargar(tmp_path: Path):
    destino = tmp_path / "yolo11n.pt"
    destino.write_bytes(CONTENIDO)
    sin_fuente = (tmp_path / "no-existe.pt").as_uri()

    assert descarga.descargar_pesos(sin_fuente, destino, SHA, len(CONTENIDO)) is False
    assert destino.read_bytes() == CONTENIDO


def test_archivo_distinto_en_destino_falla_sin_sobrescribirlo(tmp_path: Path):
    destino = tmp_path / "yolo11n.pt"
    destino.write_bytes(b"otro checkpoint")

    with pytest.raises(descarga.ErrorDescarga, match="ya existe y su SHA-256 no coincide"):
        descarga.descargar_pesos(_fuente(tmp_path), destino, SHA, len(CONTENIDO))
    assert destino.read_bytes() == b"otro checkpoint"


@pytest.mark.parametrize(
    ("contenido", "mensaje"),
    [
        (CONTENIDO + b"!", "pasa de"),
        (CONTENIDO[:-5], "se esperaban"),
        (CONTENIDO[:-1] + b"X", "SHA-256 no coincide"),
    ],
    ids=["mas-grande", "mas-chico", "mismo-tamano-otro-hash"],
)
def test_bytes_distintos_no_llegan_a_la_ruta_final(tmp_path: Path, contenido: bytes, mensaje):
    destino = tmp_path / "descargas" / "yolo11n.pt"

    with pytest.raises(descarga.ErrorDescarga, match=mensaje):
        descarga.descargar_pesos(_fuente(tmp_path, contenido), destino, SHA, len(CONTENIDO))
    assert not destino.exists()
    assert _sin_temporales(destino.parent)


def test_fuente_inalcanzable_no_deja_temporales(tmp_path: Path):
    destino = tmp_path / "descargas" / "yolo11n.pt"

    with pytest.raises(OSError):
        descarga.descargar_pesos((tmp_path / "no-existe.pt").as_uri(), destino, SHA, len(CONTENIDO))
    assert not destino.exists()
    assert _sin_temporales(destino.parent)


def test_cli_usa_ruta_y_hash_de_config_detector(monkeypatch, capsys):
    config = cargar_config_detector()
    llamadas = []

    def falsa(url, destino, sha256, tamano):
        llamadas.append((url, destino, sha256, tamano))
        return True

    monkeypatch.setattr(descarga, "descargar_pesos", falsa)

    assert descarga.main([]) == 0
    assert llamadas == [
        (descarga.URL_PESOS, config.weights_path, config.expected_model_sha256, 5_613_764)
    ]
    assert config.weights_path.parent.name == "descargas"
    assert "descargado" in capsys.readouterr().out


def test_cli_reporta_el_error_con_salida_2(monkeypatch, capsys):
    def falla(*_args):
        raise descarga.ErrorDescarga("SHA-256 no coincide")

    monkeypatch.setattr(descarga, "descargar_pesos", falla)

    assert descarga.main([]) == 2
    assert "infer.descarga: SHA-256 no coincide" in capsys.readouterr().err


def test_ficha_del_modelo_coincide_con_descarga_y_config():
    """El criterio de P5-07: lo que dice modelo/README.md es lo que baja y exige el código."""
    ficha = (RAIZ / "modelo" / "README.md").read_text(encoding="utf-8")
    config = cargar_config_detector()

    assert descarga.URL_PESOS in ficha
    assert f"{descarga.TAMANO_BYTES:,} B".replace(",", " ") in ficha
    assert config.expected_model_sha256 in ficha
    assert config.weights_path.relative_to(RAIZ).as_posix() in ficha
    assert "python -m infer.descarga" in ficha


def test_pesos_reales_coinciden_con_tamano_config_y_licencia():
    ruta = os.environ.get("P5_05_YOLO11N_PT")
    if not ruta:
        pytest.skip("definir P5_05_YOLO11N_PT para revisar los pesos reales")
    config = cargar_config_detector()
    pesos = Path(ruta)

    assert pesos.stat().st_size == descarga.TAMANO_BYTES
    assert descarga.sha256_de(pesos) == config.expected_model_sha256
    # Los metadatos que cita la ficha, leídos del pickle sin deserializarlo.
    with zipfile.ZipFile(pesos) as checkpoint:
        metadatos = checkpoint.read("yolo11n/data.pkl")
    for texto in (b"AGPL-3.0 License (https://ultralytics.com/license)", b"8.2.100", b"2024-09-25"):
        assert texto in metadatos
