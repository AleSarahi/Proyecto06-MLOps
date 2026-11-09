# Proyecto 6 · Modelo

> Issue #7 (R1.3). Ficha completa del artefacto (heredada de P5): [`modelo/README.md`](../../modelo/README.md).

| Campo | Valor |
|---|---|
| Tarea | Detección de objetos |
| Modelo | YOLO11n (Ultralytics), preentrenado en COCO (80 clases); no se entrenó ni se ajustó |
| Archivo | `yolo11n.pt` de la [release v8.3.0 de `ultralytics/assets`](https://github.com/ultralytics/assets/releases/tag/v8.3.0) |
| SHA-256 (`model_ref`) | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` (5 613 764 B) |
| Licencia | AGPL-3.0 (Ultralytics) |
| Cómo obtenerlo | `uv run python -m infer.descarga`: lo deja en `modelo/descargas/` (fuera de Git) solo si el SHA-256 coincide |
| Clases usadas | 0 person, 1 bicycle, 2 car, 3 motorcycle, 5 bus, 7 truck (las de tráfico que aparecen en el video) |
| Configuración del detector | [`config/p6/detector.json`](../../config/p6/detector.json), con `config_sha256` en el `run.json` de cada corrida |
| Preprocesamiento | JPEG → BGR (OpenCV) → RGB, letterbox a 640 (stride 32, relleno 114, `INTER_LINEAR`), /255, BCHW, float32, batch 1 |
| Posprocesamiento | piso de confianza **0.10**, NMS IoU 0.7 por clase, `max_det` 300, cajas `xyxy` en píxeles del frame original |
| Entorno de ejecución | Local, **CPU** (2 hilos de Torch), Python 3.12, ultralytics 8.3.0, torch 2.9.0, torchvision 0.24.0, opencv-python 4.11.0.86, numpy 1.26.4. Las corridas de evidencia se hicieron en Windows 11 con Intel 11.ª gen, 8 hilos y 7.7 GiB de RAM. Cada `run.json` guarda su `entorno` y su commit. |

**Diferencias con P5:** el mismo artefacto y el mismo preprocesamiento. Cambian solo las clases (P5 usaba botella
y taza) y el piso, que baja de 0.25 a 0.10 para que la zona de baja confianza (< 0.30) se pueda observar.
`src/infer/config.py` acepta ahora un catálogo de clases configurable; P5 conserva su valor por defecto.

**Procedencia de cada salida:** cada evento lleva `model_ref` (el SHA-256 calculado al cargar los pesos, no el
declarado) y `config_ref`. La carga verifica el hash antes de construir el modelo (`infer.pesos.cargar_pesos`), y
`tests/test_p6_modelo.py` corre el modelo real sobre frames de C2 cuando los pesos están disponibles.
