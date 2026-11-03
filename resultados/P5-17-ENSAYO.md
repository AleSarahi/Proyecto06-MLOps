# P5-17 · Ensayo de reproducción de la parte A desde una copia limpia

Ensayo previo a la reproducción conjunta final, que hace B3 con el equipo B. Se siguió solo el README de
`main`, sin pedir ayuda al equipo, sin secretos ni tokens. Los registros de terminal y las salidas de cada
paso están en [`p5-17-ensayo/`](p5-17-ensayo/README.md), con su índice `SHA256SUMS`.

| Qué | Valor |
|---|---|
| Quién | Andrea Arevalo (A2) |
| Cuándo | Del 2026-11-02 a las 23:08 al 2026-11-03 a las 00:04, hora del centro de México (UTC−6) |
| Commit | `f06e6f48032afaf7d9d3f2938fd2e8ed59cb4394` (`main` con #86, #87, #92 y #93) |
| Máquina | Laptop con Windows 11 Home Single Language 10.0.26200, x64; AMD Ryzen 7 8845HS (8 núcleos, 16 hilos); 62 GB de RAM; solo CPU |
| Terminales | PowerShell 5.1 y Git Bash (git 2.46.0) |
| uv | 0.12.13, la misma del CI |
| Copia | `git clone` nuevo en una carpeta vacía, sin `.venv` ni `modelo/descargas/` |

**Sin red:** después de `uv sync --locked` y de bajar los pesos, todo se corrió con `UV_OFFLINE=1` y con
`HTTP_PROXY`, `HTTPS_PROXY` y `ALL_PROXY` apuntando a `http://127.0.0.1:9`, un puerto donde no escucha nada
([`sinred.sh`](p5-17-ensayo/registros/sinred.sh)). Antes de seguir se comprobó que una petición a
`https://github.com` fallaba (`URLError`). No se desconectó el Wi-Fi: la red se cortó para uv y Python, no
para todo el equipo.

## Pasos

Los registros están en `p5-17-ensayo/registros/` y las salidas, en `p5-17-ensayo/salidas/`. Cada registro
trae el comando completo y su código de salida.

| # | Paso (README) | Resultado | Registro | Estado |
|---|---|---|---|---|
| 1 | `uv sync --locked` (con red) | Entorno creado, código 0 | `01` | Observado |
| 2 | `uv run --locked python -m infer.descarga` (con red) | `descargado, 5613764 B, SHA-256 0ebbc80d…6ee1 OK` | `02` | Observado |
| 3 | Corte de red | `URLError` al pedir `https://github.com` | `03` | Observado |
| 4 | `conjunto verificar --sha256 8a75e271…` y hashes de "Versión de entrega" | 107 cuadros, 8 secuencias, `OK con 0 excepciones`. Manifiesto `8a75e271…`, anotaciones `7e842784…`, pesos `0ebbc80d…` y `config_sha256` `6428a259…` coinciden. `datos/` y `config/detector.json` son iguales a los tags `datos-evaluacion-v1` y `config-detector-v1` | `04` | Observado |
| 5 | `infer` con JPEG elegidos por quien verifica | `S05_f0001` (botellas 0.632 y 0.439, taza 0.851), `S07_f0003` (taza 0.330) y `S01_f0001` (`ok` sin detecciones). Contrato OK en los tres; coinciden con `docs/casos-reales.md` | `05`; `salidas/jpeg-*` | Observado |
| 6 | `infer` con S01–S08 y los `t_relativo_ms` del manifiesto, y unión con `cat` | 107 eventos (uno por cuadro), 0 errores, todos `ok`, contrato OK. **Falló al primer intento** (fallo 1) | `06a` (fallo), `06b`; `salidas/S0*/`, `salidas/ensayo-p517.jsonl` | Observado |
| 7 | `metricas` con las 8 secuencias | TP=71, FP=0, FN=24; P=1.0000, R=0.7474, F1=0.8554; criterio 1.4: 5 de 6; sin advertencias | `07`; `salidas/metricas/` | Observado |
| 8 | `bench` (Git Bash, `S0*` se expande) | 100 mediciones, 0 fallos; p50 80.64 ms, p95 93.22 ms, máximo 98.56 ms. Código 1 por la advertencia de batería | `08`; `salidas/bench/` | Observado, con advertencia |
| 9 | `bench.limites` con `final-1` a `final-3` y `final-sobrecosto` | Los cinco plazos cumplen; `contraste.json` y `contraste.md` son idénticos byte a byte a `mediciones/final-contraste/` | `09`; `salidas/contraste/` | Observado |
| 10 | Enlaces y rutas absolutas en los archivos del repo | 0 enlaces rotos (relativos y anclas, en todos los `.md`) y 0 rutas personales en el texto | `10`, `enlaces.py.txt` | Observado |
| 11 | Rutas personales dentro de los 3 ZIP de `resultados/` | 0 en los tres | `11` | Observado |
| 12 | `ruff check`, `ruff format --check` y `pytest` con `P5_05_YOLO11N_PT` | Ruff limpio; 1280 pasan, 19 saltadas, 0 fallan | `12` | Observado |
| 13 | Las dos pruebas que fallaban de forma intermitente en Windows antes de #86 | 20 de 20 veces pasan | `13` | Observado |
| 14 | `control` con las 8 secuencias y `trazabilidad construir`, `recalcular` y `cuadro` | 107 eventos, 108 comandos, 0 errores. La trazabilidad da las mismas cifras que `metricas`; `recalcular` coincide con `resumen.json`; `cuadro S05_f0001` muestra del evento al comando | `14a`, `14b`; `salidas/corrida/` | Observado |
| 15 | Juntar las 8 salidas en PowerShell 5.1 | `Set-Content -Encoding UTF8` y `>` agregan BOM y `metricas` sale con 2; `[IO.File]::WriteAllLines` no lo agrega y `metricas` da lo mismo que en el paso 7 (fallo 2) | `15` | Observado |
| 16 | Bloque "Métricas del conjunto completo" del README corregido, copiado y corrido tal cual | Los mismos 107 eventos que el paso 6 y las mismas métricas que el paso 7 | `16`, `bloque.sh` | Observado |
| 17 | `contrato` con el ejemplo, `conjunto manifiesto` y `hojas`, y `casos/runner.py` | Ejemplo OK (5 eventos). `conjunto manifiesto` sin `--salida` no toca el congelado (código 2, como dice su ayuda); con `--salida` en otra carpeta, el manifiesto regenerado es idéntico byte a byte a `datos/manifiesto.jsonl`. 8 hojas. Runner: 7 de 10, con C2, C5 y C7 fallando por el límite del detector documentado en `docs/casos-reales.md`. La copia de git siguió sin cambios | `17`; `salidas/casos/resumen.txt` | Observado |
| 18 | `python -m uv` en lugar de `uv` (fallo 3) | `sync`, `run` y `conjunto verificar` funcionan igual | `18` | Observado |
| 19 | Reproducción conjunta con el equipo B | La hace B3 después de este ensayo | — | No observado |

Las 19 pruebas saltadas son propias de Windows: crear enlaces simbólicos (pide modo de desarrollador,
`WinError 1314`), FIFO y permisos POSIX. Las que usan los pesos reales sí corrieron.

## Comandos del README

P5-18 (#20) pide que cada comando del README se pruebe en este ensayo. Todos los de la sección del grupo A
se corrieron tal como están, y también los de la instalación y la tabla general, salvo `captura`:

| Dónde | Comando | Paso |
|---|---|---|
| Instalación | `uv sync --locked` | 1 |
| Instalación | `python -m uv …` (agregado en este PR) | 18 |
| Grupo A | `python -m infer.descarga` | 2 |
| Grupo A | `python -m conjunto verificar --sha256 …` | 4 |
| Grupo A | `python -m infer` con un JPEG | 5 |
| Grupo A | `python -m infer` con una secuencia | 6 |
| Grupo A | "Métricas del conjunto completo" (agregado en este PR) | 6, 15, 16 |
| Grupo A | `python -m metricas` | 7 |
| Grupo A | `python -m bench` | 8 |
| General | `pytest`, `ruff check`, `ruff format --check` | 12 |
| General | `python -m contrato` | 6, 17 |
| General | `python -m trazabilidad construir`, `recalcular`, `cuadro` | 14 |
| General | `python -m bench.limites` | 9 |
| General | `python -m conjunto manifiesto`, `verificar`, `hojas` | 4, 17 |
| General | `python -m control` | 14 |
| General | `casos/runner.py` | 17 |
| General | `python -m captura` | **No observado:** necesita el carro encendido y su stream por red, y el ensayo es sin red. Las secuencias ya capturadas se verificaron en el paso 4 |

Las secciones 1 a 5 del grupo B son de B; los comandos que comparten con la tabla general (`contrato`,
`control`, `runner`) se observaron arriba, y el resto lo cubre la reproducción conjunta de B3.

## Fallos y qué se hizo

| # | Fallo | Qué se hizo |
|---|---|---|
| 1 | Con el mismo `--run-id` en la misma carpeta, solo S01 se infiere y las otras 7 salen con código 2 (`el JSONL o manifiesto del run ya existe`): `infer` guarda `<run-id>.infer-run.json` junto a la salida. El README no decía cómo armar la corrida de las 8 secuencias que pide `metricas` | **Corregido.** Nueva subsección "Métricas del conjunto completo" en la sección del grupo A: una carpeta por secuencia, mismo `--run-id`, tiempos tomados del manifiesto, unión con `cat` y la llamada final a `metricas`. El bloque se copió del README y se corrió tal cual (paso 16) |
| 2 | En PowerShell 5.1, `>` y `Set-Content -Encoding UTF8` escriben el archivo unido con BOM, y `metricas` lo rechaza (código 2, `Unexpected UTF-8 BOM`) | **Corregido.** El README lo avisa y da una línea de PowerShell sin BOM (`[IO.File]::WriteAllLines`), probada con `metricas` (paso 15) |
| 3 | `pip install uv` sin permisos de administrador deja `uv.exe` fuera del `PATH` en Windows, y `uv` no se reconoce | **Corregido.** La instalación dice que `python -m uv` hace lo mismo (paso 18) |
| 4 | La tabla general de comandos tenía `<ruta local>/yolo11n.pt`, `pesos=<yolo11n.pt>` y `anotaciones.jsonl` sin `datos/`, y no decía cómo bajar los pesos (Karen, en la revisión de #87) | **Corregido.** Esas filas remiten a los comandos completos de la sección del grupo A, que sí están probados |
| 5 | "Traspasos" decía S9 y S10; las carpetas son S09 y S10 (Karen) | **Corregido** |
| 6 | "Inferir una secuencia" no traía los tiempos (Karen, opcional) | **Corregido.** Ahora trae los 12 `--capture-ms` de S01, los mismos del paso 6 |
| 7 | `bench` sale con código 1 porque la laptop estaba en batería | **Declarado.** Es el comportamiento documentado en `mediciones/README.md`; las 100 mediciones salieron sin fallos. Este ensayo no reemplaza las corridas oficiales `final-1` a `final-3` |
| 8 | En el repo no hay una corrida publicada de detecciones y métricas de S01–S08: E6 se puede regenerar con el README, pero no se compara contra un resultado subido | **Declarado** para PM A y A3. Las salidas de este ensayo quedan en `p5-17-ensayo/salidas/` como referencia, no como resultado oficial |

## Criterios de #19

- **Todo corre sin pedir ayuda, sin secretos y sin tokens:** sí, con las correcciones 1 a 6.
- **Los fallos quedan corregidos o declarados:** sí; los ocho de la tabla de arriba.
- **Modelo, clases, transformaciones, datos congelados, métricas y benchmark auditables desde el README:**
  se pudo seguir cada uno desde el README, con sus registros en `p5-17-ensayo/`; la validación final es del
  PM A.
