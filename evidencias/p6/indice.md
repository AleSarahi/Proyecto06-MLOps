# Proyecto 6 · Índice de evidencias

> Issue #27 (R7.2). Entrega individual de Alejandra Rayas · repositorio <https://github.com/AleSarahi/Proyecto06-MLOps>.

## Revisiones Git

| Qué | Commit | Relación |
|---|---|---|
| Código con el que se ejecutaron la referencia, C1 y C2 | `d5ab5971fd8b960018bd8d2c0f04bb5077a92132` | Cada `run.json` lo registra en `git.commit`, con `cambios_sin_commit: false`. |
| Evidencias de las corridas (JSONL, capturas, métricas, recálculo, portal) | `20bfa9b` | Se agregó **después** del código probado y no lo modifica: solo agrega `evidencias/p6/`. |
| Documentación (docs/p6, README, este índice) y ensayo desde una copia limpia | commits posteriores con prefijo `P6-` | No cambian `config/p6/` ni la lógica de inferencia, ventanas o reglas; el `config_ref` sigue siendo `c574ee88…ff6c`. El único cambio de código es cosmético (`noprogress` en la descarga, ver [`ensayo-copia-limpia.md`](ensayo-copia-limpia.md)). En la copia limpia, la corrida de C1 y C2 dio **los mismos scores** que la evidencia. |

