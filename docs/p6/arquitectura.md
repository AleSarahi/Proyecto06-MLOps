# Proyecto 6 · Arquitectura del centro de monitoreo

> Issue #1. Decisiones base del Proyecto 6 (individual). Todo lo que se cita del Proyecto 5 es un componente
> reutilizado; la lista completa está en [`autoria.md`](autoria.md).

## 1. Qué se construye

Un centro de monitoreo que convierte un **video de YouTube reproducido como stream** en inferencias reales de
**detección de objetos**, eventos persistentes, capturas vinculadas, métricas por grupo (G1–G7) y alertas, y que
permite consultar eventos y alertas en un **portal web**.

El sistema observa la operación y la confianza del modelo. **No mide calidad predictiva**: no hay etiquetas reales,
accuracy, precision, recall, F1, IoU ni mAP. Una puntuación alta es «aceptada por la política», no «correcta».

## 2. Decisiones

| Tema | Decisión | Por qué | Alternativas que se descartaron |
|---|---|---|---|
| Tarea | **Detección de objetos** | El detector YOLO11n de P5 ya está integrado, fijado por hash y probado en CPU. | Clasificación: habría que integrar otro modelo. |
| Modelo | **YOLO11n** preentrenado en COCO (Ultralytics 8.3.0, `yolo11n.pt`, SHA-256 `0ebbc80d…6ee1`) | Reutiliza `src/infer/` (carga verificada por hash, preprocesamiento documentado). Ficha: [`modelo.md`](modelo.md). | Entrenar uno propio: la rúbrica no lo pide. |
| Clases | Subconjunto COCO que aparece en el video (se fija en #6 con el video elegido) | Las clases de P5 (botella y taza) no aparecen en un video de calle. | Las 80 clases: aumenta el ruido sin aportar al monitoreo. |
| Fuente | **Video de YouTube** (lo recomienda el profe), descargado una sola vez con `yt-dlp` y verificado por SHA-256; se reproduce como **archivo de video** con `cv2.VideoCapture` a un ritmo declarado | Las mismas condiciones se pueden repetir. Ver [`fuente.md`](fuente.md). | Leer YouTube en vivo (frágil, sin hash). La cámara del carro (el evaluador no la tiene). |
| Respaldo sin red | Los frames muestreados de los segmentos de referencia, C1 y C2 se guardan en el repo con sus hashes | El video puede desaparecer y el evaluador puede no tener red; la guía pide «conservar una muestra reproducible». | Subir el video completo (pesa, `.gitignore` lo excluye y tiene derechos). |
| Ejecución | **Local, CPU**, Windows/macOS/Linux, Python 3.12 con `uv` | Es lo mismo que en P5 y no necesita GPU. | Nube o GPU: no se exigen. |
| Persistencia | **SQLite** (`sqlite3` de la biblioteca estándar) por corrida, más **exportación JSONL** de eventos, capturas, alertas y observaciones | Se puede consultar desde el portal sin un servidor de base de datos, y el JSONL se puede recalcular y versionar. | PostgreSQL (necesita un servidor), Prometheus (no guarda eventos con imágenes). |
| Portal | **Flask** con HTML generado en el servidor; una página de eventos y otra de alertas, con detalle | Es una sola dependencia, pequeña, y no hace falta construir nada de JavaScript. | Grafana (no muestra eventos con imágenes), Streamlit (más pesado). |
| Métricas | Cálculo propio con la biblioteca estándar sobre las observaciones guardadas, por ventana | Se puede recalcular sin servicios. Inventario: [`metricas.md`](metricas.md). | Prometheus/OTel: son opcionales. |
| Recursos (G3) | `psutil` para la RAM del proceso | Es multiplataforma. | Exporters de Prometheus. |

## 3. Recorrido de una observación

```text
 YouTube ──yt-dlp (una vez, SHA-256)──▶ video local ─┐            respaldo de frames (repo) ─┐
                                                     ▼                                       ▼
 01 Fuente      monitor.fuente   lee frame, aplica el muestreo declarado, asigna frame_id, tiempo en el video,
                                 timestamp UTC y reloj monotónico; cuenta descartes por motivo
                     │ Frame(frame_id, source_id, pos_ms, t_utc, t_mono, imagen)
                     ▼
 02 Inferencia  monitor.inferencia  YOLO11n real (src/infer/detector.py), candidatas ≥ piso de salida,
                                 tiempo de inferencia con perf_counter; estados ok / sin_detecciones / error
                     │
                     ▼
 03 Observaciones monitor.zonas   zona por candidata y por frame (baja / duda / aceptada)
                monitor.almacen   evento → SQLite + eventos.jsonl  (event_id)
                monitor.capturas  captura selectiva → capturas/<event_id>.jpg + sha256  (image_ref)
                monitor.observaciones  tiempos, descartes, RAM → observaciones.jsonl
                     │
                     ▼
 04 Reglas      monitor.reglas    ventanas, mínimo de observaciones, baja confianza, cambio sostenido
                                 frente a la referencia → alerta (alert_id, rule_id, event_ids)
                monitor.metricas  métricas base G1–G7 por ventana → metricas.json (con IDs de respaldo)
                     │
                     ▼
 05 Portal      monitor.portal    /eventos, /eventos/<id> (imagen, configuración, corrida), /alertas,
                                 /alertas/<id> (regla, ventana, eventos)
```

Los identificadores que unen todo son `run_id → frame_id → event_id → image_ref → alert_id`, junto con
`config_ref` y `model_ref` en cada registro. Con un `alert_id` se llega a sus eventos, de cada evento a su imagen y
a su configuración, y de ahí a la corrida (commit y entorno en `run.json`).

## 4. Componentes

| Paquete | Qué hace | Reutiliza de P5 | Issue |
|---|---|---|---|
| `src/monitor/config.py` | Carga y valida `config/p6/monitoreo.yaml` y calcula `config_ref` | Patrón de `src/control/config.py` | #4 |
| `src/monitor/contratos/` | Esquemas JSON de evento, captura y alerta | Validador de `src/contrato/` | #3 |
| `src/monitor/video.py` | Descarga y verifica el video, y extrae el respaldo de frames | — | #34 |
| `src/monitor/fuente.py` | Reproduce el video o el respaldo como stream | — | #5 |
| `src/monitor/inferencia.py` | Envuelve `DetectorJPEG` y mide tiempos | `src/infer/detector.py`, `pesos.py`, `config.py` | #6 |
| `src/monitor/zonas.py` | Dos umbrales y tres zonas | — | #11 |
| `src/monitor/almacen.py` | SQLite + exportación JSONL | — | #14 |
| `src/monitor/capturas.py` | Captura selectiva y verificador | — | #15 |
| `src/monitor/reglas.py` | Ventanas, regla sostenida y alertas | — | #13, #16, #17 |
| `src/monitor/metricas.py` | Métricas base por ventana | — | #18 |
| `src/monitor/recalculo.py` | Recálculo independiente desde los JSONL | — | #19 |
| `src/monitor/portal.py` | Portal Flask | — | #20, #21 |
| `src/monitor/__main__.py` | `python -m monitor correr …` | — | — |

Lo que **no** se usa de P5: la política de manejo y el supervisor (`src/control/`), los casos C1–C10 de control
(`casos/`), las métricas de calidad contra anotaciones (`src/metricas/`), el firmware y el lazo en vivo con el
carro. Siguen en el repo como historial; ver [`autoria.md`](autoria.md).

## 5. Ritmo de entrada y muestreo

- El video se lee frame por frame en el orden original. Se **infiere 1 frame cada `muestreo.cada_n_frames`**
  (lo dice la configuración) y el resto se descarta con el motivo `muestreo`.
- La reproducción respeta el tiempo del video (`pos_ms`), escalado por `muestreo.velocidad` (1.0 = tiempo real).
  Si la inferencia se atrasa más de `muestreo.atraso_max_ms`, los frames pendientes se descartan con el motivo
  `saturacion`, como haría una fuente en vivo.
- Los frames consecutivos se parecen mucho: el muestreo los separa, y las proporciones se reportan por ventana
  con su número de observaciones; no se presentan como muestras independientes.

## 6. Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| El video desaparece o cambia | SHA-256 en el manifiesto y respaldo de frames en el repo (#34). |
| El repo es público y los frames son de un tercero | Se elige un video con licencia Creative Commons y se pone la atribución (#34, #26). |
| El segmento de C2 no da scores bajos reales | Se prueba con el modelo antes de fijar los umbrales y, si hace falta, se elige otro segmento o video (#8). Nunca se inyectan scores. |
| El piso de salida esconde la zona baja | El piso de P6 queda por debajo del umbral inferior y se valida al arrancar (#6, #11). |
| Los C1/C2 de P5 se confunden con los de P6 | Los escenarios de P6 viven en `evidencias/p6/escenarios/c1-normal` y `c2-baja-confianza`. |
| La entrega es individual en un repo que fue de equipo | La autoría y los componentes reutilizados están declarados en [`autoria.md`](autoria.md) (#26). |
