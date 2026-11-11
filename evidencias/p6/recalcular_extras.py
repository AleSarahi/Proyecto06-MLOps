"""Recálculo independiente de las métricas adicionales X1-X7 y de las alertas técnicas (extras).

Solo usa la biblioteca estándar y los archivos exportados; no importa `monitor`.

- X1-X5 por ventana y por corrida, desde eventos.jsonl, observaciones.jsonl y run.json (X3 además
  desde los eventos de la corrida de referencia), comparados con metricas_extra.json.
- Alertas `fuente-sin-senal`: el hueco entre el último frame y la detección supera el umbral, los
  frames perdidos son los latidos `sin_senal` del corte, la recuperación son los N primeros frames
  posteriores y la alerta cierra en la ventana del N-ésimo.
- Reglas con `ventanas_consecutivas` > 1: la alerta se abre en la N-ésima ventana suficiente
  seguida que cumple, no antes.

Uso (desde la raíz del repo):
    python evidencias/p6/recalcular_extras.py evidencias/p6/extras/s1-transicion [...]
Sale con 0 si todo coincide y con 1 si algo difiere.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REF = Path("evidencias/p6/referencia/corrida")


def jsonl(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]


def rango_cercano(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[max(1, math.ceil(p / 100 * len(s))) - 1]


def hist(scores: list[float]) -> list[int]:
    h = [0] * 10
    for s in scores:
        h[min(int(s * 10), 9)] += 1
    return h


def psi(h: list[int], r: list[int], eps: float = 1e-4) -> float | None:
    n, m = sum(h), sum(r)
    if not n or not m:
        return None
    return sum(
        (max(a / n, eps) - max(b / m, eps)) * math.log(max(a / n, eps) / max(b / m, eps))
        for a, b in zip(h, r, strict=True)
    )


def recalcular(carpeta: Path) -> list[str]:
    run = json.loads((carpeta / "run.json").read_text(encoding="utf-8"))
    guardado = json.loads((carpeta / "metricas_extra.json").read_text(encoding="utf-8"))["metricas"]
    eventos = jsonl(carpeta / "eventos.jsonl")
    obs_todas = jsonl(carpeta / "observaciones.jsonl")
    obs = [o for o in obs_todas if o["tipo"] == "frame"]
    ventanas = jsonl(carpeta / "ventanas.jsonl")
    alertas = jsonl(carpeta / "alertas.jsonl")
    cfg = run["config_efectiva"]
    minimo = cfg["ventanas"]["minimo_candidatas"]
    man = run["fuente"]["manifiesto"]
    ref_eventos = jsonl(REF / "eventos.jsonl")
    ref_run = json.loads((REF / "run.json").read_text(encoding="utf-8"))
    ref_h = hist([d["score"] for e in ref_eventos for d in e["detecciones"]])
    if ref_run["config_ref"] != run["config_ref"]:
        ref_h = None
    difs: list[str] = []

    def cmp(nombre, propio, guard, tol=1e-4):
        if propio is None or guard is None:
            ok = propio is None and guard is None
        else:
            ok = abs(propio - guard) <= tol
        print(f"  {'OK ' if ok else 'DIF'} {nombre}: recalculado={propio} guardado={guard}")
        if not ok:
            difs.append(nombre)

    ev_id = {e["event_id"]: e for e in eventos}
    tasa = man["fps_video"] / man["cada_n_frames"]
    ini, fin = man["inicio_s"] * 1000, man["fin_s"] * 1000

    def calcular(evs, o, llegados, a_ms, b_ms, exigir):
        proc = [e for e in evs if e["status"] in ("ok", "sin_detecciones")]
        n = len(proc)
        x1 = sum(e["n_candidatas"] for e in proc) / n if n else None
        x2 = sum(1 for e in proc if e["status"] == "sin_detecciones") / n if n else None
        sc = [d["score"] for e in evs for d in e["detecciones"]]
        x3 = None if ref_h is None or (exigir and len(sc) < minimo) else psi(hist(sc), ref_h)
        x4 = rango_cercano([x["t_fin_registro_ms"] - x["t_llegada_ms"] for x in o], 95)
        esperados = round(max(0.0, min(b_ms, fin) - max(a_ms, ini)) / 1000 * tasa)
        x5 = llegados / esperados if esperados else None
        x6 = sum(1 for e in evs if e["status"] == "error") / len(evs) if evs else None
        sat = llegados - len(evs)  # llegaron y no se registraron: descartes por saturación
        x7 = sat / llegados if llegados else None
        return {"X1": x1, "X2": x2, "X3": x3, "X4": x4, "X5": x5, "X6": x6, "X7": x7}

    llegadas: dict[int, int] = defaultdict(int)
    for o in obs_todas:
        if o["tipo"] == "frame" or (o["tipo"] == "descarte" and o["motivo"] == "saturacion"):
            llegadas[o["ventana"]] += 1
    tol = {"X1": 1e-4, "X2": 1e-4, "X3": 1e-4, "X4": 0.01, "X5": 1e-4, "X6": 1e-4, "X7": 1e-4}
    for v in ventanas:
        i = v["indice"]
        evs = [ev_id[e] for e in v["event_ids"] if e in ev_id]
        propio = calcular(
            evs,
            [o for o in obs if o["ventana"] == i],
            llegadas[i],
            v["inicio_ms"],
            v["fin_ms"],
            True,
        )
        for g, val in propio.items():
            if g not in guardado:
                continue  # metricas_extra.json anterior a X6/X7
            gv = next(p for p in guardado[g]["por_ventana"] if p["ventana"] == i)["valor"]
            cmp(f"{g} ventana {i}", val, gv, tol[g])
    propio = calcular(eventos, obs, sum(llegadas.values()), ini, fin, False)
    for g, val in propio.items():
        if g in guardado:
            cmp(f"{g} corrida", val, guardado[g]["corrida"]["valor"], tol[g])

    # Alertas técnicas por ventana (S3/S4): recalcula la tasa de cada ventana y comprueba que la
    # alerta abre en la primera ventana suficiente que cumple y cierra en la primera que no.
    vig_cfg = run.get("vigilancia") or {}
    tecnicas = {
        vig_cfg[s]["rule_id"]: (s, vig_cfg[s])
        for s in ("errores_inferencia", "saturacion")
        if s in vig_cfg
    }
    sat_v: dict[int, int] = defaultdict(int)
    for o in obs_todas:
        if o["tipo"] == "descarte" and o["motivo"] == "saturacion":
            sat_v[o["ventana"]] += 1
    for a in alertas:
        if a.get("schema") != "p6.alerta_tecnica.v1":
            continue
        seccion, r = tecnicas[a["rule_id"]]
        abre = cierra = tasa_abre = None
        for v in ventanas:
            evs = [ev_id[e] for e in v["event_ids"] if e in ev_id]
            if seccion == "errores_inferencia":
                n, num = len(evs), sum(1 for e in evs if e["status"] == "error")
            else:
                n, num = len(evs) + sat_v[v["indice"]], sat_v[v["indice"]]
            if n < r["minimo_frames"]:
                continue
            if num / n >= r["umbral"] and abre is None:
                abre = v["indice"]
                tasa_abre = num / n
            elif num / n < r["umbral"] and abre is not None:
                cierra = v["indice"]
                break
        ok = (
            abre == a["ventanas"][0]["indice"]
            and tasa_abre is not None
            and abs(tasa_abre - a["ventanas"][0]["tasa"]) < 1e-4
            and cierra == a["cerrada_por_ventana"]
        )
        print(
            f"  {'OK ' if ok else 'DIF'} {a['alert_id']} abre en {abre} "
            f"(tasa {tasa_abre}) y cierra en {cierra}"
        )
        if not ok:
            difs.append(f"{a['alert_id']} ventanas")

    # Alertas de fuente.
    vig = (run.get("vigilancia") or {}).get("fuente_sin_senal")
    frames_t = sorted((o["t_llegada_ms"], o["event_id"], o["ventana"]) for o in obs)
    latidos = sorted(o["t_esperado_ms"] for o in obs_todas if o["tipo"] == "sin_senal")
    for a in alertas:
        if a.get("schema") != "p6.alerta_fuente.v1":
            continue
        previos = [f for f in frames_t if f[0] <= a["sin_senal_desde_ms"] + 1e-3]
        ok_hueco = a["detectada_ms"] - a["sin_senal_desde_ms"] > vig["sin_frames_ms"]
        ok_ultimo = bool(previos) and previos[-1][1] == a["ultimo_frame"]["event_id"]
        posteriores = [f for f in frames_t if f[0] > a["sin_senal_desde_ms"] + 1e-3]
        perdidos = sum(
            1
            for t in latidos
            if a["sin_senal_desde_ms"] < t < (posteriores[0][0] if posteriores else math.inf)
        )
        ok_perdidos = perdidos == a["frames_perdidos"]
        n = vig["frames_recuperacion"]
        if a["recuperacion"]:
            rec = posteriores[:n]
            ok_rec = [f[1] for f in rec] == a["recuperacion"]["event_ids"] and (
                rec[-1][2] == a["cerrada_por_ventana"]
            )
        else:
            ok_rec = len(posteriores) < n
        for nombre, ok in (
            ("hueco > umbral", ok_hueco),
            ("último frame", ok_ultimo),
            (f"frames perdidos = {perdidos}", ok_perdidos),
            ("recuperación y cierre", ok_rec),
        ):
            print(f"  {'OK ' if ok else 'DIF'} {a['alert_id']} {nombre}")
            if not ok:
                difs.append(f"{a['alert_id']} {nombre}")

    # Persistencia: una regla de N ventanas abre en la N-ésima ventana suficiente que cumple.
    reglas = {r["rule_id"]: r for r in cfg["reglas"]}
    for a in alertas:
        if a.get("schema") in ("p6.alerta_fuente.v1", "p6.alerta_tecnica.v1"):
            continue
        r = reglas[a["rule_id"]]
        seguidas = 0
        apertura = None
        for v in ventanas:
            res = v["reglas"][r["rule_id"]]["resultado"]
            if res == "cumple":
                seguidas += 1
                if seguidas == r["ventanas_consecutivas"] and apertura is None:
                    apertura = v["indice"]
            elif res == "no_cumple":
                seguidas = 0
                if apertura is not None:
                    break
        ok = (
            apertura == a["ventanas"][-1]["indice"]
            and len(a["ventanas"]) == r["ventanas_consecutivas"]
        )
        print(f"  {'OK ' if ok else 'DIF'} {a['alert_id']} abre en la ventana {apertura}")
        if not ok:
            difs.append(f"{a['alert_id']} apertura")
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
