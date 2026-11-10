"""Referencia de confianza a partir de una corrida en condiciones representativas (issue #12).

La referencia conserva:
- `proporcion_baja`: candidatas con s < inferior / candidatas, sumando solo las ventanas
  suficientes. Es lo que compara la regla de cambio sostenido.
- La distribución de las proporciones por ventana y de los scores por candidata, que sirven para
  justificar los umbrales (docs/p6/umbrales.md).
- La identidad de la serie: config_ref y model_ref. Una corrida con otra identidad no se compara.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from .almacen import leer_jsonl
from .metricas import percentil_rango_cercano


def calcular(carpeta: Path) -> dict[str, Any]:
    carpeta = Path(carpeta)
    run = json.loads((carpeta / "run.json").read_text(encoding="utf-8"))
    eventos = list(leer_jsonl(carpeta / "eventos.jsonl"))
    ventanas = list(leer_jsonl(carpeta / "ventanas.jsonl"))
    suficientes = [v for v in ventanas if v["estado"] == "suficiente"]
    if not suficientes:
        raise ValueError("la corrida no tiene ventanas suficientes: no sirve como referencia")
    n_cand = sum(v["n_candidatas"] for v in suficientes)
    n_baja = sum(v["n_baja"] for v in suficientes)
    props = [v["proporcion_baja"] for v in suficientes]
    scores = [d["score"] for e in eventos for d in e["detecciones"]]
    maximos = [e["score_max"] for e in eventos if e["score_max"] is not None]
    efectiva = run["config_efectiva"]

    def cuantiles(xs: list[float]) -> dict[str, float | None]:
        return {f"p{p}": percentil_rango_cercano(xs, p) for p in (5, 10, 25, 50, 75, 90, 95)}

    return {
        "schema": "p6.referencia.v1",
        "run_id": run["run_id"],
        "segmento": run["segmento"],
        "fuente": run["fuente"]["manifiesto"] if "manifiesto" in run["fuente"] else run["fuente"],
        "config_ref": run["config_ref"],
        "model_ref": run["model_ref_esperado"],
        "umbrales": efectiva["umbrales"],
        "unidad": "detección candidata",
        "poblacion": "candidatas con score >= piso de salida del detector, en ventanas suficientes",
        "ventanas_total": len(ventanas),
        "ventanas_suficientes": len(suficientes),
        "n_candidatas": n_cand,
        "n_baja": n_baja,
        "proporcion_baja": n_baja / n_cand,
        "proporcion_baja_por_ventana": {
            "min": min(props),
            "max": max(props),
            "media": statistics.fmean(props),
            "desviacion": statistics.pstdev(props),
            "valores": props,
        },
        "frames": len(eventos),
        "frames_por_zona": {
            zona: sum(1 for e in eventos if e["zona_frame"] == zona)
            for zona in ("baja", "duda", "aceptada")
        },
        "frames_sin_detecciones": sum(1 for e in eventos if e["status"] == "sin_detecciones"),
        "frames_error": sum(1 for e in eventos if e["status"] == "error"),
        "scores_candidatas": {"n": len(scores), **cuantiles(scores)},
        "score_max_por_frame": {"n": len(maximos), **cuantiles(maximos)},
    }
