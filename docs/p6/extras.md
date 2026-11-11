# Proyecto 6 · Extras (puntos adicionales)

> Issues #29–#33. Ninguna de estas funciones cambia la base: `config/p6/monitoreo.yaml` y su
> `config_ref c574ee88…ff6c` son los mismos, así que la referencia, C1 y C2 siguen siendo válidos y
> comparables con los escenarios adicionales. El código de los extras está en el commit
> `ac12754fb1f0382865da6c0cf5cc92203c69c97e`, el mismo con el que se ejecutaron S1 y S2
> (`run.json → git`, sin cambios pendientes).

## Inventario de extras reclamados

| ID | Tipo | Descripción | Nivel solicitado | Evidencia principal |
|---|---|---|---|---|
| **F1** | Funcionalidad | Stream en vivo con resultados: último frame con cajas por zona, estado de la corrida y de la fuente, alertas abiertas; se actualiza cada segundo mientras la corrida escribe | **15** | [`evidencias/p6/extras/portal/vivo-*.png/.json`](../../evidencias/p6/extras/portal/) (5 estados de S2) y [`portal/s1/`](../../evidencias/p6/extras/portal/s1/); `tests/test_p6_extras.py` |
| **F2** | Funcionalidad | Dashboard de gráficas históricas por ventana: una o varias corridas, cualquier métrica G1–G7 o X1–X5, rango de ventanas, alertas sombreadas y línea de referencia | **10** | [`portal/10…14-dashboard-*.png`](../../evidencias/p6/extras/portal/); pruebas de estados vacío y de error |
| **F3** | Funcionalidad | Exportación de eventos a CSV/JSONL con los filtros de la consulta (corrida, zona, estado) validados: un filtro desconocido da 400, no «todos» | **10** | [`evidencias/p6/extras/exportacion/`](../../evidencias/p6/extras/exportacion/), [`portal/19-…`](../../evidencias/p6/extras/portal/19-eventos-s2-exportar.png) y [`20-…`](../../evidencias/p6/extras/portal/20-eventos-filtro-invalido.png) |
| **M1** (X1) | Métrica | Candidatas por frame | **3** | `metricas_extra.json` de las 5 corridas; [`recalculo/x-*.txt`](../../evidencias/p6/recalculo/) |
| **M2** (X2) | Métrica | Proporción de frames sin detecciones por ventana | **5** | ídem |
| **M3** (X3) | Métrica | PSI de la distribución de scores frente a la referencia, por ventana | **8** | ídem + caso controlado de cambio: S1 (día → noche → día) |
| **M4** (X4) | Métrica | Latencia extremo a extremo p95 (llegada → evento registrado) con descomposición cola / inferencia / registro | **5** | ídem |
| **M5** (X5) | Métrica | Disponibilidad de la fuente: frames que llegaron / frames que el muestreo esperaba, por ventana | **5** | ídem + S2 (0.0 durante el corte) |
| **S1** | Escenario | Cambio sostenido de confianza: transición, persistencia de la regla de 3 ventanas y recuperación | **8** | [`evidencias/p6/extras/s1-transicion/`](../../evidencias/p6/extras/s1-transicion/README.md) |
| **S2** | Escenario | Interrupción de la fuente: fallo, diagnóstico (alerta técnica), recuperación y verificación posterior | **10** | [`evidencias/p6/extras/s2-interrupcion/`](../../evidencias/p6/extras/s2-interrupcion/README.md) |

Total solicitado: 35 (F) + 26 (M) + 18 (S) = **79 puntos**, sujeto a lo que el evaluador acredite.

## Control de doble conteo

- **Base que no se reclama:** las vistas mínimas de eventos y alertas, los filtros que ya tenía el
  portal base, los dos umbrales, las capturas obligatorias, C1, C2 y la regla sostenida
  configurada (R3.3). F3 reclama la exportación y la validación de filtros, no los filtros en sí.
