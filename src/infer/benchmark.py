"""Límites de medición emparejados para P5-06; no publica eventos ni ejecuta series."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .detector import DetectorJPEG
from .eventos import _evento_cuadro
from .plazos import PlazosInfer
from .reloj import leer_reloj_ns
from .trabajador import PredictorSupervisado


def medir_control(
    detector: DetectorJPEG,
    ruta: Path,
    *,
    request_id: int,
    plazos: PlazosInfer,
    reloj_ns: Callable[[], int] = leer_reloj_ns,
) -> tuple[float, dict[str, Any]]:
    """Desde antes de decodificar hasta terminar la validación de _evento_cuadro."""
    inicio_ns = reloj_ns()
    origen_s = inicio_ns / 1_000_000_000
    evento = _evento_cuadro(
        detector,
        ruta,
        "p506-benchmark",
        "independent",
        request_id,
        ruta.stem,
        0.0,
        lambda: (reloj_ns() / 1_000_000_000 - origen_s) * 1000,
        plazos.max_frame_age_ms,
        lambda _dimensiones: None,
    )
    fin_ns = reloj_ns()
    return (fin_ns - inicio_ns) / 1_000_000, evento


def medir_supervisado(
    predictor: PredictorSupervisado,
    ruta: Path,
    *,
    request_id: int,
    plazos: PlazosInfer,
    reloj_ns: Callable[[], int] = leer_reloj_ns,
) -> tuple[float, dict[str, Any]]:
    """Desde antes de solicitar (y enviar) hasta recibir la respuesta verificada."""
    inicio_ns = reloj_ns()
    clase, evento, _dimensiones = predictor.solicitar(
        request_id=request_id,
        ruta=ruta,
        run_id="p506-benchmark",
        secuencia="independent",
        indice=request_id,
        frame_id=ruta.stem,
        captura=0.0,
        origen=inicio_ns / 1_000_000_000,
        plazos=plazos,
    )
    fin_ns = reloj_ns()
    if clase != "result" or evento is None:
        raise RuntimeError(f"solicitud supervisada falló: {clase}")
    return (fin_ns - inicio_ns) / 1_000_000, evento


def medir_reinicio(
    predictor: PredictorSupervisado,
    *,
    reloj_ns: Callable[[], int] = leer_reloj_ns,
) -> dict[str, Any]:
    """Desde antes de terminar el hijo anterior hasta READY verificado del nuevo."""
    inicio_ns = reloj_ns()
    detenido = predictor.detener()
    fin_detencion_ns = reloj_ns()
    if not detenido:
        raise RuntimeError("el trabajador no terminó durante el reinicio")
    predictor.iniciar()
    fin_ready_ns = reloj_ns()
    ready = predictor.cronologia[-1]
    total_ms = (fin_ready_ns - inicio_ns) / 1_000_000
    detencion_ms = (fin_detencion_ns - inicio_ns) / 1_000_000
    coordinacion_ms = total_ms - detencion_ms - ready["duracion_ms"]
    return {
        "total_ms": total_ms,
        "detencion_ms": detencion_ms,
        "coordinacion_ms": coordinacion_ms,
        "ready": ready,
    }
