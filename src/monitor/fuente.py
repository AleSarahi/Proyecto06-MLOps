"""Fuente visual reproducida como stream (issue #5).

Dos modos con la misma interfaz:

- `FuenteFrames` (canónico): reproduce el respaldo datos/p6/frames/<segmento>/ (frames ya
  muestreados del video de YouTube) respetando su tiempo de video. Funciona sin red y es lo que
  usan la referencia, C1 y C2.
- `FuenteVideo`: lee el MP4 descargado con OpenCV y aplica el mismo muestreo (1 de cada N frames).

Ritmo: el frame con tiempo de video `pos` "llega" en `t0 + (pos - pos_inicio) / velocidad`. Con
velocidad 1.0 es tiempo real; con 0 llega en cuanto se pide (sin esperas). Si el consumidor se
atrasa, el frame llega igual a su hora y la demora queda como tiempo en cola (ver corrida.py).
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .config import ErrorConfig
from .video import _ruta, leer_manifiesto, verificar


@dataclass
class Frame:
    frame_id: str
    video_pos_ms: float
    t_llegada_ms: float
    imagen: np.ndarray | None
    jpeg: bytes | None = None
    error: str | None = None
    # False en un latido de `FuenteInterrumpida`: no llegó frame (la fuente está caída). No es un
    # evento: solo avanza el reloj del monitoreo para detectar la caída y cerrar ventanas a tiempo.
    senal: bool = True


@dataclass
class Contadores:
    recibidos: int = 0
    descartes: Counter = field(default_factory=Counter)
    # Solo con FuenteInterrumpida: intentos de reconexión fallidos y reconexiones logradas.
    conexion: Counter = field(default_factory=Counter)

    def como_dict(self) -> dict[str, Any]:
        d = {"recibidos": self.recibidos, "descartes": dict(self.descartes)}
        if self.conexion:
            d["conexion"] = dict(self.conexion)
        return d


class _Ritmo:
    def __init__(self, velocidad: float, reloj_ms: Callable[[], float]):
        self.velocidad = velocidad
        self.reloj_ms = reloj_ms
        self.base: tuple[float, float] | None = None

    def esperar(self, pos_ms: float) -> float:
        """Duerme hasta la hora de llegada del frame y la devuelve (ms del reloj de la corrida)."""
        ahora = self.reloj_ms()
        if self.velocidad == 0:
            return ahora
        if self.base is None:
            self.base = (ahora, pos_ms)
            return ahora
        llegada = self.base[0] + (pos_ms - self.base[1]) / self.velocidad
        if llegada > ahora:
            time.sleep((llegada - ahora) / 1000)
        return llegada


def _decodificar(datos: bytes) -> np.ndarray | None:
    imagen = cv2.imdecode(np.frombuffer(datos, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagen is None or imagen.ndim != 3 or imagen.shape[2] != 3:
        return None
    return imagen


class FuenteFrames:
    modo = "frames"

    def __init__(self, carpeta: Path, *, velocidad: float, reloj_ms: Callable[[], float]):
        self.carpeta = Path(carpeta)
        if not (self.carpeta / "manifiesto.jsonl").is_file():
            raise ErrorConfig(
                f"no hay respaldo en {self.carpeta}; corre `python -m monitor video extraer`"
            )
        self.cabecera, self.filas = leer_manifiesto(self.carpeta)
        self.ritmo = _Ritmo(velocidad, reloj_ms)
        self.contadores = Contadores()
        dur_s = self.cabecera["fin_s"] - self.cabecera["inicio_s"]
        # El muestreo se aplicó al extraer: los demás frames del segmento se descartaron ahí.
        frames_video = self.cabecera.get("frames_video") or round(
            dur_s * self.cabecera["fps_video"]
        )
        self.contadores.descartes["muestreo"] = max(0, frames_video - len(self.filas))

    def descripcion(self) -> dict[str, Any]:
        return {"modo": self.modo, "carpeta": str(self.carpeta), "manifiesto": self.cabecera}

    def __iter__(self) -> Iterator[Frame]:
        for fila in self.filas:
            llegada = self.ritmo.esperar(fila["pos_ms"])
            self.contadores.recibidos += 1
            archivo = self.carpeta / fila["archivo"]
            try:
                datos = archivo.read_bytes()
            except OSError as exc:
                self.contadores.descartes["lectura"] += 1
                yield Frame(
                    fila["frame_id"], fila["pos_ms"], llegada, None, None, f"lectura: {exc}"
                )
                continue
            if hashlib.sha256(datos).hexdigest() != fila["sha256"]:
                self.contadores.descartes["lectura"] += 1
                yield Frame(
                    fila["frame_id"],
                    fila["pos_ms"],
                    llegada,
                    None,
                    None,
                    "lectura: el SHA-256 del frame no coincide con el manifiesto",
                )
                continue
            imagen = _decodificar(datos)
            if imagen is None:
                self.contadores.descartes["decodificacion"] += 1
                yield Frame(
                    fila["frame_id"],
                    fila["pos_ms"],
                    llegada,
                    None,
                    None,
                    "decodificacion: no es un JPEG legible",
                )
                continue
            yield Frame(fila["frame_id"], fila["pos_ms"], llegada, imagen, datos)


class FuenteVideo:
    modo = "video"

    def __init__(
        self,
        segmento: str,
        fuentes: dict[str, Any],
        cada_n_frames: int,
        *,
        velocidad: float,
        reloj_ms: Callable[[], float],
    ):
        self.segmento = segmento
        self.seg = fuentes["segmentos"][segmento]
        if "tramos" in self.seg:
            raise ErrorConfig(f"{segmento} es una secuencia de tramos: córrela con --modo frames")
        self.video = fuentes["videos"][self.seg["video"]]
        self.sha = verificar(self.seg["video"], self.video)
        self.cada_n = cada_n_frames
        self.ritmo = _Ritmo(velocidad, reloj_ms)
        self.contadores = Contadores()

    def descripcion(self) -> dict[str, Any]:
        return {"modo": self.modo, "video": self.video, "video_sha256": self.sha, **self.seg}

    def __iter__(self) -> Iterator[Frame]:
        cap = cv2.VideoCapture(str(_ruta(self.video)))
        if not cap.isOpened():
            raise ErrorConfig(f"no se pudo abrir {self.video['archivo']}")
        fps = cap.get(cv2.CAP_PROP_FPS)
        indice = 0
        try:
            while True:
                if not cap.grab():
                    break
                pos_ms = indice * 1000.0 / fps
                if pos_ms >= self.seg["fin_s"] * 1000:
                    break
                if pos_ms >= self.seg["inicio_s"] * 1000:
                    if indice % self.cada_n:
                        self.contadores.descartes["muestreo"] += 1
                    else:
                        frame_id = f"{self.segmento}-f{indice:06d}"
                        llegada = self.ritmo.esperar(pos_ms)
                        self.contadores.recibidos += 1
                        ok, imagen = cap.retrieve()
                        if not ok or imagen is None:
                            self.contadores.descartes["decodificacion"] += 1
                            yield Frame(frame_id, pos_ms, llegada, None, None, "decodificacion")
                        else:
                            yield Frame(frame_id, pos_ms, llegada, imagen, None)
                indice += 1
        finally:
            cap.release()


class FuenteInterrumpida:
    """Inyección controlada de una caída de la fuente (escenario adicional, issue #33).

    Envuelve otra fuente y, durante cada corte [desde, hasta) en ms del segmento, no entrega los
    frames: los pierde, como un stream cuya conexión se cae. El ritmo sigue (el tiempo real pasa) y
    en lugar de cada frame perdido emite un latido `Frame(senal=False)` con la hora a la que debía
    llegar, que es lo que el monitor observa: su propio reloj sin frames. Cada latido cuenta como un
    intento de reconexión fallido; el primer frame después del corte, como una reconexión.
    """

    def __init__(self, interna: Any, cortes_ms: list[tuple[float, float]], inicio_ms: float):
        self.interna = interna
        self.cortes_ms = sorted(cortes_ms)
        self.inicio_ms = inicio_ms
        self.modo = getattr(interna, "modo", "frames")

    @property
    def contadores(self) -> Contadores:
        return self.interna.contadores

    def descripcion(self) -> dict[str, Any]:
        return {
            **self.interna.descripcion(),
            "inyeccion": {
                "tipo": "corte_de_fuente",
                "cortes_s": [[a / 1000, b / 1000] for a, b in self.cortes_ms],
                "nota": "frames perdidos a propósito durante el corte; no se alteran los demás",
            },
        }

    def _en_corte(self, pos_ms: float) -> bool:
        rel = pos_ms - self.inicio_ms
        return any(a <= rel < b for a, b in self.cortes_ms)

    def __iter__(self) -> Iterator[Frame]:
        caida = False
        c = self.interna.contadores
        for frame in self.interna:
            if self._en_corte(frame.video_pos_ms):
                c.recibidos -= 1  # no llegó
                c.descartes["sin_senal"] += 1
                c.conexion["intentos_fallidos"] += 1
                caida = True
                yield Frame(
                    frame.frame_id, frame.video_pos_ms, frame.t_llegada_ms, None, senal=False
                )
                continue
            if caida:
                c.conexion["reconexiones"] += 1
                caida = False
            yield frame
