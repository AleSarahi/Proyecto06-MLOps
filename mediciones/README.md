# mediciones/

Benchmark y límites (entregable **E7**): 10 calentamientos + 100 ejecuciones válidas con un registro por
ejecución, tiempos por etapa, p50/p95/máximo, hardware y runtime, y el reporte de límites (P5-15, P5-16).

## Equipo declarado (PEND-05)

El benchmark del entregable se mide en **la laptop de A3 (Ale)**, conectada a la corriente. Lo da A3 según
PEND-05; P5-04 comprueba que el detector elegido corre aquí.

| Dato | Valor |
|---|---|
| SO | Windows 11 Pro (10.0.26200), 64 bits |
| CPU | Intel Core i5-1135G7 @ 2.40 GHz (4 núcleos, 8 hilos) |
| RAM | 8 GB |
| Python | 3.12.14 (el de `.python-version`, con `uv`) |
| GPU | No se usa: todo en CPU |

`resumen.json` vuelve a registrar en cada corrida el SO, el CPU, la RAM, si estaba conectada a la corriente y las
versiones, así que se puede comprobar que se midió aquí.

## Comando (`python -m bench`)

```bash
uv run python -m bench \
  --entradas datos/cuadros/S0*/ \
  --salida mediciones/<run>/ \
  --equipo "laptop de A3" \
  --detector <módulo del detector> \
  --model-sha256 <hash de los pesos congelados> --config-sha256 <hash de la configuración congelada>
```

- `--entradas`: imágenes o carpetas (de una carpeta se toman `.jpg`, `.jpeg` y `.png` en orden de nombre, sin
  entrar a subcarpetas: por eso van las de cada secuencia). Se
  recorren en ciclo hasta juntar las ejecuciones.
- `--detector falso` (el valor por omisión) usa el detector de prueba del arnés. No tiene archivo de pesos, así que
  **solo corre con `--prueba`**. El detector real (P5-05) se
  conecta con un módulo que expone `crear(**opciones)` y devuelve un objeto como el `Detector` de
  [`src/bench/detector.py`](../src/bench/detector.py). `--opcion clave=valor` se pasa a `crear`.
- `--model-sha256` y `--config-sha256` son **obligatorios**, y el detector debe tener **archivo de pesos**. Para
  probar el arnés sin hashes o sin pesos está `--prueba`: mide, pero lo anota en `resumen.json` y nunca sale con
  `0`.
- `--config-control` (por omisión `config/control/`): de dónde se leen `plazos.yaml` y `politica.yaml` de B.
- `--mediciones` (100 por omisión, no menos) y `--max-fallos` (10). `--sin-politica` mide solo el detector.

**Qué se mide** en cada ejecución, con `time.perf_counter_ns`:

| Etapa | Qué incluye |
|---|---|
| `preprocesamiento_ms` | `preprocesar` del detector. |
| `inferencia_ms` | `inferir` del detector. |
| `posprocesamiento_ms` | `posprocesar` del detector (umbral, NMS, cajas a píxeles del cuadro original). |
| `evento_ms` | Leer las dimensiones del cuadro, armar el evento del contrato v1 y validarlo. |
| `politica_ms` | El Supervisor de B con la política y el AdaptadorVirtual reales: valida el evento, decide y registra el comando. |
| `total_ms` | **Tiempo de pared** de toda la ejecución, desde que empieza el preprocesamiento hasta que B registra el comando. Incluye las etapas y lo que pasa entre ellas, así que nunca es menor que su suma. |

**No se mide** leer y decodificar la imagen, cargar el modelo ni las pausas de reproducción: un cuadro sale en
cuanto termina el anterior. Lo que `infer` paga de más (leer el JPEG y la preparación de Ultralytics) lo mide
`python -m bench.sobrecosto` aparte (abajo).

**Qué escribe.** La carpeta de `--salida` debe no existir o estar **vacía**: con cualquier archivo adentro no se
mide, para no mezclar corridas.

