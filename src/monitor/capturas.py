"""Captura selectiva de imágenes vinculadas a eventos (issue #15).

Política (config/p6/monitoreo.yaml, sección `captura`), por frame procesado:
- zona del frame en `captura.zonas` (por defecto baja y duda) -> motivo zona_<zona>;
- frame sin detecciones, si `sin_detecciones` -> motivo sin_detecciones;
- 1 de cada `muestra_cada` frames procesados -> motivo muestra_normal;
- todos los frames de una ventana que abrió una alerta, si `alerta` -> motivo alerta.

La imagen se guarda en <corrida>/capturas/<event_id>.jpg, el evento apunta a ella (`image_ref`) y
la captura apunta al evento (`event_id`) con su SHA-256. **No hay expiración**: ningún código borra,
rota ni limpia capturas.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .almacen import leer_jsonl


def motivos(evento: dict[str, Any], n_procesado: int, politica: dict[str, Any]) -> list[str]:
    salida = []
    if evento["zona_frame"] in politica["zonas"]:
        salida.append(f"zona_{evento['zona_frame']}")
    if evento["status"] == "sin_detecciones" and politica["sin_detecciones"]:
        salida.append("sin_detecciones")
    if n_procesado % politica["muestra_cada"] == 0:
        salida.append("muestra_normal")
    return salida


def codificar(imagen: np.ndarray | None, jpeg: bytes | None, calidad: int) -> bytes | None:
    """Bytes a guardar: el JPEG original si existe (lo que se infirió); si no, se codifica."""
    if jpeg is not None:
        return jpeg
    if imagen is None:
        return None
    ok, buf = cv2.imencode(".jpg", imagen, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    return buf.tobytes() if ok else None


def guardar(
    carpeta: Path, evento: dict[str, Any], datos: bytes, razones: list[str], ahora: str
) -> dict[str, Any]:
    ruta = f"capturas/{evento['event_id']}.jpg"
    destino = Path(carpeta) / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)
    return {
        "schema": "p6.captura.v1",
        "image_id": f"img-{evento['event_id']}",
        "event_id": evento["event_id"],
        "run_id": evento["run_id"],
        "ruta": ruta,
        "sha256": hashlib.sha256(datos).hexdigest(),
        "bytes": len(datos),
        "motivos": razones,
        "timestamp_utc": ahora,
        "config_ref": evento["config_ref"],
    }


def verificar(carpeta: Path) -> dict[str, Any]:
    """Comprueba que cada captura exista con su SHA-256 y que su evento la referencie (y viceversa).

    Devuelve los conteos y la lista de problemas (vacía = todo resuelve).
    """
    carpeta = Path(carpeta)
    eventos = {e["event_id"]: e for e in leer_jsonl(carpeta / "eventos.jsonl")}
    capturas = list(leer_jsonl(carpeta / "capturas.jsonl"))
    problemas = []
    validas = 0
    for cap in capturas:
        archivo = carpeta / cap["ruta"]
        ev = eventos.get(cap["event_id"])
        if ev is None:
            problemas.append(f"{cap['image_id']}: su evento {cap['event_id']} no existe")
        elif ev["image_ref"] != cap["ruta"]:
            problemas.append(f"{cap['image_id']}: el evento apunta a {ev['image_ref']!r}")
        elif not archivo.is_file():
            problemas.append(f"{cap['image_id']}: falta el archivo {cap['ruta']}")
        elif hashlib.sha256(archivo.read_bytes()).hexdigest() != cap["sha256"]:
            problemas.append(f"{cap['image_id']}: el SHA-256 de {cap['ruta']} no coincide")
        else:
            validas += 1
    con_ref = {cap["ruta"] for cap in capturas}
    for ev in eventos.values():
        if ev["image_ref"] and ev["image_ref"] not in con_ref:
            problemas.append(
                f"{ev['event_id']}: image_ref {ev['image_ref']} sin registro de captura"
            )
    return {
        "capturas": len(capturas),
        "vinculadas_validas": validas,
        "eventos_con_imagen": sum(1 for e in eventos.values() if e["image_ref"]),
        "problemas": problemas,
    }