- **F2 frente a M1–M5:** el dashboard es la vista; las métricas se calculan aparte
  (`src/monitor/metricas_extra.py`), se guardan en `metricas_extra.json` y tienen su propio
  recálculo. El dashboard también grafica las métricas base, así que no depende de los extras.
- **F1 frente a S2:** F1 es la vista (funciona con cualquier corrida: S1, C1…). S2 es la condición
  probada (la fuente se cae) y tiene su propio criterio de aceptación; F1 solo aporta parte de su
  evidencia.
- **M5 frente a S2:** M5 es una métrica que existe en todas las corridas (vale 1.0 sin cortes); S2
  la usa como una de sus verificaciones.
- **M3 frente a G4 y la regla sostenida:** G4 cuenta la proporción bajo el umbral inferior; M3
  compara la distribución completa de scores (10 bins) con la de la referencia. Son cálculos
  distintos: en S1 la ventana 7 tiene G4 = 0.234 (normal) pero PSI = 0.53 (distribución distinta).
- **M4 frente a G1:** G1 es el p95 de la etapa de inferencia; M4 correlaciona tres etapas por
  frame (cola + inferencia + registro = extremo a extremo, comprobado frame por frame en el
  recálculo). No es otro percentil del mismo histograma.
- **S1 frente a C2:** C2 prueba una ventana de baja confianza aislada (regla de 1 ventana). S1
  prueba la persistencia: la regla de 3 ventanas solo se abre en la tercera, ninguna alerta se
  repite y las dos se cierran al volver el día.

## Funcionalidades

### F1 · Stream en vivo (`/vivo`)

- **Flujo.** Mientras corre, `Corrida` escribe en la tabla `vivo` de SQLite el último frame
  procesado (JPEG), su evento resumido (cajas, scores, zonas), la ventana, las alertas abiertas, el
  estado de la corrida (`en_curso`, `terminada`, `fallida`) y el de la fuente (`con_senal`,
  `sin_senal`, `recuperando`, de la vigilancia de S2). La base está en modo WAL para que el portal
  lea mientras la corrida escribe.
- **Coordinación de estados.** `/api/vivo` combina esos estados con la antigüedad de la última
  actualización: `en_vivo`, `sin_senal` (imagen congelada y alerta enlazada), `recuperando`,
  `sin_actualizaciones` (más de 5 s sin escribir: el proceso pudo morir), `terminada` y `fallida`.
  La página (`/vivo`) consulta cada segundo y dibuja las cajas con el color de su zona.
- **Trazabilidad.** El frame enlaza a su evento (`/eventos/<id>`), las alertas abiertas a su
  detalle y la corrida a su página.
- **Caso normal y casos borde, reproducibles.** Capturas tomadas durante la corrida real de S2
  (`evidencias/p6/extras/portal/vivo-1…5`, cada una con el JSON de `/api/vivo` de ese instante):
  en vivo → sin señal → recuperando → recuperada → terminada. Con S1, en vivo con dos alertas
  abiertas (`portal/s1/`). Sin corridas: estado vacío (`21-vivo-sin-corridas.png`). Corrida
  desconocida: 404. Proceso detenido: `sin_actualizaciones` (prueba
  `test_estados_de_la_vista_en_vivo`).
- **Reproducir:** `uv run python -m monitor portal` en una terminal y en otra
  `uv run python -m monitor correr --segmento s2-interrupcion --corte 20:40 --salida tmp/s2`; abrir
  <http://127.0.0.1:8000/vivo>.

### F2 · Dashboard (`/dashboard`)

- **Consulta parametrizada:** `run` (1 a 4 corridas), `metrica` (G1–G7, X1–X5), `desde` y `hasta`
  (índices de ventana). Lee `metricas.json` / `metricas_extra.json` de la carpeta de cada corrida
  registrada en la base y sus alertas de la tabla `alertas`.
