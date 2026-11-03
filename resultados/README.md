# resultados/

Salidas por cuadro (entregable **E6**): detecciones, decisiones, comandos y errores enlazados por `run_id`
y `frame_id`, más las métricas TP/FP/FN, precisión, recall y F1 recalculables con su script
(P5-13, P5-14, T14, T17). Se suben a Git: las cifras resumidas no bastan.

## Resultados por cuadro y trazabilidad (`python -m trazabilidad`, P5-14)

Une una corrida de `python -m control` con las anotaciones de P5-10, cuadro por cuadro, por `run_id` y
`frame_id`:

```bash
# 1. La corrida: los eventos del detector pasan por B (T14).
uv run python -m control --entrada <detector.jsonl> --config config/control/ --salida resultados/<run>/
# 2. Unirla con las anotaciones. Los hashes son los congelados del detector.
uv run python -m trazabilidad construir --corrida resultados/<run>/ --anotaciones datos/anotaciones.jsonl \
    --salida resultados/<run>/trazabilidad/ --model-sha256 <HASH> --config-sha256 <HASH>
# 3. Volver a sacar las cifras solo desde lo unido.
uv run python -m trazabilidad recalcular resultados/<run>/trazabilidad/
# 4. Un cuadro de punta a punta: del frame_id al comando.
uv run python -m trazabilidad cuadro resultados/<run>/trazabilidad/ <frame_id>
```

**`por_cuadro.jsonl`**: una línea por cuadro. Están todos los cuadros con evento y también los anotados que
el detector nunca emitió: siguen en el denominador de las métricas.

| Campo | Contenido |
|---|---|
| `run_id`, `frame_id`, `sequence_id` | La clave del cuadro. |
| `evento` | El evento del contrato v1 tal como lo emitió el detector: estado, `error` si lo hubo, detecciones, `model_sha256` y `config_sha256`. `null` si no hubo evento. |
| `anotacion` | La verdad de referencia del cuadro (formato de `config/anotaciones/`), o `null` si no está anotado. |
| `conteo` | TP/FP/FN del cuadro a IoU 0.50 (P5-13), o `null` si no está anotado. |
| `decision` | Qué decidió B: estados antes y después, acción, razón y quién decidió (política o supervisor). |
| `comando` | La orden que registró el adaptador: acción, velocidad, giro, `t_command_ms` y `valid_until_ms`. |
| `errores` | Lo que registró el supervisor para ese cuadro, con su `motivo` (p. ej. `cuadro_viejo`, `error_detector:<code>`). |
| `orden_evento`, `orden_anotacion` | Posición en los archivos de entrada, para recalcular en el mismo orden. |

**`ordenes_sin_cuadro.jsonl`**: las órdenes de B que no vienen de un cuadro (reloj, emergencia, rearme,
cierre).

**`errores_sin_cuadro.jsonl`**: los errores de B que no son de ningún cuadro de la corrida, como
`orden_vencida` (`frame_id: null`). También entran en `conteos.errores`, que tiene todos los de
`errores.jsonl`, y se cuentan por motivo en `conteos.errores_sin_cuadro`.

**`resumen.json`**: las métricas de P5-13 (micro, por clase, criterio 1.4, procedencia, cobertura y mínimos
de E3), los conteos por secuencia (acciones, estados del detector y errores por motivo), la lista de errores
con su `frame_id`, los `model_sha256` y `config_sha256` vistos, la configuración de B con sus hashes
(`run.json`), el SHA-256 de cada entrada y de cada archivo escrito, y las advertencias. Nada se quita: un
cuadro sin decisión o sin comando es una advertencia.

**Recálculo:** `recalcular` lee solo los tres `.jsonl` de arriba y vuelve a producir las métricas, el
TP/FP/FN de cada cuadro, los conteos y los hashes. Sale con `0` si da exactamente lo mismo que
`resumen.json` y con `1` si algo difiere o un archivo cambió desde que se escribió.

**Fin de línea:** todo se escribe con LF, y cada SHA-256 (de lo escrito y de la corrida) se calcula sobre
el texto con LF. Así, un clon que saque los archivos con CRLF, o una corrida de `control` escrita en
Windows, da los mismos hashes.

**Una corrida de pocas secuencias:** `construir` une un `run_id` a la vez. Si la corrida no cubre todo el
conjunto, `--secuencia S04` (repetible) une solo las anotaciones de esas secuencias; sin eso, los cuadros
de las demás contarían como FN. Los eventos tienen que ser de las secuencias elegidas, y quedan anotadas
en `resumen.json`.

**Qué no se une** (sale con `2`): eventos que no cumplen el contrato v1, anotaciones inválidas o con un
`frame_id` repetido, y una `--salida` que no es una carpeta vacía.

