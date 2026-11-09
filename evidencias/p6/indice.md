# Proyecto 6 · Índice de evidencias

> Issue #27 (R7.2). Entrega individual de Alejandra Rayas · repositorio <https://github.com/AleSarahi/Proyecto06-MLOps>.

## Revisiones Git

| Qué | Commit | Relación |
|---|---|---|
| Código con el que se ejecutaron la referencia, C1 y C2 | `d5ab5971fd8b960018bd8d2c0f04bb5077a92132` | Cada `run.json` lo registra en `git.commit`, con `cambios_sin_commit: false`. |
| Evidencias de las corridas (JSONL, capturas, métricas, recálculo, portal) | `20bfa9b` | Se agregó **después** del código probado y no lo modifica: solo agrega `evidencias/p6/`. |
| Documentación (docs/p6, README, este índice) | commits posteriores con prefijo `P6-` | No cambian `src/monitor/` ni `config/p6/`, así que el `config_ref` sigue siendo `c574ee88…ff6c`. |

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

**Esta entrega no reclama puntos extra.** El portal tiene funciones que van más allá de la consulta mínima (filtros
por corrida/zona/estado, cajas sobre la imagen y página de corrida con métricas), pero no se presentan como
adicionales con evidencia propia. Si más adelante se reclaman, se registrarán aquí con ID, tipo F/M/S, nivel
solicitado y evidencia.