- **Gráfica SVG** generada en el servidor: una línea por corrida, un valor nulo corta la línea y se
  marca con un punto hueco (sin dato ≠ 0), franjas en las ventanas con alerta (si hay una sola
  corrida), línea de referencia para G4 (0.381) y una línea orientativa de PSI 0.25 para X3. Debajo,
  la tabla con valor y `n` por ventana.
- **Estados vacíos y de error:** sin corridas, sin selección, rango sin datos (14), métrica
  desconocida, rango invertido o no numérico (400, captura 13), corrida inexistente (404),
  corrida sin archivo de métricas (aviso con el comando para generarlo).

### F3 · Exportación con filtros validados

- `/exportar/eventos.csv` y `/exportar/eventos.jsonl` aceptan `run`, `zona` y `status`, los mismos
  de `/eventos` (que ahora enlaza la exportación con sus filtros). La respuesta lleva
  `X-Total-Eventos` y un nombre de archivo con los filtros.
- Sin resultados: CSV solo con la cabecera (`exportacion/eventos_c1_baja_vacio.csv`). Filtro
  desconocido: 400 con el motivo (`exportacion/filtro_invalido_400.txt`; también `/eventos?zona=xx`).
  Corrida inexistente: 404.
- Verificación: `eventos_s1_baja.csv` tiene 6 filas, igual que los 6 frames en zona baja de S1
  (`run.json → conteos.eventos_por_zona.baja`).

## Métricas adicionales (X1–X5)

Se calculan con `uv run python -m monitor metricas-extra <carpetas>` (también al final de cada
corrida) y se recalculan con `python evidencias/p6/recalcular_extras.py <carpetas>`, que solo usa la
biblioteca estándar. Cada una existe por ventana y por corrida. Con cero observaciones el valor es
`null` y `n = 0`.

| ID | Definición | Población y exclusiones | Fórmula |
|---|---|---|---|
| X1 | Candidatas por frame | Frames procesados con estado `ok` o `sin_detecciones`; se excluyen los de `error` (no hubo inferencia) | Σ candidatas / frames |
| X2 | Frames sin detecciones | Misma población que X1 | frames `sin_detecciones` / frames |
| X3 | PSI de scores vs. referencia | Candidatas de la ventana; la ventana debe tener ≥ 20 (si no, `insuficiente`). Referencia: las 1715 candidatas de la corrida de referencia, con el mismo `config_ref` (si no, `sin_referencia`) | 10 bins de 0.1 en [0, 1]; PSI = Σ (p − q) · ln(p / q), con p y q las fracciones por bin y 1e-4 en lugar de 0 |
| X4 | Latencia extremo a extremo p95 | Frames con evento registrado (reloj monotónico de la corrida) | p95 por rango cercano de `t_fin_registro − t_llegada`; además la mediana de cola, inferencia y registro (= e2e − cola − inferencia) |
| X5 | Disponibilidad de la fuente | Frames que llegaron (con evento o descartados por saturación); los perdidos en un corte no llegaron | llegados / esperados, con esperados = traslape de la ventana con el segmento × (fps del video / 30) |

Resultados por corrida (`metricas_extra.json`):

| Corrida | X1 | X2 | X3 (corrida) | X4 p95 ms | X5 |
|---|---|---|---|---|---|
| Referencia | 19.06 | 0.0 | 0.0 | 1101.05* | 1.0 |
| C1 normal | 22.78 | 0.0 | 0.012 | 624.51 | 1.0 |
| C2 baja confianza | 5.88 | 0.0 | 2.021 | 608.51 | 1.0 |
| S1 transición | 14.58 | 0.0 | 0.066 | 362.39 | 1.0 |
| S2 interrupción | 12.5 | 0.0 | 0.104 | 476.57 | 0.667 |

\* La referencia se corrió sin esperas (`--velocidad 0`): los frames llegan todos al inicio y se
acumulan en cola. Esa X4 mide la cola de una carga en lote, no la de un stream.

Límites y supuestos:

