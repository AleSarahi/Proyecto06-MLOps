"""Métricas base G1-G7 por ventana y por corrida (issue #18). Definiciones: docs/p6/metricas.md.

Todas se calculan desde los archivos exportados de la corrida (observaciones, eventos, ventanas,
capturas, alertas), así que se pueden recalcular. Con cero observaciones el valor es `null` y se
indica `n = 0`; nunca se reporta 0 en lugar de "sin datos".
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from .almacen import leer_jsonl
from .capturas import verificar as verificar_capturas

DEFINICIONES = {
    "G1": ("tiempo_inferencia_p95_ms", "Tiempo de inferencia p95", "ms"),
    "G2": ("fps_procesamiento", "FPS de procesamiento", "frames inferidos / s"),
    "G3": ("ram_rss_max_mb", "RAM RSS máxima del proceso", "MiB"),
    "G4": ("proporcion_baja", "Proporción de baja confianza", "fracción de candidatas"),
    "G5": ("imagenes_vinculadas", "Imágenes vinculadas", "fracción de capturas"),
    "G6": (
        "version_esperada_vs_reportada",
        "Versión esperada frente a reportada",
        "fracción de eventos",
    ),
    "G7": ("alertas_activas", "Alertas activas al cierre de la ventana", "alertas"),
}


def percentil_rango_cercano(valores: list[float], p: float) -> float | None:
    """Percentil por rango cercano: el valor en la posición ceil(p/100 * n) de la lista ordenada."""
    if not valores:
        return None
    orden = sorted(valores)
    k = max(1, math.ceil(p / 100 * len(orden)))
    return orden[k - 1]


def _fps(obs: list[dict[str, Any]]) -> tuple[float | None, int]:
    inferidos = [o for o in obs if o["inferencia_ms"] is not None]
    if len(inferidos) < 2:
        return None, len(inferidos)
    duracion = max(o["t_fin_inferencia_ms"] for o in inferidos) - min(
        o["t_llegada_ms"] for o in inferidos
    )
    return (len(inferidos) / (duracion / 1000) if duracion > 0 else None), len(inferidos)


def _r(v: float | None, dec: int = 4) -> float | None:
    return None if v is None else round(v, dec)


def calcular(carpeta: Path) -> dict[str, Any]:
    carpeta = Path(carpeta)
    run = json.loads((carpeta / "run.json").read_text(encoding="utf-8"))
    obs = [o for o in leer_jsonl(carpeta / "observaciones.jsonl") if o["tipo"] == "frame"]
    eventos = list(leer_jsonl(carpeta / "eventos.jsonl"))
    ventanas = list(leer_jsonl(carpeta / "ventanas.jsonl"))
    obs_por_v: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for o in obs:
        obs_por_v[o["ventana"]].append(o)
    ev_por_id = {e["event_id"]: e for e in eventos}
    esperado_modelo = run["model_ref_esperado"]
    esperado_config = run["config_ref"]

    def version_ok(ids: list[str]) -> tuple[float | None, int]:
        evs = [ev_por_id[i] for i in ids if i in ev_por_id]
        if not evs:
            return None, 0
        ok = sum(
            1
            for e in evs
            if e["model_ref"] == esperado_modelo and e["config_ref"] == esperado_config
        )
        return ok / len(evs), len(evs)

    por_ventana: dict[str, list[dict[str, Any]]] = {g: [] for g in DEFINICIONES}
    for v in ventanas:
        i = v["indice"]
        o = obs_por_v.get(i, [])
        base = {
            "ventana": i,
            "inicio_ms": v["inicio_ms"],
            "fin_ms": v["fin_ms"],
            "event_ids": v["event_ids"],
        }
        tiempos = [x["inferencia_ms"] for x in o if x["inferencia_ms"] is not None]
        por_ventana["G1"].append(
            {**base, "valor": _r(percentil_rango_cercano(tiempos, 95), 2), "n": len(tiempos)}
        )
        fps, n = _fps(o)
        por_ventana["G2"].append({**base, "valor": _r(fps), "n": n})
        rss = [x["rss_bytes"] / 2**20 for x in o if x["rss_bytes"] is not None]
        por_ventana["G3"].append({**base, "valor": _r(max(rss) if rss else None, 2), "n": len(rss)})
        por_ventana["G4"].append(
            {
                **base,
                "valor": _r(v["proporcion_baja"]),
                "n": v["n_candidatas"],
                "numerador": v["n_baja"],
                "estado_ventana": v["estado"],
            }
        )
        val, n = version_ok(v["event_ids"])
        por_ventana["G6"].append({**base, "valor": _r(val), "n": n})
        por_ventana["G7"].append({**base, "valor": v["alertas_activas"], "n": 1})

    tiempos = [x["inferencia_ms"] for x in obs if x["inferencia_ms"] is not None]
    rss = [x["rss_bytes"] / 2**20 for x in obs if x["rss_bytes"] is not None]
    n_cand = sum(v["n_candidatas"] for v in ventanas)
    n_baja = sum(v["n_baja"] for v in ventanas)
    caps = verificar_capturas(carpeta)
    val6, n6 = version_ok(list(ev_por_id))
    fps, nf = _fps(obs)
    corrida = {
        "G1": {"valor": _r(percentil_rango_cercano(tiempos, 95), 2), "n": len(tiempos)},
        "G2": {"valor": _r(fps), "n": nf},
        "G3": {"valor": _r(max(rss) if rss else None, 2), "n": len(rss)},
        "G4": {"valor": _r(n_baja / n_cand if n_cand else None), "n": n_cand, "numerador": n_baja},
        "G5": {
            "valor": _r(
                caps["vinculadas_validas"] / caps["capturas"] if caps["capturas"] else None
            ),
            "n": caps["capturas"],
            "numerador": caps["vinculadas_validas"],
            "problemas": caps["problemas"],
        },
        "G6": {"valor": _r(val6), "n": n6},
        "G7": {
            "valor": max((v["alertas_activas"] for v in ventanas), default=None),
            "n": len(ventanas),
            "agregado": "máximo de alertas activas entre ventanas",
        },
    }
    resultado = {"run_id": run["run_id"], "config_ref": run["config_ref"], "metricas": {}}
    for g, (mid, nombre, unidad) in DEFINICIONES.items():
        resultado["metricas"][g] = {
            "id": mid,
            "nombre": nombre,
            "unidad": unidad,
            "corrida": corrida[g],
            "por_ventana": por_ventana[g],
        }
    return resultado
