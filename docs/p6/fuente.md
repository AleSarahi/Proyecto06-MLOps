# Proyecto 6 · Fuente visual: video de YouTube como stream

> Issues #34 y #5 (R1.1). Configuración: [`config/p6/fuentes.yaml`](../../config/p6/fuentes.yaml). Código:
> [`src/monitor/video.py`](../../src/monitor/video.py) y [`src/monitor/fuente.py`](../../src/monitor/fuente.py).

## Videos

| Uso | Video | Autor (canal) | Licencia | Formato | SHA-256 |
|---|---|---|---|---|---|
| Referencia y C1 | [4K Road traffic video for object detection and tracking](https://www.youtube.com/watch?v=MNn9qKG2UFI) (2018) | Karol Majek | Creative Commons Attribution (reuse allowed) | 136 · MP4/H.264 1280×720 30 fps · 86 312 442 B | `adcda3e9…e166f9` |
| C2 | [Night Traffic](https://www.youtube.com/watch?v=jKl0o9Ydi5Q) (2017) | Chalie Juno | Creative Commons Attribution (reuse allowed) | 136 · MP4/H.264 1280×720 30 fps · 4 595 103 B | `eb96b39d…b478d7` |

**Atribución:** los frames de `datos/p6/frames/` y las capturas de `evidencias/p6/` son fotogramas de estos
videos, reutilizados bajo su licencia CC BY con atribución a sus autores. El profe recomendó usar un video de
YouTube como fuente; se eligieron videos con licencia CC BY porque el repositorio es público.

**Por qué estos videos:** el primero se publicó precisamente para probar detección de objetos (tráfico denso de
día, buena luz) y es la condición representativa. El segundo es tráfico de noche (faros, poca luz, objetos lejanos)
y, con el modelo real, da puntuaciones bajas: es la condición de C2 sin alterar ninguna imagen ni ningún score.

## Segmentos

| Segmento | Video | Tramo | Frames inferidos | Condición |
|---|---|---|---|---|
| `referencia` | día | 0–90 s | 90 | Representativa |
| `c1` | día | 120–210 s | 90 | Operación normal; otro tramo del mismo video |
| `c2` | noche | 0–24 s | 24 | Poca luz (baja confianza) |

## Ritmo y política de muestreo (R1.1)

- **Muestreo:** se infiere **1 de cada 30 frames** del video, contados desde su frame 0 (`muestreo.cada_n_frames`).
  A 30 fps equivale a **1 frame por segundo de video**. Los demás frames se descartan con el motivo `muestreo`
  y quedan contados en `run.json → conteos.fuente.descartes`: 2610 en C1 y 696 en C2.
- **Ritmo:** la fuente entrega cada frame a su hora de video escalada por `muestreo.velocidad`. Con 1.0 (tiempo
  real, como en las corridas de evidencia) llega un frame por segundo de reloj. Con `--velocidad 0` se procesan sin
  esperar (solo para pruebas).
- **Saturación:** si un frame espera más de `atraso_max_ms` = 3000 ms desde su llegada, se descarta con el motivo
  `saturacion` y queda en `observaciones.jsonl`. En las corridas de evidencia no hubo ninguno.
- **Fallos de lectura:** un frame ilegible o con un hash distinto al del manifiesto produce un evento
  `status=error` (`unreadable_image`); no se inventa una inferencia.
- **Identidad de cada frame:** `frame_id = <segmento>-f<índice en el video>`, `video_pos_ms`, `t_mono_ms` (reloj de
  la corrida) y `timestamp_utc`.

## Reproducción y respaldo sin red

```bash
uv run python -m monitor video descargar     # baja el formato 136 con yt-dlp y exige el SHA-256
uv run python -m monitor video extraer --segmento c1   # solo si se quiere regenerar el respaldo
uv run python -m monitor video verificar     # hashes del respaldo y de los videos locales
```

- Los videos se guardan en `datos/p6/video/`, fuera de Git (`.gitignore`). Dos descargas del formato 136 dieron
  bytes idénticos, así que el SHA-256 sirve para verificarlos.
- **Respaldo:** `datos/p6/frames/<segmento>/` tiene los frames muestreados en JPEG (calidad 85) y un
  `manifiesto.jsonl` con el SHA-256, el índice en el video y `pos_ms` de cada uno, más la URL, la licencia y el hash
  del video de origen. Es la **entrada canónica** de la referencia, C1 y C2 (`--modo frames`, por defecto), así que
  los escenarios se reproducen sin red y con los mismos píxeles.
- Si YouTube cambia o quita un video, la descarga falla por el hash y no se guarda nada. Los escenarios siguen
  funcionando con el respaldo.
- `--modo video` lee el MP4 directamente con OpenCV y aplica el mismo muestreo; es una opción, no lo que se usó
  para la evidencia.
