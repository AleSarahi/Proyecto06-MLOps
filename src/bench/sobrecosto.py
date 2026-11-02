"""Lo que paga `infer` y el arnés no mide: leer el JPEG y la preparación de Ultralytics (P5-15).

Uso:
    python -m bench.sobrecosto --pesos <ruta>/yolo11n.pt --salida mediciones/sobrecosto/ \
        [--fotos docs/carro/] [--repeticiones 20] [--model-sha256 HASH --config-sha256 HASH]

El arnés (`python -m bench`) cronometra `preprocesar`, `inferir` y `posprocesar` de `bench.yolo`
por separado y parte de la imagen ya decodificada. `infer` (P5-05) llama a
`DetectorJPEG.inferir`, que además lee el JPEG y pasa por `predictor(...)` de Ultralytics, que
prepara cada llamada (fuente, lote, perfiles) antes de las mismas tres etapas. El plazo de 500 ms
de P5-06 cubre la solicitud completa, así que P5-16 tiene que sumar esa diferencia.

En cada llamada a `DetectorJPEG.inferir` (el mismo objeto que envuelve `bench.yolo`) se mide:

- `infer_ms`: tiempo de pared de `inferir(ruta)`, de leer el JPEG a las detecciones.
- `predictor_ms`: el `elapsed_ms` de `inferir`, la llamada `predictor(...)` de Ultralytics.
- `etapas_ms`: dentro de esa misma llamada, `preprocess` + `inference` + `postprocess` del
  predictor, cronometradas con `perf_counter_ns`: las mismas funciones que mide el arnés.
- `diferencia_ms` = `infer_ms` - `etapas_ms`: lo que hay que sumar al total del arnés. Se parte en
  `fuera_del_predictor_ms` (leer el JPEG, sus revisiones y `_extraer_detecciones`) y
  `preparacion_ms` (lo que hace `predictor(...)` alrededor de las tres etapas).

Todo sale de la misma llamada, así que no hay que restar dos mediciones distintas. Queda un poco
de más: `_extraer_detecciones` también entra en el `posprocesar` del arnés, así que se cuenta dos
veces (del lado seguro). Ninguna parte arma el evento ni pasa por B: eso lo mide el arnés.

Se mide en las mismas condiciones que la corrida final (conectada, con lo demás cerrado).
Escribe en `--salida` (carpeta nueva o vacía) `sobrecosto.csv`, una fila por medición, y
`sobrecosto.json`, con el resumen, el hardware, la energía y los hashes.

Salida: 0 si midió conectada y sin advertencias; 1 con advertencias (en batería, hashes sin
comprobar); 2 si no se puede medir (pesos, fotos, hashes distintos o carpeta no vacía).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .arnes import energia, hardware, percentil, runtime, ruta_publicable, sha256_archivo

RAIZ = Path(__file__).resolve().parents[2]
FOTOS = RAIZ / "docs" / "carro"
CALENTAMIENTOS = 3
REPETICIONES = 20
MEDIDAS = (
    "infer_ms",
    "predictor_ms",
    "etapas_ms",
    "diferencia_ms",
    "fuera_del_predictor_ms",
    "preparacion_ms",
)
COLUMNAS = ("repeticion", "foto", *MEDIDAS, "detecciones")


ETAPAS_PREDICTOR = ("preprocess", "inference", "postprocess")


class _Cronometro:
    """Envuelve las tres etapas del predictor con `perf_counter_ns`.

    `results[0].speed` de Ultralytics usa `time.time()`, que en Windows avanza a saltos de
    ~15 ms: no sirve para restar. Los envoltorios son atributos del objeto y se quitan al salir,
    así que el predictor queda como estaba.
    """

    def __init__(self, predictor: Any):
        self.predictor = predictor
        self.ns = 0

    def _envolver(self, funcion: Any) -> Any:
        def cronometrada(*args: Any, **kwargs: Any) -> Any:
            inicio = time.perf_counter_ns()
            try:
                return funcion(*args, **kwargs)
            finally:
                self.ns += time.perf_counter_ns() - inicio

        return cronometrada

    def __enter__(self) -> _Cronometro:
        for nombre in ETAPAS_PREDICTOR:
            setattr(self.predictor, nombre, self._envolver(getattr(self.predictor, nombre)))
        return self

    def __exit__(self, *_: Any) -> None:
        for nombre in ETAPAS_PREDICTOR:
            delattr(self.predictor, nombre)


def medir_una(detector: Any, ruta: Path) -> dict[str, Any]:
    """Una llamada a `DetectorJPEG.inferir`, con sus tres etapas cronometradas por dentro."""
    jpeg = detector._detector
    with _Cronometro(jpeg.predictor) as cronometro:
        inicio = time.perf_counter_ns()
        resultado = jpeg.inferir(ruta)
        infer = (time.perf_counter_ns() - inicio) / 1e6
    etapas = cronometro.ns / 1e6
    return {
        "foto": ruta.name,
        "infer_ms": infer,
        "predictor_ms": resultado.elapsed_ms,
        "etapas_ms": etapas,
        "diferencia_ms": infer - etapas,
        "fuera_del_predictor_ms": infer - resultado.elapsed_ms,
        "preparacion_ms": resultado.elapsed_ms - etapas,
        "detecciones": len(resultado.detections),
    }


def medir(
    detector: Any, fotos: Sequence[Path], calentamientos: int, repeticiones: int
) -> list[dict[str, Any]]:
    for _ in range(calentamientos):
        for ruta in fotos:
            medir_una(detector, ruta)
    return [
        {"repeticion": repeticion, **medir_una(detector, ruta)}
        for repeticion in range(repeticiones)
        for ruta in fotos
    ]


def resumir(filas: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    resumen = {}
    for medida in MEDIDAS:
        valores = [f[medida] for f in filas]
        resumen[medida] = {
            "n": len(valores),
            "p50": percentil(valores, 0.50),
            "p95": percentil(valores, 0.95),
            "maximo": max(valores),
            "minimo": min(valores),
            "media": sum(valores) / len(valores),
        }
    return resumen


def _fotos(rutas: Sequence[Path]) -> list[Path]:
    fotos: list[Path] = []
    for ruta in rutas:
        if ruta.is_dir():  # NOSONAR (S8707)
            fotos += sorted(p for p in ruta.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"})
        else:
            fotos.append(ruta)
    if not fotos:
        raise ValueError("no hay fotos JPEG")
    return fotos


def _hash(valor: str) -> str:
    if len(valor) != 64 or not set(valor) <= set("0123456789abcdef"):
        raise argparse.ArgumentTypeError("debe tener 64 caracteres hex en minúsculas")
    return valor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bench.sobrecosto",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--pesos", type=Path, required=True, help="yolo11n.pt verificado")
    parser.add_argument("--salida", type=Path, required=True, help="carpeta nueva o vacía")
    parser.add_argument("--fotos", type=Path, nargs="+", default=[FOTOS], help="JPEG o carpetas")
    parser.add_argument("--repeticiones", type=int, default=REPETICIONES)
    parser.add_argument("--model-sha256", type=_hash, help="SHA-256 de los pesos congelados")
    parser.add_argument("--config-sha256", type=_hash, help="SHA-256 de la config congelada")
    parser.add_argument("--equipo", help="Máquina declarada (PEND-05)")
    return parser


def _crear_detector(args: argparse.Namespace, esperados: dict[str, str | None]) -> Any:
    """El detector de `bench.yolo`; falla si sus hashes no son los indicados."""
    from .yolo import crear

    detector = crear(str(args.pesos))
    for nombre, esperado in esperados.items():
        if esperado is not None and getattr(detector, nombre) != esperado:
            raise ValueError(f"{nombre} del detector no es el indicado")
    return detector


def _advertencias(
    args: argparse.Namespace, corriente: str, esperados: dict[str, str | None]
) -> list[str]:
    advertencias = []
    if corriente != "corriente":
        advertencias.append(f"energía: {corriente}; la medición final va conectada")
    if None in esperados.values():
        advertencias.append("sin --model-sha256 o --config-sha256: los hashes no se comprobaron")
    if not args.equipo:
        advertencias.append("no se declaró el equipo (--equipo, PEND-05)")
    return advertencias


def _escribir_csv(ruta: Path, filas: Sequence[dict[str, Any]]) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as archivo:  # NOSONAR (S8707)
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS, lineterminator="\n")
        escritor.writeheader()
        for fila in filas:
            escritor.writerow(
                {k: f"{v:.4f}" if isinstance(v, float) else v for k, v in fila.items()}
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.repeticiones < 1:
        parser.error("--repeticiones debe ser al menos 1")
    salida = args.salida
    if salida.exists() and (not salida.is_dir() or any(salida.iterdir())):  # NOSONAR (S8707)
        parser.error(f"{salida} no está vacía: usa una carpeta nueva")

    esperados = {"model_sha256": args.model_sha256, "config_sha256": args.config_sha256}
    try:
        fotos = _fotos(args.fotos)
        detector = _crear_detector(args, esperados)
        filas = medir(detector, fotos, CALENTAMIENTOS, args.repeticiones)
    except (OSError, ValueError) as exc:
        print(f"no se mide: {exc}", file=sys.stderr)
        return 2

    corriente = energia()
    advertencias = _advertencias(args, corriente, esperados)
    salida.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
    ruta_csv = salida / "sobrecosto.csv"
    _escribir_csv(ruta_csv, filas)

    resumen = resumir(filas)
    salida_json = {
        "version": 1,
        "equipo": args.equipo,
        "hardware": hardware(),
        "energia": corriente,
        "runtime": runtime(detector),
        "model_sha256": detector.model_sha256,
        "config_sha256": detector.config_sha256,
        "hashes_comprobados": None not in esperados.values(),
        "protocolo": {
            "calentamientos": CALENTAMIENTOS,
            "repeticiones": args.repeticiones,
            "reloj": "time.perf_counter_ns",
            "diferencia": (
                "infer_ms - etapas_ms en la misma llamada: leer el JPEG, sus revisiones y la "
                "preparación de Ultralytics (más _extraer_detecciones, que el arnés sí mide)"
            ),
        },
        "fotos": {ruta_publicable(f): sha256_archivo(f) for f in fotos},
        "resumen": resumen,
        "por_foto": {
            f.name: percentil([x["diferencia_ms"] for x in filas if x["foto"] == f.name], 0.5)
            for f in fotos
        },
        "archivos": {"sobrecosto.csv": sha256_archivo(ruta_csv)},
        "advertencias": advertencias,
    }
    texto = json.dumps(salida_json, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    (salida / "sobrecosto.json").write_text(texto, encoding="utf-8")  # NOSONAR (S8707)

    for medida in ("diferencia_ms", "fuera_del_predictor_ms", "preparacion_ms"):
        r = resumen[medida]
        print(f"{medida}: p50={r['p50']:.2f} p95={r['p95']:.2f} máx={r['maximo']:.2f} ms")
    for advertencia in advertencias:
        print(f"advertencia: {advertencia}", file=sys.stderr)
    print(f"resultados en {salida.as_posix()}/")
    return 1 if advertencias else 0


if __name__ == "__main__":
    raise SystemExit(main())
