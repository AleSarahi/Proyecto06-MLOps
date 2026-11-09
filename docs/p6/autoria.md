# Proyecto 6 · Autoría, aportación propia y componentes reutilizados

> Issue #26 (R7.3). El Proyecto 6 es una **entrega individual**.

## Autora

| | |
|---|---|
| Estudiante | Alejandra Rayas (GitHub `AleSarahi`) |
| Matrícula | _pendiente de completar por la autora_ |
| Materia | Integración de Servicios de Aprendizaje Automático (MLOps), ITESO |
| Repositorio | <https://github.com/AleSarahi/Proyecto06-MLOps> |
| Inicio del trabajo del Proyecto 6 | commit `243c31a` (`P6-2`). Lo anterior (hasta `4ab8ac1`) es el Proyecto 5 de equipo. |

El repositorio parte de una copia del repositorio de equipo del Proyecto 5 (Mini Tesla), donde la autora fue A3
(repositorio, entorno, CI, métricas y benchmark). Reutilizar el Proyecto 5 está permitido; abajo se declara qué se
reutilizó y de quién es.

## Aportación propia del Proyecto 6

Todo lo siguiente se escribió para el Proyecto 6 (commits con prefijo `P6-`):

- `src/monitor/` completo: configuración y `config_ref`, video de YouTube y respaldo de frames, fuente como stream,
  envoltorio de inferencia con tiempos, zonas, contratos, persistencia SQLite, capturas, ventanas, reglas y
  alertas, métricas G1–G7, referencia, CLI y portal Flask.
- `config/p6/` (monitoreo, fuentes, detector de P6 y contratos v1 con sus ejemplos).
- `datos/p6/frames/` (respaldo extraído de los videos) y todo `evidencias/p6/`, incluido el script de recálculo
  independiente.
- `tests/test_p6_*.py`.
- `docs/p6/` y el README del Proyecto 6.
- Cambios al material heredado: el CI acepta ramas y PR `p6-NN`/`P6-NN`, `pyproject.toml` se renombró y tiene
  dependencias nuevas, y `src/infer/config.py` acepta un catálogo de clases configurable (el comportamiento de P5
  se conserva por defecto).

## Componentes reutilizados

| Componente | Ruta | Origen | Autoría | Uso en P6 |
|---|---|---|---|---|
| Carga verificada de pesos, detector validado en CPU y descarga de pesos | `src/infer/pesos.py`, `detector.py`, `config.py`, `descarga.py`, `reloj.py` | Proyecto 5 (P5-04 a P5-07) | Heriberto Vlaminck (A1, usuario `BeetlejuiceXD`) | Se usa sin cambios, salvo el parámetro `clases_aprobadas` de `config.py` (aportación P6). |
| Ficha del modelo | `modelo/README.md`, `modelo/DECISION.md` | Proyecto 5 | Heriberto Vlaminck, con revisiones de Luis Santana y de la autora | Referencia del artefacto; la ficha de P6 está en [`modelo.md`](modelo.md). |
| Entorno fijado (`uv`, `uv.lock`), CI (Ruff + pytest) y convención de ramas | `pyproject.toml`, `uv.lock`, `.github/` | Proyecto 5 (P5-01) | La autora (A3) | Se reutiliza y se adapta a P6. |
| Resto del Proyecto 5 (política, supervisor, casos C1–C10, métricas de calidad, firmware, lazo en vivo) | `src/control/`, `casos/`, `src/metricas/`, `src/trazabilidad/`, `firmware/`, `src/vivo/`, `README-P5.md`, ... | Proyecto 5 | Equipo del Proyecto 5 (ver [`README-P5.md`](../../README-P5.md)) | **No se usa** en P6; se conserva como historial. |

## Terceros

| Componente | Licencia | Uso |
|---|---|---|
| YOLO11n (`yolo11n.pt`), Ultralytics 8.3.0 | AGPL-3.0 | Modelo preentrenado (sin reentrenar). |
| Video «4K Road traffic video for object detection and tracking», Karol Majek | CC BY (YouTube) | Fuente de la referencia y de C1; frames en el repo con atribución. |
| Video «Night Traffic», Chalie Juno | CC BY (YouTube) | Fuente de C2; frames en el repo con atribución. |
| yt-dlp, Flask, psutil, OpenCV, PyTorch, jsonschema, PyYAML | Las de cada paquete (ver `uv.lock`) | Descarga, portal, RAM del proceso, decodificación e inferencia, validación y configuración. |

El repositorio está bajo AGPL-3.0 ([`LICENSE`](../../LICENSE)), compatible con Ultralytics.

## Uso de asistentes de IA

Parte del código, de las pruebas y de la documentación del Proyecto 6 se escribió con ayuda de Claude Code. Los
commits correspondientes llevan la línea `Co-Authored-By: Claude`. La autora dirigió las decisiones de alcance,
fuente y fechas y es responsable de revisar la entrega.
