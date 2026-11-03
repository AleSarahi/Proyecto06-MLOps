# modelo/ · Ficha del detector

Detector de obstáculos (entregable **E2**, P5-07). Esta ficha basta para saber qué modelo es, de dónde
sale, con qué licencia y cómo recuperarlo sin preguntar. Por qué se eligió está en
[`DECISION.md`](DECISION.md) (P5-04); los parámetros y sus validaciones, en
[`config/DETECTOR.md`](../config/DETECTOR.md) (P5-05).

## Qué modelo es

| Campo | Valor |
|---|---|
| Modelo | YOLO11n de Ultralytics, detector COCO de 80 clases (aquí solo se usan 2) |
| Archivo | `yolo11n.pt`, checkpoint de PyTorch |
| Origen | [release v8.3.0 de `ultralytics/assets`](https://github.com/ultralytics/assets/releases/tag/v8.3.0): `https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt` |
| Metadatos del checkpoint | `date` 2024-09-25T21:10:26, `version` 8.2.100 (Ultralytics con que se guardó), `license` "AGPL-3.0 License (https://ultralytics.com/license)" |
| Tamaño | 5 613 764 B |
| SHA-256 | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`, el mismo que `artifacts.expected_model_sha256` de [`config/detector.json`](../config/detector.json) |
| Dónde queda | `modelo/descargas/yolo11n.pt` (`artifacts.weights_path`), fuera de Git (`.gitignore`) |

## Cómo recuperar los pesos

Desde la raíz del repo, con red y una sola vez (después de `uv sync --locked`):

```bash
uv run --locked python -m infer.descarga
# .../modelo/descargas/yolo11n.pt: descargado, 5613764 B, SHA-256 0ebbc80d…6ee1 OK
```

- Baja el archivo de la release, comprueba el tamaño y el SHA-256 de `config/detector.json` y solo
  entonces lo deja en `modelo/descargas/`. Si no coincide, no queda nada en esa ruta y sale con 2.
- Si el archivo ya está y coincide, no vuelve a bajarlo (`ya estaba`). Si está pero es otro, falla y no
  lo sobrescribe: hay que borrarlo a mano.
- `--destino <ruta>` lo guarda en otro lado; `--url <url>` lo baja de otra fuente, con el mismo
  SHA-256 obligatorio.
- Después, todo corre sin red: `--weights modelo/descargas/yolo11n.pt` en `infer`, y
  `P5_05_YOLO11N_PT=modelo/descargas/yolo11n.pt` para las pruebas con el detector real.
- Para comprobarlo a mano: `sha256sum modelo/descargas/yolo11n.pt` (Git Bash) o
  `Get-FileHash modelo\descargas\yolo11n.pt` (PowerShell).

**PEND-11, pesos:** fuera de Git, con descarga automatizable y hash, como permite la guía. Pesan menos
de 50 MB y cabrían, pero así el repo no redistribuye los pesos AGPL-3.0 (ver Licencia) y se conserva
la ruta que ya fijaban `config/detector.json` y `.gitignore`.

## Clases

COCO completo dentro del modelo; `postprocess.class_ids` deja solo dos ([`clases.json`](clases.json)):

| `class_id` | Nombre COCO | Obstáculo |
|---|---|---|
| 39 | `bottle` | botella |
| 41 | `cup` | taza |

Al cargar, `infer.pesos` comprueba que el checkpoint diga `bottle` en 39 y `cup` en 41.

## Entrada, preprocesamiento y posprocesamiento

Los hace Ultralytics 8.3.0 dentro de `predict`; los valores salen de `config/detector.json`.

- **Entrada:** JPEG decodificado con `cv2.imread` (BGR), pasado a RGB, BCHW, `float32` entre 255.
- **Resolución:** `imgsz` 640 con letterbox de rectángulo mínimo (múltiplo de stride 32), centrado,
  relleno 114, `INTER_LINEAR`.
- **Ejecución:** CPU, FP32, batch 1, 2 hilos de PyTorch, sin aumentos.
- **Posprocesamiento:** confianza ≥ 0.25, NMS por clase con IoU 0.7, hasta 300 cajas, solo clases 39 y
  41. Cajas `xyxy` en píxeles de la imagen original, recortadas al borde.

## Runtime (D-02)

PyTorch con el checkpoint `.pt` a través de Ultralytics, no ONNX Runtime: es la ruta que midió P5-04
y la que valida P5-05, y deja el letterbox y el NMS a Ultralytics en vez de escribirlos aparte.

| Paquete | Versión |
|---|---|
| Python | 3.12 |
| `ultralytics` | 8.3.0 |
| `torch` | 2.9.0 (en Linux, rueda CPU del índice de PyTorch) |
| `torchvision` | 0.24.0 |
| `opencv-python` | 4.11.0.86 |
| `numpy` | 1.26.4 |

Están fijadas en [`pyproject.toml`](../pyproject.toml) y [`uv.lock`](../uv.lock), y forman parte del
`config_sha256`. `infer` se niega a cargar el modelo si el entorno instalado tiene otras.

## Licencia

- **Código de Ultralytics:** AGPL-3.0.
- **Pesos:** AGPL-3.0. Lo dice el propio checkpoint en sus metadatos (`license`), y la
  [página de licencia de Ultralytics](https://www.ultralytics.com/license) declara que sus modelos se
  ofrecen bajo AGPL-3.0 o con licencia Enterprise. Este proyecto no tiene licencia Enterprise.

Cómo aplica a esta entrega (lectura del equipo, no asesoría legal):

- Ni el código de Ultralytics ni los pesos se modifican: se usan tal como se publican.
- Los pesos no se redistribuyen: cada quien los baja de la release oficial con `infer.descarga`.
- No hay servicio en red: todo corre offline en CPU, así que la cláusula de acceso por red de la
  AGPL-3.0 (sección 13) no entra en juego.
- El repo es público y contiene todo el código fuente del proyecto, pero no declara licencia propia.
  Si se distribuyera junto con Ultralytics como una sola obra, la AGPL-3.0 pediría ofrecer ese código
  bajo AGPL-3.0. Elegir la licencia del repo les toca a las PM, no a este ticket.
- Atribución: Glenn Jocher y Jing Qiu, *Ultralytics YOLO11* (2024),
  <https://github.com/ultralytics/ultralytics>, AGPL-3.0.

## Otros archivos de esta carpeta

- [`DECISION.md`](DECISION.md): candidatos, licencias y razón de la elección (P5-04).
- [`clases.json`](clases.json): las dos clases del dominio.
- `configuracion.p5-04.propuesta.json` y su `.sha256`: la configuración que propuso P5-04, antecedente
  de `config/detector.json`.
- [`experimentos-publicados/`](experimentos-publicados/README.md): scripts y evidencia de P5-04.
- `descargas/`: los pesos que baja `infer.descarga`. No se sube.
