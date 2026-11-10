"""Proyecto 6: configuración, zonas, contratos, reglas, métricas y respaldo (issues #3, #4, #11,
#13, #16, #18 y #34). No necesitan los pesos del modelo."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from monitor import config as cfgmod
from monitor import contratos, zonas
from monitor.config import ErrorConfig
from monitor.metricas import percentil_rango_cercano
from monitor.reglas import EvaluadorReglas, resumen_ventana
from monitor.video import DIR_FRAMES, verificar_respaldo

RAIZ = Path(__file__).resolve().parents[1]
EJEMPLOS = RAIZ / "config" / "p6" / "contratos" / "ejemplos"


def _datos():
    return cfgmod.leer_yaml(cfgmod.RUTA_MONITOREO)


def _cargar_con(tmp_path, cambio):
    datos = _datos()
    cambio(datos)
    ruta = tmp_path / "m.yaml"
    import yaml

    ruta.write_text(yaml.safe_dump(datos), encoding="utf-8")
    return cfgmod.cargar(ruta)


# --- configuración (#4) ------------------------------------------------------------------------


def test_config_real_valida_y_config_ref_estable():
    a, b = cfgmod.cargar(), cfgmod.cargar()
    assert a.config_ref == b.config_ref and len(a.config_ref) == 64
    assert 0 <= a.inferior < a.superior <= 1


def test_velocidad_no_cambia_config_ref():
    assert cfgmod.cargar(velocidad=0).config_ref == cfgmod.cargar(velocidad=1).config_ref


def test_un_cambio_cambia_config_ref(tmp_path):
    base = cfgmod.cargar().config_ref
    otro = _cargar_con(tmp_path, lambda d: d["ventanas"].update(minimo_candidatas=21))
    assert otro.config_ref != base


@pytest.mark.parametrize(
    ("inferior", "superior"), [(0.6, 0.3), (0.5, 0.5), (-0.1, 0.5), (0.3, 1.2)]
)
def test_umbrales_invalidos(tmp_path, inferior, superior):
    with pytest.raises(ErrorConfig):
        _cargar_con(tmp_path, lambda d: d["umbrales"].update(inferior=inferior, superior=superior))


def test_piso_del_detector_debe_quedar_bajo_el_inferior(tmp_path):
    with pytest.raises(ErrorConfig, match="piso de salida"):
        _cargar_con(tmp_path, lambda d: d["umbrales"].update(inferior=0.05, superior=0.6))


@pytest.mark.parametrize(
    "cambio",
    [
        lambda d: d["ventanas"].update(minimo_candidatas=0),
        lambda d: d["ventanas"].update(duracion_s=0),
        lambda d: d["muestreo"].update(cada_n_frames=0),
        lambda d: d["reglas"][0].update(severidad="urgente"),
        lambda d: d["reglas"].append(copy.deepcopy(d["reglas"][0])),
        lambda d: d["captura"].update(zonas=["rara"]),
        lambda d: d.update(extra=1),
    ],
)
def test_configuraciones_invalidas(tmp_path, cambio):
    with pytest.raises(ErrorConfig):
        _cargar_con(tmp_path, cambio)


# --- zonas (#11) -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "esperada"),
    [
        (0.0, "baja"),
        (0.2999, "baja"),
        (0.30, "duda"),
        (0.5999, "duda"),
        (0.60, "aceptada"),
        (1.0, "aceptada"),
    ],
)
def test_bordes_de_zona(score, esperada):
    assert zonas.zona(score, 0.30, 0.60) == esperada


@pytest.mark.parametrize("score", [-0.01, 1.01, float("nan"), None, True])
def test_score_invalido(score):
    with pytest.raises(ValueError):
        zonas.zona(score, 0.3, 0.6)


def test_zona_frame_sin_candidatas_no_tiene_zona():
    assert zonas.zona_frame([], 0.3, 0.6) is None
    assert zonas.zona_frame([0.1, 0.65], 0.3, 0.6) == "aceptada"


# --- contratos (#3) ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tipo", "archivo"),
    [
        ("evento", "evento-ok.json"),
        ("evento", "evento-sin-detecciones.json"),
        ("evento", "evento-error.json"),
        ("captura", "captura.json"),
        ("ventana", "ventana.json"),
        ("alerta", "alerta.json"),
    ],
)
def test_ejemplos_validos(tipo, archivo):
    contratos.validar(tipo, json.loads((EJEMPLOS / archivo).read_text(encoding="utf-8")))


def _ok():
    return json.loads((EJEMPLOS / "evento-ok.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "cambio",
    [
        lambda e: e.update(status="sin_detecciones"),  # con detecciones
        lambda e: e.update(
            score_max=0.0, status="sin_detecciones", detecciones=[], n_candidatas=0, zona_frame=None
        ),  # confianza artificial
        lambda e: e.update(error={"code": "x", "message": "y"}),  # error con status ok
        lambda e: e["detecciones"][0].update(score=1.5),
        lambda e: e.update(zona_frame="media"),
        lambda e: e.pop("config_ref"),
    ],
)
def test_eventos_invalidos(cambio):
    e = _ok()
    cambio(e)
    with pytest.raises(contratos.ErrorContrato):
        contratos.validar("evento", e)


# --- reglas y ventanas (#13, #16) --------------------------------------------------------------


def _ev(i, baja, total):
    return {
        "event_id": f"e{i}",
        "status": "ok" if total else "sin_detecciones",
        "n_candidatas": total,
        "conteo_zonas": {"baja": baja, "duda": 0, "aceptada": total - baja},
    }


def _evaluador(referencia):
    return EvaluadorReglas(
        cfgmod.cargar(),
        run_id="t",
        model_ref="0" * 64,
        referencia=referencia,
        reloj_utc=lambda: "2026-11-08T00:00:00.000Z",
    )


def _ventana(ev, i, baja, total):
    return ev.evaluar(i, i * 10000.0, (i + 1) * 10000.0, [_ev(i, baja, total)])


def test_cero_candidatas_es_insuficiente_sin_proporcion():
    r = resumen_ventana([_ev(0, 0, 0)], 20)
    assert r["estado"] == "insuficiente" and r["proporcion_baja"] is None


def test_baja_confianza_abre_una_sola_alerta_y_cierra_con_ventana_normal():
    ev = _evaluador(0.38)
    v0, a0 = _ventana(ev, 0, 30, 40)  # 0.75 >= 0.60
    assert v0["reglas"]["baja-confianza-v1"]["resultado"] == "cumple"
    assert [a["estado"] for a in a0] == ["abierta"] and a0[0]["event_ids"] == ["e0"]
    _, a1 = _ventana(ev, 1, 30, 40)
    assert a1 == []  # no se repite mientras sigue abierta
    v2, a2 = _ventana(ev, 2, 5, 40)
    assert [a["estado"] for a in a2] == ["cerrada"] and a2[0]["cerrada_por_ventana"] == 2
    assert v2["alertas_activas"] == 0


def test_insuficiente_no_cierra_ni_alerta():
    ev = _evaluador(0.38)
    _ventana(ev, 0, 30, 40)
    v1, a1 = _ventana(ev, 1, 10, 10)  # 10 < 20 candidatas
    assert v1["estado"] == "insuficiente" and a1 == []
    assert v1["reglas"]["baja-confianza-v1"]["resultado"] == "insuficiente"
    assert v1["alertas_activas"] == 1


def test_cambio_sostenido_requiere_tres_ventanas_y_no_lo_reinicia_lo_insuficiente():
    ev = _evaluador(0.38)  # cumple con >= 0.58
    _, a = _ventana(ev, 0, 24, 40)  # 0.60
    assert not [x for x in a if x["rule_id"] == "cambio-sostenido-v1"]
    _ventana(ev, 1, 5, 5)  # insuficiente: no cuenta ni reinicia
    _, a = _ventana(ev, 2, 24, 40)
    assert not [x for x in a if x["rule_id"] == "cambio-sostenido-v1"]
    v, a = _ventana(ev, 3, 24, 40)
    sostenidas = [x for x in a if x["rule_id"] == "cambio-sostenido-v1"]
    assert len(sostenidas) == 1 and len(sostenidas[0]["ventanas"]) == 3
    assert v["reglas"]["cambio-sostenido-v1"]["consecutivas"] == 3


def test_cambio_transitorio_no_dispara():
    ev = _evaluador(0.38)
    _ventana(ev, 0, 24, 40)
    _ventana(ev, 1, 24, 40)
    _ventana(ev, 2, 4, 40)  # vuelve a lo normal
    _, a = _ventana(ev, 3, 24, 40)
    assert not [x for x in a if x["rule_id"] == "cambio-sostenido-v1"]


def test_sin_referencia_la_regla_sostenida_no_evalua():
    v, _ = _ventana(_evaluador(None), 0, 30, 40)
    assert v["reglas"]["cambio-sostenido-v1"]["resultado"] == "sin_referencia"


def test_las_alertas_cumplen_su_contrato():
    ev = _evaluador(0.38)
    for i in range(3):
        v, alertas = _ventana(ev, i, 30, 40)
        contratos.validar("ventana", {**v})
        for a in alertas:
            contratos.validar("alerta", a)


# --- métricas (#18) ----------------------------------------------------------------------------


def test_percentil_rango_cercano():
    assert percentil_rango_cercano([], 95) is None
    assert percentil_rango_cercano([5.0], 95) == 5.0
    assert percentil_rango_cercano([float(i) for i in range(1, 101)], 95) == 95.0
    assert percentil_rango_cercano([1.0, 2.0, 3.0, 4.0], 50) == 2.0


# --- respaldo de frames (#34) ------------------------------------------------------------------


@pytest.mark.parametrize("segmento", ["referencia", "c1", "c2"])
def test_respaldo_integro(segmento):
    assert verificar_respaldo(DIR_FRAMES / segmento) == []


def test_fuentes_declaran_licencia_y_hash():
    f = cfgmod.cargar_fuentes()
    for v in f["videos"].values():
        assert "Creative Commons" in v["licencia"]
        assert len(v["sha256"]) == 64
