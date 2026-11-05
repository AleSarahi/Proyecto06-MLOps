"""Lazo en vivo: ESP32-CAM → detector → política → carro (P5-21).

    uv run python -m vivo --ip <ip> --salida resultados/vivo-seco          # modo seco (omisión)
    uv run python -m vivo --ip <ip> --salida resultados/vivo-1 --enviar    # manda a los motores

La IP del carro va por `--ip` o por la variable `P5_CARRO_IP`; el stream (puerto 81) y las
órdenes UDP (puerto 4210) son de la misma placa. No hay credenciales: ningún archivo del repo
lleva la IP.

**Modo seco (omisión):** lee el stream real, corre el detector, la política y el supervisor y
registra todo, pero no abre el socket del carro ni manda nada. Mandar a los motores exige
`--enviar`, una terminal con teclado (para el paro) y escribir la palabra de confirmación de
`config/vivo.yaml`.

**Paro:** `e` = emergencia (STOP enclavado), `r` = rearme (solo con un cuadro fresco y válido),
`q` = salir. Ctrl+C, una excepción o `--duracion-s` también cierran. Al cerrar, siempre se manda
STOP antes de salir. Sin cuadros (cámara desconectada) frena el watchdog; si el detector muere, cada
cuadro sale como error y el supervisor da STOP.

En `--salida` queda lo de `python -m control` (`detecciones.jsonl`, `decisiones.jsonl`,
`comandos.jsonl`, `errores.jsonl`), `respuestas.jsonl` (lo que contesta la placa, con el tiempo de
ida y vuelta), la bitácora del emisor (`carro.jsonl`, solo con `--enviar`) y `vivo.json` (hashes,
conteos y latencias). Los eventos se validan con `python -m contrato <salida>/detecciones.jsonl`.

Salida: 0 si cerró sin fallos, 1 si hubo un fallo (ya con STOP), 2 si no arrancó por la
configuración, la IP o los hashes, 3 si no se confirmó el envío a motores.
"""

from __future__ import annotations

import argparse
import signal
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import yaml

from control.__main__ import (
    CARPETA_CONFIG,
    NOMBRE_PLAZOS,
    NOMBRE_POLITICA,
    ErrorPlazos,
    cargar_plazos,
)
from control.config import ErrorConfigPolitica, cargar_config_politica
from infer.config import RUTA_CONFIG_DETECTOR
from infer.cuadro import DetectorEnVivo
from infer.eventos import ErrorRunInfer
from infer.reloj import leer_reloj_s
from infer.trabajador import ErrorTrabajador

from .config import RAIZ, RUTA_CONFIG_VIVO, ErrorConfigVivo, cargar_config_vivo, resolver_ip
from .corrida import CorridaVivo
from .lazo import LazoVivo
from .lector import LectorStream, abrir_stream
from .teclado import Teclado


def _como_ctrl_c(_signo: int, _marco: object) -> None:
    raise KeyboardInterrupt