| Archivo | Contenido |
|---|---|
| `ejecuciones.csv` | Una fila por ejecución válida: `intento`, `fase` (`calentamiento` o `medicion`), entrada, cada etapa en ms, número de detecciones y la acción que decidió B. |
| `fallos.csv` | Las ejecuciones que fallaron en cualquier etapa (también al armar el evento o en B), **aparte**: etapa, tipo de error y mensaje. No cuentan ni entran en p50/p95; el arnés sigue hasta juntar las 10 + 100 válidas. |
| `resumen.json` | Por etapa: p50, p95, máximo, mínimo y media de las 100 mediciones (sin calentamientos). Hardware, energía, runtime e hilos, pesos (ruta, bytes, SHA-256), procedencia, protocolo, SHA-256 de cada entrada y de los CSV, y advertencias. |

**Procedencia.** `resumen.json` separa dos cosas:

- `procedencia.detector` (**comprobada**): el arnés calcula el SHA-256 del archivo de pesos y lo compara con el
  `model_sha256` del detector y con `--model-sha256`; también compara el `config_sha256` con `--config-sha256`.
  Si el detector no tiene archivo de pesos, si el archivo no existe o si algún hash no coincide, **no se mide**
  (salida 2). Solo con `--prueba` se puede medir sin pesos, y entonces `comprobada` queda en `false`.
- `procedencia.config_b` (**registrada**): el SHA-256 de `plazos.yaml` y `politica.yaml` con que se midió la etapa
  de B. Si alguien cambia la política, el hash cambia. B todavía no tiene una referencia congelada con qué
  compararlos, así que quedan con `comparada_con_referencia: false`.

**Código de salida:** `0` completo y sin advertencias · `1` se midió pero hay advertencias (detector falso,
`--prueba`, pesos sin verificar, equipo sin declarar, en batería, sin política) o quedó incompleto porque los fallos pasaron de
`--max-fallos` · `2` no se mide así (configuración distinta, hashes sin indicar, sin archivo de pesos, entradas, configuración de B o
argumentos inválidos; no se escribe nada). La medición del entregable debe salir con `0`.

El detector falso no decodifica, pero rechaza archivos que no sean un JPEG o PNG completo.

El percentil es lineal (posición `(n - 1) * q`, interpolando entre vecinos), igual que en P4.

## Contraste con los plazos (`python -m bench.limites`, P5-16)

```bash
uv run python -m bench.limites mediciones/<run>/ [--config-control config/control/] [--periodo-ms 200]
```

