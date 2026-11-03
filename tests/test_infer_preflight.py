"""Estados de energía comprobados sin consultar el equipo de CI."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from infer.preflight import (
    ErrorPreflight,
    consultar_preflight,
    exigir_preflight,
    guardar_y_exigir_preflight,
)


def _pmset(ps: str, lowpower: str = "0", *, fallo: bool = False):
    def ejecutar(*args):
        if fallo:
            raise OSError("consulta denegada")
        if args == ("pmset", "-g", "ps"):
            return subprocess.CompletedProcess(args, 0, f"Now drawing from '{ps}'\n", "")
        assert args == ("pmset", "-g")
        return subprocess.CompletedProcess(args, 0, f" lowpowermode         {lowpower}\n", "")

    return ejecutar


@pytest.mark.parametrize(
    ("fuente", "modo", "aprobado"),
    [
        ("AC Power", "0", True),
        ("Battery Power", "0", False),
        ("AC Power", "1", False),
        ("Other Power", "0", False),
        ("AC Power", "?", False),
    ],
)
def test_mac_ac_bateria_desconocido_y_ahorro(fuente, modo, aprobado) -> None:
    estado = consultar_preflight(sistema="darwin", ejecutar=_pmset(fuente, modo))
    assert estado["aprobado"] is aprobado
    assert "pmset" in estado["fuente"]
    if aprobado:
        assert estado["alimentacion"] == "ac" and estado["ahorro"] == "desactivado"
        exigir_preflight(estado)
    else:
        with pytest.raises(ErrorPreflight):
            exigir_preflight(estado)


def test_mac_error_de_consulta_bloquea() -> None:
    estado = consultar_preflight(sistema="darwin", ejecutar=_pmset("AC Power", fallo=True))
    assert not estado["aprobado"] and estado["alimentacion"] == "desconocida"
    with pytest.raises(ErrorPreflight, match="AC"):
        exigir_preflight(estado)


def test_mac_consulta_que_agota_plazo_bloquea() -> None:
    def agotar(*_args):
        raise subprocess.TimeoutExpired("pmset", 5)

    estado = consultar_preflight(sistema="darwin", ejecutar=agotar)
    assert not estado["aprobado"] and estado["alimentacion"] == "desconocida"


def _tasklist(*_args):
    return subprocess.CompletedProcess([], 0, '"python.exe","1","Console","1","10,000 K"\n', "")


@pytest.mark.parametrize(
    ("ac", "ahorro", "aprobado"),
    [(1, 0, True), (0, 0, False), (255, 0, False), (1, 1, False), (1, 255, False)],
)
def test_windows_ac_bateria_desconocido_y_ahorro(ac, ahorro, aprobado) -> None:
    estado = consultar_preflight(
        sistema="win32", consultar_windows=lambda: (ac, ahorro), ejecutar=_tasklist
    )
    assert estado["aprobado"] is aprobado
    assert "GetSystemPowerStatus" in estado["fuente"]
    if aprobado:
        exigir_preflight(estado)
    else:
        with pytest.raises(ErrorPreflight):
            exigir_preflight(estado)


def test_windows_error_de_consulta_bloquea() -> None:
    def fallar():
        raise OSError("GetSystemPowerStatus falló")

    estado = consultar_preflight(sistema="win32", consultar_windows=fallar, ejecutar=_tasklist)
    assert not estado["aprobado"] and estado["ahorro"] == "desconocido"
    with pytest.raises(ErrorPreflight):
        exigir_preflight(estado)


@pytest.mark.parametrize("nombre", ["OneDrive.exe", "Code.exe", "Code - Insiders.exe"])
def test_windows_procesos_bloqueantes(nombre) -> None:
    def procesos(*_args):
        return subprocess.CompletedProcess([], 0, f'"{nombre}","1","Console","1","10 K"\n', "")

    estado = consultar_preflight(
        sistema="win32", consultar_windows=lambda: (1, 0), ejecutar=procesos
    )
    assert not estado["aprobado"] and estado["procesos_bloqueantes"]


def test_windows_tasklist_no_verificable_bloquea() -> None:
    def fallar(*_args):
        return subprocess.CompletedProcess([], 1, "", "error")

    estado = consultar_preflight(sistema="win32", consultar_windows=lambda: (1, 0), ejecutar=fallar)
    assert not estado["aprobado"] and estado["procesos_bloqueantes"] is None


def test_preflight_fallido_se_guarda_y_bloquea(tmp_path) -> None:
    estado = consultar_preflight(sistema="darwin", ejecutar=_pmset("Battery Power"))
    ruta = tmp_path / "benchmark.preflight.json"
    with pytest.raises(ErrorPreflight, match="AC"):
        guardar_y_exigir_preflight(ruta, estado)
    assert json.loads(ruta.read_text(encoding="utf-8")) == estado
    with pytest.raises(FileExistsError):
        guardar_y_exigir_preflight(ruta, estado)


def test_script_no_inicia_predictor_si_preflight_falla(tmp_path, monkeypatch) -> None:
    ruta_script = Path(__file__).resolve().parents[1] / "resultados/p5-06-benchmark.py"
    spec = importlib.util.spec_from_file_location("p506_benchmark_preflight_test", ruta_script)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    pesos = tmp_path / "yolo11n.pt"
    with pesos.open("wb") as archivo:
        archivo.truncate(5_613_764)
    salida = tmp_path / "benchmark.json"
    estado = consultar_preflight(sistema="darwin", ejecutar=_pmset("Battery Power"))
    monkeypatch.setattr(modulo, "consultar_preflight", lambda: estado)
    monkeypatch.setattr(
        modulo,
        "_sha256",
        lambda ruta: modulo.MODELO_SHA256 if ruta == pesos else modulo.IMAGEN_SHA256,
    )
    monkeypatch.setattr(modulo, "DetectorJPEG", lambda *_args: pytest.fail("inició predictor"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark", "--weights", str(pesos), "--output", str(salida), "--responsable", "A1"],
    )
    with pytest.raises(ErrorPreflight):
        modulo.main()
    assert not salida.exists()
    contenido = (tmp_path / "benchmark.preflight.json").read_text(encoding="utf-8")
    assert "alimentación" in contenido
    assert json.loads(contenido) == estado
