# Evidencia del ensayo P5-17

Registros y salidas del ensayo descrito en [`../P5-17-ENSAYO.md`](../P5-17-ENSAYO.md). Son las salidas
originales de esa corrida: no se repitió nada para generarlas.

## Qué hay

- **`registros/`**: lo que se escribió en la terminal en cada paso, con el comando completo y su código de
  salida. La numeración es la de los pasos del acta.
  - `LEEME.txt`: commit, máquina y hora.
  - `sinred.sh`: las variables con las que se cortó la red.
  - `enlaces.py.txt`: la revisión de enlaces y rutas.
  - `bloque.sh`: el bloque "Métricas del conjunto completo" del README, tal como se corrió.
- **`salidas/`**: lo que escribieron los comandos.
  - `jpeg-*.jsonl` y `ensayo-S0*_f000*.infer-run.json`: los 3 JPEG elegidos por quien verifica.
  - `S01/` a `S08/`: la salida de `infer` de cada secuencia (`detecciones.jsonl`) y su manifiesto de run.
  - `ensayo-p517.jsonl`: las 8 salidas unidas con `cat` (107 eventos, uno por cuadro).
  - `metricas/`: `resumen.json`, `por_cuadro.csv` y `detalle.csv` de `python -m metricas`.
  - `bench/`: `resumen.json`, `ejecuciones.csv` y `fallos.csv` de `python -m bench`.
  - `contraste/`: la salida de `python -m bench.limites`, idéntica a `mediciones/final-contraste/`.
  - `corrida/`: la corrida de `python -m control` y, en `corrida/trazabilidad/`, la de `python -m trazabilidad`.
  - `casos/resumen.txt`: la tabla de `casos/runner.py`.

No se suben:
- las 8 hojas PNG de `conjunto hojas` (12 MB; se regeneran con un comando);
- las copias de prueba de PowerShell del paso 15 (su resultado está en el registro);
- el manifiesto regenerado, que es idéntico byte a byte a `datos/manifiesto.jsonl` (registro 17).

## Rutas personales

La única depuración fue cambiar el nombre de la cuenta local de Windows por `<usuario>` dentro de las rutas
(por ejemplo, `C:/Users/<usuario>/p517-ensayo/...`). No cambió nada más: comandos, tiempos, detecciones,
métricas ni códigos de salida. Fueron **39** sustituciones en 15 archivos; los originales se conservan fuera
de Git. Con la copia pública, `python -m trazabilidad recalcular salidas/corrida/trazabilidad/` sigue dando
las mismas cifras que su `resumen.json`.

| Archivo | Sustituciones | SHA-256 original | SHA-256 público |
|---|---:|---|---|
| `registros/02-pesos.txt` | 1 | `ba18273ee36916062324f801f9fa0161f51397374a348a7f4da7e478ae94fcb9` | `b08232f9bbf81c72cccec0f3438a266909028085da57f46630615d30ebc6628a` |
| `registros/05-infer-jpeg.txt` | 6 | `93165bf4167277388da5c6f36b8cebf7b019ae4eccaf4223ca21773492f90d65` | `5a6310608e16a615f974ee1676c3499324d717cbf197a7edf6506ebe8f8d2eda` |
| `registros/06a-infer-mismo-run-id-FALLA.txt` | 9 | `dfd3648cabbe70175b17685db095c9bb4a2291f586f5cb66d7310076a14d1420` | `7bb15ee4ecb3e8acdb5905433a68b7d021a80f1f25288b9d8b7030a14750e373` |
| `registros/06b-infer-secuencias.txt` | 9 | `1d7f9a446f6c4f41df1bb5f2d8f3b803bb8672e67275adaf88f4e5c915e62c3e` | `c4633169b402e945beadff8504e1be1c53185dc6d712b25bd5b6c8fa093be765` |
| `registros/07-metricas.txt` | 1 | `6f04c16e641a16135f50f103a0241fbc015fe2d08232f964b9f8bbc4f2c6b9a8` | `12f951f08278103fc56a80e8ff69d868cfba73e0aa8720605eba225a2654ffd9` |
| `registros/08-bench.txt` | 1 | `1ac715f033319a64b84dacb6340b75de85c0111e50e76158c0b23fb50365c246` | `53764fa72522a9c76eb5d3ae54926d3eb1de90ff7bdaf24710fc6deb7113165d` |
| `registros/09-limites.txt` | 2 | `0298c2c92ee10b1187e628d5a634230dbd878c74b01eca34cbee6cfd79f87c00` | `0bbbd25ffce34fa9a043c3cea5d9c1295ee9aa44ace7c1762116e28afe69d286` |
| `registros/14a-control-unido.txt` | 1 | `ce3f703c86853e9133176293fe892e2ff81e5fa0ddc320138eac8c3b5211e3e7` | `d65567cfa3714c4b707efd06abe906e0a345afc1e4c3dba5434fe5bc279ace57` |
| `registros/14b-trazabilidad.txt` | 1 | `030ca5e8cd3e183b4db3b9318c053fd88b17e645d6edc267676c4579e0889809` | `668d513abb8be30f3844c1b7be955887ecc685341b3696c1a2d18a651bb02bfe` |
| `registros/15-powershell-bom.txt` | 1 | `e6d973b21bb2812272517e8cb55258565a0d7d30599fd78f6fd4787e3ee2486c` | `f3fc9f54e2dfb138071f84df79a68bee3228507049103212f7546385f90de67b` |
| `registros/17-resto-comandos.txt` | 3 | `efe2431687315956c20125ce2489e9ee5d60d391a0778ad04d987d738b58b988` | `b3ce09697ac060ed375a4a88ac65824c79743d80daa0f469ff26068766e57329` |
| `registros/sinred.sh` | 1 | `4307051dfcab5062104e3d2036c38795d8e7d01a97b8fa94111460425a2d95d3` | `38c324ccc3583104d5af9af59ca4f378fe3f702378de412d1dddbc8afc8aa212` |
| `salidas/casos/resumen.txt` | 1 | `6f676fe68e02d74595d978e4b126b3fe1690b93f5c9325ae4eb3aa35fecc5387` | `fbb650625e1bc8e2d1b4483246e4f762bc4334371c96fe9b5d312a7652fa4dc5` |
| `salidas/corrida/run.json` | 1 | `f7609669515f1ab52774177910e5ec66ac46aa2eac021361ea39c7a9ffa627d5` | `3e0c665276b72064a4df57c6e150369ae2d62c5e8eb4a65c24004dfb2c912140` |
| `salidas/metricas/resumen.json` | 1 | `8d576b902726c497109d636f2431df02b5aea60ed93a3572615fcc71b64be277` | `9e3a5298fbe1ac9dc9f474522a4aead812de07d3bcb2619d22ff33794f4572b7` |

Además, 20 archivos de texto escritos en Windows pasaron de fin de línea CRLF a LF, como hace `.gitattributes` con todo el texto del repo; no cambia su contenido. Los SHA-256 públicos de la tabla y de `SHA256SUMS` son de la versión con LF.

## Verificar

`SHA256SUMS` lista todos los archivos de esta carpeta salvo este README y el propio índice (UTF-8 sin BOM,
fin de línea LF). Desde esta carpeta, en Git Bash: `sha256sum -c SHA256SUMS`.
