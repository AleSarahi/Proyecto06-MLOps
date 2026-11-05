"""El lazo en vivo: cuadro más nuevo → detector → supervisor y política → adaptador → carro.

Tres hilos además del principal:

- el lector del stream (`LectorStream`): deja siempre el cuadro más nuevo y descarta los viejos;
- el reloj: llama a `tic()` cada `paso_reloj_ms` (plazos.yaml), así el watchdog frena aunque el
  hilo principal esté dentro del detector, esperando un cuadro o reiniciándolo;
- las teclas: emergencia, rearme y salida.

El hilo principal toma el cuadro más nuevo, le pide el evento al detector y se lo pasa a
`CorridaVivo.cuadro_vivo`, que decide y manda la orden. Ante cualquier excepción, y al cerrar por
Ctrl+C, por la tecla de salida o por `duracion_s`, lo primero es el STOP final: `cerrar_vivo`
(supervisor + tres STOP al carro) va antes de esperar a los demás hilos.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from infer.cuadro import DetectorEnVivo

from .config import ConfigVivo
from .corrida import CorridaVivo
from .lector import LectorStream

NOMBRE_RESUMEN = "vivo.json"
ESPERA_CUADRO_S = 0.1


def percentil(valores: list[float], p: float) -> float | None:
    """Percentil por rango más cercano (el que se usa para el p95 del proyecto)."""
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[max(0, math.ceil(p / 100 * len(ordenados)) - 1)]


def resumen_de(valores: list[float]) -> dict[str, Any]:
    return {
        "n": len(valores),
        "p50": percentil(valores, 50),
        "p95": percentil(valores, 95),
        "max": max(valores) if valores else None,
    }


MAX_MOTIVO = 60  # caracteres del motivo en la terminal; el texto completo queda en los logs


def linea_de_cuadro(comando: dict[str, Any], evento: dict[str, Any], seco: bool) -> str:
    """Una línea por cuadro: acción, latencia y motivo, legible en las tomas del video."""
    latencia = comando["t_command_ms"] - evento["t_capture_ms"]
    motivo = comando["reason"]
    if len(motivo) > MAX_MOTIVO:
        motivo = motivo[: MAX_MOTIVO - 1].rstrip() + "…"
    marca = "SECO " if seco else "CARRO"
    return (
        f"[{marca}] {comando['frame_id']:<7} {comando['action']:<9} "
        f"v={comando['speed']:.2f} g={comando['steering']:+.2f} "
        f"lat={latencia:4.0f} ms {evento['status']:<5} {motivo}"
    )


class LazoVivo:
    def __init__(
        self,
        corrida: CorridaVivo,
        lector: LectorStream,
        detector: DetectorEnVivo,
        config: ConfigVivo,
        paso_reloj_ms: float,
        carpeta_trabajo: Path,
        *,
        teclas: Callable[[float], str | None] | None = None,
        imprimir: Callable[[str], None] = print,
        duracion_s: float | None = None,
        guardar_cuadros: bool = False,
        archivos_de_config: dict[str, Path] | None = None,
    ) -> None:
        self.corrida = corrida
        self.lector = lector
        self.detector = detector
        self.config = config
        self.paso_reloj_s = paso_reloj_ms / 1000
        self.teclas = teclas
        self.imprimir = imprimir
        self.duracion_s = duracion_s
        self.archivos_de_config = archivos_de_config or {}
        self._dir_cuadros = Path(carpeta_trabajo)
        self._dir_cuadros.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
        self._guardar_cuadros = guardar_cuadros
        self._fin = threading.Event()
        self._hilos: list[threading.Thread] = []
        self._ultima_captura = -1.0
        self._aviso_camara: str | None = None
        self.motivo_de_cierre = "pendiente"
        self.error: BaseException | None = None
        self.cuadros_atendidos = 0
        self.cierre_limpio: bool | None = None

    @property
    def seco(self) -> bool:
        return self.corrida.adaptador.seco

    # -- ejecución -----------------------------------------------------------------------
    def correr(self) -> int:
        """Corre hasta que algo cierre el lazo. Salida: 0 si cerró sin fallo, 1 si hubo un fallo."""
        inicio_s = time.monotonic()
        try:
            self._arrancar_hilos()
            while not self._fin.is_set():
                if self.duracion_s is not None and time.monotonic() - inicio_s >= self.duracion_s:
                    self.motivo_de_cierre = "duracion"
                    break
                cuadro = self.lector.siguiente(ESPERA_CUADRO_S)
                if cuadro is None:
                    self._avisar_si_no_hay_camara()
                    continue
                self._atender(cuadro.n, cuadro.datos, cuadro.t_capture_ms)
            else:
                if self.error is None and self.motivo_de_cierre == "pendiente":
                    self.motivo_de_cierre = "salida"
        except KeyboardInterrupt:
            self.motivo_de_cierre = "ctrl_c"
        except BaseException as exc:
            self._fallar(exc)
        finally:
            self._cerrar(time.monotonic() - inicio_s)
        return 1 if self.error is not None else 0

    def _atender(self, n: int, datos: bytes, t_capture_ms: float) -> None:
        frame_id = f"F{n:06d}"
        # t_capture_ms crece estrictamente (lo exige el contrato) aunque el reloj no se mueva.
        captura = max(t_capture_ms, self._ultima_captura + 0.001)
        self._ultima_captura = captura
        ruta = self._dir_cuadros / (f"{frame_id}.jpg" if self._guardar_cuadros else "actual.jpg")
        ruta.write_bytes(datos)  # NOSONAR (S8707)
        evento = self.detector.evento(ruta, frame_id, captura)
        comando = self.corrida.cuadro_vivo(evento)
        self.cuadros_atendidos += 1
        self.imprimir(linea_de_cuadro(comando, evento, self.seco))

    def _avisar_si_no_hay_camara(self) -> None:
        if self.lector.conectado:
            self._aviso_camara = None
            return
        aviso = f"cámara sin stream ({self.lector.ultimo_error or 'conectando'}): el watchdog frena"
        if aviso != self._aviso_camara:  # una vez por cambio, no 10 veces por segundo
            self._aviso_camara = aviso
            self.imprimir(aviso)

    # -- hilos ---------------------------------------------------------------------------
    def _arrancar_hilos(self) -> None:
        self.lector.iniciar()
        self._hilos = [threading.Thread(target=self._hilo_reloj, name="reloj", daemon=True)]
        if self.teclas is not None:
            self._hilos.append(
                threading.Thread(target=self._hilo_teclas, name="teclas", daemon=True)
            )
        for hilo in self._hilos:
            hilo.start()

    def _hilo_reloj(self) -> None:
        while not self._fin.wait(self.paso_reloj_s):
            try:
                comando = self.corrida.tic()
            except BaseException as exc:
                self._fallar(exc)
                return
            if comando is not None:
                self.imprimir(
                    f"[{'SECO ' if self.seco else 'CARRO'}] {'(reloj)':<11} STOP      "
                    f"{comando['reason']}"
                )

    def _hilo_teclas(self) -> None:
        assert self.teclas is not None
        while not self._fin.is_set():
            try:
                tecla = self.teclas(0.1)
                if tecla is None:
                    continue
                self._tecla(tecla.lower())
            except BaseException as exc:
                self._fallar(exc)
                return

    def _tecla(self, tecla: str) -> None:
        if tecla == self.config.tecla_emergencia:
            self.corrida.emergencia_vivo()
            self.imprimir(
                f"EMERGENCIA: STOP enclavado. '{self.config.tecla_rearme}' rearma, "
                f"'{self.config.tecla_salida}' sale."
            )
        elif tecla == self.config.tecla_rearme:
            comando = self.corrida.rearmar_vivo()
            if comando is None:
                self.imprimir("rearme: no había emergencia")
            else:
                self.imprimir(f"rearme: {comando['reason']}")
        elif tecla == self.config.tecla_salida:
            self.motivo_de_cierre = "tecla_salida"
            self._fin.set()

    def _fallar(self, exc: BaseException) -> None:
        if self.error is None:
            self.error = exc
            self.motivo_de_cierre = f"error:{type(exc).__name__}"
            self.imprimir(f"FALLO: {type(exc).__name__}: {exc}. STOP y cierre.")
        self._fin.set()

    # -- cierre --------------------------------------------------------------------------
    def _cerrar(self, duracion_s: float) -> None:
        """El STOP va primero; después se esperan los hilos y se escribe el resumen."""
        self._fin.set()
        try:
            self.corrida.cerrar_vivo()
        except BaseException as exc:
            self._registrar_fallo_de_cierre(exc)
        self.lector.detener()
        for hilo in self._hilos:
            if hilo is not threading.current_thread():
                hilo.join(timeout=2)
        try:
            self.cierre_limpio = self.detector.cerrar()
        except BaseException as exc:
            self._registrar_fallo_de_cierre(exc)
        try:
            self._escribir_resumen(duracion_s)
        except OSError as exc:
            print(f"vivo: no se pudo escribir {NOMBRE_RESUMEN}: {exc}", file=sys.stderr)
        self.imprimir(f"cierre: {self.motivo_de_cierre}; {self.cuadros_atendidos} cuadros")

    def _registrar_fallo_de_cierre(self, exc: BaseException) -> None:
        if self.error is None:
            self.error = exc
        print(f"vivo: fallo al cerrar: {type(exc).__name__}: {exc}", file=sys.stderr)

    def _escribir_resumen(self, duracion_s: float) -> None:
        corrida, adaptador = self.corrida, self.corrida.adaptador
        resumen = {
            "run_id": self.detector.run_id,
            "modo": "seco" if self.seco else "motores",
            "fin_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "duracion_s": round(duracion_s, 3),
            "cierre": {
                "motivo": self.motivo_de_cierre,
                "error": None
                if self.error is None
                else f"{type(self.error).__name__}: {self.error}",
                "predictor_limpio": self.cierre_limpio,
            },
            "detector": {
                "model_sha256": self.detector.model_sha256,
                "config_sha256": self.detector.config_sha256,
                "plazos_sha256": self.detector.plazos_sha256,
                "reinicios": self.detector.reinicios,
            },
            "config": {
                nombre: hashlib.sha256(ruta.read_bytes()).hexdigest()
                for nombre, ruta in self.archivos_de_config.items()
            },
            "stream": {
                "recibidos": self.lector.recibidos,
                "descartados": self.lector.descartados,
                "conexiones": self.lector.conexiones,
            },
            "cuadros": {"atendidos": self.cuadros_atendidos, "por_estado": corrida.por_estado},
            "comandos": {"total": corrida.comandos, "por_accion": corrida.por_accion},
            "latencia_cuadro_a_comando_ms": resumen_de(corrida.latencias_ms),
            "carro": {
                "enviadas": adaptador.enviadas,
                "rechazadas_por_la_placa": adaptador.rechazadas_por_la_placa,
                "fallos_de_envio": adaptador.fallos_de_envio,
                "rtt_comando_a_respuesta_ms": resumen_de(adaptador.rtts_ms),
            },
            "contratos": {"percepcion": "1", "comando": "1"},
            "archivos": [
                "detecciones.jsonl",
                "decisiones.jsonl",
                "comandos.jsonl",
                "errores.jsonl",
                "respuestas.jsonl",
            ],
        }
        ruta = corrida.salida / NOMBRE_RESUMEN
        ruta.write_text(  # NOSONAR (S8707)
            json.dumps(resumen, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
