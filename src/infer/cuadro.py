"""Entrada por cuadro del predictor supervisado, para el lazo en vivo (P5-21).

`ejecutar_run_supervisado` recorre una carpeta de JPEG ya filmados. El lazo en vivo recibe un
cuadro a la vez y no tiene carpeta, así que aquí se repite lo que ese recorrido hace con cada
cuadro, con las mismas piezas y sin cambiarlas: el mismo `PredictorSupervisado` (proceso `spawn`,
mismos pesos y misma configuración, hashes verificados), el mismo armado de eventos A→B v1, los
mismos plazos de `config/control/plazos.yaml` y el mismo reinicio del predictor después de un
timeout o un fallo.

`DetectorEnVivo.evento(ruta, frame_id, captura_ms)` devuelve siempre un evento que cumple el
contrato v1: `ok`, `stale` o `error` (`unreadable_image`, `detector_exception`,
`detector_timeout` o `invalid_output`). Nunca lanza por un fallo del detector; si el evento
armado no cumpliera el contrato, lanza `ErrorRunInfer`, igual que el recorrido de carpetas.

El reloj es el de `infer.reloj` (`perf_counter`). `origen_s` es el instante 0 de `t_capture_ms` y
`t_emit_ms`: quien llama debe medir `captura_ms` contra el mismo origen.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from contrato.validador import validar_evento

from .config import cargar_config_detector
from .detector import DetectorJPEG
from .eventos import _ID, ErrorRunInfer, _evento_error
from .plazos import RUTA_PLAZOS, PlazosInfer, cargar_plazos_infer_con_hash
from .reloj import leer_reloj_s
from .rutas_seguras import verificar_checkpoint
from .trabajador import (
    INICIO_GUARDA_S,
    PESO_OFICIAL_BYTES,
    PESO_OFICIAL_SHA256,
    ErrorTrabajador,
    PredictorSupervisado,
    crear_detector_real,
)


class DetectorEnVivo:
    """Un predictor supervisado que contesta cuadro por cuadro."""

    def __init__(
        self,
        config_ruta: Path,
        pesos_ruta: Path,
        *,
        run_id: str,
        sequence_id: str = "vivo",
        origen_s: float | None = None,
        plazos: PlazosInfer | None = None,
        fabrica: Callable[[Path, Path], DetectorJPEG] = crear_detector_real,
        inicio_guarda_s: float = INICIO_GUARDA_S,
        reloj: Callable[[], float] = leer_reloj_s,
    ) -> None:
        for nombre, valor in (("run_id", run_id), ("sequence_id", sequence_id)):
            if not isinstance(valor, str) or _ID.fullmatch(valor) is None:
                raise ErrorRunInfer(f"{nombre} debe cumplir [A-Za-z0-9._-]{{1,64}}")
        self.config = cargar_config_detector(config_ruta)
        if plazos is None:
            plazos, self.plazos_sha256 = cargar_plazos_infer_con_hash(RUTA_PLAZOS)
        else:
            self.plazos_sha256 = None
        self.plazos = plazos
        self.pesos_ruta = Path(pesos_ruta)
        self.run_id = run_id
        self.sequence_id = sequence_id
        self.reloj = reloj
        self.origen_s = reloj() if origen_s is None else origen_s
        self._fabrica = fabrica
        self._revisar_checkpoint = fabrica is crear_detector_real
        self._predictor = PredictorSupervisado(
            Path(config_ruta),
            self.pesos_ruta,
            self.config,
            fabrica=fabrica,
            inicio_guarda_s=inicio_guarda_s,
            reloj=reloj,
        )
        # Lo que `_evento_error` necesita del detector: los hashes del run.
        self._meta = SimpleNamespace(
            config=self.config,
            cargado=SimpleNamespace(model_sha256=self.config.expected_model_sha256),
        )
        self._indice = 0
        self._disponible = False
        self._cerrado = False
        self.reinicios = 0

    @property
    def model_sha256(self) -> str:
        return self.config.expected_model_sha256

    @property
    def config_sha256(self) -> str:
        return self.config.config_sha256

    @property
    def disponible(self) -> bool:
        """El predictor está vivo; si no, cada cuadro sale como `detector_exception`."""
        return self._disponible

    def ahora_ms(self) -> float:
        return (self.reloj() - self.origen_s) * 1000

    def iniciar(self) -> None:
        """Verifica los pesos y levanta el predictor. Lanza si no queda listo."""
        if self._revisar_checkpoint:
            try:
                verificar_checkpoint(
                    self.pesos_ruta,
                    self.config.expected_model_sha256,
                    bytes_esperados=(
                        PESO_OFICIAL_BYTES
                        if self.config.expected_model_sha256 == PESO_OFICIAL_SHA256
                        else None
                    ),
                )
            except (OSError, ValueError, RuntimeError) as exc:
                raise ErrorRunInfer(f"checkpoint local inválido: {exc}") from exc
        self._predictor.iniciar()
        self._disponible = True

    def evento(self, ruta: Path, frame_id: str, captura_ms: float) -> dict[str, Any]:
        """Un evento v1 para el JPEG de `ruta`, con `t_emit_ms` ya puesto.

        `frame_id` debe ser único dentro del run y `captura_ms` crecer de un cuadro al siguiente
        (lo exige `contrato.validar_flujo`); el lazo los cumple por construcción.
        """
        if self._cerrado:
            raise ErrorRunInfer("el detector en vivo ya está cerrado")
        if _ID.fullmatch(frame_id) is None:
            raise ErrorRunInfer("frame_id debe cumplir [A-Za-z0-9._-]{1,64}")
        self._indice += 1
        recuperar = False
        if not self._disponible:
            evento = self._error(
                ruta, frame_id, captura_ms, "detector_exception", "predictor no disponible"
            )
        else:
            clase, recibido, dimensiones = self._predictor.solicitar(
                request_id=self._indice,
                ruta=ruta,
                run_id=self.run_id,
                secuencia=self.sequence_id,
                indice=self._indice,
                frame_id=frame_id,
                captura=captura_ms,
                origen=self.origen_s,
                plazos=self.plazos,
            )
            if clase == "result" and recibido is not None:
                evento = recibido
            else:
                recuperar = True
                codigo = "detector_timeout" if clase == "timeout" else "detector_exception"
                evento = self._error(ruta, frame_id, captura_ms, codigo, clase, dimensiones)

        evento["t_emit_ms"] = self.ahora_ms()
        if (
            evento["status"] == "ok"
            and evento["t_emit_ms"] - captura_ms > self.plazos.max_frame_age_ms
        ):
            evento["status"] = "stale"
            evento["detections"] = []
        fallos = validar_evento(evento)
        if fallos:
            raise ErrorRunInfer("evento incompatible con contrato v1: " + "; ".join(fallos))
        if recuperar:
            self._reiniciar()
        return evento

    def cerrar(self) -> bool:
        """Detiene el proceso del predictor. `True` si terminó limpio."""
        self._cerrado = True
        self._disponible = False
        self._predictor.close()
        return self._predictor.cierre_limpio is not False

    def _error(
        self,
        ruta: Path,
        frame_id: str,
        captura_ms: float,
        codigo: str,
        causa: str,
        dimensiones: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        return _evento_error(
            self._meta,
            ruta,
            self.run_id,
            self.sequence_id,
            self._indice,
            frame_id,
            captura_ms,
            self.ahora_ms,
            codigo,
            ErrorTrabajador(causa),
            dimensiones,
        )

    def _reiniciar(self) -> None:
        """Como en el recorrido de carpetas: tras un fallo se baja el proceso y se levanta otro."""
        if not self._predictor.detener():
            self._disponible = False
            return
        try:
            self._predictor.iniciar()
        except ErrorTrabajador as exc:
            print(f"infer: reinicio fallido: {exc}", file=sys.stderr)
            self._disponible = False
        else:
            self._disponible = True
            self.reinicios += 1
