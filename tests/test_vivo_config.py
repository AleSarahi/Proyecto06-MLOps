"""P5-21: `config/vivo.yaml`, la IP del carro y los hashes calificados."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml

from infer.config import RUTA_CONFIG_DETECTOR, cargar_config_detector
from vivo.config import (
    RAIZ,
    RUTA_CONFIG_VIVO,
    ErrorConfigVivo,
    cargar_config_vivo,
    resolver_ip,
    validar_config_vivo,
)

BASE = yaml.safe_load(RUTA_CONFIG_VIVO.read_text(encoding="utf-8"))


def _con(**cambios: object) -> dict:
    datos = copy.deepcopy(BASE)
    datos.update(cambios)
    return datos


def test_vivo_yaml_carga_y_trae_los_hashes_calificados() -> None:
    vivo = cargar_config_vivo()
    assert vivo.model_sha256.startswith("0ebbc80d")
    assert vivo.config_sha256.startswith("6428a259")
    detector = cargar_config_detector(RUTA_CONFIG_DETECTOR)
    assert (vivo.model_sha256, vivo.config_sha256) == (
        detector.expected_model_sha256,
        detector.config_sha256,
    )


def test_vivo_yaml_no_lleva_ip_ni_credenciales() -> None:
    texto = RUTA_CONFIG_VIVO.read_text(encoding="utf-8")
    sin_comentarios = "\n".join(
        linea for linea in texto.splitlines() if not linea.lstrip().startswith("#")
    )
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", sin_comentarios)
    assert not re.search(r"(?i)pass|token|secret|clave|usuario|@", sin_comentarios)


def test_nada_de_vivo_lleva_una_ip_escrita() -> None:
    patron = re.compile(r"\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")
    for ruta in [*(RAIZ / "src" / "vivo").glob("*.py"), RAIZ / "src" / "infer" / "cuadro.py"]:
        assert not patron.search(ruta.read_text(encoding="utf-8")), ruta


def test_los_plazos_no_se_repiten_en_vivo_yaml() -> None:
    assert not {"watchdog_ms", "validez_orden_ms", "paso_reloj_ms", "max_frame_age_ms"} & set(BASE)


def test_el_modo_virtual_calificado_no_cambia() -> None:
    """Mandar a motores es una bandera de `python -m vivo`, no un cambio de ejecucion.yaml."""
    ejecucion = yaml.safe_load((RAIZ / "config" / "ejecucion.yaml").read_text(encoding="utf-8"))
    assert ejecucion["adaptador"] == "virtual" and ejecucion["motores_conectados"] is False


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("model_sha256", "0ebbc80d"),
        ("config_sha256", "G" * 64),
        ("puerto_stream", 0),
        ("puerto_carro", 70000),
        ("puerto_stream", True),
        ("ruta_stream", "stream"),
        ("espera_stream_s", 0),
        ("reconexion_s", 120),
        ("max_cuadro_bytes", 10),
        ("sequence_id", "con espacio"),
        ("confirmacion", "ok"),
        ("tecla_emergencia", "ee"),
        ("tecla_rearme", "e"),  # repite la de emergencia
    ],
)
def test_valores_fuera_de_rango_se_rechazan(campo: str, valor: object) -> None:
    with pytest.raises(ErrorConfigVivo, match=campo.split("_")[0]):
        validar_config_vivo(_con(**{campo: valor}))


def test_faltan_y_sobran_claves() -> None:
    datos = copy.deepcopy(BASE)
    del datos["puerto_carro"]
    datos["ip"] = "192.0.2.1"
    with pytest.raises(ErrorConfigVivo, match=r"faltan claves.*puerto_carro.*desconocidas.*ip"):
        validar_config_vivo(datos)


def test_no_es_un_mapa_o_no_existe(tmp_path: Path) -> None:
    with pytest.raises(ErrorConfigVivo, match="mapa"):
        validar_config_vivo([1, 2])
    with pytest.raises(ErrorConfigVivo, match="no se pudo leer"):
        cargar_config_vivo(tmp_path / "no_existe.yaml")
    mal = tmp_path / "mal.yaml"
    mal.write_text("a: [", encoding="utf-8")
    with pytest.raises(ErrorConfigVivo, match="YAML"):
        cargar_config_vivo(mal)


def test_la_ip_viene_del_argumento_o_del_entorno() -> None:
    assert resolver_ip("host-uno", {"P5_CARRO_IP": "host-dos"}) == "host-uno"
    assert resolver_ip(None, {"P5_CARRO_IP": "host-dos"}) == "host-dos"
    assert resolver_ip(None, {}) is None
    assert resolver_ip("", {}) is None


@pytest.mark.parametrize("ip", ["http://host", "usuario@host", "host/ruta", "host:81", "a b"])
def test_la_ip_no_acepta_url_ni_credenciales(ip: str) -> None:
    with pytest.raises(ErrorConfigVivo, match="IP"):
        resolver_ip(ip, {})
