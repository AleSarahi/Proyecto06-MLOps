"""P5-21: `python -m vivo`: arranque seguro, modo seco por omisión y confirmación para motores."""

from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest
import yaml

import vivo.__main__ as cli
from test_carro_emisor import placa_falsa
from vivo.config import RUTA_CONFIG_VIVO
from vivo_comun import DetectorFalso, servidor_mjpeg


@pytest.fixture(autouse=True)
def _sin_ip_en_el_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("P5_CARRO_IP", raising=False)


def _config(tmp_path: Path, **cambios: object) -> Path:
    datos = yaml.safe_load(RUTA_CONFIG_VIVO.read_text(encoding="utf-8")) | cambios
    ruta = tmp_path / "vivo.yaml"
    ruta.write_text(yaml.safe_dump(datos), encoding="utf-8")
    return ruta


def _detector_falso(monkeypatch: pytest.MonkeyPatch, **cambios: str) -> DetectorFalso:
    from vivo.config import cargar_config_vivo

    vivo = cargar_config_vivo()
    detector = DetectorFalso()
    detector.model_sha256, detector.config_sha256 = vivo.model_sha256, vivo.config_sha256
    for campo, valor in cambios.items():
        setattr(detector, campo, valor)
    monkeypatch.setattr(cli, "DetectorEnVivo", lambda *_a, **_k: detector)
    return detector


def test_sin_ip_no_arranca(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--salida", str(tmp_path / "run")]) == 2
    assert "falta la IP" in capsys.readouterr().err


def test_la_ip_puede_venir_del_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("P5_CARRO_IP", "http://mala")
    assert cli.main(["--salida", str(tmp_path / "run")]) == 2
    assert "configuración inválida" in capsys.readouterr().err  # la validó: no es un host


def test_una_salida_con_archivos_no_se_pisa(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    (tmp_path / "viejo.txt").write_text("x", encoding="utf-8")
    assert cli.main(["--ip", "127.0.0.1", "--salida", str(tmp_path)]) == 2
    assert "carpeta nueva" in capsys.readouterr().err


def test_hashes_distintos_a_los_calificados_no_arrancan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config(tmp_path, model_sha256="1" * 64)
    codigo = cli.main(
        ["--ip", "127.0.0.1", "--salida", str(tmp_path / "run"), "--config-vivo", str(config)]
    )
    assert codigo == 2
    assert "no son los calificados" in capsys.readouterr().err
    assert not (tmp_path / "run").exists()


def test_enviar_sin_terminal_no_manda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    detector = _detector_falso(monkeypatch)
    codigo = cli.main(["--ip", "127.0.0.1", "--salida", str(tmp_path / "run"), "--enviar"])
    assert codigo == 3
    assert "terminal con teclado" in capsys.readouterr().err
    assert not detector.iniciado  # ni siquiera arrancó el detector


class TecladoFalso:
    disponible = True

    def __init__(self) -> None:
        pass

    def __enter__(self) -> TecladoFalso:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def tecla(self, espera_s: float) -> None:
        import time

        time.sleep(espera_s)


def test_enviar_sin_la_palabra_de_confirmacion_no_manda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detector = _detector_falso(monkeypatch)
    monkeypatch.setattr(cli, "Teclado", TecladoFalso)
    monkeypatch.setattr(builtins, "input", lambda _p="": "si")
    with placa_falsa() as (puerto, placa):
        config = _config(tmp_path, puerto_carro=puerto)
        codigo = cli.main(
            [
                "--ip",
                "127.0.0.1",
                "--salida",
                str(tmp_path / "run"),
                "--enviar",
                "--config-vivo",
                str(config),
            ]
        )
        assert codigo == 3 and placa.sesion == 0  # la placa no recibió ni el STOP inicial
    assert not detector.iniciado


def test_modo_seco_por_omision_no_abre_el_socket_del_carro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import carro.emisor

    def prohibido(*_a: object, **_k: object) -> None:
        raise AssertionError("el modo seco no debe crear el emisor")

    monkeypatch.setattr(carro.emisor, "Emisor", prohibido)
    detector = _detector_falso(monkeypatch)
    with servidor_mjpeg(0.05) as servidor:
        config = _config(tmp_path, puerto_stream=servidor.puerto)
        salida = tmp_path / "run"
        codigo = cli.main(
            [
                "--ip",
                "127.0.0.1",
                "--salida",
                str(salida),
                "--duracion-s",
                "0.8",
                "--config-vivo",
                str(config),
            ]
        )
    assert codigo == 0 and detector.iniciado and detector.cerrado
    resumen = json.loads((salida / "vivo.json").read_text(encoding="utf-8"))
    assert resumen["modo"] == "seco" and resumen["carro"]["enviadas"] == 0
    assert resumen["cuadros"]["atendidos"] > 3 and resumen["stream"]["conexiones"] == 1
    assert not (salida / "carro.jsonl").exists()
    # Los hashes de los archivos de configuración quedan en el resumen.
    assert set(resumen["config"]) == {"vivo.yaml", "plazos.yaml", "politica.yaml", "detector.json"}


def test_con_confirmacion_manda_y_cierra_con_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _detector_falso(monkeypatch)
    monkeypatch.setattr(cli, "Teclado", TecladoFalso)
    monkeypatch.setattr(builtins, "input", lambda _p="": "MOVER")
    with placa_falsa() as (puerto, placa), servidor_mjpeg(0.05) as servidor:
        config = _config(tmp_path, puerto_carro=puerto, puerto_stream=servidor.puerto)
        salida = tmp_path / "run"
        codigo = cli.main(
            [
                "--ip",
                "127.0.0.1",
                "--salida",
                str(salida),
                "--enviar",
                "--duracion-s",
                "0.8",
                "--config-vivo",
                str(config),
            ]
        )
        assert codigo == 0
        assert placa.sesion != 0 and placa.estado == "DETENIDO"
    resumen = json.loads((salida / "vivo.json").read_text(encoding="utf-8"))
    assert resumen["modo"] == "motores" and resumen["carro"]["enviadas"] > 3
    assert resumen["cuadros"]["atendidos"] > 3
    assert (salida / "carro.jsonl").is_file()
