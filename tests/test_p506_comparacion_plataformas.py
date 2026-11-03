"""Política de paridad local y trazabilidad de P5-05 sin tolerancias nuevas."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parents[1]
REFERENCIA = RAIZ / "resultados/p5-05-aceptacion-2h-a.jsonl"


def _modulo(nombre: str, archivo: str):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / "resultados" / archivo)
    assert spec is not None
    assert spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


comparar_plataformas = _modulo("p506_comparacion", "p5_06_comparacion.py").comparar_plataformas


def _evento(clases=(41, 39)) -> dict:
    return {
        "frame_id": "taza",
        "status": "ok",
        "image_width": 640,
        "image_height": 480,
        "detections": [
            {"class_id": clase, "confidence": 0.8 - i * 0.1, "bbox": [i, 2, 20, 30]}
            for i, clase in enumerate(clases)
        ],
    }


@pytest.mark.parametrize("delta", [0.000001, 0.3])
def test_diferencia_numerica_mac_windows_no_se_acepta_automaticamente(delta):
    referencia = _evento()
    actual = deepcopy(referencia)
    actual["detections"][0]["confidence"] += delta
    actual["detections"][1]["bbox"][2] += delta
    comparacion = comparar_plataformas(actual, referencia)
    assert comparacion["clasificacion"] == "diferencia_numerica_pendiente"
    assert comparacion["problemas_estructurales"] == []
    assert comparacion["por_deteccion"][0]["actual"] == actual["detections"][0]
    assert comparacion["por_deteccion"][0]["referencia"] == referencia["detections"][0]
    assert comparacion["max_abs_delta_confidence"] == pytest.approx(delta)
    assert comparacion["max_abs_delta_bbox_px"] == pytest.approx(delta)


@pytest.mark.parametrize(
    ("actual", "campo"),
    [(_evento((41,)), "cantidad"), (_evento((41, 40)), "clase"), (_evento((39, 41)), "orden")],
)
def test_cambio_estructural_requiere_investigacion(actual, campo):
    comparacion = comparar_plataformas(actual, _evento())
    assert comparacion["clasificacion"] == "discrepancia_estructural"
    assert campo in {p["campo"] for p in comparacion["problemas_estructurales"]}


def test_cambio_de_orden_con_clase_repetida_se_registra():
    referencia = _evento((41, 41))
    actual = deepcopy(referencia)
    actual["detections"].reverse()
    comparacion = comparar_plataformas(actual, referencia)
    assert comparacion["clasificacion"] == "discrepancia_estructural"
    assert "orden" in {p["campo"] for p in comparacion["problemas_estructurales"]}


def test_comparacion_local_exige_confianza_y_bbox_exactos():
    modulo = _modulo("p506_benchmark_comparacion", "p5-06-benchmark.py")
    control = _evento()
    supervisado = deepcopy(control)
    supervisado["detections"][0]["confidence"] += 0.000001
    par = modulo._comparar_par(control, supervisado, _evento(), 1)
    assert par["diferencias_locales"] == ["detections"]
    with pytest.raises(RuntimeError, match="rutas locales"):
        modulo._exigir_paridad(par)
    supervisado = deepcopy(control)
    supervisado["detections"][0]["bbox"][0] += 0.000001
    assert modulo._comparar_par(control, supervisado, _evento(), 1)["diferencias_locales"]


@pytest.mark.parametrize("delta", [0.000001, 0.3])
def test_benchmark_conserva_par_local_ante_diferencia_numerica_mac(delta):
    modulo = _modulo("p506_benchmark_numerica", "p5-06-benchmark.py")
    local = _evento()
    local["detections"][0]["confidence"] += delta
    par = modulo._comparar_par(local, deepcopy(local), _evento(), 11)
    assert par["diferencias_locales"] == []
    assert par["requiere_revision"] is True
    assert par["comparaciones_p5_05"]["control"]["clasificacion"] == "diferencia_numerica_pendiente"
    modulo._exigir_paridad(par)


def test_referencia_historica_permanece_integra():
    antes = REFERENCIA.read_bytes()
    assert hashlib.sha256(antes).hexdigest() == (
        "01c62b38cdd45f900d77938bdd7003fe55e028087a17f6bfc0a62ef34fd75ab1"
    )
    evento = next(json.loads(linea) for linea in antes.splitlines() if b'"ensayo-0012"' in linea)
    assert evento["frame_id"] == "ensayo-0012"
    assert evento["detections"][0]["class_id"] == 41
    assert len(evento["detections"]) == 1
    comparar_plataformas(evento, evento)
    assert hashlib.sha256(REFERENCIA.read_bytes()).hexdigest() == hashlib.sha256(antes).hexdigest()


def test_benchmark_guarda_muestra_y_discrepancia_antes_de_detenerse(tmp_path, monkeypatch):
    modulo = _modulo("p506_benchmark_parcial", "p5-06-benchmark.py")
    referencia = next(
        json.loads(linea)
        for linea in REFERENCIA.read_text().splitlines()
        if '"ensayo-0012"' in linea
    )
    local = deepcopy(referencia)
    local["frame_id"] = "objeto_taza_centro_cerca"
    local["detections"][0]["class_id"] = 40
    pesos = tmp_path / "yolo11n.pt"
    with pesos.open("wb") as archivo:
        archivo.truncate(5_613_764)
    salida = tmp_path / "benchmark.json"
    monkeypatch.setattr(
        modulo,
        "_sha256",
        lambda ruta: modulo.MODELO_SHA256 if ruta == pesos else modulo.IMAGEN_SHA256,
    )
    monkeypatch.setattr(modulo, "consultar_preflight", lambda: {"alimentacion": "AC"})
    monkeypatch.setattr(
        modulo,
        "guardar_y_exigir_preflight",
        lambda ruta, estado: ruta.write_text(json.dumps(estado)),
    )
    monkeypatch.setattr(modulo, "exigir_preflight", lambda _estado: None)
    monkeypatch.setattr(modulo, "cargar_pesos", lambda *_: object())
    monkeypatch.setattr(modulo, "DetectorJPEG", lambda *_: SimpleNamespace(calentar=lambda: None))
    monkeypatch.setattr(modulo.torch, "get_num_threads", lambda: 2)
    monkeypatch.setattr(
        modulo,
        "PredictorSupervisado",
        lambda *_: SimpleNamespace(iniciar=lambda: None, close=lambda: None),
    )
    monkeypatch.setattr(modulo, "medir_control", lambda *_args, **_kwargs: (12.0, deepcopy(local)))
    monkeypatch.setattr(
        modulo, "medir_supervisado", lambda *_args, **_kwargs: (13.0, deepcopy(local))
    )
    monkeypatch.setattr(modulo, "_validar_muestra", lambda _evento: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark", "--weights", str(pesos), "--output", str(salida), "--responsable", "test"],
    )
    with pytest.raises(RuntimeError, match="discrepancia estructural"):
        modulo.main()
    parcial = json.loads(salida.read_text())
    assert parcial["reloj"]["nombre"] == "perf_counter"
    assert parcial["reloj"]["resolucion_reportada_s"] > 0
    assert parcial["fase"] == "latencia_supervisado"
    assert parcial["indice"] == 1
    assert parcial["calentamientos_excluidos_ms"] == {"control": [12.0], "supervisado": [13.0]}
    assert (
        parcial["comparaciones"][0]["comparaciones_p5_05"]["control"]["clasificacion"]
        == "discrepancia_estructural"
    )
    assert parcial["evento_actual"]["evento"] == local
