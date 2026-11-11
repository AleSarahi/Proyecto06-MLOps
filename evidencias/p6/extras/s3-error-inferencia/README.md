# S3 · Error de inferencia y recuperación (escenario adicional)

> Issue #37 · extra **S3**, nivel solicitado **10** (secuencia compuesta: fallo, diagnóstico y
> reacción, recuperación y verificación posterior). Corrida `s3-error-inferencia-20261111T183922Z` ·
> commit `5f004fbdc5318ec2ca3d296df633f7c7ae580a1b` (sin cambios pendientes; ver `run.json → git`) · `config_ref c574ee88…ff6c` ·
> `vigilancia_ref 26e10cb2…` (en `run.json → vigilancia`).

| | |
|---|---|
| **Entrada** | Los mismos 60 frames de día que S2 (240–300 s del video `dia`, respaldo [`datos/p6/frames/s2-interrupcion/`](../../../../datos/p6/frames/s2-interrupcion/), declarado con `respaldo:` en `fuentes.yaml`). Por eso los `frame_id` empiezan con `s2-interrupcion-`. La entrada es idéntica y lo único que cambia es la condición probada. |
| **Fallo inyectado** | `--error-inferencia 20:35`: para los frames de 20 a 35 s del segmento, la llamada al modelo lanza `RuntimeError: fallo inyectado: el runtime del modelo no respondió` ([`src/monitor/fallas.py`](../../../../src/monitor/fallas.py)). `Inferidor` la convierte en un evento `status: error`, `code: detector_exception`. No se inventa ninguna detección. Fuera del intervalo el detector es el real. La inyección queda en `run.json → modelo.inyeccion`. |
| **Comando** | `uv run python -m monitor correr --segmento s3-error-inferencia --error-inferencia 20:35 --salida evidencias/p6/extras/s3-error-inferencia` (tiempo real) |
| **Regla** | [`config/p6/vigilancia.yaml`](../../../../config/p6/vigilancia.yaml) → `errores-inferencia-v1`, crítica: fracción de frames procesados con `error` ≥ **0.5** en una ventana con ≥ 5 frames. Se cierra en la primera ventana suficiente por debajo del umbral. |
| **Esperado** | Ventanas 0–1 sin errores. Ventana 2 [20, 30) s: 10/10 errores → se abre la alerta con diagnóstico. Ventana 3 [30, 40) s: 5/10 (los frames 30–34 fallan y 35–39 ya no) → 0.5 cumple todavía, la alerta sigue abierta y no se repite. Ventana 4: 0 errores → se cierra. Ventana 5: normal. Por su parte, la confianza no debe tomar los errores como «normal»: la ventana 2 queda *insuficiente* (0 candidatas). |

## Observado

| Ventana | Frames | Errores | `errores-inferencia-v1` | Ventana de confianza | Alertas activas |
|---|---|---|---|---|---|
| 0 [0, 10) | 10 | 0 | no cumple | suficiente, 0.234 | 0 |
| 1 [10, 20) | 10 | 0 | no cumple | suficiente, 0.308 | 0 |
| 2 [20, 30) | 10 | **10** | **cumple → abre** | **insuficiente** (0 candidatas) | 1 |
| 3 [30, 40) | 10 | **5** | cumple (abierta, sin repetirse) | suficiente, 0.267 (75 candidatas de los 5 frames sanos) | 1 |
| 4 [40, 50) | 10 | 0 | **no cumple → cierra** | suficiente, 0.264 | 0 |
| 5 [50, 60) | 10 | 0 | no cumple | suficiente, 0.297 | 0 |

(Resultados por regla técnica: registros `ventana_tecnica` de [`observaciones.jsonl`](observaciones.jsonl).)

**Alerta** ([`alertas.jsonl`](alertas.jsonl)): `s3-error-inferencia-20261111T183922Z-errores-inferencia-v1-v002`.

- **Datos:** crítica; abierta el 18:39:53.759 UTC y cerrada el 18:40:13.759 UTC por la ventana 4.
- **Motivo:** «10/10 frames con error de inferencia en la ventana 2 [260 s, 270 s): tasa 1.000, umbral 0.5». Los segundos son del video.
- **Ventanas:** 2 (10/10) y 3 (5/10).
- **Diagnóstico:**
  - `codigos: {detector_exception: 10}`;
  - 3 ejemplos con `event_id`, código y mensaje;
  - `frames_ok_en_ventana: 0`.
- **Eventos vinculados:** los 10 eventos `error` de la ventana 2.

Captura: [`../portal/22-alerta-errores-s3.png`](../portal/22-alerta-errores-s3.png). Lista de los 15 eventos con error: [`../portal/27-eventos-s3-error.png`](../portal/27-eventos-s3-error.png).

**Resultado: coincide con lo esperado.** El fallo se diagnostica con su código y su mensaje. La alerta no se repite y se cierra en cuanto el modelo vuelve a responder. Después de la recuperación, las ventanas 4–5 tienen inferencias normales (proporción baja 0.264 y 0.297, igual que en S2 con los mismos frames).

## Métricas

- **Base** ([`metricas.json`](metricas.json)): G1 288.52 ms · G2 1.015 fps · G3 384.84 MiB · G4 0.2748 ·
  G5 1.0 (6/6) · G6 1.0 · G7 1.
- **X6, tasa de errores de inferencia** ([`metricas_extra.json`](metricas_extra.json)):
  - por ventana: **0, 0, 1.0, 0.5, 0, 0**;
  - en la corrida: 0.25 (15/60).
- **X1** excluye los frames con error. En la ventana 2 vale `null` (sin frames inferidos), no 0.
- Gráfica: [`../portal/24-dashboard-s3-x6.png`](../portal/24-dashboard-s3-x6.png).

## Verificación

- `python evidencias/p6/recalcular_extras.py evidencias/p6/extras/s3-error-inferencia` → todo coincide
  ([`../../recalculo/x-s3-error-inferencia.txt`](../../recalculo/x-s3-error-inferencia.txt)). Recalcula
  la tasa de errores de cada ventana desde `eventos.jsonl`, «abre en 2 (tasa 1.0) y cierra en 4», y
  X1–X7.
- `python evidencias/p6/recalcular.py evidencias/p6/extras/s3-error-inferencia` → todo coincide
  ([`../../recalculo/extras-s3-error-inferencia.txt`](../../recalculo/extras-s3-error-inferencia.txt)).
- Captura: `verificar-capturas` → 6/6.
- `tests/test_p6_extras.py` prueba la regla: apertura, permanencia, ventana insuficiente que no abre
  ni cierra, y cierre.

**Límite:** el fallo es una excepción inyectada en la llamada al modelo, no un fallo real del
runtime. Se eligió así para que sea reproducible. La ruta que recorre es la real: excepción →
`Inferidor` → evento `error` → regla → alerta.
