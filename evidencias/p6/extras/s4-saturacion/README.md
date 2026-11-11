# S4 · Saturación del procesamiento y recuperación (escenario adicional)

> Issue #37 · extra **S4**, nivel solicitado **8** (secuencia temporal con transición, persistencia y
> recuperación, con registros vinculados). Corrida `s4-saturacion-20261111T184104Z` · commit
> `5f004fbdc5318ec2ca3d296df633f7c7ae580a1b` (sin cambios pendientes) · `config_ref c574ee88…ff6c` · `vigilancia_ref 26e10cb2…`.

| | |
|---|---|
| **Entrada** | Los mismos 60 frames de día que S2 y S3 (respaldo `s2-interrupcion`), en tiempo real (1 frame por segundo). |
| **Falla inyectada** | `--lentitud 20:40 --lentitud-ms 2000`: para los frames de 20 a 40 s, el detector tarda 2 s más antes de inferir. Simula contención de CPU ([`src/monitor/fallas.py`](../../../../src/monitor/fallas.py)). El modelo infiere igual; solo tarda más. Llegan frames cada 1 s y cada uno tarda ~2.1 s, así que la cola crece. Cuando un frame espera más de `muestreo.atraso_max_ms` (3000 ms, regla base de [`monitoreo.yaml`](../../../../config/p6/monitoreo.yaml)), se descarta por saturación, como en un stream que no espera. |
| **Comando** | `uv run python -m monitor correr --segmento s4-saturacion --lentitud 20:40 --lentitud-ms 2000 --salida evidencias/p6/extras/s4-saturacion` |
| **Regla** | `saturacion-v1` ([`vigilancia.yaml`](../../../../config/p6/vigilancia.yaml)), advertencia: fracción de frames llegados que se descartaron por saturación ≥ **0.2** en una ventana con ≥ 5 frames llegados. |
| **Esperado** | Ventanas 0–1 sin descartes. Ventanas 2–3: la cola crece, aparecen descartes y se abre la alerta con el diagnóstico de cola e inferencia. Al terminar la lentitud (40 s), la cola acumulada se vacía en unos segundos. La ventana 4 ya no descarta y la alerta se cierra. Las ventanas de confianza siguen siendo suficientes con los frames que sí se infirieron. |

## Observado

| Ventana | Llegaron | Procesados | Descartados | `saturacion-v1` | X4 p95 (ms) | Alertas activas |
|---|---|---|---|---|---|---|
| 0 [0, 10) | 10 | 10 | 0 | no cumple | 408.79 | 0 |
| 1 [10, 20) | 10 | 10 | 0 | no cumple | 246.70 | 0 |
| 2 [20, 30) | 10 | 6 | **4** | **cumple (0.4) → abre** | **5868.69** | 1 |
| 3 [30, 40) | 10 | 4 | **6** | cumple (0.6), abierta y sin repetirse | **4674.79** | 1 |
| 4 [40, 50) | 10 | 10 | 0 | **no cumple → cierra** | 2826.54 (la cola se vacía) | 0 |
| 5 [50, 60) | 10 | 10 | 0 | no cumple | 186.76 | 0 |

**Alerta** ([`alertas.jsonl`](alertas.jsonl)): `s4-saturacion-20261111T184104Z-saturacion-v1-v002`.

- **Datos:** advertencia; abierta el 18:41:38.603 UTC y cerrada el 18:41:54.691 UTC por la ventana 4.
- **Motivo:** «4/10 frames descartados por saturación … en la ventana 2 [260 s, 270 s): tasa 0.400, umbral 0.2».
- **Ventanas:** 2 (4/10) y 3 (6/10).
- **Diagnóstico:**
  - `cola_max_ms 2972.075`;
  - `cola_mediana_ms 2677.843`;
  - `inferencia_mediana_ms 2094.242`: la inferencia es la causa, porque tarda más que el intervalo
    entre frames;
  - `frames_procesados_en_ventana 6`.
- **Eventos vinculados:** los 6 frames que sí se infirieron en la ventana 2, con su inferencia y su
  cola.

Captura: [`../portal/23-alerta-saturacion-s4.png`](../portal/23-alerta-saturacion-s4.png).

Los descartes quedan en [`observaciones.jsonl`](observaciones.jsonl) (`tipo: descarte`,
`motivo: saturacion`, con su `cola_ms`) y en `run.json → conteos.descartes_saturacion` = 10.

**Resultado: coincide con lo esperado.** La transición se ve en la cola y en X4. La persistencia
abarca dos ventanas con una sola alerta. La recuperación queda verificada en la ventana 4: 0
descartes aunque la cola todavía se vacía (X4 2.8 s), y en la ventana 5 la latencia ya es normal
(187 ms).

## Métricas

- **Base** ([`metricas.json`](metricas.json)): G1 **2117.37 ms** (la inferencia lenta domina el p95) ·
  G2 0.846 fps · G3 386.0 MiB · G4 0.2805 · G5 1.0 · G6 1.0 · G7 1.
- **X7, tasa de descarte por saturación** ([`metricas_extra.json`](metricas_extra.json)):
  - por ventana: **0, 0, 0.4, 0.6, 0, 0**;
  - en la corrida: 0.1667 (10/60).
- **X5** (disponibilidad de la fuente) se queda en **1.0**: la fuente entregó todo y el cuello de
  botella está en el procesamiento. Así se distingue de S2.
- Gráficas: [`../portal/25-dashboard-s4-x7.png`](../portal/25-dashboard-s4-x7.png) y
  [`../portal/26-dashboard-s4-x4.png`](../portal/26-dashboard-s4-x4.png).

## Verificación

- `python evidencias/p6/recalcular_extras.py evidencias/p6/extras/s4-saturacion` → todo coincide
  ([`../../recalculo/x-s4-saturacion.txt`](../../recalculo/x-s4-saturacion.txt)). Recalcula la tasa
  de descarte de cada ventana desde `observaciones.jsonl`, «abre en 2 (tasa 0.4) y cierra en 4», y
  X1–X7.
- `python evidencias/p6/recalcular.py evidencias/p6/extras/s4-saturacion` → todo coincide.
- `verificar-capturas` → 5/5.
- `tests/test_p6_extras.py` prueba la regla, incluido el caso de una ventana con todos los frames
  descartados, y corre la cadena completa con un reloj falso.

**Límite:** la lentitud es una demora inyectada antes de la inferencia real, no carga real de la
CPU. Se eligió así para que sea reproducible: con otra máquina cambia el tiempo de inferencia base
(~140 ms aquí), pero 2 s de demora siguen saturando un stream de 1 fps.
