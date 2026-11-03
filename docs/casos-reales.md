# Entradas reales de C1 a C7 (T20)

Cada `casos/Cn/entrada.jsonl` de C1 a C7 sale de `python -m infer` con el detector congelado sobre los
cuadros del tag `datos-evaluacion-v1`, siguiendo `datos/MAPA_CASOS.md` (P5-12). Todo es offline, en CPU
y **sin mover motores**.

> **Resultado (2026-11-02):** `casos/runner.py` da **7 de 10**. Pasan C1, C3, C4 y C6 con las
> entradas reales, y C8, C9 y C10 armados. **C2, C5 y C7 fallan por el detector**: en algunos cuadros
> no ve el obstáculo o lo ve por debajo de `umbral_confianza` (0.5), y el control hace lo correcto con
> lo que recibe ([Por qué fallan](#por-qué-fallan-c2-c5-y-c7)). No se tocó ninguna expectativa, umbral,
> zona, plazo ni configuración. El resumen está en `resultados/casos/resumen.txt`.

## Datos y detector

| Tag | Commit | Qué fija |
|---|---|---|
| `datos-evaluacion-v1` | `9b8dc08` | `manifiesto.jsonl` `8a75e271…`, `anotaciones.jsonl` `7e842784…` (#13) |
| `config-detector-v1` | `baa3a9d` | `config_sha256` `6428a259…`, `model_sha256` `0ebbc80d…` (#13) |

- `datos/cuadros/` es igual en el tag y en `main` (`git diff` vacío). Antes de correr, el SHA-256 de
  cada JPEG de S01 a S08 coincidió con su `captura.jsonl` y con el manifiesto (P5-09, #11).
- Las corridas se hicieron el 2026-11-01 con `infer` en `d3a2f1c` (#75). Entre `d3a2f1c` y
  `config-detector-v1` no cambia nada de `src/infer/`, `config/detector.json`, `modelo/`,
  `pyproject.toml` ni `uv.lock`. Todos los eventos traen el `config_sha256` y el `model_sha256` de
  `config-detector-v1`: lo revisa `tests/test_casos_reales.py`.
- **Una corrida por secuencia, y se queda la primera** (#36). La de S02 es la misma que la de `centro`
  en `docs/recorrido-real.md` (T16): mismo SHA-256 (`138e67f5…`). La de S07 es la de A
  (`resultados/p5-12-c6-s07.jsonl`, P5-12): B no corrió S07.

## De dónde sale cada entrada

| Caso | Corrida (`run_id`) | Cuadros | `entrada` | Edad de los cuadros | SHA-256 de `entrada.jsonl` |
|---|---|---:|---|---|---|
| C1 | `c1-s01-s08`: S01 y luego S08 | 24 | `real` | 63–109 ms | `669032d9…d45b` |
| C2 | `mapa-S02` | 12 | `real` | 93–202 ms | `138e67f5…20ac` |
| C3 | `mapa-S03` | 12 | `real` | 78–344 ms | `c663a6f4…cda1` |
| C4 | `mapa-S04` | 12 | `real` | 93–172 ms | `3dc18f92…382a` |
| C5 | `mapa-S05` | 12 | `real` | 78–141 ms | `94c4cb0a…ac7` |
| C6 | `c6-s07` (de A), reordenada | 11 de 15 | `armada` | 79–156 ms | `50a8d99e…44b9` |
| C7 | `mapa-S06` | 20 | `real` | 94–282 ms | `9f2675cd…39ab` |

C2, C3, C4, C5 y C7 son la salida de `infer` **sin cambios**: la secuencia completa, en el orden de los
nombres de los JPEG, con los `t_capture_ms` de su `captura.jsonl`. Ningún cuadro pasa de 500 ms de edad.
Los tramos de cada `tramos.yaml` son los de `datos/MAPA_CASOS.md`.

### Comandos

Desde la raíz del repo, con los pesos `yolo11n.pt` (README, sección 5 del grupo B). Para S02 a S06, un
`--capture-ms` por JPEG con su `t_capture_ms`:

```bash
uv run --locked python -m infer --input datos/cuadros/S02 --weights <ruta local>/yolo11n.pt \
  --output <archivo>.jsonl --run-id mapa-S02 --sequence-id S02 \
  --capture-ms 0 --capture-ms 219 --capture-ms 547 ...   # los 12 de datos/cuadros/S02/captura.jsonl
```

### C1: S01 y después S08

C1 pide las dos secuencias en la misma entrada, y el reloj del control (`t_emit_ms`) no puede
retroceder. Por eso son **dos llamadas a `infer` con el mismo `run_id`** (`c1-s01-s08`):

- S01 con sus `t_capture_ms`, de 0 a 3156 ms.
- S08 con sus `t_capture_ms` **+ 3406 ms**: el último de S01 (3156) más 250, de 3406 a 5968 ms.

`entrada.jsonl` es la salida de la primera seguida de la segunda, sin cambios. S01 y S08 también se
corrieron por separado (`mapa-S01`, `mapa-S08`) para comprobar la lectura de las secuencias (P5-09,
#11), pero esas dos empiezan en 0 ms y no sirven para C1 sin editar tiempos a mano. En las cuatro
corridas el detector da **0 detecciones** en los 24 cuadros: solo cambian los tiempos.

### C6: S07 reordenada

`casos/C6/expectativa.yaml` pide primero los cuadros de abajo del umbral y después los de arriba, pero
en S07 la confianza alterna y empieza en 0.656 (`datos/MAPA_CASOS.md`, "C6: scores de S7"). En el orden
original, C6 no puede pasar: tras `S07_f0001` (0.656) la política gira, y por la histéresis (3
cuadros libres para reanudar) en los cuadros de abajo del umbral sigue girando o da STOP, en vez de
avanzar. Por eso C6 es `armada`, y
`casos/armar_c6.py` la arma desde la corrida de A:

| Tramo | Cuadros (score de `infer`) |
|---|---|
| `bajo_umbral` | `f0003` 0.330, `f0006` 0.439, `f0007` 0.292, `f0009` 0.372 |
| `sobre_umbral` | `f0001` 0.656, `f0002` 0.525, `f0005` 0.635, `f0010` 0.517, `f0011` 0.529, `f0014` 0.817, `f0015` 0.948 |

- Cada grupo va en el orden de S07, con capturas nuevas cada 200 ms (0 a 2000 ms). Cada cuadro conserva
  su demora `t_emit_ms − t_capture_ms`.
- El `frame_id` y las detecciones son los de `infer`.
- Los 4 cuadros sin detección (`f0004`, `f0008`, `f0012`, `f0013`) no entran: no tienen una confianza
  que poner de un lado del umbral. En las métricas cuentan como falsos negativos.
- El umbral se lee de `config/control/politica.yaml`; el script no lo fija.

```bash
uv run python casos/armar_c6.py              # escribe casos/C6/entrada.jsonl
uv run python casos/armar_c6.py --revisar    # sale 1 si la entrada no es la que se arma
```

## Por qué fallan C2, C5 y C7

En los tres, las cajas que el detector sí da coinciden con las anotadas, y la política decide bien con lo
que recibe. Lo que falla es que el detector no ve el obstáculo, o lo ve por debajo de 0.5, en estos
cuadros. Es un **límite del detector**: no se cambia la expectativa ni el umbral, y la secuencia no se
refilma (#36, `datos/DOMINIO.md`).

### C2 · Obstáculo central (`obstaculo`, 0 de 1)

| Cuadro | Anotado | `infer` | Orden | Motivo del runner |
|---|---|---|---|---|
| `S02_f0001` | `cup`, x 272–458 | nada | AVANZAR | AVANZAR está prohibida |
| `S02_f0002` | `cup`, x 269–458 | nada | AVANZAR | AVANZAR está prohibida |
| `S02_f0003` | `cup`, x 267–456 | `cup` 0.30 | AVANZAR | AVANZAR está prohibida |
| `S02_f0004` | `cup`, x 266–453 | `cup` 0.42 | AVANZAR | AVANZAR está prohibida |
| `S02_f0005` | `cup`, x 267–459 | `cup` 0.49 | AVANZAR | AVANZAR está prohibida |
| `S02_f0006` | `cup`, x 270–462 | `cup` 0.79 | GIRAR_IZQ | Sale a los 1312 ms; el plazo es 500 desde la captura de `f0001` |

De `S02_f0006` a `S02_f0012` el carro gira a la izquierda (la taza está cargada a la derecha), como en
`docs/recorrido-real.md`, sección "Centro (S02)".

### C5 · Sin zona libre (`sin_zona_libre`, 0 de 1)

| Cuadro | Anotado | `infer` | Orden | Motivo del runner |
|---|---|---|---|---|
| `S05_f0001` | `bottle` x 26–146 (izq), `cup` x 260–418 (centro), `bottle` x 486–608 (der) | `cup` 0.85, `bottle` der 0.63, **`bottle` izq 0.44** | GIRAR_IZQ | GIRAR_IZQ está prohibida |

La botella de la izquierda queda por debajo del umbral, así que para la política la izquierda está
libre y gira hacia allá. Desde `S05_f0002` (botella izquierda 0.72) las tres zonas están ocupadas y
sale STOP en el resto de los cuadros.

### C7 · Libre → bloqueo → libre (3 de 5 tramos)

| Tramo | Cuadro | Anotado | `infer` | Orden | Motivo del runner |
|---|---|---|---|---|---|
| `bloqueo` | `S06_f0002` | `cup`, x 140–267 (toca el centro) | nada | AVANZAR | AVANZAR está prohibida |
| `bloqueo_otra_vez` | `S06_f0007` | `cup`, x 183–312 (toca el centro) | nada | AVANZAR | AVANZAR está prohibida |

En `f0003`, `f0004` y `f0008` el detector ve la taza (0.58, 0.57 y 0.52) y el control no avanza. En
`f0005` tampoco la ve, pero no falla: viene de girar en `f0003` y `f0004`, y la histéresis (3 cuadros
libres para reanudar) lo mantiene girando. Pasan `libre`, `un_cuadro_libre` y `libre_otra_vez`.

`tests/test_casos_reales.py` guarda estos tramos y `frame_id`. Si cambian, la prueba falla y hay que
volver a revisar este documento.

## Cómo comprobarlo

```bash
uv run python casos/runner.py                        # 7 de 10; tabla en resultados/casos/resumen.txt
uv run pytest -q tests/test_casos_reales.py          # de dónde sale cada entrada y qué falla
uv run python casos/armar_c6.py --revisar            # C6 es la que arma el script
for c in C1 C2 C3 C4 C5 C6 C7; do uv run python -m contrato casos/$c/entrada.jsonl; done
```
