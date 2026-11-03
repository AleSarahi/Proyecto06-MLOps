"""Corrida de P5-14: las 8 secuencias de evaluación en un solo run, de `infer` a la trazabilidad.

Uso (desde la raíz del repo, conectada a la corriente y con lo demás cerrado):

    uv run --locked python resultados/p5-14-corrida.py --pesos <ruta>/yolo11n.pt

`infer` acepta una secuencia por llamada, y `trazabilidad construir` une un `run_id` a la vez. Para
tener las métricas de P5-13 sobre los 107 cuadros en un solo `resumen.json`, se hace una llamada a
`infer` por secuencia (S01 a S08, en orden), todas con el mismo `run_id`. Los `t_capture_ms` de
cada secuencia son los de su `captura.jsonl`, recorridos para que el reloj siga creciendo: cada
secuencia empieza `--hueco-ms` después del último cuadro de la anterior (250 ms, el periodo normal
entre cuadros). Así B ve una sola corrida continua. `infer` espera a cada instante antes de
procesar el cuadro, así que la edad de cada cuadro es real.

Después corre `python -m control`, `python -m trazabilidad construir` (con los hashes congelados
en el paso 2 de #13) y `python -m trazabilidad recalcular`, y escribe en `--salida`:

- `infer/Sxx.jsonl`: la salida de cada llamada a `infer`; `detector.jsonl`: las 8 juntas.
- `corrida/`: lo que escribe `control`.
- `trazabilidad/`: `por_cuadro.jsonl`, `resumen.json` y lo demás de `construir`.
- `corrida.json`: cómo se hizo (commit, energía, hardware, desplazamiento de cada secuencia, el
  SHA-256 de cada JPEG comprobado contra `captura.jsonl` y la salida de cada comando).

Los JPEG se copian a una carpeta temporal porque `infer` pide un directorio solo con JPEG; antes se
comprueba su SHA-256 contra `captura.jsonl`. Sale con el peor código de los comandos (0, 1 o 2), o
con 2 si la salida no es una carpeta nueva o vacía o un JPEG no coincide; con 1 si no estaba
conectada a la corriente.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from bench.arnes import energia, hardware  # noqa: E402

CUADROS = RAIZ / "datos" / "cuadros"
SECUENCIAS = tuple(f"S0{n}" for n in range(1, 9))
# Registrados en el paso 2 de #13 (tag config-detector-v1).
MODEL_SHA256 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
CONFIG_SHA256 = "6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08"


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()  # NOSONAR (S8707)


def _captura(secuencia: str) -> list[dict[str, Any]]:
    texto = (CUADROS / secuencia / "captura.jsonl").read_text(encoding="utf-8")
    filas = [json.loads(linea) for linea in texto.splitlines() if linea.strip()]
    return sorted(filas, key=lambda f: f["archivo"])


def _correr(nombre: str, argumentos: list[str], registro: list[dict[str, Any]]) -> int:
    proceso = subprocess.run(
        [sys.executable, "-m", *argumentos],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    salida = (proceso.stdout + proceso.stderr).strip()
    print(f"{nombre}: salida {proceso.returncode}")
    if salida:
        print(salida)
    registro.append({"paso": nombre, "salida": proceso.returncode, "texto": salida})
    return proceso.returncode


def _relativa(ruta: Path) -> str:
    try:
        return ruta.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return ruta.name


def _arg(ruta: Path) -> str:
    """Relativa al repo si está dentro (así `run.json` no guarda rutas de la máquina)."""
    try:
        return ruta.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(ruta)


def _sin_rutas_personales(texto: str, salida: Path) -> str:
    """Quita del texto registrado las rutas de la máquina (la salida y la raíz del repo)."""
    for ruta, cambio in ((salida.resolve(), _relativa(salida)), (RAIZ, ".")):
        for forma in (str(ruta), ruta.as_posix()):
            texto = texto.replace(forma, cambio)
    return texto


def _infer(args: argparse.Namespace, temporal: Path, registro: list[dict[str, Any]]) -> dict:
    """Una llamada a `infer` por secuencia; devuelve el desplazamiento y los JPEG de cada una."""
    secuencias: dict[str, Any] = {}
    inicio = 0
    for secuencia in SECUENCIAS:
        filas = _captura(secuencia)
        carpeta = temporal / secuencia
        carpeta.mkdir()
        for fila in filas:
            origen = CUADROS / secuencia / fila["archivo"]
            if _sha256(origen) != fila["sha256"]:
                raise ValueError(f"{origen.name} no coincide con su captura.jsonl")
            shutil.copyfile(origen, carpeta / fila["archivo"])
        desplazamiento = inicio - filas[0]["t_capture_ms"]
        tiempos = [fila["t_capture_ms"] + desplazamiento for fila in filas]
        salida = args.salida / "infer" / f"{secuencia}.jsonl"
        comando = ["infer", "--input", str(carpeta), "--weights", str(args.pesos)]
        comando += ["--output", _arg(salida), "--run-id", args.run_id, "--sequence-id", secuencia]
        for tiempo in tiempos:
            comando += ["--capture-ms", str(tiempo)]
        codigo = _correr(f"infer {secuencia}", comando, registro)
        if codigo == 2:
            raise ValueError(f"infer no pudo correr {secuencia}")
        secuencias[secuencia] = {
            "cuadros": len(filas),
            "desplazamiento_ms": desplazamiento,
            "t_capture_ms": [tiempos[0], tiempos[-1]],
            "jpeg_sha256": {fila["archivo"]: fila["sha256"] for fila in filas},
        }
        inicio = tiempos[-1] + args.hueco_ms
    return secuencias


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python resultados/p5-14-corrida.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--pesos", type=Path, required=True, help="yolo11n.pt verificado")
    parser.add_argument("--salida", type=Path, default=RAIZ / "resultados" / "p5-14")
    parser.add_argument("--run-id", default="p5-14-s01-s08")
    parser.add_argument("--hueco-ms", type=int, default=250)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    salida: Path = args.salida.resolve()
    if salida.exists() and (not salida.is_dir() or any(salida.iterdir())):  # NOSONAR (S8707)
        print(f"{salida} no está vacía: usa una carpeta nueva", file=sys.stderr)
        return 2
    (salida / "infer").mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
    registro: list[dict[str, Any]] = []
    corriente = energia()
    try:
        with tempfile.TemporaryDirectory() as temporal:
            secuencias = _infer(args, Path(temporal), registro)
    except (OSError, ValueError) as exc:
        print(f"no se completó la corrida: {exc}", file=sys.stderr)
        return 2

    detector = salida / "detector.jsonl"
    with detector.open("w", encoding="utf-8", newline="\n") as archivo:  # NOSONAR (S8707)
        for secuencia in SECUENCIAS:
            archivo.write((salida / "infer" / f"{secuencia}.jsonl").read_text(encoding="utf-8"))

    corrida, trazabilidad = salida / "corrida", salida / "trazabilidad"
    codigos = [r["salida"] for r in registro]
    codigos.append(
        _correr(
            "control",
            [
                *("control", "--entrada", _arg(detector), "--config", "config/control/"),
                "--salida",
                _arg(corrida),
            ],
            registro,
        )
    )
    codigos.append(
        _correr(
            "trazabilidad construir",
            [
                *("trazabilidad", "construir", "--corrida", _arg(corrida)),
                *("--anotaciones", "datos/anotaciones.jsonl", "--salida", _arg(trazabilidad)),
                *("--model-sha256", MODEL_SHA256, "--config-sha256", CONFIG_SHA256),
            ],
            registro,
        )
    )
    codigos.append(
        _correr(
            "trazabilidad recalcular", ["trazabilidad", "recalcular", _arg(trazabilidad)], registro
        )
    )

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=RAIZ, capture_output=True, text=True, check=False
    ).stdout.strip()
    resumen = {
        "version": 1,
        "run_id": args.run_id,
        "commit": commit,
        "energia_al_empezar": corriente,
        "energia_al_terminar": energia(),
        "hardware": hardware(),
        "hueco_ms": args.hueco_ms,
        "model_sha256": MODEL_SHA256,
        "config_sha256": CONFIG_SHA256,
        "pesos": args.pesos.name,
        "secuencias": secuencias,
        "pasos": [{**r, "texto": _sin_rutas_personales(r["texto"], salida)} for r in registro],
    }
    texto = json.dumps(resumen, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    (salida / "corrida.json").write_text(texto, encoding="utf-8", newline="\n")  # NOSONAR (S8707)
    if corriente != "corriente":
        print(f"advertencia: energía {corriente}; la corrida va conectada", file=sys.stderr)
        codigos.append(1)
    return max(codigos)


if __name__ == "__main__":
    raise SystemExit(main())