Lee el `resumen.json` de la corrida y `plazos.yaml` de B, y escribe junto a la corrida `contraste.json` y
`contraste.md`: p50/p95/máximo contra cada plazo, con veredicto (**cumple**, **cumple en p95**, **no cumple**),
margen y razón. `--periodo-ms` es el ritmo de entrada de PEND-09 (200 ms, provisional); con otro valor se
contrasta igual, pero queda como advertencia. La fila de la edad tiene en cuenta la cola (ver
[`LIMITES.md`](LIMITES.md#contraste-con-los-plazos)).

**Código de salida:** `0` todo cumple hasta el máximo y la corrida es la del entregable · `1` algo no cumple
del todo, o la corrida tiene advertencias o fallos, quedó incompleta, no midió B, usa otro periodo que el de
PEND-09, o sus plazos o CSV cambiaron · `2` no se puede leer la corrida, los plazos o los argumentos (valores
no finitos, tipos inválidos); no queda ningún `contraste.*`, ni siquiera uno anterior.

Qué acredita y qué no el control virtual, y lo que no se midió: [`LIMITES.md`](LIMITES.md).

## Corrida final: regla fija antes de medir

Se decidió antes de ver ningún número (revisión de #82):

1. **Siempre 3 corridas** del benchmark, seguidas, con la laptop **conectada** y las demás aplicaciones
   cerradas (OneDrive, VS Code, navegador). Van en `mediciones/final-1/`, `final-2/` y `final-3/`.
2. Antes de las tres, **una vez** y en las mismas condiciones, `python -m bench.sobrecosto` (abajo), en
   `mediciones/final-sobrecosto/`.
3. **Se suben y se reportan las tres**, salgan como salgan. No se repite ninguna por su resultado.
4. P5-16 contrasta con los plazos **la peor**: por cada etapa, el mayor p95 y el mayor máximo de las tres, más
   la diferencia de `bench.sobrecosto` donde aplique.
5. Una corrida solo se invalida por una condición que el arnés registra y no depende del tiempo medido
   (salida distinta de `0`: en batería, hashes, fallos). Entonces se sube igual, se anota por qué y se repiten
   **las tres**.

## Lo que el arnés no mide y `infer` sí paga (`python -m bench.sobrecosto`)

El arnés parte de la imagen ya decodificada y llama a `preprocesar`, `inferir` y `posprocesar` de
`bench.yolo` por separado. `infer` (P5-05) llama a `DetectorJPEG.inferir`, que además **lee el JPEG** y pasa
por `predictor(...)` de Ultralytics, que **prepara cada llamada** alrededor de esas tres etapas. El plazo de
500 ms de P5-06 cubre la solicitud completa, así que P5-16 suma esa diferencia.

```bash
uv run python -m bench.sobrecosto --pesos <ruta>/yolo11n.pt --salida mediciones/final-sobrecosto/ \
  --equipo "laptop de A3" --model-sha256 <hash> --config-sha256 <hash>
```

Con las fotos de `docs/carro/` (no las de S01–S08), 3 vueltas de calentamiento y 20 repeticiones de cada foto.
En cada llamada a `DetectorJPEG.inferir` mide el tiempo de pared (`infer_ms`) y, dentro de la misma llamada,
las tres etapas del predictor (`etapas_ms`, con `perf_counter_ns`; el `speed` de Ultralytics usa `time.time()`,
que en Windows avanza a saltos de ~15 ms). `diferencia_ms = infer_ms - etapas_ms` se parte en
`fuera_del_predictor_ms` (leer el JPEG, sus revisiones, `_extraer_detecciones`) y `preparacion_ms`. Cuenta
`_extraer_detecciones` dos veces (también está en el `posprocesar` del arnés): queda del lado seguro.

Escribe `sobrecosto.csv` (una fila por llamada) y `sobrecosto.json` (p50/p95/máximo, hardware, energía, hashes
y SHA-256 de cada foto). Sale con `0` conectada y con los hashes comprobados, `1` con advertencias y `2` si no
puede medir.

En el ensayo en batería (2026-11-01, 10 repeticiones, no cuenta) dio `diferencia_ms` p50 14.5, p95 28.9 y
máximo 34.1 ms: casi todo es leer el JPEG; la preparación de Ultralytics, p95 6 ms. Las fotos de `docs/carro/`
son de celular (~1200×1600) y los cuadros del conjunto de 640×480, así que la lectura queda del lado alto.

## Resultado de la corrida final (2026-11-01, 22:57–22:59 hora local)

Con `config-detector-v1` (`config_sha256 6428a259…`, `model_sha256 0ebbc80d…`, 2 hilos) sobre S01–S08 de
`datos-evaluacion-v1`, en la laptop de A3 conectada a la corriente. Las cuatro salieron con `0`: completas, sin
fallos ni advertencias y con la procedencia comprobada. Se suben las tres corridas, como dice la regla.

| Corrida | `inferencia_ms` p50 / p95 / máx | `total_ms` p50 / p95 / máx |
|---|---|---|
| [`final-1`](final-1/resumen.json) | 83.20 / 91.84 / 102.03 | 92.78 / 101.71 / 111.05 |
| [`final-2`](final-2/resumen.json) | 85.15 / 107.69 / 138.49 | 94.87 / 118.63 / 154.38 |
| [`final-3`](final-3/resumen.json) | 82.99 / 89.67 / 98.20 | 92.42 / 99.04 / 106.90 |
| **Peor de las tres** | 107.69 / 138.49 (`final-2`) | 118.63 / 154.38 (`final-2`) |

[`final-sobrecosto`](final-sobrecosto/sobrecosto.json), medido justo antes: `diferencia_ms` p50 12.33, p95 14.70,
máximo 16.49 ms (`fuera_del_predictor_ms` máx 15.65; `preparacion_ms` máx 1.18). El contraste con los plazos lo
hace P5-16 (#73) con la peor corrida más esta diferencia.

**Condiciones, tal cual:** VS Code cerrado y OneDrive en pausa. El registro de procesos al empezar todavía mostró
procesos de `chrome`, `msedge` y `OneDrive`, posiblemente en segundo plano. Se reporta así; no se repitió ninguna
corrida.