- **X2 es 0 en las cinco corridas reales:** en estos videos de tráfico siempre hay alguna
  candidata con score ≥ 0.10. El cálculo y el caso con frames sin detecciones están probados en
  `tests/test_p6_integracion.py` y `tests/test_p6_extras.py`.
- **X3 es descriptiva:** un PSI alto dice que la distribución de scores cambió respecto a la
  referencia, no que el modelo se equivoque. El 0.25 de la gráfica es una convención habitual de
  PSI, no un umbral de alerta del proyecto. Caso controlado: en S1, las ventanas de día dan
  0.12–0.29, las de noche 0.61–2.53 y al volver el día 0.53 → 0.08–0.13. Las ventanas 3 y 4 de S1
  y las 0 y 1 de C2 son los mismos frames y dan el mismo PSI (1.8873 y 2.5315): el cálculo es
  determinista.
- **X4** usa el reloj de la corrida, así que no incluye el tiempo de descarga del video.
- **X5** supone que la fuente entrega a la tasa del muestreo (1 frame por segundo de video). Con
  `--velocidad 0` se sigue contando por tiempo de video, no por tiempo real.

## Escenarios adicionales

- **S1 · Cambio sostenido de confianza** (#32). La secuencia `s1-transicion` concatena 30 s de día,
  20 s del video nocturno de C2, 20 s de un segundo video nocturno y 30 s de día. Ficha y
  resultados: [`evidencias/p6/extras/s1-transicion/README.md`](../../evidencias/p6/extras/s1-transicion/README.md).
- **S2 · Interrupción de la fuente** (#33). El segmento `s2-interrupcion` (60 s de día) se corre con
  `--corte 20:40`: la fuente pierde los frames de 20 a 40 s. Ficha:
  [`evidencias/p6/extras/s2-interrupcion/README.md`](../../evidencias/p6/extras/s2-interrupcion/README.md).

### Fuentes que agregan los extras

Se agregó un video en [`config/p6/fuentes.yaml`](../../config/p6/fuentes.yaml):

- **noche2:** «Time Lapse of Night Traffic at a Busy Intersection», canal *non copyright videos*,
  <https://www.youtube.com/watch?v=4a9ANcON_eU>, licencia Creative Commons Attribution (reuse
  allowed). Formato 136 (MP4 H.264 1280×720, 30 fps, solo video), 5 619 707 B,
  SHA-256 `929f20ec50e2f9e359b9125217b27ae18dbc82343ec49440c37f26bbb69e31ab`. Dos descargas
  independientes dieron los mismos bytes. Es un *time lapse*: el tráfico se ve más rápido que en
  tiempo real, lo cual no afecta la confianza por frame que se monitorea.

Hacía falta porque el video nocturno de C2 dura 23 s: a 1 frame por segundo da solo 2 ventanas
suficientes y la regla sostenida pide 3 seguidas.

Una **secuencia** (`tramos` en `fuentes.yaml`) se reproduce como un solo stream: el tiempo del
segmento corre de 0 a la suma de las duraciones y cada frame del manifiesto guarda su video, su
tramo y `pos_video_ms` (la posición original). Los respaldos están en
`datos/p6/frames/s1-transicion/` y `datos/p6/frames/s2-interrupcion/`, con SHA-256 por frame.

### Vigilancia de la fuente

[`config/p6/vigilancia.yaml`](../../config/p6/vigilancia.yaml) define `fuente-sin-senal-v1`:
alerta crítica si pasan más de 5 s (reloj de la corrida) sin recibir frames, cerrada cuando llegan 3
frames seguidos. Va aparte de `monitoreo.yaml` para no cambiar `config_ref`; su identidad es
`vigilancia_ref` (SHA-256 del contenido efectivo), registrada en `run.json` y en cada alerta. El
contrato de la alerta es
[`alerta_fuente.v1`](../../config/p6/contratos/alerta_fuente.v1.schema.json). La alerta cuenta en
`alertas_activas` (G7). En C1 y C2 (base) no existía la vigilancia, pero tampoco hubo cortes: el
resultado de esas corridas sería el mismo.
