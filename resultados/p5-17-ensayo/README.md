# Evidencia del ensayo P5-17

Registros y salidas del ensayo descrito en [`../P5-17-ENSAYO.md`](../P5-17-ENSAYO.md). Son las salidas
originales de esa corrida: no se repitió nada para generarlas. Los registros `19a` a `19c` son del paso 19,
corrido después (2026-11-03, 15:59) en la misma copia; sus salidas no se suben (dan las mismas métricas que
el paso 16).

## Qué hay

- **`registros/`**: lo que se escribió en la terminal en cada paso, con su código de salida. Algunos traen el
  comando abreviado; el acta dice cuáles. La numeración es la de los pasos del acta.
  - `LEEME.txt`: commit, máquina y hora.
  - `sinred.sh.txt`: las variables con las que se cortó la red.
  - `enlaces.py.txt`: la revisión de enlaces y rutas.
  - `bloque.sh.txt`: el bloque "Métricas del conjunto completo" del README, tal como se corrió.
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

Los registros traían rutas de la laptop con el nombre de la cuenta local de Windows. La única depuración fue
cambiar cada ruta completa por un marcador, para que en el repo no quede ninguna ruta de una máquina (lo pide
`tests/test_copia_limpia.py`):

| Marcador | Qué era |
|---|---|
| `<ensayo>` | La carpeta, fuera del repo, donde se guardaron registros y salidas |
| `<copia>` | La copia limpia del repo |
| `<carpeta de uv>` | La carpeta de usuario donde `pip` dejó `uv.exe` (fallo 3 del acta) |

Además, en `salidas/corrida/run.json` la ruta de la entrada apunta a la copia publicada,
`resultados/p5-17-ensayo/salidas/ensayo-p517.jsonl`, que es el mismo archivo: su SHA-256, `20f9008e…1cc3`,
es el que ya registraba `run.json`. No cambió nada más: comandos, tiempos, detecciones, métricas ni códigos de
salida. Fueron **39** sustituciones en 15 archivos; los originales se
conservan fuera de Git. Con la copia pública, `python -m trazabilidad recalcular salidas/corrida/trazabilidad/`
sigue dando las mismas cifras que su `resumen.json`.

| Archivo | Sustituciones | SHA-256 original | SHA-256 público |
|---|---:|---|---|
| `registros/02-pesos.txt` | 1 | `ba18273ee36916062324f801f9fa0161f51397374a348a7f4da7e478ae94fcb9` | `7a89e5d63572d9efe1a92c0b8cf2d99f5a16c842d9b33ae5c32d4e2482f56ad9` |
| `registros/05-infer-jpeg.txt` | 6 | `93165bf4167277388da5c6f36b8cebf7b019ae4eccaf4223ca21773492f90d65` | `2e7d95dc2d7915f8a03930c5b4617faf6b7ce8bac59196e13b9ea8b3279d9568` |
| `registros/06a-infer-mismo-run-id-FALLA.txt` | 9 | `dfd3648cabbe70175b17685db095c9bb4a2291f586f5cb66d7310076a14d1420` | `97d2f644ba8776a605b339ba98fade787fd0f5d163afc09dbea7e8fb090ce95c` |
| `registros/06b-infer-secuencias.txt` | 9 | `1d7f9a446f6c4f41df1bb5f2d8f3b803bb8672e67275adaf88f4e5c915e62c3e` | `f77e996acebed7702206486162756dcb7a65ba5e3dd7c23e2250ed4d08cd4005` |
| `registros/07-metricas.txt` | 1 | `6f04c16e641a16135f50f103a0241fbc015fe2d08232f964b9f8bbc4f2c6b9a8` | `a20adea8d0a73d70ffdf7fb235ca44d120f7d223e78f5d25960db62985991dcb` |
| `registros/08-bench.txt` | 1 | `1ac715f033319a64b84dacb6340b75de85c0111e50e76158c0b23fb50365c246` | `0cb7b1702b47b2f0470823deafa16c0ad60599f688da9551a3ed239114629839` |
| `registros/09-limites.txt` | 2 | `0298c2c92ee10b1187e628d5a634230dbd878c74b01eca34cbee6cfd79f87c00` | `65d70b9ef1713683a08e52ae36eb15876ecabfb22b9ada0caed42428b231ec26` |
| `registros/14a-control-unido.txt` | 1 | `ce3f703c86853e9133176293fe892e2ff81e5fa0ddc320138eac8c3b5211e3e7` | `6358757ccfbd28bd546660f322bbeb7ea1ed10a7f582f94a51121bdadbe68644` |
| `registros/14b-trazabilidad.txt` | 1 | `030ca5e8cd3e183b4db3b9318c053fd88b17e645d6edc267676c4579e0889809` | `0d41d98f6b23db1a7787cad7bd10a6686b2090310db9d15423eaf111ca77b6a3` |
| `registros/15-powershell-bom.txt` | 1 | `e6d973b21bb2812272517e8cb55258565a0d7d30599fd78f6fd4787e3ee2486c` | `b31b82dc2c3cc9b9591de5aa3fc2cdae4fa32fea059986c725a861e979283b5f` |
| `registros/17-resto-comandos.txt` | 3 | `efe2431687315956c20125ce2489e9ee5d60d391a0778ad04d987d738b58b988` | `f3bdc080c63e809a81007105c9a509506f7e03f508b2e95e828f42548d7f94a2` |
| `registros/sinred.sh.txt` | 1 | `4307051dfcab5062104e3d2036c38795d8e7d01a97b8fa94111460425a2d95d3` | `e5e12a8bb8941c83841585fc9ad15e739907a6cf337c4c9daa0dbce88f00156a` |
| `salidas/casos/resumen.txt` | 1 | `6f676fe68e02d74595d978e4b126b3fe1690b93f5c9325ae4eb3aa35fecc5387` | `8cf3f655e31e392f21f8f17c14b2479938b30ae0cbcced1a755bb42636284ecc` |
| `salidas/corrida/run.json` | 1 | `f7609669515f1ab52774177910e5ec66ac46aa2eac021361ea39c7a9ffa627d5` | `eb5fa27da429bc818e6e6f9f17ece0a2c0489cfd5c5bb852c3b5dda43f98df17` |
| `salidas/metricas/resumen.json` | 1 | `8d576b902726c497109d636f2431df02b5aea60ed93a3572615fcc71b64be277` | `e8e5d1099011378167469d27a8783e4218076f0431fc8ae34de684077a0504c0` |

Además, los archivos de texto escritos en Windows pasaron de fin de línea CRLF a LF, como hace
`.gitattributes` con todo el texto del repo; no cambia su contenido. Los SHA-256 públicos de la tabla y de
`SHA256SUMS` son de la versión con LF. `registros/10-enlaces-rutas.txt` quedó en la codificación de la
consola de Windows (cp1252), tal como se escribió.

## Verificar

`SHA256SUMS` lista todos los archivos de esta carpeta salvo este README y el propio índice (UTF-8 sin BOM,
fin de línea LF). Desde esta carpeta, en Git Bash: `sha256sum -c SHA256SUMS`.
