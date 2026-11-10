"""Proyecto 6 · recorrido imagen -> evento -> captura -> ventana -> alerta -> portal (issue #24).

El detector es un DOBLE DE PRUEBA con scores fijos: prueba la lógica de la cadena y sus vínculos,
no el modelo. Las corridas de la referencia, C1 y C2 usan siempre YOLO11n real (tests de humo con
el modelo: test_p6_modelo.py).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from markupsafe import escape

from monitor import config as cfgmod
from monitor.almacen import Almacen, importar, leer_jsonl
from monitor.capturas import verificar
from monitor.corrida import Corrida
from monitor.fuente import FuenteFrames
from monitor.inferencia import Salida
from monitor.portal import crear_app


class DetectorDoble:
    model_ref = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"

    def __init__(self, guion, reloj):
        self.guion = list(guion)
        self.reloj = reloj

    def ficha(self):
        return {"doble_de_prueba": True}

    def inferir(self, imagen):
        scores = self.guion.pop(0)
        inicio = self.reloj()
        if scores == "error":
            return Salida(
                "error", [], inicio, self.reloj(), {"code": "detector_exception", "message": "x"}
            )
        dets = [
            {"class_id": 2, "class_name": "car", "score": s, "bbox": [1.0, 1.0, 20.0, 20.0]}
            for s in scores
        ]
        return Salida("ok" if dets else "sin_detecciones", dets, inicio, self.reloj(), None)


def _respaldo(carpeta: Path, n: int, paso_ms: float) -> None:
    carpeta.mkdir(parents=True)
    filas = []
    for i in range(n):
        img = np.full((48, 64, 3), (i * 20) % 255, dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", img)
        assert ok
        nombre = f"t-f{i:06d}.jpg"
        (carpeta / nombre).write_bytes(buf.tobytes())
        filas.append(
            {
                "frame_id": f"t-f{i:06d}",
                "archivo": nombre,
                "sha256": hashlib.sha256(buf.tobytes()).hexdigest(),
                "indice_video": i,
                "pos_ms": i * paso_ms,
                "width": 64,
                "height": 48,
            }
        )
    cab = {
        "segmento": "t",
        "fps_video": 30.0,
        "inicio_s": 0,
        "fin_s": n * paso_ms / 1000,
        "url": "https://example.invalid",
        "licencia": "CC BY",
        "canal": "prueba",
    }
    with (carpeta / "manifiesto.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps({"cabecera": cab}) + "\n")
        for fila in filas:
            f.write(json.dumps(fila) + "\n")


@pytest.fixture
def corrida(tmp_path):
    # 3 ventanas de 10 s con 1 frame/s: normal, baja confianza, y una con un error y un frame
    # sin detecciones (insuficiente).
    normal = [[0.9, 0.8, 0.7, 0.2]] * 10  # 4 candidatas, 1 baja
    baja = [[0.25, 0.2, 0.15, 0.5]] * 10  # 3 de 4 bajas -> 0.75
    rara = ["error", [], *([[0.9]] * 8)]  # 8 candidatas < 20 -> insuficiente
    guion = normal + baja + rara
    _respaldo(tmp_path / "frames", len(guion), 1000.0)
    cfg = cfgmod.cargar(velocidad=0)
    reloj = iter(range(10**6))
    r = lambda: float(next(reloj))  # noqa: E731
    fuente = FuenteFrames(tmp_path / "frames", velocidad=0, reloj_ms=r)
    salida, db = tmp_path / "corrida", tmp_path / "m.sqlite"
    Corrida(
        cfg,
        fuente,
        DetectorDoble(guion, r),
        segmento="t",
        inicio_segmento_ms=0,
        salida=salida,
        db=db,
        referencia={"run_id": "ref", "proporcion_baja": 0.38},
        reloj_ms=r,
        run_id="prueba",
    ).correr()
    return salida, db


def test_cadena_completa(corrida):
    salida, _ = corrida
    eventos = {e["event_id"]: e for e in leer_jsonl(salida / "eventos.jsonl")}
    assert len(eventos) == 30
    assert {e["status"] for e in eventos.values()} == {"ok", "sin_detecciones", "error"}
    ventanas = list(leer_jsonl(salida / "ventanas.jsonl"))
    assert [v["estado"] for v in ventanas] == ["suficiente", "suficiente", "insuficiente"]
    alertas = list(leer_jsonl(salida / "alertas.jsonl"))
    baja = [a for a in alertas if a["rule_id"] == "baja-confianza-v1"]
    assert len(baja) == 1 and baja[0]["estado"] == "abierta"  # la ventana insuficiente no la cierra
    assert all(i in eventos for i in baja[0]["event_ids"])
    # Los eventos de la ventana de la alerta tienen imagen capturada por la política "alerta".
    for i in baja[0]["event_ids"]:
        assert eventos[i]["image_ref"] == f"capturas/{i}.jpg"
    rv = verificar(salida)
    assert rv["problemas"] == [] and rv["vinculadas_validas"] == rv["capturas"] > 0
    m = json.loads((salida / "metricas.json").read_text(encoding="utf-8"))["metricas"]
    assert set(m) == {f"G{i}" for i in range(1, 8)}
    assert m["G4"]["por_ventana"][1]["valor"] == 0.75
    assert m["G5"]["corrida"]["valor"] == 1.0
    assert m["G7"]["por_ventana"][1]["valor"] == 1


def test_imagen_rota_se_detecta(corrida):
    salida, _ = corrida
    cap = next(leer_jsonl(salida / "capturas.jsonl"))
    (salida / cap["ruta"]).write_bytes(b"otra cosa")
    assert any("SHA-256" in p for p in verificar(salida)["problemas"])


def test_portal_sigue_la_alerta_hasta_la_imagen(corrida):
    salida, db = corrida
    c = crear_app(db).test_client()
    alerta = next(a for a in leer_jsonl(salida / "alertas.jsonl"))
    r = c.get(f"/alertas/{alerta['alert_id']}")
    assert r.status_code == 200 and str(escape(alerta["motivo"])).encode() in r.data
    ev = alerta["event_ids"][0]
    r = c.get(f"/eventos/{ev}")
    assert r.status_code == 200 and alerta["alert_id"].encode() in r.data
    assert c.get(f"/imagenes/img-{ev}").status_code == 200
    assert c.get("/alertas").status_code == 200
    assert c.get("/eventos?status=error").status_code == 200
    assert c.get("/eventos/no-existe").status_code == 404


def test_reimportar_desde_la_exportacion_da_lo_mismo(corrida, tmp_path):
    salida, db = corrida
    otra = tmp_path / "otra.sqlite"
    with Almacen(otra) as alm:
        importar(alm, salida)
    with Almacen(db, solo_lectura=True) as a, Almacen(otra, solo_lectura=True) as b:
        assert a.eventos(limite=1000) == b.eventos(limite=1000)
        assert a.alertas() == b.alertas()


def test_duplicado_no_se_guarda_dos_veces(corrida):
    salida, db = corrida
    ev = next(leer_jsonl(salida / "eventos.jsonl"))
    with Almacen(db) as alm:
        assert alm.guardar_evento(ev) is False
        assert alm.duplicados == 1


def test_portal_vacio_y_sin_base(tmp_path):
    vacia = tmp_path / "vacia.sqlite"
    Almacen(vacia).cerrar()
    c = crear_app(vacia).test_client()
    for url in ("/eventos", "/alertas", "/corridas"):
        r = c.get(url)
        assert r.status_code == 200 and b"vacio" in r.data
    r = crear_app(tmp_path / "no-existe.sqlite").test_client().get("/eventos")
    assert r.status_code == 503 and b"importar" in r.data