**El `frame_id` tiene que ser el mismo** en el detector y en las anotaciones. Si ninguno coincide,
`construir` no une nada y sale con `2`. `infer` (P5-05, #75) usa el nombre del JPEG sin extensión, que es el
`frame_id` del conjunto (`S01_f0001`), así que hay que pasarle los cuadros con su nombre original.

Salida de `construir`: `0` sin advertencias · `1` con advertencias (cuadros sin evento, errores del detector,
mínimos de E3, procedencia sin comprobar...) · `2` si no se puede leer o unir; no se escribe nada.

### La corrida de entrega: S01–S08 en un solo run (`resultados/p5-14/`)

Las 8 secuencias de evaluación de `datos-evaluacion-v1`, de `infer` a la trazabilidad, con el `run_id`
`p5-14-s01-s08`. Se hizo con [`p5-14-corrida.py`](p5-14-corrida.py) en la laptop de A3 (i5-1135G7, 8 GB,
Windows 11), conectada a la corriente y con lo demás cerrado:

```bash
uv run --locked python resultados/p5-14-corrida.py --pesos modelo/descargas/yolo11n.pt
```

`infer` recibe una secuencia por llamada, así que el script la llama 8 veces con el mismo `run_id` y los
`t_capture_ms` de cada `captura.jsonl`, recorridos para que el reloj siga creciendo: cada secuencia empieza
250 ms después del último cuadro de la anterior. Antes comprueba el SHA-256 de cada JPEG contra su
`captura.jsonl`. Cada secuencia va en su carpeta (`infer/Sxx/`) porque `infer` escribe el manifiesto del run
(`<run_id>.infer-run.json`) junto al JSONL. `corrida.json` guarda el commit, la energía al empezar y al
terminar, el equipo, el desplazamiento de cada secuencia, el SHA-256 de cada JPEG y la salida de cada paso.

| | |
|---|---|
| Cuadros | 107, los 107 `status=ok`: ningún `stale`, `detector_timeout` ni otro error |
| Edad del cuadro al emitirse (`t_emit_ms − t_capture_ms`) | de 99 a 161 ms (p50 104) |
| Errores de B | 0; la única orden sin cuadro es el `STOP` de cierre |
| Métricas (IoU 0.50) | TP 71, FP 0, FN 24: precisión 1.0, recall 0.747, **F1 0.8554**; criterio 1.4: 5.0 |
| Por clase | botella (39) F1 0.829; taza (41) F1 0.881 |
| Hashes | `model_sha256` `0ebbc80d…` y `config_sha256` `6428a259…`, los congelados (`procedencia.comprobada: true`) |
| Salida de los pasos | `infer` ×8, `control`, `construir` y `recalcular`: `0` |

Conteos por caso: `resumen.json` los da por secuencia (`conteos.por_secuencia`, que `recalcular` vuelve a
sacar), y cada secuencia es un caso según [`datos/MAPA_CASOS.md`](../datos/MAPA_CASOS.md). C8 a C10 no usan
cuadros reales (son de las pruebas de B), así que no entran en esta corrida.

| Caso | Secuencia | Acciones de B |
|---|---|---|
| C1 · Vía libre | S01 | AVANZAR 12 |
| C2 · Obstáculo central | S02 | AVANZAR 5, GIRAR_IZQ 7 |
| C3 · Obstáculo izquierdo | S03 | AVANZAR 10, GIRAR_IZQ 2 |
| C4 · Obstáculo derecho | S04 | AVANZAR 12 |
| C5 · Sin zona libre | S05 | GIRAR_IZQ 1, STOP 11 |
| C7 · Libre → bloqueo → libre | S06 | AVANZAR 11, GIRAR_IZQ 3, STOP 6 |
| C6 · Confianza | S07 | AVANZAR 2, GIRAR_IZQ 13 |
| C1 · Vía libre, transitables | S08 | AVANZAR 10, GIRAR_IZQ 2 |

**Estas acciones no son el veredicto de cada caso.** En un solo run, B no se reinicia entre secuencias: sigue
con el estado en que terminó la anterior y necesita 3 cuadros libres seguidos para reanudar. Por eso:
- `S03_f0001` y `f0002` siguen girando a la izquierda como al final de S02;
- `S05_f0001` gira a la izquierda antes de frenar;
- `S06_f0001` a `f0006` siguen en STOP desde S05;
- `S08_f0001` y `f0002` siguen girando como al final de S07.

El veredicto de cada caso lo da el runner de casos, que corre cada uno por separado (`casos/`, T17; con
entradas reales, [`docs/casos-reales.md`](../docs/casos-reales.md), T20). Esta corrida sirve para las métricas
de P5-13 y para seguir cada cuadro hasta su comando.

Para comprobarlo:

```bash
uv run --locked python -m trazabilidad recalcular resultados/p5-14/trazabilidad/   # sale 0: mismas cifras
uv run --locked python -m trazabilidad cuadro resultados/p5-14/trazabilidad/ S02_f0008
```

`S02_f0008` llega en un paso a su detección (taza, confianza 0.82), su anotación (TP 1), la decisión de la
política y el comando `GIRAR_IZQ` (velocidad 0.4, giro −0.5).

**En batería no sale así.** Una prueba antes de esta, en batería al 68 %, dio 74 `stale` y 4
`detector_timeout` de 107 (F1 0.21): el primer cuadro de varias secuencias pasó los 500 ms con el detector
en frío, y reiniciarlo tras el timeout deja viejos los cuadros siguientes. Esa prueba no se guardó. Ver
[`mediciones/LIMITES.md`](../mediciones/LIMITES.md), *En una máquina lenta o cargada*.
