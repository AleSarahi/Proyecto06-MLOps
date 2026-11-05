"""P5-20: emisor de prueba del carro (`python -m carro`).

Ejemplos (IP por `--ip` o por la variable `P5_CARRO_IP`):

    uv run python -m carro --ip 192.168.1.50 stop
    uv run python -m carro --ip 192.168.1.50 orden AVANZAR --durante-ms 2000
    uv run python -m carro --ip 192.168.1.50 --enviar orden GIRAR_IZQ --durante-ms 1500
    uv run python -m carro --ip 192.168.1.50 --enviar prueba todas --bitacora b/pruebas.jsonl

Sin `--enviar` es modo seco: imprime los datagramas que mandaría y no abre la red. Con
`--enviar` las órdenes mueven los motores: primero con las ruedas en el aire. STOP no necesita
`--enviar`. Siempre termina con STOP, también con Ctrl+C.
"""

from __future__ import annotations

import argparse
import os
import sys

from .emisor import (
    GIRO,
    PERIODO_MS,
    PRUEBAS,
    VELOCIDAD,
    VIGENCIA_MS,
    Emisor,
    Recibida,
    sostener,
)
from .protocolo import ACCIONES, PUERTO, Orden, codificar_orden

GIRO_POR_ACCION = {"AVANZAR": 0.0, "GIRAR_IZQ": -GIRO, "GIRAR_DER": GIRO, "STOP": 0.0}


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m carro", description=__doc__.split("\n")[0])
    p.add_argument(
        "--ip", default=os.environ.get("P5_CARRO_IP"), help="IP del carro (o variable P5_CARRO_IP)"
    )
    p.add_argument("--puerto", type=int, default=PUERTO)
    p.add_argument("--bitacora", help="JSONL con cada datagrama enviado y recibido")
    p.add_argument(
        "--enviar",
        action="store_true",
        help="mandar de verdad (mueve motores); sin esto es modo seco",
    )
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("stop", help="manda STOP")

    o = sub.add_parser("orden", help="sostiene una orden y luego STOP")
    o.add_argument("accion", choices=[a for a in ACCIONES if a != "STOP"])
    o.add_argument("--velocidad", type=float, default=VELOCIDAD)
    o.add_argument("--giro", type=float, help="de -1 a 1; por omisión ±0.5 según la acción")
    o.add_argument("--durante-ms", type=float, default=1000)
    o.add_argument("--periodo-ms", type=float, default=PERIODO_MS)
    o.add_argument("--vigencia-ms", type=int, default=VIGENCIA_MS)

    t = sub.add_parser("prueba", help="rechazos y paro automático; necesita --enviar")
    t.add_argument("nombre", choices=[*PRUEBAS, "todas"])
    return p.parse_args(argv)


def _imprimir(r: Recibida) -> None:
    x = r.respuesta
    rtt = f"{r.rtt_ms:6.1f} ms" if r.rtt_ms is not None else "      -  "
    print(
        f"seq={x.seq:<6} {x.motivo:<13} {x.estado:<9} pwm={x.pwm_izq:>3}/{x.pwm_der:<3} "
        f"rtt={rtt} t_placa={x.t_placa_ms}"
    )


def _seco(args: argparse.Namespace) -> int:
    print("modo seco: no se manda nada (agrega --enviar para mover el carro)")
    if args.comando == "prueba":
        print("las pruebas necesitan la placa o el carro simulado: usa --enviar")
        return 2
    if args.comando == "orden":
        giro = args.giro if args.giro is not None else GIRO_POR_ACCION[args.accion]
        veces = max(int(args.durante_ms // args.periodo_ms), 1)
        o = Orden(1, 2, args.accion, args.velocidad, giro, args.vigencia_ms)
        print(f"STOP inicial, {veces} veces cada {args.periodo_ms:g} ms:")
        print(" ", codificar_orden(o).decode())
        print("y STOP al final")
    else:
        print(" ", codificar_orden(Orden(1, 1, "STOP", 0, 0, VIGENCIA_MS)).decode())
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    if args.comando != "stop" and not args.enviar:
        return _seco(args)
    if not args.ip:
        print("falta la IP del carro: --ip o P5_CARRO_IP", file=sys.stderr)
        return 2

    with Emisor(args.ip, args.puerto, args.bitacora) as em:
        print(f"sesion={em.sesion} destino={args.ip}:{args.puerto}")
        for r in em.recibir(200):
            _imprimir(r)
        if args.comando == "orden":
            return _orden(em, args)
        if args.comando == "prueba":
            return _pruebas(em, args.nombre)
    return 0


def _orden(em: Emisor, args: argparse.Namespace) -> int:
    giro = args.giro if args.giro is not None else GIRO_POR_ACCION[args.accion]
    recibidas = sostener(
        em,
        args.accion,
        args.velocidad,
        giro,
        args.durante_ms,
        args.periodo_ms,
        args.vigencia_ms,
        al_recibir=_imprimir,
    )
    if not recibidas:
        print("sin respuestas: revisa IP, puerto y que la placa esté en la misma red")
        return 1
    return 0


def _pruebas(em: Emisor, nombre: str) -> int:
    nombres = list(PRUEBAS) if nombre == "todas" else [nombre]
    fallas = 0
    for n in nombres:
        res = PRUEBAS[n](em)
        fallas += not res.pasa
        print(f"{'PASA ' if res.pasa else 'FALLA'} {n:<14} {res.detalle}")
        em.stop()
        em.recibir(200)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
