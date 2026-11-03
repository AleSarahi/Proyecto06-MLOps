"""Carga estricta de los dos plazos que A toma del YAML compartido."""

from __future__ import annotations

import math

import pytest
import yaml

from infer.config import cargar_config_detector
from infer.plazos import (
    RUTA_PLAZOS,
    ErrorPlazosInfer,
    PlazosInfer,
    cargar_plazos_infer,
    validar_plazos_infer,
)


def test_carga_plazos_compartidos_sin_cambiar_hash_detector():
    plazos = cargar_plazos_infer()
    assert (plazos.detector_timeout_ms, plazos.max_frame_age_ms) == (500, 500)
    assert cargar_config_detector().config_sha256 == (
        "6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08"
    )


def test_acepta_otros_plazos_de_b_sin_incluirlos_en_la_config_de_a():
    datos = yaml.safe_load(RUTA_PLAZOS.read_text(encoding="utf-8"))
    datos["watchdog_ms"] = 700
    assert validar_plazos_infer(datos) == cargar_plazos_infer()


def test_archivo_ausente(tmp_path):
    with pytest.raises(ErrorPlazosInfer, match="no se pudo leer"):
        cargar_plazos_infer(tmp_path / "ausente.yaml")


def test_ruta_predeterminada_funciona_desde_otro_directorio(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cargar_plazos_infer() == PlazosInfer(500, 500)


def test_yaml_invalido(tmp_path):
    ruta = tmp_path / "plazos.yaml"
    ruta.write_text("max_frame_age_ms: [500\n", encoding="utf-8")
    with pytest.raises(ErrorPlazosInfer, match="no se pudo leer"):
        cargar_plazos_infer(ruta)


@pytest.mark.parametrize("datos", [None, [], "texto"])
def test_documento_no_es_mapa(datos):
    with pytest.raises(ErrorPlazosInfer, match="mapa"):
        validar_plazos_infer(datos)


@pytest.mark.parametrize("clave", ["detector_timeout_ms", "max_frame_age_ms"])
def test_plazo_ausente(clave):
    datos = {"detector_timeout_ms": 500, "max_frame_age_ms": 500}
    del datos[clave]
    with pytest.raises(ErrorPlazosInfer, match=clave):
        validar_plazos_infer(datos)


@pytest.mark.parametrize("valor", [None, True, "500", [], 0, -1, math.nan, math.inf])
@pytest.mark.parametrize("clave", ["detector_timeout_ms", "max_frame_age_ms"])
def test_tipo_o_rango_invalido(clave, valor):
    datos = {"detector_timeout_ms": 500, "max_frame_age_ms": 500}
    datos[clave] = valor
    with pytest.raises(ErrorPlazosInfer, match=clave):
        validar_plazos_infer(datos)


def test_timeout_no_puede_superar_edad_maxima():
    with pytest.raises(ErrorPlazosInfer, match="detector_timeout_ms"):
        validar_plazos_infer({"detector_timeout_ms": 501, "max_frame_age_ms": 500})


def test_entero_demasiado_grande_produce_error_controlado():
    with pytest.raises(ErrorPlazosInfer, match="detector_timeout_ms"):
        validar_plazos_infer({"detector_timeout_ms": 10**400, "max_frame_age_ms": 10**400})


@pytest.mark.parametrize("valor", [PlazosInfer(0, 500), PlazosInfer(501, 500), object()])
def test_ejecutar_run_rechaza_plazos_inyectados_invalidos(tmp_path, valor):
    from infer.eventos import ErrorRunInfer, ejecutar_run

    with pytest.raises((ErrorPlazosInfer, ErrorRunInfer), match=r"plazos|detector_timeout_ms"):
        ejecutar_run(
            object(), tmp_path / "cuadro.jpg", tmp_path / "salida.jsonl", run_id="r", plazos=valor
        )
    assert not (tmp_path / "salida.jsonl").exists()
