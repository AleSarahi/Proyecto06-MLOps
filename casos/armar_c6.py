"""T20 · Arma la entrada de C6 con la única corrida de `infer` sobre S07 (P5-12).

`casos/C6/expectativa.yaml` pide primero los cuadros de abajo del umbral y después los de arriba,
pero en S07 la confianza alterna (`datos/MAPA_CASOS.md`, "C6: scores de S7"). Por eso C6 es
`armada`: toma los eventos de `resultados/p5-12-c6-s07.jsonl` tal como salieron de `infer` y solo
cambia

- el orden: los cuadros con detección de abajo de `umbral_confianza`
  (`config/control/politica.yaml`), luego los de arriba, cada grupo en el orden de S07;
- los tiempos: capturas nuevas cada `PASO_MS`, y cada cuadro conserva su demora
  (`t_emit_ms` - `t_capture_ms`).

Las detecciones y el `frame_id` no se tocan. Los cuadros sin detección se quedan fuera: no tienen
una confianza que poner de un lado del umbral, y en las métricas cuentan como falsos negativos.

    uv run python casos/armar_c6.py              # escribe casos/C6/entrada.jsonl
    uv run python casos/armar_c6.py --revisar    # sale 1 si la entrada no es la que se arma
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[1]
CORRIDA = RAIZ / "resultados" / "p5-12-c6-s07.jsonl"
POLITICA = RAIZ / "config" / "control" / "politica.yaml"
ENTRADA = RAIZ / "casos" / "C6" / "entrada.jsonl"
PASO_MS = 200.0


def confianza(evento: dict[str, Any]) -> float | None:
    return max((d["confidence"] for d in evento["detections"]), default=None)


def grupos(eventos: list[dict[str, Any]], umbral: float) -> tuple[list[dict], list[dict]]:
    """(bajo el umbral, sobre el umbral), sin los cuadros sin detección."""
    con = [e for e in eventos if confianza(e) is not None]
    return [e for e in con if confianza(e) < umbral], [e for e in con if confianza(e) >= umbral]


def armar(eventos: list[dict[str, Any]], umbral: float) -> list[dict[str, Any]]:
    bajo, sobre = grupos(eventos, umbral)
    armados = []
    for n, evento in enumerate(bajo + sobre):
        captura = PASO_MS * n
        demora = evento["t_emit_ms"] - evento["t_capture_ms"]
        armados.append(dict(evento, t_capture_ms=captura, t_emit_ms=captura + demora))
    return armados


def texto(eventos: list[dict[str, Any]]) -> str:
    # El mismo formato de línea que `infer` (src/infer/eventos.py).
    lineas = (
        json.dumps(e, ensure_ascii=False, separators=(",", ":"), allow_nan=False) for e in eventos
    )
    return "".join(linea + "\n" for linea in lineas)


def leer_corrida(ruta: Path = CORRIDA) -> list[dict[str, Any]]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea]


def umbral_de_la_politica(ruta: Path = POLITICA) -> float:
    return float(yaml.safe_load(ruta.read_text(encoding="utf-8"))["umbral_confianza"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--revisar", action="store_true", help="no escribe; compara con la entrada")
    args = parser.parse_args(argv)
    esperado = texto(armar(leer_corrida(), umbral_de_la_politica()))
    if args.revisar:
        actual = ENTRADA.read_text(encoding="utf-8") if ENTRADA.is_file() else None
        if actual != esperado:
            print(f"{ENTRADA.relative_to(RAIZ).as_posix()}: no es la que arma este script")
            return 1
        print(f"{ENTRADA.relative_to(RAIZ).as_posix()}: OK")
        return 0
    ENTRADA.write_text(esperado, encoding="utf-8", newline="\n")
    print(f"{ENTRADA.relative_to(RAIZ).as_posix()}: {esperado.count(chr(10))} eventos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
