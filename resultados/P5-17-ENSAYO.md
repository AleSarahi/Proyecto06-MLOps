# P5-17 · Ensayo de reproducción de la parte A desde una copia limpia

Ensayo previo a la reproducción conjunta final, que hace B3 con el equipo B. Se siguió solo el README de
`main`, sin pedir ayuda al equipo, sin secretos ni tokens.

| Qué | Valor |
|---|---|
| Quién | Andrea Arevalo (A2) |
| Cuándo | 2026-11-02, de 23:08 a 23:35, hora del centro de México (UTC−6) |
| Commit | `f06e6f48032afaf7d9d3f2938fd2e8ed59cb4394` (`main` con #86, #87, #92 y #93) |
| Máquina | Laptop con Windows 11 Home Single Language 10.0.26200, x64; AMD Ryzen 7 8845HS (8 núcleos, 16 hilos); 62 GB de RAM; solo CPU |
| Terminales | PowerShell 5.1 y Git Bash (git 2.46.0) |
| uv | 0.12.13, la misma del CI |
| Copia | `git clone` nuevo en una carpeta vacía, sin `.venv` ni `modelo/descargas/` |

**Sin red:** después de `uv sync --locked` y de bajar los pesos, todo se corrió con `UV_OFFLINE=1` y con
`HTTP_PROXY`, `HTTPS_PROXY` y `ALL_PROXY` apuntando a `http://127.0.0.1:9`, un puerto donde no escucha nada.
Antes de seguir se comprobó que una petición a `https://github.com` fallaba (`URLError`). No se desconectó el
Wi-Fi: la red se cortó para uv y Python, no para todo el equipo.

## Pasos

| # | Paso (README) | Resultado | Estado |
|---|---|---|---|
| 1 | `uv sync --locked` (con red) | Entorno creado, código 0 | Observado |
| 2 | `uv run --locked python -m infer.descarga` (con red) | `descargado, 5613764 B, SHA-256 0ebbc80d…6ee1 OK` | Observado |
| 3 | `conjunto verificar --sha256 8a75e271…` | 107 cuadros, 8 secuencias, `OK con 0 excepciones` | Observado |
| 4 | Hashes de "Versión de entrega" | Manifiesto `8a75e271…`, anotaciones `7e842784…`, pesos `0ebbc80d…` y `config_sha256` `6428a259…`: los cuatro coinciden. `datos/` y `config/detector.json` son iguales a los tags `datos-evaluacion-v1` y `config-detector-v1` | Observado |
| 5 | `infer` con JPEG elegidos por quien verifica | `S05_f0001` (botellas 0.632 y 0.439, taza 0.851), `S07_f0003` (taza 0.330) y `S01_f0001` (sin detecciones, `ok`). Contrato OK en los tres; coinciden con `docs/casos-reales.md` | Observado |
| 6 | `infer` con S01–S08 y los `t_relativo_ms` del manifiesto | 107 cuadros, 0 errores, contrato OK, todos `ok`. **Falló al primer intento** (fallo 1) | Observado |
| 7 | `metricas` con las 8 secuencias | TP=71, FP=0, FN=24; P=1.0000, R=0.7474, F1=0.8554; criterio 1.4: 5 de 6; sin advertencias | Observado |
| 8 | `bench` (Git Bash, `S0*` se expande) | 100 mediciones, 0 fallos; p50 80.64 ms, p95 93.22 ms, máximo 98.56 ms. Código 1 por la advertencia de batería | Observado, con advertencia |
| 9 | `bench.limites` con `final-1` a `final-3` y `final-sobrecosto` | Los cinco plazos cumplen; `contraste.json` y `contraste.md` son idénticos byte a byte a `mediciones/final-contraste/` | Observado |
| 10 | `control` y `trazabilidad construir`, `recalcular` y `cuadro` | 107 eventos, 108 comandos, 0 errores; la trazabilidad da las mismas cifras que `metricas`; `recalcular` coincide con `resumen.json`; `cuadro S05_f0001` muestra del evento al comando | Observado |
| 11 | `ruff check`, `ruff format --check` y `pytest` con `P5_05_YOLO11N_PT` | Ruff limpio; 1280 pasan, 19 saltadas, 0 fallan | Observado |
| 12 | Enlaces y rutas absolutas en los archivos del repo | 0 enlaces rotos (relativos y anclas, en todos los `.md`); 0 rutas personales en el texto ni dentro de los 3 ZIP de `resultados/` | Observado |
| 13 | Reproducción conjunta con el equipo B | La hace B3 después de este ensayo | No observado |

Las 19 pruebas saltadas son propias de Windows: crear enlaces simbólicos (pide modo de desarrollador,
`WinError 1314`), FIFO y permisos POSIX. Las que usan los pesos reales sí corrieron.
`test_frame_id_neutral_en_directorio` y `test_directorio_reproduce_tiempos_explicitos_y_ids_unicos`, que
fallaban de forma intermitente en Windows antes de #86, pasaron 20 de 20 veces.

## Fallos y qué se hizo

| # | Fallo | Qué se hizo |
|---|---|---|
| 1 | Con el mismo `--run-id` en la misma carpeta, solo S01 se infiere y las otras 7 salen con código 2 (`el JSONL o manifiesto del run ya existe`): `infer` guarda `<run-id>.infer-run.json` junto a la salida. El README no decía cómo armar la corrida de las 8 secuencias que pide `metricas` | **Corregido.** Nueva subsección "Métricas del conjunto completo" en la sección del grupo A: una carpeta por secuencia, mismo `--run-id`, tiempos tomados del manifiesto y unión con `cat`. El bloque se copió del README y se corrió tal cual: mismas 107 detecciones que el ensayo |
| 2 | En PowerShell 5.1, `>` y `Set-Content -Encoding UTF8` escriben el archivo unido con BOM, y `metricas` lo rechaza (código 2, `Unexpected UTF-8 BOM`) | **Corregido.** El README lo avisa y da una línea de PowerShell sin BOM (`[IO.File]::WriteAllLines`), probada con `metricas` |
| 3 | `pip install uv` sin permisos de administrador deja `uv.exe` fuera del `PATH` en Windows, y `uv` no se reconoce | **Corregido.** La instalación dice que `python -m uv` hace lo mismo (probado con `sync`, `run` y `conjunto verificar`) |
| 4 | La tabla general de comandos tenía `<ruta local>/yolo11n.pt`, `pesos=<yolo11n.pt>` y `anotaciones.jsonl` sin `datos/`, y no decía cómo bajar los pesos (Karen, en la revisión de #87) | **Corregido.** Esas filas remiten a los comandos completos de la sección del grupo A, que sí están probados |
| 5 | "Traspasos" decía S9 y S10; las carpetas son S09 y S10 (Karen) | **Corregido** |
| 6 | "Inferir una secuencia" no traía los tiempos (Karen, opcional) | **Corregido.** Ahora trae los 12 `--capture-ms` de S01 |
| 7 | `bench` sale con código 1 porque la laptop estaba en batería | **Declarado.** Es el comportamiento documentado en `mediciones/README.md`; las 100 mediciones salieron sin fallos. Este ensayo no reemplaza las corridas oficiales `final-1` a `final-3` |
| 8 | En el repo no hay una corrida publicada de detecciones y métricas de S01–S08: E6 se puede regenerar con el README, pero no se compara contra un resultado subido | **Declarado** para PM A y A3 |

## Criterios de #19

- **Todo corre sin pedir ayuda, sin secretos y sin tokens:** sí, con las correcciones 1 a 6.
- **Los fallos quedan corregidos o declarados:** sí; los ocho de la tabla de arriba.
- **Modelo, clases, transformaciones, datos congelados, métricas y benchmark auditables desde el README:**
  se pudo seguir cada uno desde el README; la validación final es del PM A.
