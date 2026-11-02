"""Predictor CPU persistente, aislado con spawn y supervisado por el publicador A."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import queue
import sys
import time
from collections.abc import Callable, Sequence
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch

from .config import ConfigDetector, cargar_config_detector
from .detector import DetectorJPEG
from .eventos import (
    _ID,
    ErrorRunInfer,
    _archivos,
    _capturas,
    _esperar_reloj,
    _evento_cuadro,
    _evento_error,
    _serializar_evento,
)
from .pesos import cargar_pesos
from .plazos import RUTA_PLAZOS, PlazosInfer, cargar_plazos_infer_con_hash
from .rutas_seguras import abrir_exclusivo, verificar_checkpoint

INICIO_GUARDA_S = 120.0  # Guarda operativa de arranque, no umbral de aceptación de latencia.
CIERRE_GUARDA_S = 1.0
PESO_OFICIAL_SHA256 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
PESO_OFICIAL_BYTES = 5_613_764


class ErrorTrabajador(RuntimeError):
    """No se pudo iniciar, verificar o recuperar el predictor."""


def _desglosar_ready_ns(marcas: tuple[int, int, int, int, int, int]) -> dict[str, Any]:
    """Descompone una línea de tiempo monotónica compartida por principal e hijo."""
    inicio, creacion, hijo, carga, calentamiento, ready = marcas
    if not (inicio <= creacion <= ready and inicio <= hijo <= carga <= calentamiento <= ready):
        raise ErrorTrabajador("marcas monotónicas de READY inconsistentes")

    def ms(ns: int) -> float:
        return ns / 1_000_000

    return {
        "duracion_ms": ms(ready - inicio),
        "fases_ms": {
            "creacion_proceso": ms(creacion - inicio),
            "arranque_hijo": ms(max(0, hijo - creacion)),
            "carga_verificacion": ms(carga - hijo),
            "calentamiento": ms(calentamiento - carga),
            "entrega_ready": ms(ready - calentamiento),
        },
        "solapamiento_creacion_hijo_ms": ms(max(0, creacion - hijo)),
    }


def crear_detector_real(config_ruta: Path, pesos_ruta: Path) -> DetectorJPEG:
    """Se ejecuta solo dentro del proceso hijo."""
    config = cargar_config_detector(config_ruta)
    return DetectorJPEG(cargar_pesos(pesos_ruta, config), config)


def _bucle_trabajador(
    solicitudes: Any,
    respuestas: Any,
    fabrica: Callable[[Path, Path], DetectorJPEG],
    config_ruta: Path,
    pesos_ruta: Path,
    hash_config: str,
    hash_modelo: str,
    generacion: int,
) -> None:
    inicio_carga_ns = time.monotonic_ns()
    try:
        detector = fabrica(config_ruta, pesos_ruta)
        if (
            detector.config.config_sha256 != hash_config
            or detector.cargado.config_sha256 != hash_config
            or detector.cargado.model_sha256 != hash_modelo
        ):
            raise ErrorTrabajador("los SHA-256 del trabajador no coinciden con el run")
        if detector.config.torch_threads != 2:
            raise ErrorTrabajador("la configuración efectiva no usa torch_threads=2")
        fin_carga_ns = time.monotonic_ns()
        detector.calentar()
        if torch.get_num_threads() != 2:
            raise ErrorTrabajador("el trabajador no confirmó torch_threads=2 tras calentar")
        fin_calentamiento_ns = time.monotonic_ns()
        respuestas.put(
            (
                generacion,
                "ready",
                hash_modelo,
                hash_config,
                2,
                (inicio_carga_ns, fin_carga_ns, fin_calentamiento_ns),
            )
        )
    except Exception as exc:
        respuestas.put((generacion, "init_error", f"{type(exc).__name__}: {exc}"))
        return

    while True:
        solicitud = solicitudes.get()
        if solicitud is None:
            return
        gen, request_id, ruta, run_id, secuencia, indice, frame_id, captura, origen, edad = (
            solicitud
        )
        if gen != generacion:
            continue

        def transcurrido(origen_run: float = origen) -> float:
            return (time.monotonic() - origen_run) * 1000

        def aviso(dimensiones: tuple[int, int], solicitud_id: int = request_id) -> None:
            respuestas.put((generacion, solicitud_id, "decoded", dimensiones))

        evento = _evento_cuadro(
            detector,
            Path(ruta),
            run_id,
            secuencia,
            indice,
            frame_id,
            captura,
            transcurrido,
            edad,
            aviso,
        )
        respuestas.put((generacion, request_id, "result", evento))


class PredictorSupervisado:
    """Una solicitud en vuelo; cada reinicio usa canales y generación nuevos."""

    def __init__(
        self,
        config_ruta: Path,
        pesos_ruta: Path,
        config: ConfigDetector,
        *,
        fabrica: Callable[[Path, Path], DetectorJPEG] = crear_detector_real,
        inicio_guarda_s: float = INICIO_GUARDA_S,
        reloj: Callable[[], float] = time.monotonic,
        trazas: list[dict[str, Any]] | None = None,
    ) -> None:
        self.contexto = mp.get_context("spawn")
        self.config_ruta = Path(config_ruta)
        self.pesos_ruta = Path(pesos_ruta)
        self.config = config
        self.fabrica = fabrica
        self.inicio_guarda_s = inicio_guarda_s
        self.reloj = reloj
        self.trazas = trazas
        self.generacion = 0
        self.solicitudes: Any = None
        self.respuestas: Any = None
        self.proceso: Any = None
        self.cronologia: list[dict[str, Any]] = []
        self.cierre_limpio: bool | None = None

    def iniciar(self) -> None:
        inicio_total_ns = time.monotonic_ns()
        self.generacion += 1
        self.solicitudes = self.contexto.Queue(maxsize=1)
        self.respuestas = self.contexto.Queue()
        self.proceso = self.contexto.Process(
            target=_bucle_trabajador,
            args=(
                self.solicitudes,
                self.respuestas,
                self.fabrica,
                self.config_ruta,
                self.pesos_ruta,
                self.config.config_sha256,
                self.config.expected_model_sha256,
                self.generacion,
            ),
        )
        inicio = self.reloj()
        try:
            self.proceso.start()
            fin_creacion_ns = time.monotonic_ns()
            limite_inicio = time.monotonic() + self.inicio_guarda_s
            while True:
                restante = limite_inicio - time.monotonic()
                if restante <= 0:
                    raise ErrorTrabajador("se agotó la guarda de inicialización")
                try:
                    respuesta = self.respuestas.get(timeout=min(restante, 0.05))
                    break
                except queue.Empty:
                    if not self.proceso.is_alive():
                        raise ErrorTrabajador("el trabajador terminó antes de READY") from None
            if (
                not isinstance(respuesta, tuple)
                or len(respuesta) != 6
                or respuesta[:5]
                != (
                    self.generacion,
                    "ready",
                    self.config.expected_model_sha256,
                    self.config.config_sha256,
                    2,
                )
                or not isinstance(respuesta[5], tuple)
                or len(respuesta[5]) != 3
            ):
                raise ErrorTrabajador(f"READY inválido: {respuesta!r}")
            inicio_carga_ns, fin_carga_ns, fin_calentamiento_ns = respuesta[5]
            fin_ready_ns = time.monotonic_ns()
            tiempos = _desglosar_ready_ns(
                (
                    inicio_total_ns,
                    fin_creacion_ns,
                    inicio_carga_ns,
                    fin_carga_ns,
                    fin_calentamiento_ns,
                    fin_ready_ns,
                )
            )
            self.cronologia.append(
                {
                    "generacion": self.generacion,
                    "estado": "ready",
                    "model_sha256": respuesta[2],
                    "config_sha256": respuesta[3],
                    "torch_threads": respuesta[4],
                    **tiempos,
                }
            )
        except Exception as exc:
            self.cronologia.append(
                {
                    "generacion": self.generacion,
                    "estado": "fallo_inicio",
                    "duracion_ms": (self.reloj() - inicio) * 1000,
                }
            )
            self.detener()
            raise ErrorTrabajador(f"no se pudo iniciar el predictor: {exc}") from exc

    def detener(self) -> bool:
        proceso = self.proceso
        detenido = True
        if proceso is not None and proceso.pid is not None:
            if proceso.is_alive():
                proceso.terminate()
                proceso.join(CIERRE_GUARDA_S)
            if proceso.is_alive():
                proceso.kill()
                proceso.join(CIERRE_GUARDA_S)
            if not proceso.is_alive():
                proceso.join(0)
            detenido = not proceso.is_alive()
        for canal in (self.solicitudes, self.respuestas):
            if canal is not None:
                canal.cancel_join_thread()
                canal.close()
        self.proceso = None
        self.solicitudes = None
        self.respuestas = None
        return detenido

    def close(self) -> None:
        self.cierre_limpio = self.detener()

    def solicitar(
        self,
        *,
        request_id: int,
        ruta: Path,
        run_id: str,
        secuencia: str,
        indice: int,
        frame_id: str,
        captura: float,
        origen: float,
        plazos: PlazosInfer,
    ) -> tuple[str, dict[str, Any] | None, tuple[int, int] | None]:
        """Devuelve resultado, timeout o fallo. El plazo empieza antes de put_nowait."""
        inicio = self.reloj()
        if getattr(self, "trazas", None) is not None:
            self.trazas.append(
                {
                    "frame_id": frame_id,
                    "request_id": request_id,
                    "generacion": self.generacion,
                    "inicio_monotonic_s": inicio,
                    "publicado_monotonic_s": None,
                    "duracion_publicacion_ms": None,
                    "reinicio_ok": None,
                }
            )
        limite = inicio + plazos.detector_timeout_ms / 1000
        try:
            self.solicitudes.put_nowait(
                (
                    self.generacion,
                    request_id,
                    str(ruta),
                    run_id,
                    secuencia,
                    indice,
                    frame_id,
                    captura,
                    origen,
                    plazos.max_frame_age_ms,
                )
            )
        except Exception:
            return "fallo", None, None
        dimensiones = None
        while True:
            restante = limite - self.reloj()
            if restante < 0:
                return "timeout", None, dimensiones
            try:
                recibido = self.respuestas.get(timeout=min(restante, 0.05))
            except queue.Empty:
                if self.proceso is not None and not self.proceso.is_alive():
                    return "fallo", None, dimensiones
                continue
            except (OSError, EOFError):
                return "fallo", None, dimensiones
            fin = self.reloj()
            if fin > limite:
                return "timeout", None, dimensiones
            if not isinstance(recibido, tuple) or len(recibido) != 4:
                return "fallo", None, dimensiones
            if recibido[:2] != (self.generacion, request_id):
                continue
            if recibido[2] == "decoded":
                valor = recibido[3]
                if (
                    not isinstance(valor, tuple)
                    or len(valor) != 2
                    or any(type(n) is not int or n < 1 for n in valor)
                ):
                    return "fallo", None, dimensiones
                dimensiones = valor
            elif recibido[2] == "result":
                evento = recibido[3]
                if (
                    not isinstance(evento, dict)
                    or evento.get("run_id") != run_id
                    or evento.get("frame_id") != frame_id
                ):
                    return "fallo", None, dimensiones
                return "result", evento, dimensiones


def ejecutar_run_supervisado(
    entrada: Path,
    salida: Path,
    *,
    run_id: str,
    config_ruta: Path,
    pesos_ruta: Path,
    sequence_id: str | None = None,
    capture_ms: Sequence[float] | None = None,
    fabrica: Callable[[Path, Path], DetectorJPEG] = crear_detector_real,
    inicio_guarda_s: float = INICIO_GUARDA_S,
    trazas: list[dict[str, Any]] | None = None,
) -> tuple[Path, int, int, bool]:
    """Publica un evento v1 por JPEG aun si falla el reinicio; devuelve fallo fatal."""
    config = cargar_config_detector(config_ruta)
    plazos, plazos_sha256 = cargar_plazos_infer_con_hash(RUTA_PLAZOS)
    if fabrica is crear_detector_real:
        try:
            verificar_checkpoint(
                pesos_ruta,
                config.expected_model_sha256,
                bytes_esperados=(
                    PESO_OFICIAL_BYTES
                    if config.expected_model_sha256 == PESO_OFICIAL_SHA256
                    else None
                ),
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise ErrorRunInfer(f"checkpoint local inválido: {exc}") from exc
    if not isinstance(run_id, str) or _ID.fullmatch(run_id) is None:
        raise ErrorRunInfer("run_id debe cumplir [A-Za-z0-9._-]{1,64}")
    archivos, directorio = _archivos(Path(entrada))
    secuencia = (None if directorio else "independent") if sequence_id is None else sequence_id
    if secuencia is None or _ID.fullmatch(secuencia) is None:
        raise ErrorRunInfer("sequence_id válido es obligatorio para un directorio")
    tiempos = _capturas(capture_ms, len(archivos), directorio)
    frame_ids = [ruta.stem for ruta in archivos]
    if any(_ID.fullmatch(frame_id) is None for frame_id in frame_ids) or len(set(frame_ids)) != len(
        frame_ids
    ):
        raise ErrorRunInfer("frame_id inválido o repetido en el run")
    destino = Path(salida)
    if destino.suffix.lower() != ".jsonl":
        destino /= f"{run_id}.jsonl"
    manifiesto = destino.parent / f"{run_id}.infer-run.json"
    if destino == manifiesto:
        raise ErrorRunInfer("el JSONL y el manifiesto deben tener nombres distintos")
    if destino.exists() or manifiesto.exists() or destino.is_symlink() or manifiesto.is_symlink():
        raise FileExistsError("el JSONL o manifiesto del run ya existe")

    supervisor = PredictorSupervisado(
        config_ruta,
        pesos_ruta,
        config,
        fabrica=fabrica,
        inicio_guarda_s=inicio_guarda_s,
        trazas=trazas,
    )
    falla_reinicio = False
    try:
        supervisor.iniciar()
    except ErrorTrabajador as exc:
        print(f"infer: {exc}", file=sys.stderr)
        falla_reinicio = True
    destino.parent.mkdir(parents=True, exist_ok=True)
    origen = time.monotonic()

    def transcurrido() -> float:
        return (time.monotonic() - origen) * 1000

    meta = SimpleNamespace(
        config=config, cargado=SimpleNamespace(model_sha256=config.expected_model_sha256)
    )
    eventos: list[dict[str, Any]] = []
    ultima_captura: float | None = None
    with closing(supervisor), abrir_exclusivo(destino, lectura=True) as archivo:
        for indice, (ruta, frame_id) in enumerate(zip(archivos, frame_ids, strict=True), start=1):
            recuperar = False
            registro_recuperacion: dict[str, Any] | None = None
            if tiempos is None:
                captura = transcurrido()
                if ultima_captura is not None and captura <= ultima_captura:
                    captura = _esperar_reloj(
                        transcurrido, time.sleep, ultima_captura, estricto=True
                    )
            else:
                captura = tiempos[indice - 1]
                _esperar_reloj(transcurrido, time.sleep, captura)

            if falla_reinicio:
                evento = _evento_error(
                    meta,
                    ruta,
                    run_id,
                    secuencia,
                    indice,
                    frame_id,
                    captura,
                    transcurrido,
                    "detector_exception",
                    ErrorTrabajador("predictor no disponible"),
                )
            else:
                clase, evento, dimensiones = supervisor.solicitar(
                    request_id=indice,
                    ruta=ruta,
                    run_id=run_id,
                    secuencia=secuencia,
                    indice=indice,
                    frame_id=frame_id,
                    captura=captura,
                    origen=origen,
                    plazos=plazos,
                )
                if clase != "result":
                    recuperar = True
                    codigo = "detector_timeout" if clase == "timeout" else "detector_exception"
                    evento = _evento_error(
                        meta,
                        ruta,
                        run_id,
                        secuencia,
                        indice,
                        frame_id,
                        captura,
                        transcurrido,
                        codigo,
                        ErrorTrabajador(clase),
                        dimensiones,
                    )
                    registro_recuperacion = {
                        "generacion": supervisor.generacion,
                        "frame_id": frame_id,
                        "estado": clase,
                        "t_fallo_ms": transcurrido(),
                    }
                    supervisor.cronologia.append(registro_recuperacion)
                assert evento is not None
            evento["t_emit_ms"] = transcurrido()
            if evento["status"] == "ok" and evento["t_emit_ms"] - captura > plazos.max_frame_age_ms:
                evento["status"] = "stale"
                evento["detections"] = []
            linea = _serializar_evento(evento, eventos)
            archivo.write(linea + "\n")
            archivo.flush()
            if trazas is not None and not falla_reinicio:
                publicado_s = time.monotonic()
                traza = trazas[-1]
                traza["publicado_monotonic_s"] = publicado_s
                traza["duracion_publicacion_ms"] = (
                    publicado_s - traza["inicio_monotonic_s"]
                ) * 1000
                traza["status"] = evento["status"]
                traza["error_code"] = evento.get("error", {}).get("code")
            eventos.append(evento)
            ultima_captura = captura
            if recuperar:
                assert registro_recuperacion is not None
                inicio_recuperacion = time.monotonic()
                if not supervisor.detener():
                    falla_reinicio = True
                else:
                    try:
                        supervisor.iniciar()
                    except ErrorTrabajador as exc:
                        print(f"infer: reinicio fallido: {exc}", file=sys.stderr)
                        falla_reinicio = True
                registro_recuperacion["reinicio_ms"] = (
                    time.monotonic() - inicio_recuperacion
                ) * 1000
                registro_recuperacion["reinicio_ok"] = not falla_reinicio
                if trazas is not None:
                    trazas[-1]["reinicio_ok"] = not falla_reinicio
        archivo.flush()
        archivo.buffer.seek(0)
        jsonl_sha256 = hashlib.file_digest(archivo.buffer, "sha256").hexdigest()
    if supervisor.cierre_limpio is False:
        falla_reinicio = True
    with abrir_exclusivo(manifiesto) as archivo_manifiesto:
        archivo_manifiesto.write(
            json.dumps(
                {
                    "run_id": run_id,
                    "percepcion": {
                        "archivo": destino.name,
                        "sha256": jsonl_sha256,
                    },
                    "plazos": {
                        "detector_timeout_ms": plazos.detector_timeout_ms,
                        "max_frame_age_ms": plazos.max_frame_age_ms,
                        "plazos_sha256": plazos_sha256,
                    },
                    "model_sha256": config.expected_model_sha256,
                    "config_sha256": config.config_sha256,
                    "generaciones": supervisor.cronologia,
                    "conteos": {
                        "eventos": len(eventos),
                        "errores": sum(e["status"] == "error" for e in eventos),
                        "stale": sum(e["status"] == "stale" for e in eventos),
                    },
                    "fallo_reinicio": falla_reinicio,
                    "cierre_limpio": supervisor.cierre_limpio,
                },
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
    return destino, len(eventos), sum(e["status"] == "error" for e in eventos), falla_reinicio