| Código de los extras (#29–#33), con el que se ejecutaron S1 y S2 | `ac12754fb1f0382865da6c0cf5cc92203c69c97e` | No cambia `config/p6/monitoreo.yaml` ni `config_ref`. Agrega `metricas_extra.json` a las corridas base sin tocar sus demás archivos. |
| Código de S3, S4, X6 y X7 (#37), con el que se ejecutaron S3 y S4 | `5f004fbdc5318ec2ca3d296df633f7c7ae580a1b` | Igual: `config_ref` sin cambios. Se regeneró `metricas_extra.json` de las corridas anteriores para agregar X6 y X7 (los valores X1–X5 no cambian). |

Para ubicar la revisión evaluada: `git log --oneline -- evidencias/p6 src/monitor config/p6`.

## Identidades de la serie

`config_ref c574ee88333cbf676b469df9ddbb6f1cf2c1cf0df1d2c3499631fadbfecaff6c` ·
`model_ref 0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` · detector `config/p6/detector.json` ·
videos `adcda3e9…e166f9` (día) y `eb96b39d…b478d7` (noche).

| Corrida | run_id | Carpeta |
|---|---|---|
| Referencia | `referencia-20261109T042407Z` | [`referencia/corrida/`](referencia/corrida/), resumen [`referencia/referencia.json`](referencia/referencia.json) |
| C1 · normal | `c1-20261109T042610Z` | [`escenarios/c1-normal/`](escenarios/c1-normal/) ([ficha](escenarios/c1-normal/README.md)) |
| C2 · baja confianza | `c2-20261109T042757Z` | [`escenarios/c2-baja-confianza/`](escenarios/c2-baja-confianza/) ([ficha](escenarios/c2-baja-confianza/README.md)) |

## Criterios

| ID | Evidencia | IDs / valores para comprobar |
|---|---|---|
| R1.1 | [`docs/p6/fuente.md`](../../docs/p6/fuente.md), [`src/monitor/fuente.py`](../../src/monitor/fuente.py), `run.json → conteos.fuente`, `observaciones.jsonl` (`t_llegada_ms`) | 1 de cada 30 frames (1 fps), tiempo real; C1: 90 recibidos y 2610 descartados por muestreo; G2 ≈ 1.0 fps |
| R1.2 | `eventos.jsonl` (scores por candidata, `model_ref`), [`src/monitor/inferencia.py`](../../src/monitor/inferencia.py), `tests/test_p6_modelo.py` | `model_ref` = SHA-256 de los pesos cargados en los 204 eventos |
| R1.3 | [`docs/p6/modelo.md`](../../docs/p6/modelo.md), [`config/p6/detector.json`](../../config/p6/detector.json), `run.json → modelo, entorno` | YOLO11n, clases 0/1/2/3/5/7, letterbox 640, piso 0.10, NMS 0.7, CPU |
| R2 | [`docs/p6/metricas.md`](../../docs/p6/metricas.md) (G1–G7, M1–M5), `metricas.json` de cada corrida, [`recalcular.py`](recalcular.py), [`recalculo/`](recalculo/) | 7 grupos aplicables, 7 métricas base; recálculo: «todo coincide» en 3 corridas |
| R3.1 | [`docs/p6/umbrales.md`](../../docs/p6/umbrales.md), [`referencia/referencia.json`](referencia/referencia.json) | 0.30 / 0.60 justificados con cuantiles de la referencia (p5 del máximo por frame 0.707) |
| R3.2 | `eventos.jsonl` (`detecciones[].zona`, `zona_frame`, `conteo_zonas`, `status`), [`src/monitor/zonas.py`](../../src/monitor/zonas.py), [`config/p6/contratos/evento.v1.schema.json`](../../config/p6/contratos/evento.v1.schema.json) | C2: 9 frames baja, 13 duda, 2 aceptadas; estados `sin_detecciones` y `error` separados y probados |
| R3.3 | `referencia.json` (proporción 0.3808, config_ref), `ventanas.jsonl` (`estado`), regla `cambio-sostenido-v1` en [`config/p6/monitoreo.yaml`](../../config/p6/monitoreo.yaml) | C2 ventana 2: `insuficiente` (19 < 20) sin cerrar la alerta |
| R4.1 | `eventos.jsonl`, [`docs/p6/contratos.md`](../../docs/p6/contratos.md) | p. ej. `c2-20261109T042757Z-c2-f000210` |
| R4.2 | Base SQLite (`python -m monitor importar …`), portal [`portal/01-eventos-c1.png`](portal/01-eventos-c1.png), [`portal/05-evento-c2-baja.png`](portal/05-evento-c2-baja.png), [`portal/06-eventos-c2-baja.png`](portal/06-eventos-c2-baja.png) (+ `.html`) | `/eventos/c2-20261109T042757Z-c2-f000210` enlaza la imagen, la ventana, la alerta, la corrida y la configuración |
| R4.3 | `capturas.jsonl` + `capturas/*.jpg` de cada corrida; política en [`contratos.md`](../../docs/p6/contratos.md#captura-capturav1-y-política-de-conservación-r43) | `verificar-capturas`: 9/9, 9/9 y 23/23; sin expiración |
| R5.1 | [`docs/p6/umbrales.md`](../../docs/p6/umbrales.md#reglas-de-alerta-r51), sección `reglas` de `monitoreo.yaml` | `baja-confianza-v1`, `cambio-sostenido-v1` |
| R5.2 | [`escenarios/c2-baja-confianza/alertas.jsonl`](escenarios/c2-baja-confianza/alertas.jsonl) | `c2-20261109T042757Z-baja-confianza-v1-v000` → ventana 0 (63/79), 10 `event_ids`, `config_ref`, `model_ref` |
| R5.3 | [`portal/03-alertas.png`](portal/03-alertas.png), [`portal/04-alerta-c2.png`](portal/04-alerta-c2.png) | Momento 2026-11-09T04:28:08.121Z, motivo, severidad advertencia, acción sugerida |
| R6.1 | [Ficha de C1](escenarios/c1-normal/README.md) | 90 eventos, 0 alertas, métricas coherentes |
| R6.2 | [Ficha de C2](escenarios/c2-baja-confianza/README.md) | Alerta por baja confianza real, 23 capturas vinculadas |
| R7.1 | [`README.md`](../../README.md), [`docs/p6/configuracion.md`](../../docs/p6/configuracion.md), `pyproject.toml` + `uv.lock` | `uv sync --locked`, comandos de C1/C2 y recálculo |
| R7.2 | Este índice y [`recalcular.py`](recalcular.py) | — |
| R7.3 | [`docs/p6/autoria.md`](../../docs/p6/autoria.md) | Aportación propia frente a P5 y terceros |

## Cadena de muestra (C2)

1. **Frame:** `datos/p6/frames/c2/c2-f000210.jpg` (7.0 s del video «Night Traffic»; SHA-256 en
   `datos/p6/frames/c2/manifiesto.jsonl`).
2. **Inferencia → evento:** `c2-20261109T042757Z-c2-f000210` en `escenarios/c2-baja-confianza/eventos.jsonl`:
   9 candidatas `car`, todas bajas (máx. 0.221); `zona_frame` baja.
3. **Captura:** `capturas/c2-20261109T042757Z-c2-f000210.jpg` (motivos `zona_baja` y `alerta`), registrada en
   `capturas.jsonl` con su SHA-256.
4. **Ventana:** índice 0 de `ventanas.jsonl`: 63/79 = 0.797, suficiente; `baja-confianza-v1` cumple.
5. **Alerta:** `c2-20261109T042757Z-baja-confianza-v1-v000`, cuyos `event_ids` incluyen el evento del paso 2.
6. **Portal:** [`portal/04-alerta-c2.png`](portal/04-alerta-c2.png) → [`portal/05-evento-c2-baja.png`](portal/05-evento-c2-baja.png).

## Cómo recalcular una muestra

```bash
python evidencias/p6/recalcular.py evidencias/p6/escenarios/c2-baja-confianza   # solo biblioteca estándar
uv run python -m monitor verificar-capturas evidencias/p6/escenarios/*/
uv run python -m monitor video verificar        # hashes del respaldo de frames
```

## Extras

Inventario completo, con definiciones, límites y control de doble conteo: [`docs/p6/extras.md`](../../docs/p6/extras.md).
Los filtros que ya tenía el portal base, las cajas sobre la imagen y la página de corrida **no** se reclaman.

| ID | Tipo | Nivel solicitado | Evidencia | IDs / valores para comprobar |
|---|---|---|---|---|
| F1 | F · stream en vivo | 15 | [`extras/portal/vivo-1…5`](extras/portal/) (+ `.json`), [`portal/s1/`](extras/portal/s1/), `tests/test_p6_extras.py` | S2: `en_vivo` → `sin_senal` → `recuperando` → `en_vivo` → `terminada` |
| F2 | F · dashboard | 10 | [`extras/portal/10…14`](extras/portal/) | `/dashboard?run=s1-transicion-20261111T180825Z&metrica=G4`; 400 con `metrica=ZZ` |
| F3 | F · exportación con filtros validados | 10 | [`extras/exportacion/`](extras/exportacion/), `portal/19-…`, `portal/20-…` | `eventos_s1_baja.csv`: 6 filas = 6 frames baja de S1 |
| M1 | M · X1 candidatas por frame | 3 | `metricas_extra.json` de las 5 corridas, [`recalculo/x-*.txt`](recalculo/) | C1 22.78 · C2 5.88 |
| M2 | M · X2 frames sin detecciones | 5 | ídem | 0.0 en las 5 corridas (probado con frames vacíos en las pruebas) |
| M3 | M · X3 PSI de scores vs. referencia | 8 | ídem + S1 como caso controlado | S1 por ventana: 0.12–0.29 día, 0.61–2.53 noche, 0.08–0.13 al volver |
| M4 | M · X4 latencia e2e p95 + etapas | 5 | ídem | C1 624.51 ms · S1 362.39 ms |
| M5 | M · X5 disponibilidad de la fuente | 5 | ídem + S2 | S2 por ventana: 1, 1, 0, 0, 1, 1 |
| S1 | S · cambio sostenido con transición y recuperación | 8 | [ficha S1](extras/s1-transicion/README.md) | `s1-transicion-20261111T180825Z-cambio-sostenido-v1-v005` (ventanas 3, 4 y 5) |
| S2 | S · interrupción, diagnóstico, recuperación y verificación | 10 | [ficha S2](extras/s2-interrupcion/README.md) | `s2-interrupcion-20261111T180638Z-fuente-sin-senal-v1-000` (20 frames perdidos, 21.0 s sin señal) |
| M6 | M · X6 tasa de errores de inferencia | 5 | `metricas_extra.json`, [`recalculo/x-*.txt`](recalculo/) | S3 por ventana: 0, 0, 1.0, 0.5, 0, 0 |
| M7 | M · X7 tasa de descarte por saturación | 5 | ídem | S4 por ventana: 0, 0, 0.4, 0.6, 0, 0 |
| S3 | S · error de inferencia, diagnóstico, recuperación y verificación | 10 | [ficha S3](extras/s3-error-inferencia/README.md) | `s3-error-inferencia-20261111T183922Z-errores-inferencia-v1-v002` (código `detector_exception`) |
| S4 | S · saturación con persistencia y recuperación | 8 | [ficha S4](extras/s4-saturacion/README.md) | `s4-saturacion-20261111T184104Z-saturacion-v1-v002` (cola máx. 2972 ms) |

Total solicitado: **107 puntos** (35 F + 36 M + 36 S).
