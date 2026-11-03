"""P5-08: compara el recorrido de T16 (Windows) con la repetición en Mac, cuadro por cuadro.

    uv run python resultados/p5-08-comparar.py

Lee ``resultados/recorrido-real/{izq,der}/`` y ``resultados/p5-08-mac/{izq,der}/``. Sale con 1
si cambia el número de detecciones, una clase o un hash, o si confianza o caja se alejan más que
la tolerancia. Los tiempos no se comparan: dependen de la máquina.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

RESULTADOS = Path(__file__).resolve().parent
TOLERANCIA_CONFIANZA = 1e-4
TOLERANCIA_CAJA_PX = 0.01


def _leer(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea]


def _acciones(carpeta: Path) -> dict[str, int]:
    comandos = _leer(carpeta / "comandos.jsonl")
    return dict(Counter(c["action"] for c in comandos if c.get("frame_id")))


def comparar(lado: str) -> bool:
    windows = RESULTADOS / "recorrido-real" / lado
    mac = RESULTADOS / "p5-08-mac" / lado
    eventos_w = {e["frame_id"]: e for e in _leer(windows / "detector.jsonl")}
    eventos_m = {e["frame_id"]: e for e in _leer(mac / "detector.jsonl")}
    iguales = eventos_w.keys() == eventos_m.keys()
    max_confianza = max_caja = 0.0
    for frame_id in sorted(eventos_w.keys() & eventos_m.keys()):
        w, m = eventos_w[frame_id], eventos_m[frame_id]
        iguales &= all(w[clave] == m[clave] for clave in ("model_sha256", "config_sha256"))
        iguales &= len(w["detections"]) == len(m["detections"])
        for a, b in zip(w["detections"], m["detections"], strict=False):
            iguales &= a["class_id"] == b["class_id"]
            max_confianza = max(max_confianza, abs(a["confidence"] - b["confidence"]))
            diferencias = (abs(x - y) for x, y in zip(a["bbox"], b["bbox"], strict=True))
            max_caja = max(max_caja, *diferencias)
    iguales &= max_confianza <= TOLERANCIA_CONFIANZA and max_caja <= TOLERANCIA_CAJA_PX
    print(
        f"{lado}: {len(eventos_w)} cuadros · máx |Δ confianza| {max_confianza:.1e} · "
        f"máx |Δ caja| {max_caja:.1e} px · {'igual' if iguales else 'DISTINTO'}"
    )
    print(f"  acciones Windows {_acciones(windows)} · Mac {_acciones(mac)}")
    return iguales


def main() -> int:
    resultados = [comparar(lado) for lado in ("izq", "der")]
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
