"""T20 · Las entradas de C1 a C7 salen de `infer` sobre los datos congelados, sin retoques.

C1 a C5 y C7: cada `entrada.jsonl` trae la secuencia completa del manifiesto, en orden, con sus
`t_capture_ms` de `captura.jsonl` y los hashes del detector congelado (`config-detector-v1`). C6
es la única corrida sobre S07 (`resultados/p5-12-c6-s07.jsonl`) reordenada por
`casos/armar_c6.py`, con las mismas detecciones. Cómo se armaron y por qué fallan C2, C5 y C7:
`docs/casos-reales.md`.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
CASOS = RAIZ / "casos"


def cargar(nombre: str, archivo: str):
    """casos/ no es un paquete: se carga el archivo."""
    spec = importlib.util.spec_from_file_location(nombre, CASOS / archivo)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


armar_c6 = cargar("armar_c6", "armar_c6.py")
runner = cargar("runner_casos_reales", "runner.py")

# Paso 2 del congelamiento (#13): mensaje del tag config-detector-v1 y config/detector.json.
CONFIG_SHA256 = "6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08"
MODEL_SHA256 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"

# Caso → secuencias, en el orden en que van en la entrada, y cuánto se desplazan sus capturas.
REALES = {
    "C1": [("S01", 0.0), ("S08", 3406.0)],
    "C2": [("S02", 0.0)],
    "C3": [("S03", 0.0)],
    "C4": [("S04", 0.0)],
    "C5": [("S05", 0.0)],
    "C7": [("S06", 0.0)],
}


def eventos(caso: str) -> list[dict]:
    texto = (CASOS / caso / "entrada.jsonl").read_text(encoding="utf-8")
    return [json.loads(linea) for linea in texto.splitlines() if linea]


def manifiesto() -> dict[str, list[dict]]:
    por_secuencia: dict[str, list[dict]] = {}
    for linea in (RAIZ / "datos" / "manifiesto.jsonl").read_text(encoding="utf-8").splitlines():
        cuadro = json.loads(linea)
        por_secuencia.setdefault(cuadro["sequence_id"], []).append(cuadro)
    return por_secuencia


@pytest.mark.parametrize("caso", sorted(REALES))
def test_la_entrada_es_la_secuencia_completa_con_sus_tiempos(caso):
    cuadros = manifiesto()
    esperados = [
        (c["frame_id"], c["sequence_id"], c["t_relativo_ms"] + desplazamiento)
        for secuencia, desplazamiento in REALES[caso]
        for c in cuadros[secuencia]
    ]
    actuales = [(e["frame_id"], e["sequence_id"], e["t_capture_ms"]) for e in eventos(caso)]
    assert actuales == esperados


@pytest.mark.parametrize("caso", [*sorted(REALES), "C6"])
def test_la_entrada_es_del_detector_congelado(caso):
    evs = eventos(caso)
    assert {e["config_sha256"] for e in evs} == {CONFIG_SHA256}
    assert {e["model_sha256"] for e in evs} == {MODEL_SHA256}
    assert len({e["run_id"] for e in evs}) == 1
    assert all(e["status"] == "ok" for e in evs)


@pytest.mark.parametrize("caso", sorted(REALES))
def test_los_casos_reales_dicen_real(caso):
    assert (
        yaml.safe_load((CASOS / caso / "tramos.yaml").read_text(encoding="utf-8"))["entrada"]
        == "real"
    )


def test_c1_el_reloj_no_retrocede_entre_s01_y_s08():
    evs = eventos("C1")
    emisiones = [e["t_emit_ms"] for e in evs]
    assert emisiones == sorted(emisiones)
    assert evs[12]["frame_id"] == "S08_f0001" and evs[12]["t_capture_ms"] > evs[11]["t_emit_ms"]


def test_c6_es_la_corrida_de_s07_armada_por_el_script():
    entrada = (CASOS / "C6" / "entrada.jsonl").read_text(encoding="utf-8")
    corrida = armar_c6.leer_corrida()
    assert entrada == armar_c6.texto(armar_c6.armar(corrida, armar_c6.umbral_de_la_politica()))
    originales = {e["frame_id"]: e for e in corrida}
    for evento in eventos("C6"):
        original = originales[evento["frame_id"]]
        cambian = {"t_capture_ms", "t_emit_ms"}
        assert {k: v for k, v in evento.items() if k not in cambian} == {
            k: v for k, v in original.items() if k not in cambian
        }
        demora = evento["t_emit_ms"] - evento["t_capture_ms"]
        assert demora == pytest.approx(original["t_emit_ms"] - original["t_capture_ms"])


def test_c6_tramos_son_los_de_abajo_y_arriba_del_umbral():
    umbral = armar_c6.umbral_de_la_politica()
    bajo, sobre = armar_c6.grupos(armar_c6.leer_corrida(), umbral)
    tramos = yaml.safe_load((CASOS / "C6" / "tramos.yaml").read_text(encoding="utf-8"))
    assert tramos["entrada"] == "armada"
    assert tramos["tramos"] == {
        "bajo_umbral": [e["frame_id"] for e in bajo],
        "sobre_umbral": [e["frame_id"] for e in sobre],
    }
    assert [e["frame_id"] for e in eventos("C6")] == tramos["tramos"]["bajo_umbral"] + tramos[
        "tramos"
    ]["sobre_umbral"]


# Lo que falla por el detector, por tramo y frame_id (docs/casos-reales.md). Si cambia, hay que
# volver a revisar el documento: la entrada, la política o el detector ya no son los mismos.
FALLAS_DEL_DETECTOR = {
    "C2": {
        "obstaculo": ["S02_f0001", "S02_f0002", "S02_f0003", "S02_f0004", "S02_f0005", "S02_f0006"]
    },
    "C5": {"sin_zona_libre": ["S05_f0001"]},
    "C7": {"bloqueo": ["S06_f0002"], "bloqueo_otra_vez": ["S06_f0007"]},
}


def test_pasan_c1_c3_c4_c6_y_fallan_c2_c5_c7_donde_dice_el_documento(tmp_path):
    reales = [*sorted(REALES), "C6"]
    assert runner.main([*reales, "--salida", str(tmp_path)]) == 1
    for caso in reales:
        v = json.loads((tmp_path / caso / "veredicto.json").read_text(encoding="utf-8"))
        fallas = {
            t["tramo"]: [re.search(r"frame_id=(\w+)", m).group(1) for m in t["motivos"]]
            for t in v["tramos"]
            if t["motivos"]
        }
        assert fallas == FALLAS_DEL_DETECTOR.get(caso, {}), caso
        assert v["pasa"] is (caso not in FALLAS_DEL_DETECTOR)
