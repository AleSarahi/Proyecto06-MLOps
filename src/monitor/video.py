"""Video de YouTube: descarga verificada y respaldo de frames por segmento (issue #34).

- `descargar`: baja el formato fijo de config/p6/fuentes.yaml con yt-dlp a datos/p6/video/ y exige
  el SHA-256 declarado. Si el archivo existe y coincide, no vuelve a bajarlo; si es otro, falla.
- `extraer`: lee el video en orden, aplica el muestreo (1 de cada N frames, contado desde el frame 0
  del video) y guarda como JPEG los frames del segmento [inicio_s, fin_s) con su manifiesto. Esa
  secuencia es el respaldo sin red y la entrada canónica de los escenarios.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import RAIZ, ErrorConfig

DIR_FRAMES = RAIZ / "datos" / "p6" / "frames"
PENDIENTE = "PENDIENTE"
# Calidad JPEG del respaldo: equilibrio entre fidelidad y tamaño del repo (~150 KB por frame 720p).
CALIDAD_RESPALDO = 85


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _ruta(video: dict[str, Any]) -> Path:
    p = Path(video["archivo"])
    return p if p.is_absolute() else RAIZ / p


def verificar(nombre: str, video: dict[str, Any]) -> str:
    """Devuelve el SHA-256 del archivo local; falla si no existe o no coincide con el declarado."""
    ruta = _ruta(video)
    if not ruta.is_file():
        raise ErrorConfig(f"{nombre}: no existe {ruta}; corre `python -m monitor video descargar`")
    real = sha256_archivo(ruta)
    esperado = video.get("sha256")
    if esperado not in (None, PENDIENTE) and real != esperado:
        raise ErrorConfig(
            f"{nombre}: el SHA-256 de {ruta.name} es {real}, se esperaba {esperado}. YouTube pudo "
            "cambiar el archivo: usa el respaldo de frames de datos/p6/frames/ (docs/p6/fuente.md)."
        )
    return real


def descargar(nombre: str, video: dict[str, Any]) -> str:
    ruta = _ruta(video)
    if ruta.is_file():
        sha = verificar(nombre, video)
        print(f"{nombre}: ya estaba ({ruta.name}, SHA-256 {sha[:12]}…)")
        return sha
    import yt_dlp

    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(".part.mp4")
    opciones = {
        "format": video["formato"],
        "outtmpl": str(temporal),
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opciones) as ydl:
        ydl.download([video["url"]])
    sha = sha256_archivo(temporal)
    esperado = video.get("sha256")
    if esperado not in (None, PENDIENTE) and sha != esperado:
        temporal.unlink()
        raise ErrorConfig(
            f"{nombre}: se descargó un archivo con SHA-256 {sha}, se esperaba {esperado}. No se "
            "guardó. Usa el respaldo de frames de datos/p6/frames/ (docs/p6/fuente.md)."
        )
    temporal.replace(ruta)
    print(f"{nombre}: descargado {ruta.name}, {ruta.stat().st_size} B, SHA-256 {sha}")
    return sha


def _extraer_tramo(
    carpeta: Path,
    video: dict[str, Any],
    inicio_s: float,
    fin_s: float,
    cada_n_frames: int,
    *,
    prefijo: str,
    desfase_ms: float,
    extra: dict[str, Any],
) -> tuple[list[dict[str, Any]], float, int]:
    """Frames muestreados de [inicio_s, fin_s) del video; pos_ms = desfase + (pos - inicio)."""
    import cv2

    cap = cv2.VideoCapture(str(_ruta(video)))
    if not cap.isOpened():
        raise ErrorConfig(f"no se pudo abrir {video['archivo']}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    filas = []
    indice = 0
    frames_tramo = 0
    try:
        while True:
            if not cap.grab():
                break
            pos_ms = indice * 1000.0 / fps
            if pos_ms >= fin_s * 1000:
                break
            if pos_ms >= inicio_s * 1000:
                frames_tramo += 1
            if indice % cada_n_frames == 0 and pos_ms >= inicio_s * 1000:
                ok, imagen = cap.retrieve()
                if ok:
                    frame_id = f"{prefijo}-f{indice:06d}"
                    archivo = carpeta / f"{frame_id}.jpg"
                    if not cv2.imwrite(
                        str(archivo), imagen, [cv2.IMWRITE_JPEG_QUALITY, CALIDAD_RESPALDO]
                    ):
                        raise ErrorConfig(f"no se pudo escribir {archivo}")
                    filas.append(
                        {
                            "frame_id": frame_id,
                            "archivo": archivo.name,
                            "sha256": sha256_archivo(archivo),
                            "indice_video": indice,
                            "pos_ms": round(desfase_ms + pos_ms - inicio_s * 1000, 3),
                            **({**extra, "pos_video_ms": round(pos_ms, 3)} if extra else {}),
                            "width": int(imagen.shape[1]),
                            "height": int(imagen.shape[0]),
                        }
                    )
            indice += 1
    finally:
        cap.release()
    return filas, fps, frames_tramo


def extraer(
    segmento: str, fuentes: dict[str, Any], cada_n_frames: int, *, destino: Path | None = None
) -> Path:
    """Escribe <destino>/<segmento>/*.jpg y su manifiesto; no sobrescribe un respaldo existente.

    Un segmento simple conserva el tiempo del video. Una secuencia (`tramos`) concatena los tramos:
    su tiempo va de 0 a la suma de duraciones y cada fila guarda su video y `pos_video_ms`."""
    seg = fuentes["segmentos"][segmento]
    carpeta = (destino or DIR_FRAMES) / segmento
    if (carpeta / "manifiesto.jsonl").exists():
        raise ErrorConfig(f"{carpeta} ya tiene un respaldo; bórralo a mano si quieres regenerarlo")
    if "tramos" not in seg:
        nombre_video = seg["video"]
        video = fuentes["videos"][nombre_video]
        sha_video = verificar(nombre_video, video)
        carpeta.mkdir(parents=True, exist_ok=True)
        filas, fps, _ = _extraer_tramo(
            carpeta,
            video,
            seg["inicio_s"],
            seg["fin_s"],
            cada_n_frames,
            prefijo=segmento,
            desfase_ms=seg["inicio_s"] * 1000,
            extra={},
        )
        cabecera = {
            "segmento": segmento,
            "video": nombre_video,
            "youtube_id": video["youtube_id"],
            "url": video["url"],
            "licencia": video["licencia"],
            "canal": video["canal"],
            "formato": video["formato"],
            "video_sha256": sha_video,
            "fps_video": fps,
            "cada_n_frames": cada_n_frames,
            "inicio_s": seg["inicio_s"],
            "fin_s": seg["fin_s"],
            "frames": len(filas),
        }
    else:
        carpeta.mkdir(parents=True, exist_ok=True)
        filas, tramos, desfase, total_video, fps_todos = [], [], 0.0, 0, set()
        for k, t in enumerate(seg["tramos"]):
            video = fuentes["videos"][t["video"]]
            sha_video = verificar(t["video"], video)
            f, fps, n_video = _extraer_tramo(
                carpeta,
                video,
                t["inicio_s"],
                t["fin_s"],
                cada_n_frames,
                prefijo=f"{segmento}-t{k}",
                desfase_ms=desfase,
                extra={"tramo": k, "video": t["video"]},
            )
            filas += f
            fps_todos.add(fps)
            total_video += n_video
            tramos.append(
                {
                    "tramo": k,
                    "video": t["video"],
                    "youtube_id": video["youtube_id"],
                    "url": video["url"],
                    "licencia": video["licencia"],
                    "canal": video["canal"],
                    "formato": video["formato"],
                    "video_sha256": sha_video,
                    "inicio_s": t["inicio_s"],
                    "fin_s": t["fin_s"],
                    "inicio_segmento_s": desfase / 1000,
                    "frames": len(f),
                }
            )
            desfase += (t["fin_s"] - t["inicio_s"]) * 1000
        if len(fps_todos) != 1:
            raise ErrorConfig(f"{segmento}: los tramos tienen fps distintos {sorted(fps_todos)}")
        cabecera = {
            "segmento": segmento,
            "secuencia": True,
            "url": " · ".join(dict.fromkeys(t["url"] for t in tramos)),
            "licencia": " · ".join(dict.fromkeys(t["licencia"] for t in tramos)),
            "canal": " · ".join(dict.fromkeys(t["canal"] for t in tramos)),
            "tramos": tramos,
            "fps_video": fps_todos.pop(),
            "cada_n_frames": cada_n_frames,
            "inicio_s": 0,
            "fin_s": desfase / 1000,
            "frames": len(filas),
            "frames_video": total_video,
        }
    with (carpeta / "manifiesto.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"cabecera": cabecera}, ensure_ascii=False) + "\n")
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(f"{segmento}: {len(filas)} frames en {carpeta}")
    return carpeta


def leer_manifiesto(carpeta: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lineas = (carpeta / "manifiesto.jsonl").read_text(encoding="utf-8").splitlines()
    cabecera = json.loads(lineas[0])["cabecera"]
    return cabecera, [json.loads(linea) for linea in lineas[1:] if linea.strip()]


def verificar_respaldo(carpeta: Path) -> list[str]:
    """Errores del respaldo: archivos ausentes o con hash distinto. Lista vacía = íntegro."""
    _, filas = leer_manifiesto(carpeta)
    errores = []
    for fila in filas:
        archivo = carpeta / fila["archivo"]
        if not archivo.is_file():
            errores.append(f"falta {archivo}")
        elif sha256_archivo(archivo) != fila["sha256"]:
            errores.append(f"hash distinto en {archivo}")
    return errores
