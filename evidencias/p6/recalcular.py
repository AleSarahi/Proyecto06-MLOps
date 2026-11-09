"""Recálculo independiente de las métricas base y de las alertas de una corrida (issue #19).

Solo usa la biblioteca estándar y los archivos exportados de la corrida; no importa `monitor`.
Recalcula desde los datos primarios y compara con lo que guardó el sistema:

- G1–G7 de la corrida (metricas.json -> corrida) y G4 por ventana;
- la proporción de baja confianza de cada ventana, recontando zonas desde los scores de cada
  candidata con los umbrales de run.json (no usa las zonas guardadas);
- que cada alerta de baja confianza corresponda a una ventana suficiente que cumple su regla;
- que cada captura exista y tenga su SHA-256.

Uso (desde la raíz del repo):
    python evidencias/p6/recalcular.py evidencias/p6/escenarios/c2-baja-confianza [...]
Sale con 0 si todo coincide (tolerancia 1e-6; p95 y FPS con 0.01) y con 1 si algo difiere.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def jsonl(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]


def p95(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[max(1, math.ceil(0.95 * len(s))) - 1]


def recalcular(carpeta: Path) -> list[str]:
    run = json.loads((carpeta / "run.json").read_text(encoding="utf-8"))
    met = json.loads((carpeta / "metricas.json").read_text(encoding="utf-8"))["metricas"]
    eventos = jsonl(carpeta / "eventos.jsonl")
    obs = [o for o in jsonl(carpeta / "observaciones.jsonl") if o["tipo"] == "frame"]
    ventanas = jsonl(carpeta / "ventanas.jsonl")
    alertas = jsonl(carpeta / "alertas.jsonl")
    caps = jsonl(carpeta / "capturas.jsonl")
    cfg = run["config_efectiva"]
    inf = cfg["umbrales"]["inferior"]
    minimo = cfg["ventanas"]["minimo_candidatas"]
    dur = cfg["ventanas"]["duracion_s"] * 1000
    inicio_seg = run["fuente"]["manifiesto"]["inicio_s"] * 1000
    difs: list[str] = []

    def comparar(nombre, propio, guardado, tol=1e-6):
        if propio is None or guardado is None:
            ok = propio is None and guardado is None
        else:
            ok = abs(propio - guardado) <= tol
        print(f"  {'OK ' if ok else 'DIF'} {nombre}: recalculado={propio} guardado={guardado}")
        if not ok:
            difs.append(nombre)

    # Ventanas: zonas recontadas desde los scores y asignación por tiempo de video.
    por_v: dict[int, list[dict]] = defaultdict(list)
    for e in eventos:
        por_v[math.floor((e["video_pos_ms"] - inicio_seg) / dur)].append(e)
    for v in ventanas:
        evs = por_v.get(v["indice"], [])
        scores = [d["score"] for e in evs for d in e["detecciones"]]
        n, baja = len(scores), sum(1 for s in scores if s < inf)
        prop = baja / n if n else None
        comparar(f"ventana {v['indice']} candidatas", n, v["n_candidatas"])
        comparar(f"ventana {v['indice']} proporcion_baja", prop, v["proporcion_baja"])
        estado = "suficiente" if n >= minimo else "insuficiente"
        if estado != v["estado"]:
            difs.append(f"ventana {v['indice']} estado")
            print(f"  DIF ventana {v['indice']} estado: {estado} vs {v['estado']}")
        g4 = next(x for x in met["G4"]["por_ventana"] if x["ventana"] == v["indice"])
        comparar(f"G4 ventana {v['indice']}", None if prop is None else round(prop, 4), g4["valor"])

    # Métricas de la corrida.
    tiempos = [o["inferencia_ms"] for o in obs if o["inferencia_ms"] is not None]
    comparar("G1 p95 ms", p95(tiempos), met["G1"]["corrida"]["valor"], 0.01)
    inferidos = [o for o in obs if o["inferencia_ms"] is not None]
    if len(inferidos) >= 2:
        d = max(o["t_fin_inferencia_ms"] for o in inferidos) - min(
            o["t_llegada_ms"] for o in inferidos
        )
        fps = len(inferidos) / (d / 1000)
    else:
        fps = None
    comparar("G2 fps", fps, met["G2"]["corrida"]["valor"], 0.01)
    rss = [o["rss_bytes"] / 2**20 for o in obs if o["rss_bytes"] is not None]
    comparar("G3 RAM MiB", max(rss) if rss else None, met["G3"]["corrida"]["valor"], 0.01)
    todos = [d["score"] for e in eventos for d in e["detecciones"]]
    g4 = sum(1 for s in todos if s < inf) / len(todos) if todos else None
    comparar("G4 corrida", g4, met["G4"]["corrida"]["valor"], 1e-4)
    validas = 0
    for c in caps:
        archivo = carpeta / c["ruta"]
        ev = next((e for e in eventos if e["event_id"] == c["event_id"]), None)
        if (archivo.is_file() and hashlib.sha256(archivo.read_bytes()).hexdigest() == c["sha256"]
                and ev is not None and ev["image_ref"] == c["ruta"]):
            validas += 1
    comparar("G5 imágenes vinculadas", validas / len(caps) if caps else None,
             met["G5"]["corrida"]["valor"], 1e-4)
    ok6 = sum(1 for e in eventos if e["model_ref"] == run["model_ref_esperado"]
              and e["config_ref"] == run["config_ref"])
    comparar("G6 versión", ok6 / len(eventos) if eventos else None,
             met["G6"]["corrida"]["valor"], 1e-4)
    comparar("G7 máx. alertas activas", max((v["alertas_activas"] for v in ventanas), default=None),
             met["G7"]["corrida"]["valor"])

    # Alertas de baja confianza: su ventana debe ser suficiente y cumplir la regla.
    reglas = {r["rule_id"]: r for r in cfg["reglas"]}
    for a in alertas:
        regla = reglas[a["rule_id"]]
        for w in a["ventanas"]:
            v = next(x for x in ventanas if x["indice"] == w["indice"])
            if regla["tipo"] == "proporcion_baja":
                cumple = v["estado"] == "suficiente" and v["proporcion_baja"] >= regla["umbral"]
            else:
                ref = run["referencia"]["proporcion_baja"]
                cumple = (v["estado"] == "suficiente"
                          and v["proporcion_baja"] - ref >= regla["tolerancia"])
            print(f"  {'OK ' if cumple else 'DIF'} alerta {a['alert_id']} ventana {w['indice']}")
            if not cumple:
                difs.append(f"alerta {a['alert_id']}")
        faltan = set(a["event_ids"]) - {e["event_id"] for e in eventos}
        if faltan:
            difs.append(f"alerta {a['alert_id']} eventos inexistentes")
    return difs


def main() -> int:
    estado = 0
    for c in sys.argv[1:]:
        print(f"== {c}")
        difs = recalcular(Path(c))
        print(f"  resultado: {'todo coincide' if not difs else f'{len(difs)} diferencias'}")
        estado |= bool(difs)
    return estado


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
