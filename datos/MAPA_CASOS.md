# Mapa de casos (P5-12)

Qué cuadros y qué entradas usa cada caso de `casos/`, y qué se espera de la percepción, sobre los datos
congelados en `datos-evaluacion-v1` (#13). Los tramos de C1 a C5 y C7 salen de las cajas anotadas
(`datos/anotaciones.jsonl`) y de las zonas de `config/control/politica.yaml`, no del detector. Los de C6 sí
salen del detector, con la configuración de `config-detector-v1`.

## C1 a C7: cuadros reales

| Caso | Secuencia | Cuadros | Qué se espera de la percepción |
|---|---|---|---|
| C1 · Vía libre | S1 | `S01_f0001`–`f0012` | Sin `bottle` ni `cup` |
| C1 · Vía libre, transitables | S8 | `S08_f0001`–`f0012` | Sin `bottle` ni `cup`; tapa, borrador y cable no cuentan |
| C2 · Obstáculo central | S2 | `S02_f0001`–`f0012` | `cup` en el centro; en 10 cuadros también toca la derecha |
| C3 · Obstáculo izquierdo | S3 | `S03_f0001`–`f0012` | `bottle` solo a la izquierda |
| C4 · Obstáculo derecho | S4 | `S04_f0001`–`f0012` | `bottle` solo a la derecha |
| C5 · Sin zona libre | S5 | `S05_f0001`–`f0012` | Dos `bottle` y una `cup` en las tres zonas |
| C6 · Confianza | S7 | Ver [C6](#c6-scores-de-s7) | `cup` al centro, bajo y sobre el umbral de 0.50 |
| C7 · Libre → bloqueo → libre | S6 | Ver [C7](#c7-tramos-de-s6) | `cup` que entra y sale del centro |

S1–S8 son evaluación. S9 y S10 no entran en este mapa: son solo para las pruebas del grupo B.

### C7: tramos de S6

Los nombres son los de `casos/C7/expectativa.yaml`.

| Tramo | Cuadros | Centro |
|---|---|---|
| `libre` | `S06_f0001` | Libre: la taza está a la izquierda |
| `bloqueo` | `S06_f0002`–`f0005` | Ocupado |
| `un_cuadro_libre` | `S06_f0006` | Libre: la taza está a la izquierda |
| `bloqueo_otra_vez` | `S06_f0007`–`f0008` | Ocupado |
| `libre_otra_vez` | `S06_f0009`–`f0020` | Libre: sin taza |

### C6: scores de S7

Salen de correr `python -m infer` desde `config-detector-v1` sobre `datos/cuadros/S07/`, con los
`t_capture_ms` de `captura.jsonl`, después del paso 2 de #13 (`config_sha256` `6428a259…`, `model_sha256`
`0ebbc80d…`). Fue una sola corrida, guardada en
[`resultados/p5-12-c6-s07.jsonl`](../resultados/p5-12-c6-s07.jsonl). Los 15 cuadros tienen una `cup`
anotada al centro.

| Grupo | Cuadros y score | Total |
|---|---|---:|
| Sobre el umbral (≥ 0.50) | `f0001` 0.656, `f0002` 0.525, `f0005` 0.635, `f0010` 0.517, `f0011` 0.529, `f0014` 0.817, `f0015` 0.948 | 7 |
| Bajo el umbral (0.25 a 0.50) | `f0003` 0.330, `f0006` 0.439, `f0007` 0.292, `f0009` 0.372 | 4 |
| Sin detección | `f0004`, `f0008`, `f0012`, `f0013` | 4 |

**Sí hay `cup` entre 0.25 y 0.50 y otra ≥ 0.50**, así que S7 cubre lo que pide C6. Dos diferencias con lo
planeado:

- **El score no sube con la distancia:** `DOMINIO.md` esperaba empezar bajo y pasar de 0.50 al acercarse,
  pero S7 empieza en 0.656 y alterna. `casos/C6/expectativa.yaml` pide los cuadros de abajo del umbral
  primero; en la secuencia original no van en ese orden.
- **Los 4 cuadros sin detección** no entran en `bajo_umbral` tal como está escrito, porque no tienen
  detección con confianza menor que el umbral. Cuentan como falsos negativos en las métricas.

S7 no se refilma por este resultado (`DOMINIO.md`).

## C8 y C9: entradas fallidas

Las fixtures están en [`fixtures/`](fixtures/), con su SHA-256 en `SHA256SUMS`. Son sintéticas: no parten
de cuadros del conjunto, y en `datos/` no hay ningún JPEG truncado real del stream que conservar.

| Fixture | Qué es | `python -m captura` la rechaza como | `python -m infer` (`config-detector-v1`) |
|---|---|---|---|
| `no_es_jpeg.jpg` | Texto con extensión `.jpg` | `jpeg_incompleto` | `status=error`, `unreadable_image` |
| `sin_imagen.jpg` | Encabezado JPEG sin datos de imagen | `jpeg_incompleto` | `status=error`, `unreadable_image` |
| `truncado.jpg` | JPEG cortado a la mitad de los datos | `jpeg_incompleto` | `status=error`, `unreadable_image` |
| `vacia.jpg` | Archivo de 0 bytes | `jpeg_incompleto` | `status=error`, `unreadable_image` |
| `otras_dimensiones.jpg` | JPEG válido de 320×240 | `tamano_320x240` | `status=ok`, 320×240 |

`otras_dimensiones.jpg` no es un error para `infer`: el contrato pide los píxeles del cuadro original. Lo
detectan `captura` y las métricas, que avisan si el tamaño no coincide con la anotación.

Un JPEG que no existe no necesita fixture: basta una ruta inexistente. En `config-detector-v1`, `infer`
termina con código 2 y sin evento; A1 lo corrige en P5-06.

### `error.code` del contrato

| `error.code` | Cómo se produce | Estado |
|---|---|---|
| `unreadable_image` | Fixtures de arriba | Comprobado, salvo el JPEG inexistente (P5-06) |
| `detector_exception` | Se fuerza una excepción en el detector | Sin archivo de entrada; pendiente de la lista de A1 (P5-06) |
| `invalid_output` | Se fuerza una salida inválida del detector | Sin archivo de entrada; pendiente de la lista de A1 (P5-06) |
| `detector_timeout` | Se fuerza un tiempo agotado | `infer` todavía no lo aplica (P5-06) |

C8 no necesita archivos: el hueco sin cuadros y los cuadros viejos (`status=stale`, o `status=ok` con
`t_emit_ms − t_capture_ms` mayor que `max_frame_age_ms`) son eventos armados en `casos/C8/entrada.jsonl`.
C10 puede usar cualquier secuencia.

## Falta

- [ ] Lista de errores de A1: cómo se fuerza `detector_exception`, `invalid_output` y `detector_timeout` (P5-06).
- [ ] Corrección del JPEG inexistente en `infer` (P5-06).
- [ ] B3 confirma que el mapa le sirve para armar C1–C9.
