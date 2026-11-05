"""Piezas compartidas por las pruebas del lazo en vivo (P5-21): sin cámara, sin carro, sin pesos.

- `servidor_mjpeg`: un servidor HTTP en localhost que manda JPEG con el formato del firmware.
- `DetectorFalso`: lo que `LazoVivo` usa de `DetectorEnVivo`, con eventos que cumplen el contrato.
- `ColaTeclas`: las teclas que el hilo de teclas va a leer.
- `plazos`: los de `config/control/plazos.yaml`.
"""

from __future__ import annotations

import http.server
import queue
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from control.__main__ import CARPETA_CONFIG, cargar_plazos
from control.config import cargar_config_politica
from infer.reloj import leer_reloj_s

SEPARADOR = b"\r\n--123456789000000000000987654321\r\n"
MODELO = "a" * 64
CONFIG = "b" * 64


def plazos() -> dict[str, Any]:
    return cargar_plazos(CARPETA_CONFIG / "plazos.yaml")


def politica() -> Any:
    return cargar_config_politica(CARPETA_CONFIG / "politica.yaml")


def jpeg_falso(n: int) -> bytes:
    """Bytes con forma de JPEG: el stream y el detector falso no los decodifican."""
    return b"\xff\xd8" + bytes([n % 256]) * 40 + b"\xff\xd9"


class ServidorMjpeg:
    """Manda un cuadro cada `periodo_s`. `cortar()` simula la cámara apagada o sin WiFi."""

    def __init__(self, periodo_s: float) -> None:
        self.periodo_s = periodo_s
        self.activo = threading.Event()
        self.activo.set()
        self.conexiones = 0
        self.enviados = 0
        servidor = self

        class Manejador(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def do_GET(self) -> None:
                servidor.conexiones += 1
                if not servidor.activo.is_set():
                    self.send_error(503)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=123456789")
                self.end_headers()
                try:
                    while servidor.activo.is_set():
                        servidor.enviados += 1
                        datos = jpeg_falso(servidor.enviados)
                        self.wfile.write(
                            SEPARADOR
                            + b"Content-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(datos)
                            + datos
                        )
                        self.wfile.flush()
                        time.sleep(servidor.periodo_s)
                except OSError:
                    return

            def log_message(self, *_: object) -> None:
                return

        self._http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self._http.daemon_threads = True
        self.puerto = self._http.server_address[1]
        self._hilo = threading.Thread(target=self._http.serve_forever, daemon=True)

    def cortar(self) -> None:
        self.activo.clear()

    def reanudar(self) -> None:
        self.activo.set()

    def __enter__(self) -> ServidorMjpeg:
        self._hilo.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.activo.clear()
        self._http.shutdown()
        self._http.server_close()


@contextmanager
def servidor_mjpeg(periodo_s: float = 0.05) -> Iterator[ServidorMjpeg]:
    with ServidorMjpeg(periodo_s) as servidor:
        yield servidor


class DetectorFalso:
    """Mismo contrato que `DetectorEnVivo` para el lazo. `modo` se puede cambiar en pleno vuelo.

    - "libre": evento `ok` sin detecciones.
    - "obstaculo": una botella (clase 39) en el centro.
    - "error": evento de error `detector_exception`, como cuando el predictor murió.
    - "explotar": lanza `RuntimeError`.
    """

    def __init__(self, modo: str = "libre", demora_s: float = 0.0) -> None:
        self.modo = modo
        self.demora_s = demora_s
        self.run_id = "prueba-vivo"
        self.sequence_id = "vivo"
        self.model_sha256 = MODELO
        self.config_sha256 = CONFIG
        self.plazos_sha256 = "c" * 64
        self.reinicios = 0
        self.cerrado = False
        self.iniciado = False
        self.origen_s = leer_reloj_s()
        self.vistos: list[str] = []

    def ahora_ms(self) -> float:
        return (leer_reloj_s() - self.origen_s) * 1000

    def evento(self, ruta: Path, frame_id: str, captura_ms: float) -> dict[str, Any]:
        assert ruta.is_file()
        self.vistos.append(frame_id)
        if self.modo == "explotar":
            raise RuntimeError("detector roto a propósito")
        if self.demora_s:
            time.sleep(self.demora_s)
        evento: dict[str, Any] = {
            "schema_version": "1",
            "run_id": self.run_id,
            "sequence_id": self.sequence_id,
            "frame_id": frame_id,
            "t_capture_ms": captura_ms,
            "t_emit_ms": self.ahora_ms(),
            "image_width": 640,
            "image_height": 480,
            "model_sha256": self.model_sha256,
            "config_sha256": self.config_sha256,
            "status": "ok",
            "bbox_format": "xyxy",
            "bbox_unit": "px",
            "detections": [],
        }
        if self.modo == "obstaculo":
            evento["detections"] = [
                {"class_id": 39, "confidence": 0.9, "bbox": [250.0, 100.0, 400.0, 400.0]}
            ]
        elif self.modo == "error":
            evento["status"] = "error"
            evento["image_width"] = evento["image_height"] = None
            evento["error"] = {"code": "detector_exception", "message": "predictor muerto"}
        return evento

    def iniciar(self) -> None:
        self.iniciado = True

    def cerrar(self) -> bool:
        self.cerrado = True
        return True


class ColaTeclas:
    def __init__(self) -> None:
        self._cola: queue.Queue[str] = queue.Queue()

    def poner(self, tecla: str) -> None:
        self._cola.put(tecla)

    def __call__(self, espera_s: float) -> str | None:
        try:
            return self._cola.get(timeout=espera_s)
        except queue.Empty:
            return None


def esperar(condicion: Any, limite_s: float = 5.0) -> bool:
    """Espera a que `condicion()` sea verdadera; falso si pasa `limite_s`."""
    fin = time.monotonic() + limite_s
    while time.monotonic() < fin:
        if condicion():
            return True
        time.sleep(0.01)
    return bool(condicion())
