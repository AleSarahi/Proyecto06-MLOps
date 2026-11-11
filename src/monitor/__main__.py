"""CLI del centro de monitoreo (Proyecto 6).

uv run python -m monitor video descargar            # una vez, con red
uv run python -m monitor video extraer --segmento c1
uv run python -m monitor video verificar
uv run python -m monitor correr --segmento referencia --salida evidencias/p6/referencia/corrida
uv run python -m monitor referencia evidencias/p6/referencia/corrida
uv run python -m monitor correr --segmento c1 --salida evidencias/p6/escenarios/c1-normal
uv run python -m monitor verificar-capturas evidencias/p6/escenarios/c1-normal
uv run python -m monitor metricas evidencias/p6/escenarios/c1-normal
uv run python -m monitor importar evidencias/p6/referencia/corrida evidencias/p6/escenarios/*/
uv run python -m monitor portal

Extras (docs/p6/extras.md):
uv run python -m monitor correr --segmento s1-transicion --salida evidencias/p6/extras/s1-transicion
uv run python -m monitor correr --segmento s2-interrupcion --corte 20:40 --salida …
uv run python -m monitor metricas-extra evidencias/p6/escenarios/c1-normal
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import RAIZ, RUTA_VIGILANCIA, ErrorConfig, cargar, cargar_fuentes, cargar_vigilancia

DB_DEFECTO = RAIZ / "datos" / "p6" / "monitoreo.sqlite"


def _video(args: argparse.Namespace) -> int:
    from . import video

    fuentes = cargar_fuentes()
    if args.accion == "descargar":
        nombres = [args.video] if args.video else list(fuentes["videos"])
        for n in nombres:
            video.descargar(n, fuentes["videos"][n])
        return 0
    if args.accion == "extraer":
        cfg = cargar()
        segmentos = [args.segmento] if args.segmento else list(fuentes["segmentos"])
        for s in segmentos:
            video.extraer(s, fuentes, cfg.cada_n_frames)
        return 0
    # verificar: respaldo de frames (siempre) y videos locales (si están)
    estado = 0
    for s in fuentes["segmentos"]:
        carpeta = video.DIR_FRAMES / s
        errores = video.verificar_respaldo(carpeta) if carpeta.exists() else [f"falta {carpeta}"]
        print(f"respaldo {s}: {'OK' if not errores else '; '.join(errores[:3])}")
        estado |= bool(errores)
    for n, v in fuentes["videos"].items():
        try:
            print(f"video {n}: OK {video.verificar(n, v)[:12]}…")
        except ErrorConfig as exc:
            print(f"video {n}: {exc}")
    return int(estado)


def _correr(args: argparse.Namespace) -> int:
    from .corrida import Corrida, cargar_referencia, resumen_texto
    from .fuente import FuenteFrames, FuenteInterrumpida, FuenteVideo
    from .inferencia import Inferidor, reloj_monotonico
    from .video import DIR_FRAMES

    cfg = cargar(args.config, velocidad=args.velocidad)
    fuentes = cargar_fuentes()
    if args.segmento not in fuentes["segmentos"]:
        raise ErrorConfig(f"segmento desconocido: {args.segmento}")
    seg = fuentes["segmentos"][args.segmento]
    referencia = None if args.sin_referencia else cargar_referencia(cfg)
    reloj = reloj_monotonico()
    if args.modo == "frames":
        fuente = FuenteFrames(DIR_FRAMES / args.segmento, velocidad=cfg.velocidad, reloj_ms=reloj)
    else:
        fuente = FuenteVideo(
            args.segmento, fuentes, cfg.cada_n_frames, velocidad=cfg.velocidad, reloj_ms=reloj
        )
    if args.corte:
        fuente = FuenteInterrumpida(fuente, _cortes(args.corte), seg["inicio_s"] * 1000)
    vigilancia = None if args.sin_vigilancia else cargar_vigilancia(args.vigilancia)
    inferidor = Inferidor(cfg.detector_ruta, reloj)
    if inferidor.detector_config_sha256 != cfg.detector_config_sha256:
        raise ErrorConfig("el detector cargado no corresponde a config_ref")
    corrida = Corrida(
        cfg,
        fuente,
        inferidor,
        segmento=args.segmento,
        inicio_segmento_ms=seg["inicio_s"] * 1000,
        salida=Path(args.salida),
        db=Path(args.db),
        referencia=referencia,
        reloj_ms=reloj,
        comando=["python", "-m", "monitor", *sys.argv[1:]],
        run_id=args.run_id,
        vigilancia=vigilancia,
        carpeta_referencia=cfg.ruta_referencia.parent / "corrida",
    )
    corrida.correr()
    print(resumen_texto(Path(args.salida)))
    return 0


def _cortes(textos: list[str]) -> list[tuple[float, float]]:
    cortes = []
    for t in textos:
        try:
            a, b = (float(x) for x in t.split(":"))
        except ValueError as exc:
            raise ErrorConfig(f"--corte {t!r}: usa desde:hasta en segundos, p. ej. 20:40") from exc
        if not 0 <= a < b:
            raise ErrorConfig(f"--corte {t!r}: se requiere 0 <= desde < hasta")
        cortes.append((a * 1000, b * 1000))
    return cortes


def _metricas_extra(args: argparse.Namespace) -> int:
    from .metricas_extra import calcular

    cfg = cargar(args.config)
    ref = cfg.ruta_referencia.parent / "corrida"
    for c in args.corridas:
        m = calcular(Path(c), ref)
        destino = Path(c) / "metricas_extra.json"
        destino.write_text(
            json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        print(f"{c}:")
        for g, d in m["metricas"].items():
            print(
                f"  {g} {d['nombre']}: {d['corrida']['valor']} {d['unidad']} "
                f"(n={d['corrida']['n']})"
            )
    return 0


def _referencia(args: argparse.Namespace) -> int:
    from .referencia import calcular

    cfg = cargar(args.config)
    ref = calcular(Path(args.corrida))
    if ref["config_ref"] != cfg.config_ref:
        raise ErrorConfig("la corrida no se hizo con la configuración actual")
    destino = Path(args.salida) if args.salida else cfg.ruta_referencia
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(ref, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"referencia {destino}: proporcion_baja {ref['proporcion_baja']:.4f} "
        f"({ref['n_baja']}/{ref['n_candidatas']}, {ref['ventanas_suficientes']} ventanas)"
    )
    return 0


def _verificar_capturas(args: argparse.Namespace) -> int:
    from .capturas import verificar

    estado = 0
    for c in args.corridas:
        r = verificar(Path(c))
        print(
            f"{c}: {r['vinculadas_validas']}/{r['capturas']} capturas vinculadas y válidas; "
            f"{r['eventos_con_imagen']} eventos con imagen; problemas: {len(r['problemas'])}"
        )
        for p in r["problemas"]:
            print(f"  - {p}")
        estado |= bool(r["problemas"])
    return int(estado)


def _metricas(args: argparse.Namespace) -> int:
    from .metricas import calcular

    for c in args.corridas:
        m = calcular(Path(c))
        destino = Path(c) / "metricas.json"
        destino.write_text(
            json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        print(f"{c}:")
        for g, d in m["metricas"].items():
            print(
                f"  {g} {d['nombre']}: {d['corrida']['valor']} {d['unidad']} "
                f"(n={d['corrida']['n']})"
            )
    return 0


def _importar(args: argparse.Namespace) -> int:
    from .almacen import Almacen, importar

    with Almacen(args.db) as alm:
        for c in args.corridas:
            print(f"importada {importar(alm, Path(c))} desde {c}")
    return 0


def _portal(args: argparse.Namespace) -> int:
    from .portal import crear_app

    crear_app(Path(args.db)).run(host=args.host, port=args.puerto, debug=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(
        prog="python -m monitor",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("video", help="descargar/extraer/verificar el video de YouTube")
    v.add_argument("accion", choices=["descargar", "extraer", "verificar"])
    v.add_argument("--video")
    v.add_argument("--segmento")
    v.set_defaults(f=_video)

    c = sub.add_parser("correr", help="corre el monitoreo sobre un segmento")
    c.add_argument("--segmento", required=True)
    c.add_argument("--salida", required=True)
    c.add_argument("--modo", choices=["frames", "video"], default="frames")
    c.add_argument("--velocidad", type=float, help="1 = tiempo real, 0 = sin esperas")
    c.add_argument("--config", default=str(RAIZ / "config" / "p6" / "monitoreo.yaml"))
    c.add_argument("--db", default=str(DB_DEFECTO))
    c.add_argument("--run-id")
    c.add_argument(
        "--sin-referencia",
        action="store_true",
        help="solo para la corrida de referencia: la regla sostenida queda sin_referencia",
    )
    c.add_argument(
        "--corte",
        action="append",
        metavar="DESDE:HASTA",
        help="inyecta una caída de la fuente entre esos segundos del segmento (extra #33)",
    )
    c.add_argument("--vigilancia", default=str(RUTA_VIGILANCIA))
    c.add_argument("--sin-vigilancia", action="store_true", help="no vigilar la fuente")
    c.set_defaults(f=_correr)

    r = sub.add_parser("referencia", help="calcula referencia.json desde una corrida")
    r.add_argument("corrida")
    r.add_argument("--salida")
    r.add_argument("--config", default=str(RAIZ / "config" / "p6" / "monitoreo.yaml"))
    r.set_defaults(f=_referencia)

    vc = sub.add_parser("verificar-capturas", help="comprueba que las capturas resuelven")
    vc.add_argument("corridas", nargs="+")
    vc.set_defaults(f=_verificar_capturas)

    m = sub.add_parser("metricas", help="recalcula metricas.json de una corrida")
    m.add_argument("corridas", nargs="+")
    m.set_defaults(f=_metricas)

    mx = sub.add_parser("metricas-extra", help="calcula metricas_extra.json (X1-X5)")
    mx.add_argument("corridas", nargs="+")
    mx.add_argument("--config", default=str(RAIZ / "config" / "p6" / "monitoreo.yaml"))
    mx.set_defaults(f=_metricas_extra)

    i = sub.add_parser("importar", help="carga corridas exportadas en la base del portal")
    i.add_argument("corridas", nargs="+")
    i.add_argument("--db", default=str(DB_DEFECTO))
    i.set_defaults(f=_importar)

    po = sub.add_parser("portal", help="portal de eventos y alertas")
    po.add_argument("--db", default=str(DB_DEFECTO))
    po.add_argument("--host", default="127.0.0.1")
    po.add_argument("--puerto", type=int, default=8000)
    po.set_defaults(f=_portal)

    args = p.parse_args(argv)
    try:
        return args.f(args)
    except ErrorConfig as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