def _confirmar(palabra: str) -> bool:
    print("ATENCIÓN: se van a mandar órdenes a los MOTORES del carro.")
    print("Ruedas en el aire o carro en un lugar libre, y la mano en la tecla de emergencia.")
    try:
        return input(f"Escribe {palabra} para continuar: ").strip() == palabra
    except EOFError:
        return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m vivo",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ip", help="IP del carro; si falta se usa la variable P5_CARRO_IP")
    parser.add_argument("--salida", type=Path, required=True, help="carpeta nueva para el run")
    parser.add_argument(
        "--enviar", action="store_true", help="manda las órdenes a los motores (pide confirmación)"
    )
    parser.add_argument("--run-id", help="ID del run; por omisión vivo-<fecha UTC>")
    parser.add_argument("--duracion-s", type=float, help="cierra solo después de estos segundos")
    parser.add_argument("--guardar-cuadros", action="store_true", help="guarda cada JPEG atendido")
    parser.add_argument(
        "--pesos", type=Path, help="checkpoint .pt; por omisión el de detector.json"
    )
    parser.add_argument("--config-detector", type=Path, default=RUTA_CONFIG_DETECTOR)
    parser.add_argument("--config-vivo", type=Path, default=RUTA_CONFIG_VIVO)
    parser.add_argument(
        "--config", type=Path, default=CARPETA_CONFIG, help="carpeta con plazos y política"
    )
    args = parser.parse_args(argv)

    try:
        vivo = cargar_config_vivo(args.config_vivo)
        plazos = cargar_plazos(args.config / NOMBRE_PLAZOS)
        politica = cargar_config_politica(args.config / NOMBRE_POLITICA)
        ip = resolver_ip(args.ip)
    except (OSError, yaml.YAMLError, ErrorConfigVivo, ErrorPlazos, ErrorConfigPolitica) as exc:
        print(f"vivo: configuración inválida: {exc}", file=sys.stderr)
        return 2
    if ip is None:
        print("vivo: falta la IP del carro (--ip o la variable P5_CARRO_IP)", file=sys.stderr)
        return 2
    if args.duracion_s is not None and args.duracion_s <= 0:
        print("vivo: --duracion-s debe ser mayor que 0", file=sys.stderr)
        return 2
    if args.salida.exists() and any(args.salida.iterdir()):
        print(f"vivo: {args.salida} ya tiene archivos; usa una carpeta nueva", file=sys.stderr)
        return 2

    run_id = args.run_id or datetime.now(UTC).strftime("vivo-%Y%m%dT%H%M%SZ")
    pesos = args.pesos
    origen_s = leer_reloj_s()
    try:
        detector = DetectorEnVivo(
            args.config_detector,
            pesos if pesos is not None else _pesos_por_omision(args.config_detector),
            run_id=run_id,
            sequence_id=vivo.sequence_id,
            origen_s=origen_s,
        )
    except (OSError, ValueError) as exc:  # incluye ErrorConfigDetector y ErrorRunInfer
        print(f"vivo: no se pudo preparar el detector: {exc}", file=sys.stderr)
        return 2
    if (detector.model_sha256, detector.config_sha256) != (vivo.model_sha256, vivo.config_sha256):
        print(
            "vivo: el modelo o la configuración del detector no son los calificados\n"
            f"  modelo       {detector.model_sha256}\n  esperado     {vivo.model_sha256}\n"
            f"  configuración {detector.config_sha256}\n  esperada     {vivo.config_sha256}",
            file=sys.stderr,
        )
        return 2

    teclado = Teclado()
    if args.enviar:
        if not teclado.disponible:
            print("vivo: --enviar necesita una terminal con teclado para el paro", file=sys.stderr)
            return 3
        if not _confirmar(vivo.confirmacion):
            print("vivo: sin confirmación; no se manda nada", file=sys.stderr)
            return 3

    signal.signal(signal.SIGTERM, _como_ctrl_c)
    print(f"vivo: arrancando el detector ({run_id}); puede tardar unos segundos...")
    try:
        detector.iniciar()
    except (ErrorTrabajador, ErrorRunInfer) as exc:
        detector.cerrar()
        print(f"vivo: el detector no arrancó: {exc}", file=sys.stderr)
        return 2

    emisor = None
    try:
        # La carpeta la elige quien corre el comando (igual que `python -m control --salida`).
        args.salida.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
        if args.enviar:
            # Importar aquí: el modo seco no necesita el emisor ni abre ningún socket. Crear el
            # emisor manda el primer STOP de la sesión.
            from carro.emisor import Emisor

            emisor = Emisor(ip, vivo.puerto_carro, bitacora=args.salida / "carro.jsonl")
        corrida = CorridaVivo(args.salida, plazos, politica, detector.ahora_ms, emisor)
        lector = LectorStream(
            lambda: abrir_stream(ip, vivo.puerto_stream, vivo.ruta_stream, vivo.espera_stream_s),
            detector.ahora_ms,
            max_cuadro=vivo.max_cuadro_bytes,
            reconexion_s=vivo.reconexion_s,
        )
        lazo = LazoVivo(
            corrida,
            lector,
            detector,
            vivo,
            plazos["paso_reloj_ms"],
            args.salida / "_cuadros",
            teclas=teclado.tecla if teclado.disponible else None,
            duracion_s=args.duracion_s,
            guardar_cuadros=args.guardar_cuadros,
            archivos_de_config={
                "vivo.yaml": args.config_vivo,
                NOMBRE_PLAZOS: args.config / NOMBRE_PLAZOS,
                NOMBRE_POLITICA: args.config / NOMBRE_POLITICA,
                "detector.json": args.config_detector,
            },
        )
    except BaseException:
        # Si algo falla armando el lazo, el carro no queda con una orden: STOP y cierre.
        if emisor is not None:
            emisor.cerrar()
        detector.cerrar()
        raise

    modo = "MOTORES" if args.enviar else "seco (no manda nada)"
    print(f"vivo: modo {modo}; modelo {vivo.model_sha256[:8]}… config {vivo.config_sha256[:8]}…")
    print(
        f"vivo: '{vivo.tecla_emergencia}' emergencia · '{vivo.tecla_rearme}' rearme · "
        f"'{vivo.tecla_salida}' salir · Ctrl+C cierra"
    )
    with teclado:
        return lazo.correr()


def _pesos_por_omision(config_ruta: Path) -> Path:
    from infer.config import cargar_config_detector

    ruta = cargar_config_detector(config_ruta).weights_path
    return ruta if ruta.is_absolute() else RAIZ / ruta


if __name__ == "__main__":
    raise SystemExit(main())
