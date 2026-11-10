# Proyecto 6 · Inventario de métricas G1–G7

> Issues #9, #10, #18 y #19. Hay una **métrica base por grupo** y los **siete grupos aplican**. No se reclaman
> métricas adicionales (ver [`evidencias/p6/indice.md`](../../evidencias/p6/indice.md#extras)).
> Ninguna métrica es de calidad predictiva: no hay etiquetas, accuracy, precision, recall, IoU ni mAP.

## Aplicabilidad

| Grupo | ¿Aplica? | Justificación desde la arquitectura | Métrica base |
|---|---|---|---|
| G1 Salud y rendimiento del servicio | **Sí** | Hay un procesamiento de inferencias (sin endpoint HTTP, que la rúbrica no exige). | Tiempo de inferencia p95 |
| G2 Captura y procesamiento del stream | **Sí** | La fuente es un video reproducido como stream a 1 fps. | FPS de procesamiento |
| G3 Uso de recursos | **Sí** | No hay GPU, pero se puede medir la RAM del proceso con psutil. | RAM RSS máxima del proceso |
| G4 Comportamiento de las predicciones | **Sí** | Hay puntuaciones por candidata; no hace falta etiquetarlas. | Proporción de baja confianza |
| G5 Datos y trazabilidad | **Sí** | Hay eventos e imágenes capturadas con referencias. | Imágenes vinculadas |
| G6 Dispositivos, fuentes y versiones | **Sí** | Cada evento reporta el modelo y la configuración; hay una versión esperada con la que comparar. | Versión esperada frente a reportada |
| G7 Alertas, recuperación y costos | **Sí** | Hay alertas con estado abierta/cerrada por ventana. | Alertas activas al cierre de la ventana |

G = 7. Ninguna métrica base se repite entre grupos.

## Reglas comunes

- **Ventana:** intervalos de 10 s de **tiempo de video**, sin traslape, contados desde el inicio del segmento
  (`[k·10 s, (k+1)·10 s)`). A 1 fps son 10 frames; la última ventana de un segmento puede quedar incompleta (C2
  dura 24 s, así que su ventana 2 tiene 4 frames).
- **Cero observaciones:** el valor es `null` con `n = 0`. Nunca se reporta 0 en lugar de «sin datos».
- **Frames consecutivos:** se parecen mucho. El muestreo a 1 fps los separa, pero las métricas describen la
  corrida y **no** se presentan como muestras independientes.
- **Dónde se calculan:** [`src/monitor/metricas.py`](../../src/monitor/metricas.py), al final de cada corrida, y
  se guardan en `metricas.json` (por ventana y por corrida). Se recalculan con `python -m monitor metricas
  <corrida>`.
- **Verificación independiente (M5):** [`evidencias/p6/recalcular.py`](../../evidencias/p6/recalcular.py), escrito
  solo con la biblioteca estándar y sin importar `monitor`, vuelve a calcular todo desde los JSONL y lo compara.
  Salidas: [`evidencias/p6/recalculo/`](../../evidencias/p6/recalculo/). En las tres corridas el resultado es
  «todo coincide».
- **Fuentes de datos primarios (M2/M4):** `observaciones.jsonl` (un registro por frame procesado, con
  `event_id`), `eventos.jsonl`, `ventanas.jsonl` (con los `event_ids` de cada ventana), `capturas.jsonl` y
  `alertas.jsonl` de cada corrida. Cada valor por ventana de `metricas.json` lista los `event_ids` que lo respaldan.

## G1 · Tiempo de inferencia p95 (base)

| | |
|---|---|
| **Qué mide (M1)** | Duración de la llamada al modelo, separada de la captura, la decodificación, la persistencia y la captura de imágenes. |
| Unidad | ms |
| Fórmula | Percentil 95 por rango cercano: el valor en la posición `ceil(0.95·n)` de los tiempos ordenados. |
| Población | Frames con intento de inferencia (`inferencia_ms` no nulo). Los frames ilegibles y los descartados por saturación no se cuentan. |
| Ventana | Por ventana de 10 s y por corrida. |
| Cero observaciones | `null`, `n = 0`. |
| **Adquisición (M2)** | `time.perf_counter()` antes y después de `DetectorJPEG.inferir` en [`inferencia.py`](../../src/monitor/inferencia.py); se guarda en `observaciones.jsonl` (`inferencia_ms`) y en el evento (`tiempos_ms.inferencia`). |
| **Cálculo (M3)** | `percentil_rango_cercano` en `metricas.py`; pruebas en `tests/test_p6_unidad.py::test_percentil_rango_cercano`. |
| **Trazabilidad (M4)** | `metricas.json → G1.por_ventana[i].event_ids` → `observaciones.jsonl` (mismo `event_id`). |
| **Resultado (M5)** | C1: **499.05 ms** (n = 90). C2: **484.42 ms** (n = 24). Recalculado por `recalcular.py`. |

Límite: a 1 fps la CPU baja de frecuencia entre frames, por eso el p95 en tiempo real (~500 ms) es mayor que con
`--velocidad 0` (~220 ms). Las dos cifras miden lo mismo con cargas distintas y no se mezclan.

## G2 · FPS de procesamiento (base)

| | |
|---|---|
| **Qué mide (M1)** | Frames inferidos por segundo de reloj en la ventana. |
| Unidad | frames inferidos / s |
| Fórmula | `n_inferidos / ((max t_fin_inferencia − min t_llegada) / 1000)`, con tiempos del reloj monotónico de la corrida. |
| Población | Frames con inferencia. No se cuentan los descartados por muestreo (2610 en C1 y 696 en C2, registrados en `run.json → conteos.fuente.descartes`) ni los descartados por saturación (0). |
| Ventana | Por ventana y por corrida. |
| Cero o una observación | `null` (no hay intervalo que medir). |
| **Adquisición (M2)** | La fuente fija `t_llegada_ms` de cada frame según su tiempo de video y la velocidad; la inferencia fija `t_fin_inferencia_ms`. Las dos van en `observaciones.jsonl`. |
| **Cálculo (M3)** | `_fps` en `metricas.py`. |
| **Trazabilidad (M4)** | Igual que G1. |
| **Resultado (M5)** | C1: **1.0059 fps**; C2: **1.0307 fps**. Coincide con el muestreo declarado (1 fps, tiempo real): no hubo atraso. |

## G3 · RAM RSS máxima del proceso (base)

| | |
|---|---|
| **Qué mide (M1)** | Memoria residente (RSS) del proceso que corre el monitoreo; no es la del equipo. |
| Unidad | MiB (2^20 bytes) |
| Fórmula | `max(rss_bytes) / 2^20` sobre las muestras de la ventana. |
| Población | Una muestra por frame procesado, tomada al terminar de registrarlo. |
| Ventana | Por ventana y por corrida. |
| Cero observaciones | `null`. |
| **Adquisición (M2)** | `psutil.Process().memory_info().rss` en [`corrida.py`](../../src/monitor/corrida.py), guardado en `observaciones.jsonl` (`rss_bytes`). |
| **Resultado (M5)** | C1: **384.2 MiB**; C2: **377.18 MiB** (equipo con 7.7 GiB de RAM total, según `run.json → entorno`). |

## G4 · Proporción de baja confianza (base)

| | |
|---|---|
| **Qué mide (M1)** | Fracción de detecciones candidatas con puntuación por debajo del umbral inferior. Describe salidas, **no** aciertos. |
| Unidad | fracción de candidatas (0–1) |
| Fórmula | `candidatas con s < inferior / candidatas puntuadas`, con inferior = 0.30. |
| Población | Candidatas que deja pasar el detector: score ≥ piso de 0.10, después de un NMS con IoU 0.7, solo de las clases configuradas. Los frames sin detecciones y los errores no aportan candidatas (el denominador es por candidata, no por frame). |
| Ventana | Por ventana y por corrida. Para la **regla de alerta**, una ventana con menos de 20 candidatas es *insuficiente*. La métrica se reporta igual, con su `n` y `estado_ventana`. |
| Cero observaciones | `null`. |
| **Adquisición (M2)** | Scores reales de YOLO11n en `eventos.jsonl → detecciones[].score`; la zona sale de [`zonas.py`](../../src/monitor/zonas.py). |
| **Trazabilidad (M4)** | `ventanas.jsonl → n_baja / n_candidatas` con sus `event_ids`; cada evento trae sus scores. |
| **Resultado (M5)** | Referencia: **0.3808** (653/1715). C1: **0.3859** (ventanas de 0.282 a 0.509). C2: **0.8298** (ventanas 0.797 / 0.837 / 0.947). `recalcular.py` recuenta las zonas desde los scores, sin usar las zonas guardadas. |

## G5 · Imágenes vinculadas (base)

| | |
|---|---|
| **Qué mide (M1)** | Fracción de capturas registradas que se pueden resolver: el archivo existe, su SHA-256 coincide, su evento existe y el `image_ref` del evento apunta a esa captura. |
| Unidad | fracción de capturas (0–1) |
| Fórmula | `capturas válidas / capturas registradas en capturas.jsonl`. También se reportan como problemas los eventos con `image_ref` que no tienen captura registrada. |
| Población | Todas las capturas de la corrida. |
| Ventana | La corrida (las capturas por alerta se deciden al cerrar la ventana, así que se mide al final). |
| Cero observaciones | `null`. |
| **Adquisición (M2)** | `capturas.jsonl` + archivos `capturas/*.jpg` + `eventos.jsonl`; verificador [`capturas.verificar`](../../src/monitor/capturas.py) (`python -m monitor verificar-capturas`). |
| **Resultado (M5)** | Referencia 9/9, C1 9/9, C2 23/23 → **1.0** en las tres. La prueba `test_imagen_rota_se_detecta` comprueba que una imagen alterada sí se detecta. |

## G6 · Versión esperada frente a reportada (base)

| | |
|---|---|
| **Qué mide (M1)** | Fracción de eventos cuyo `model_ref` y `config_ref` reportados coinciden con los esperados de la corrida (SHA-256 de los pesos y `config_ref` de la configuración cargada). |
| Unidad | fracción de eventos (0–1) |
| Fórmula | `eventos con model_ref = esperado y config_ref = esperado / eventos`. |
| Población | Todos los eventos (incluidos los de error). Hay una sola fuente por corrida (`source_id = youtube-<segmento>`). |
| Ventana | Por ventana y por corrida. |
| Cero observaciones | `null`. |
| **Adquisición (M2)** | El esperado sale de `run.json` (`model_ref_esperado`, que es el SHA-256 calculado al cargar los pesos, y `config_ref`); lo reportado sale de cada evento. |
| **Resultado (M5)** | **1.0** en la referencia, en C1 y en C2. |

## G7 · Alertas activas al cierre de la ventana (base)

| | |
|---|---|
| **Qué mide (M1)** | Número de alertas abiertas (de cualquier regla) cuando se termina de evaluar cada ventana. |
| Unidad | alertas |
| Fórmula | Por ventana: alertas en estado `abierta` después de evaluar la ventana. Por corrida: el máximo entre ventanas. |
| Población | Alertas de la corrida. Una alerta se cierra con la primera ventana *suficiente* que ya no cumple; una ventana insuficiente no la cierra. |
| Ventana | Cada ventana evaluada. |
| Cero observaciones | Sin ventanas → `null`. |
| **Adquisición (M2)** | `EvaluadorReglas` en [`reglas.py`](../../src/monitor/reglas.py) escribe `alertas_activas` en `ventanas.jsonl`. |
| **Resultado (M5)** | C1: **0** en las 9 ventanas. C2: **1, 1, 1** (la alerta se abre en la ventana 0 y sigue abierta). |

## Métricas descartadas como base y por qué

- **Throughput o inferencias recibidas (G1):** a 1 fps duplicarían a G2. El p95 dice más sobre la salud del servicio.
- **Distribución de confianza y frames sin detecciones (G4):** están en `referencia.json` y en los eventos, pero
  la base es la proporción baja porque es la que usan las reglas.
- **Cobertura de trazabilidad (G5):** se parece a imágenes vinculadas; se eligió esta porque R4.3 exige que las
  capturas resuelvan.
