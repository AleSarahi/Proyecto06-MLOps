"""Métricas adicionales X1-X7 (extras, issues #31 y #37). Definiciones: docs/p6/extras.md.

No son métricas base: ninguna repite G1-G7 ni es una variante de umbral, ventana o percentil de una
de ellas. Se calculan desde los archivos exportados de la corrida (y, para X3, desde los eventos
de la corrida de referencia) y se escriben en `metricas_extra.json`, aparte de `metricas.json`.
Con cero observaciones el valor es `null` con `n = 0`; nunca 0 en lugar de «sin datos».

X1  candidatas por frame          media de candidatas por frame procesado (ok + sin_detecciones)
X2  frames sin detecciones        fracción de frames procesados sin ninguna candidata
X3  PSI de scores vs. referencia  índice de estabilidad de la distribución de scores por candidata
X4  latencia extremo a extremo    p95 de llegada -> evento registrado, con descomposición por etapa
X5  disponibilidad de la fuente   frames que llegaron / frames que el muestreo esperaba
X6  tasa de errores de inferencia frames con status error / frames procesados
X7  tasa de descarte por saturación frames descartados por atraso / frames que llegaron
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from .almacen import leer_jsonl
from .metricas import percentil_rango_cercano

DEFINICIONES = {
    "X1": ("candidatas_por_frame", "Candidatas por frame", "candidatas / frame"),
    "X2": ("frames_sin_detecciones", "Frames sin detecciones", "fracción de frames procesados"),
    "X3": ("psi_scores_referencia", "PSI de scores frente a la referencia", "PSI (adimensional)"),
    "X4": ("latencia_e2e_p95_ms", "Latencia extremo a extremo p95", "ms"),
    "X5": ("disponibilidad_fuente", "Disponibilidad de la fuente", "fracción de frames esperados"),
    "X6": (
        "tasa_errores_inferencia",
        "Tasa de errores de inferencia",
        "fracción de frames procesados",
    ),
    "X7": (
        "tasa_descarte_saturacion",
        "Tasa de descarte por saturación",
        "fracción de frames llegados",
    ),
}
# Bins de score para X3: [0.0, 0.1), [0.1, 0.2), ..., [0.9, 1.0]. El último incluye 1.0.
BORDES = [round(i / 10, 1) for i in range(11)]
EPS = 1e-4  # sustituye proporciones 0 para que ln(p/q) esté definido


def _r(v: float | None, dec: int = 4) -> float | None:
    return None if v is None else round(v, dec)


def histograma(scores: list[float]) -> list[int]:
    cuenta = [0] * (len(BORDES) - 1)
    for s in scores:
        cuenta[min(int(s * 10), len(cuenta) - 1)] += 1
    return cuenta


def psi(cuenta: list[int], ref: list[int]) -> float | None:
    n, m = sum(cuenta), sum(ref)
    if not n or not m:
        return None
    total = 0.0
    for a, b in zip(cuenta, ref, strict=True):
        p, q = max(a / n, EPS), max(b / m, EPS)
        total += (p - q) * math.log(p / q)
    return total


def _esperados(fuente: dict[str, Any], a_ms: float, b_ms: float) -> int | None:
    man = fuente.get("manifiesto")
    if not man or not {"fps_video", "cada_n_frames", "inicio_s", "fin_s"} <= set(man):
        return None
    tasa = man["fps_video"] / man["cada_n_frames"]  # frames muestreados por segundo de video
    ini, fin = man["inicio_s"] * 1000, man["fin_s"] * 1000
    traslape = max(0.0, min(b_ms, fin) - max(a_ms, ini))
    return round(traslape / 1000 * tasa)


def eventos_referencia(carpeta_ref: Path, config_ref: str) -> tuple[list[dict[str, Any]], str]:
    run = json.loads((carpeta_ref / "run.json").read_text(encoding="utf-8"))
    if run["config_ref"] != config_ref:
        raise ValueError("la corrida de referencia tiene otro config_ref: no es comparable")
    return list(leer_jsonl(carpeta_ref / "eventos.jsonl")), run["run_id"]


def calcular(carpeta: Path, carpeta_ref: Path | None) -> dict[str, Any]:
    carpeta = Path(carpeta)
    run = json.loads((carpeta / "run.json").read_text(encoding="utf-8"))
    eventos = list(leer_jsonl(carpeta / "eventos.jsonl"))
    ventanas = list(leer_jsonl(carpeta / "ventanas.jsonl"))
    todas_obs = list(leer_jsonl(carpeta / "observaciones.jsonl"))
    obs = [o for o in todas_obs if o["tipo"] == "frame"]
    minimo = run["config_efectiva"]["ventanas"]["minimo_candidatas"]
    ev_por_id = {e["event_id"]: e for e in eventos}

    ref_hist, ref_run = None, None
    if carpeta_ref is not None and Path(carpeta_ref, "eventos.jsonl").is_file():
        evs_ref, ref_run = eventos_referencia(Path(carpeta_ref), run["config_ref"])
        ref_hist = histograma([d["score"] for e in evs_ref for d in e["detecciones"]])

    llegadas_por_v: dict[int, int] = defaultdict(int)
    for o in todas_obs:
        # Un frame descartado por saturación sí llegó; un latido sin señal no.
        if o["tipo"] == "frame" or (o["tipo"] == "descarte" and o["motivo"] == "saturacion"):
            llegadas_por_v[o["ventana"]] += 1
    saturados_por_v: dict[int, int] = defaultdict(int)
    for o in todas_obs:
        if o["tipo"] == "descarte" and o["motivo"] == "saturacion":
            saturados_por_v[o["ventana"]] += 1
    obs_por_v: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for o in obs:
        obs_por_v[o["ventana"]].append(o)

    def x1x2(evs: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
        procesados = [e for e in evs if e["status"] in ("ok", "sin_detecciones")]
        n = len(procesados)
        cand = sum(e["n_candidatas"] for e in procesados)
        sin = sum(1 for e in procesados if e["status"] == "sin_detecciones")
        return (
            {"valor": _r(cand / n if n else None), "n": n, "numerador": cand},
            {"valor": _r(sin / n if n else None), "n": n, "numerador": sin},
        )

    def x3(evs: list[dict[str, Any]], exigir_minimo: bool) -> dict[str, Any]:
        scores = [d["score"] for e in evs for d in e["detecciones"]]
        h = histograma(scores)
        if ref_hist is None:
            return {"valor": None, "n": len(scores), "estado": "sin_referencia", "histograma": h}
        if exigir_minimo and len(scores) < minimo:
            return {"valor": None, "n": len(scores), "estado": "insuficiente", "histograma": h}
        return {"valor": _r(psi(h, ref_hist)), "n": len(scores), "estado": "ok", "histograma": h}

    def x4(o: list[dict[str, Any]]) -> dict[str, Any]:
        e2e = [x["t_fin_registro_ms"] - x["t_llegada_ms"] for x in o]
        inferidos = [x for x in o if x["inferencia_ms"] is not None]
        etapas = {
            "cola": [x["cola_ms"] for x in inferidos],
            "inferencia": [x["inferencia_ms"] for x in inferidos],
            "registro": [
                x["t_fin_registro_ms"] - x["t_llegada_ms"] - x["cola_ms"] - x["inferencia_ms"]
                for x in inferidos
            ],
        }
        return {
            "valor": _r(percentil_rango_cercano(e2e, 95), 2),
            "n": len(e2e),
            "mediana_por_etapa_ms": {
                k: _r(percentil_rango_cercano(v, 50), 2) for k, v in etapas.items()
            },
        }

    def x5(llegados: int, esperados: int | None) -> dict[str, Any]:
        return {
            "valor": _r(llegados / esperados if esperados else None),
            "n": esperados or 0,
            "numerador": llegados,
        }

    def x6(evs: list[dict[str, Any]]) -> dict[str, Any]:
        err = sum(1 for e in evs if e["status"] == "error")
        return {"valor": _r(err / len(evs) if evs else None), "n": len(evs), "numerador": err}

    def x7(procesados: int, saturados: int) -> dict[str, Any]:
        n = procesados + saturados
        return {"valor": _r(saturados / n if n else None), "n": n, "numerador": saturados}

    por_ventana: dict[str, list[dict[str, Any]]] = {g: [] for g in DEFINICIONES}
    for v in ventanas:
        i = v["indice"]
        evs = [ev_por_id[e] for e in v["event_ids"] if e in ev_por_id]
        base = {"ventana": i, "inicio_ms": v["inicio_ms"], "fin_ms": v["fin_ms"]}
        a, b = x1x2(evs)
        por_ventana["X1"].append({**base, **a})
        por_ventana["X2"].append({**base, **b})
        por_ventana["X3"].append({**base, **x3(evs, True)})
        por_ventana["X4"].append({**base, **x4(obs_por_v.get(i, []))})
        por_ventana["X5"].append(
            {
                **base,
                **x5(
                    llegadas_por_v.get(i, 0), _esperados(run["fuente"], v["inicio_ms"], v["fin_ms"])
                ),
            }
        )
        por_ventana["X6"].append({**base, **x6(evs)})
        por_ventana["X7"].append({**base, **x7(len(evs), saturados_por_v.get(i, 0))})

    a, b = x1x2(eventos)
    man = run["fuente"].get("manifiesto")
    corrida = {
        "X1": a,
        "X2": b,
        "X3": x3(eventos, False),
        "X4": x4(obs),
        "X5": x5(
            sum(llegadas_por_v.values()),
            _esperados(run["fuente"], man["inicio_s"] * 1000, man["fin_s"] * 1000) if man else None,
        ),
        "X6": x6(eventos),
        "X7": x7(len(eventos), sum(saturados_por_v.values())),
    }
    resultado = {
        "run_id": run["run_id"],
        "config_ref": run["config_ref"],
        "referencia_x3": {
            "run_id": ref_run,
            "bordes": BORDES,
            "histograma": ref_hist,
            "eps": EPS,
        },
        "metricas": {},
    }
    for g, (mid, nombre, unidad) in DEFINICIONES.items():
        resultado["metricas"][g] = {
            "id": mid,
            "nombre": nombre,
            "unidad": unidad,
            "corrida": corrida[g],
            "por_ventana": por_ventana[g],
        }
    return resultado
