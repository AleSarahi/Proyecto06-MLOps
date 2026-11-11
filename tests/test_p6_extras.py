"""Proyecto 6 · extras: secuencias de tramos, caída de la fuente, métricas X1-X5 y portal ampliado.

Igual que test_p6_integracion.py, el detector es un doble de prueba: estas pruebas cubren la lógica
(vigilancia, ventanas, métricas, rutas del portal). Los escenarios S1 y S2 se corrieron con YOLO11n
real (evidencias/p6/extras/).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from monitor import config as cfgmod
from monitor import fuente as fuente_mod
from monitor.almacen import leer_jsonl
from monitor.corrida import Corrida
from monitor.fuente import FuenteFrames, FuenteInterrumpida
from monitor.metricas_extra import histograma, psi
from monitor.portal import crear_app
from monitor.portal_extras import estado_vista
from monitor.video import DIR_FRAMES, leer_manifiesto
from monitor.vigilancia import Vigilante
from test_p6_integracion import DetectorDoble, _respaldo

VIG = cfgmod.cargar_vigilancia()


class Reloj:
    """Reloj falso: `sleep` avanza el tiempo en lugar de esperar."""

    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def dormir(self, s: float) -> None:
        self.t += s * 1000


# --- configuración y respaldo ------------------------------------------------------------------


def test_secuencia_de_tramos_en_fuentes():
    f = cfgmod.cargar_fuentes()
    s1 = f["segmentos"]["s1-transicion"]
    assert (s1["inicio_s"], s1["fin_s"]) == (0, 100)
    assert [t["video"] for t in s1["tramos"]] == ["dia", "noche", "noche2", "dia"]


def test_tramo_invalido(tmp_path):
    ruta = tmp_path / "f.yaml"
    ruta.write_text(
        "videos: {v: {}}\nsegmentos:\n  s: {tramos: [{video: v, inicio_s: 5, fin_s: 2}]}\n",
        encoding="utf-8",
    )
    with pytest.raises(cfgmod.ErrorConfig, match="inicio_s"):
        cfgmod.cargar_fuentes(ruta)


def test_respaldo_de_la_secuencia_es_continuo():
    cab, filas = leer_manifiesto(DIR_FRAMES / "s1-transicion")
    assert cab["secuencia"] and cab["fin_s"] == 100 and cab["frames"] == len(filas) == 100
    pos = [f["pos_ms"] for f in filas]
    assert pos == sorted(pos) and pos[0] == 0 and pos[-1] < 100_000
    # Cada frame conserva su video y su posición original.
    assert {f["video"] for f in filas} == {"dia", "noche", "noche2"}
    assert filas[30]["video"] == "noche" and filas[30]["pos_video_ms"] == 0


def test_vigilancia_valida_y_tiene_identidad():
    assert VIG["fuente_sin_senal"]["sin_frames_ms"] == 5000
    assert len(VIG["vigilancia_ref"]) == 64


# --- vigilante ---------------------------------------------------------------------------------


def _vig() -> Vigilante:
    return Vigilante(
        VIG,
        run_id="r",
        config_ref="c" * 64,
        model_ref="m" * 64,
        reloj_utc=lambda: "2026-01-01T00:00:00Z",
    )


def _ev(i: int) -> dict:
    return {"event_id": f"e{i}", "frame_id": f"f{i}", "video_pos_ms": i * 1000.0}


def test_vigilante_abre_con_latidos_y_cierra_tras_recuperacion():
    v = _vig()
    for i in range(3):
        assert v.frame(i * 1000.0, 0, _ev(i)) == []
    # Latidos de 3 a 7 s: el hueco desde el último frame (2 s) supera 5 s en el de 8 s.
    cambios = [c for t in range(3, 9) for c in v.latido(t * 1000.0, 0)]
    assert len(cambios) == 1 and cambios[0]["estado"] == "abierta"
    assert cambios[0]["detectada_ms"] == 8000 and cambios[0]["ultimo_frame"]["event_id"] == "e2"
    assert v.estado_fuente() == "sin_senal" and v.activas == 1
    assert v.frame(9000.0, 0, _ev(9)) == [] and v.estado_fuente() == "recuperando"
    # Un latido en medio reinicia la recuperación.
    v.latido(10000.0, 1)
    assert v.frame(11000.0, 1, _ev(11)) == [] and v.frame(12000.0, 1, _ev(12)) == []
    cerrada = v.frame(13000.0, 1, _ev(13))
    assert len(cerrada) == 1 and cerrada[0]["estado"] == "cerrada"
    assert cerrada[0]["recuperacion"]["event_ids"] == ["e11", "e12", "e13"]
    assert cerrada[0]["frames_perdidos"] == 1 and cerrada[0]["cerrada_por_ventana"] == 1
    assert v.activas == 0


def test_vigilante_deteccion_tardia_sin_latidos():
    v = _vig()
    v.frame(0.0, 0, _ev(0))
    abierta = v.frame(7000.0, 0, _ev(7))
    assert len(abierta) == 1 and abierta[0]["deteccion_tardia"] is True


def test_vigilante_no_alerta_con_inferencia_lenta():
    v = _vig()
    for i in range(10):
        assert v.frame(i * 4900.0, 0, _ev(i)) == []  # 4.9 s entre frames < 5 s


# --- corrida con caída de la fuente ------------------------------------------------------------


@pytest.fixture
def interrumpida(tmp_path, monkeypatch):
    reloj = Reloj()
    monkeypatch.setattr(fuente_mod.time, "sleep", reloj.dormir)
    guion = [[0.9, 0.8, 0.7]] * 20  # 30 frames de 1 s; 10 se pierden en el corte [10, 20) s
    _respaldo(tmp_path / "frames", 30, 1000.0)
    man = tmp_path / "frames" / "manifiesto.jsonl"
    lineas = man.read_text(encoding="utf-8").splitlines()
    cab = json.loads(lineas[0])
    cab["cabecera"]["cada_n_frames"] = 30
    man.write_text("\n".join([json.dumps(cab), *lineas[1:]]) + "\n", encoding="utf-8")
    cfg = cfgmod.cargar(velocidad=1.0)
    fuente = FuenteInterrumpida(
        FuenteFrames(tmp_path / "frames", velocidad=1.0, reloj_ms=reloj), [(10000, 20000)], 0
    )
    salida, db = tmp_path / "corrida", tmp_path / "m.sqlite"
    Corrida(
        cfg,
        fuente,
        DetectorDoble(guion, reloj),
        segmento="t",
        inicio_segmento_ms=0,
        salida=salida,
        db=db,
        referencia={"run_id": "ref", "proporcion_baja": 0.38},
        reloj_ms=reloj,
        run_id="corte",
        vigilancia=VIG,
    ).correr()
    return salida, db


def test_caida_de_fuente_alerta_y_recupera(interrumpida):
    salida, _ = interrumpida
    run = json.loads((salida / "run.json").read_text(encoding="utf-8"))
    assert run["conteos"]["fuente"]["descartes"]["sin_senal"] == 10
    assert run["conteos"]["fuente"]["conexion"] == {"intentos_fallidos": 10, "reconexiones": 1}
    assert run["fuente"]["inyeccion"]["cortes_s"] == [[10.0, 20.0]]
    ventanas = list(leer_jsonl(salida / "ventanas.jsonl"))
    assert [v["n_frames"] for v in ventanas] == [10, 0, 10]
    assert ventanas[1]["estado"] == "insuficiente"  # no es «normal» ni cierra nada
    assert [v["alertas_activas"] for v in ventanas] == [0, 1, 0]
    (alerta,) = list(leer_jsonl(salida / "alertas.jsonl"))
    assert alerta["schema"] == "p6.alerta_fuente.v1" and alerta["estado"] == "cerrada"
    assert alerta["frames_perdidos"] == 10 and alerta["cerrada_por_ventana"] == 2
    assert alerta["vigilancia_ref"] == VIG["vigilancia_ref"]
    assert alerta["ultimo_frame"]["event_id"] == "corte-t-f000009"
    m = json.loads((salida / "metricas.json").read_text(encoding="utf-8"))["metricas"]
    assert m["G7"]["corrida"]["valor"] == 1
    x = json.loads((salida / "metricas_extra.json").read_text(encoding="utf-8"))["metricas"]
    assert [p["valor"] for p in x["X5"]["por_ventana"]] == [1.0, 0.0, 1.0]
    assert x["X5"]["corrida"] == {"valor": 0.6667, "n": 30, "numerador": 20}
    assert [p["valor"] for p in x["X1"]["por_ventana"]] == [3.0, None, 3.0]


def test_portal_vivo_y_alerta_de_fuente(interrumpida):
    salida, db = interrumpida
    c = crear_app(db).test_client()
    d = c.get("/api/vivo?run=corte").get_json()
    assert d["vista"] == "terminada" and d["ultimo"]["frame_id"] == "t-f000029"
    assert c.get("/vivo").status_code == 200
    assert c.get("/vivo/corte/frame.jpg").data[:2] == b"\xff\xd8"
    assert c.get("/vivo?run=otra").status_code == 404
    assert c.get("/api/vivo?run=otra").status_code == 404
    (alerta,) = list(leer_jsonl(salida / "alertas.jsonl"))
    r = c.get(f"/alertas/{alerta['alert_id']}")
    assert r.status_code == 200 and b"corte-t-f000009" in r.data and b"vigilancia_ref" in r.data


def test_estados_de_la_vista_en_vivo():
    ahora = datetime.now(UTC)

    def v(estado="en_curso", fuente="con_senal", hace=0.0):
        t = (ahora - timedelta(seconds=hace)).isoformat().replace("+00:00", "Z")
        return {"estado": estado, "estado_fuente": fuente, "actualizado_utc": t}

    assert estado_vista(v())[0] == "en_vivo"
    assert estado_vista(v(fuente="sin_senal"))[0] == "sin_senal"
    assert estado_vista(v(fuente="recuperando"))[0] == "recuperando"
    assert estado_vista(v(hace=30))[0] == "sin_actualizaciones"
    assert estado_vista(v("terminada", hace=999))[0] == "terminada"
    assert estado_vista(v("fallida"))[0] == "fallida"


# --- métricas adicionales y portal ------------------------------------------------------------


def test_psi_y_histograma():
    assert histograma([0.0, 0.05, 0.1, 0.95, 1.0]) == [2, 1, 0, 0, 0, 0, 0, 0, 0, 2]
    h = [0, 3, 2, 1, 0, 0, 4, 5, 2, 0]
    assert psi(h, h) == 0
    assert psi(h, [0] * 10) is None
    assert psi([10, 0, 0, 0, 0, 0, 0, 0, 0, 0], h) > 1  # distribución muy distinta


def test_dashboard_y_exportacion(interrumpida):
    _, db = interrumpida
    c = crear_app(db).test_client()
    assert b"Elige una" in c.get("/dashboard").data
    r = c.get("/dashboard?run=corte&metrica=X5")
    assert r.status_code == 200 and b"<svg" in r.data and b"polyline" in r.data
    assert b"Sin datos" in c.get("/dashboard?run=corte&metrica=X1&desde=1&hasta=1").data
    assert c.get("/dashboard?run=corte&metrica=Z9").status_code == 400
    assert c.get("/dashboard?run=corte&desde=3&hasta=1").status_code == 400
    assert c.get("/dashboard?run=corte&desde=x").status_code == 400
    assert c.get("/dashboard?run=nada").status_code == 404
    r = c.get("/exportar/eventos.csv?run=corte")
    filas = r.data.decode().splitlines()
    assert r.status_code == 200 and filas[0].startswith("event_id,") and len(filas) == 21
    assert r.headers["X-Total-Eventos"] == "20"
    r = c.get("/exportar/eventos.csv?run=corte&zona=baja")
    assert r.data.decode().splitlines() == [r.data.decode().splitlines()[0]]  # solo cabecera
    j = c.get("/exportar/eventos.jsonl?run=corte&status=ok").data.decode().splitlines()
    assert len(j) == 20 and json.loads(j[0])["run_id"] == "corte"
    assert c.get("/exportar/eventos.csv?zona=xx").status_code == 400
    assert c.get("/exportar/eventos.xml").status_code == 404
    assert c.get("/exportar/eventos.csv?run=nada").status_code == 404
    assert c.get("/eventos?zona=xx").status_code == 400
