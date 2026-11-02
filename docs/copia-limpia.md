# Copia limpia (T19)

Ensayo final: clonar el repo desde cero en una carpeta nueva, instalar **siguiendo solo el README** y
correr, sin red, lo mismo que correrá el evaluador. Todo es offline, en CPU y **sin mover motores**.

> **Resultado (2026-11-02):** desde un clon nuevo de `main` (`58bce1e`), sin red después de instalar,
> corren el contrato, el recorrido de una secuencia real hasta el adaptador virtual, los 10 casos
> (**3 de 10 pasan**, como dice el README: C1–C7 esperan sus entradas reales de T20) y el cambio
> deliberado de una expectativa (falla, y al restaurarla vuelve a pasar). Ninguna prueba ni comando
> intentó conectarse a la red. Lo que se encontró está en [Problemas](#problemas-encontrados):
> 4 corregidos en esta rama y 5 anotados.

## Máquina

| Qué | Valor |
|---|---|
| Fecha | 2026-11-02, de 16:35 a 17:10 (UTC−6) |
| Equipo | Laptop Windows 11 Home 10.0.26200, Intel Core i7-1255U (10 núcleos, 12 hilos), 15.7 GB de RAM |
| Energía | **Con batería, al 10 % y descargando**; CPU al 57 % de carga por otros programas (Discord, Chrome, VS Code, VPN) |
| Terminal | Git Bash; el paso 4b también en PowerShell 5.1 |
| uv | 0.12.23 (el README pide 0.12.13; con la 0.12.23 `uv sync --locked` funciona igual) |
| Python | 3.12.10 del sistema; `.python-version` pide 3.12 |
| Repo | `git clone https://github.com/karenelizabg/Proyecto05-MLOPS.git`, `main` en `58bce1e` (#73) |
| Pesos | `yolo11n.pt` de la release v8.3.0 de Ultralytics, 5 613 764 B, SHA-256 `0ebbc80d…6ee1` (el de `config/detector.json`), fuera del repo |

## Cómo se quitó la red

Con red solo se hicieron `git clone`, `uv sync --locked` y la descarga de los pesos. Después:

- `UV_OFFLINE=1`: uv no puede descargar nada.
- Un `sitecustomize.py` **fuera del repo**, cargado con `PYTHONPATH`. Hace fallar toda conexión y
  resolución de nombres que no sea a la propia máquina (`127.0.0.1`, `localhost`), igual que con el
  Wi-Fi apagado, y anota cada intento. Antes de empezar se comprobó que `urllib` a `github.com`
  falla.
- **0 intentos anotados** en todo el ensayo, pytest incluido.

No se apagó el Wi-Fi del equipo: la sesión de trabajo necesitaba la red. Esa prueba queda en
[Qué no se probó](#qué-no-se-probó).

Para que la instalación no aprovechara lo ya descargado en esta laptop, `uv sync` usó una caché de uv
**vacía** (`UV_CACHE_DIR` en una carpeta nueva).

## Comandos y resultados

Todos desde la raíz del clon. `<pesos>` es la ruta local de `yolo11n.pt`.

| # | Comando | Sale | Resultado |
|---|---|---|---|
| 0 | `uv sync --locked` (con red, caché vacía) | 0 | 1 min 51 s; 890 MB de descargas en la caché. |
| 1 | `uv run pytest -q` | 1 | **1110 pasan**, 17 se saltan, 2 fallan (problema 6). |
| 1b | `P5_05_YOLO11N_PT=<pesos> uv run pytest -q -rs` | 1 | **1125 pasan**, 2 se saltan (permisos POSIX, no aplican en Windows), las mismas 2 fallan. |
| 2 | `uv run ruff check .` · `uv run ruff format --check .` | 0 · 0 | `All checks passed!` · `112 files already formatted`. |
| 3 | `uv run python -m contrato config/contrato/ejemplos/flujo.jsonl` | 0 | `OK (5 eventos)`, igual que el README. |
| 4 | `uv run python -m control --entrada config/contrato/ejemplos/flujo.jsonl --config config/control/ --salida resultados/ejemplo-01/` | 0 | `5 eventos, 6 comandos, 2 errores`, igual que el README, y los 5 archivos de su tabla. |
| 5 | `uv run python -m infer --input datos/pruebas-b/S09 --weights <pesos> --output resultados/s09/detector.jsonl --run-id s09 --sequence-id S09 --capture-ms 0 … --capture-ms 2531` | 0 | `12 cuadros, 0 errores`; `cup` (41) en los 12, confianza de 0.76 a 0.93. |
| 6 | `uv run python -m contrato resultados/s09/detector.jsonl` | 0 | `OK (12 eventos)`. |
| 7 | `uv run python -m control --entrada resultados/s09/detector.jsonl --config config/control/ --salida resultados/s09/` | 0 | `12 eventos, 13 comandos, 12 errores`: **STOP 12 por `cuadro_viejo`** (problema 5). |
| 8 | `uv run python -m control.traza --salida resultados/s09/` | 0 | Los 12 cuadros llegan a su decisión y su comando; `run.json` con rutas relativas. |
| 9 | `uv run python casos/runner.py` | 1 | **3 de 10**: C8, C9 y C10 PASA; C1–C7 FALLA con "falta entrada.jsonl". Es lo que dice el README. |
| 10a | En `casos/C8/expectativa.yaml`, tramo `hueco`: `acciones_permitidas: [AVANZAR]`; luego `uv run pytest -q tests/test_expectativas.py` | 1 | 4 fallan, entre ellas `test_las_expectativas_estan_congeladas` (el hash). |
| 10b | Con el mismo cambio: `uv run python casos/runner.py C8 --salida <carpeta temporal>` | 1 | `C8 armada 2/3 FALLA` · `hueco: ninguna orden con AVANZAR en el plazo de 600 ms`, el motivo del README. |
| 10c | `git checkout -- casos/C8/expectativa.yaml`, y otra vez 10a y 10b | 0 · 0 | 78 pasan; `C8 armada 3/3 PASA`. `git status` sin cambios en `casos/`. |
| 10d | El paso 4b del README en PowerShell (`Copy-Item` a `$env:TEMP\casos-copia`, mismo cambio, runner) | 1 | `C8 armada 2/3 FALLA` con el mismo motivo. |
| 11 | El paso 5 otra vez, con la misma salida | 2 | `File exists`: `infer` no sobrescribe; el archivo queda igual. |

El README de `main` no tenía cómo correr una secuencia real (pasos 5 a 8): solo la fila "Inferir" de la
tabla, que remite a `config/DETECTOR.md`. Los `--capture-ms` salen de `datos/pruebas-b/S09/captura.jsonl`,
como dice `config/DETECTOR.md`. Esta rama agrega esos pasos al README (sección 5 del grupo B).

También se buscó en todo lo versionado: rutas de una máquina (`C:\Users\…`, `/home/…`, `/Users/…`),
llaves (`.env`, `.pem`, `.key`, tokens) y enlaces relativos rotos en los 30 `.md`. Solo aparecieron las
rutas del problema 1. Las credenciales de `tests/test_captura.py` son datos falsos de una prueba que
comprueba que no se impriman.

## Problemas encontrados

### Corregidos en esta rama

1. **Rutas de una máquina en `resultados/recorrido-real/izq/run.json` y `der/run.json`** (T16). Guardaban
   la ruta absoluta de la carpeta temporal donde se corrió `control`. Se volvió a correr `control` sobre el
   mismo `detector.jsonl` con la ruta relativa del repo: solo cambia esa línea, y el SHA-256 de la entrada
   es el mismo. `tests/test_copia_limpia.py` lo revisa ahora en todo lo versionado.
2. **CRLF en Windows.** `.gitattributes` pide LF, pero `control`, el adaptador virtual, el supervisor y el
   runner escribían CRLF en Windows. Después de correr los casos, `git status` marcaba 26 archivos de
   `resultados/casos/` como modificados aunque el contenido era el mismo. Ahora escriben con
   `newline="\n"`. Lo prueba `test_control_y_runner_escriben_lf_tambien_en_windows`.
3. **El README no decía de dónde sacar los pesos ni cómo correr una secuencia real.** La URL y el SHA-256
   estaban repartidos en `modelo/experimentos-publicados/` y `resultados/P5-05-REVISION-A3.md`. Se agregó
   la sección "5. Recorrido con una secuencia real" con la descarga, cómo comprobar el hash y los cuatro
   comandos. La descarga automatizada de los pesos sigue en PEND-11 (grupo A, P5-07).
4. **15 pruebas se saltaban en silencio sin `P5_05_YOLO11N_PT`.** Solo lo explicaba
   `resultados/P5-05-ACEPTACION.md`. El README ahora dice cómo definirla.

### Anotados (no se corrigen aquí)

5. **S09 terminó en STOP 12 por `cuadro_viejo`.** Cada inferencia tardó de 375 a 860 ms, y los cuadros
   llegaron con 563 a 4063 ms de edad (el límite es 500). No es la copia limpia: la misma corrida en la
   copia usada en T16, que el 2026-11-01 dio de 79 a 188 ms, dio ahora de 516 a 3563 ms. La laptop estaba
   con batería al 10 % y la CPU ocupada. B hizo lo correcto (rechazar cuadros viejos), y se dejó la
   primera corrida. Va como dato para P5-16: las mediciones de `mediciones/` se hicieron conectadas a la
   corriente.
6. **2 pruebas de A fallan en Windows:** `test_benchmark_rechaza_enlace_final_sin_tocar_destino[True]` y
   `test_enlace_final_de_salida_no_se_sobrescribe[True]` (P5-05/P5-15). Prueban enlaces simbólicos, que
   en Windows piden permisos especiales. También fallan en la copia de trabajo de `main`. Las ve el grupo A.
7. **Acentos rotos al redirigir la salida a un archivo en Windows.** `python casos/runner.py > archivo.txt`
   o `python -m control.traza … > traza.txt` escriben en cp1252, y Git Bash muestra `Por qu�`. En la
   terminal se ve bien. Solución: `PYTHONIOENCODING=utf-8` antes del comando. En Windows, las rutas
   también salen con `\` (`config\contrato\...`) donde el README muestra `/`.
8. **Versión de uv.** El README pide 0.12.13 y aquí había 0.12.23. Funcionó igual; quien no tenga uv
   instala la del README.
9. **C1–C7 sin entrada.** Es lo esperado hasta T20 (entradas reales desde `datos-evaluacion-v1` y
   `config-detector-v1`). Cuando lleguen, cambia el "3 de 10" del README y `tests/test_readme_b.py` avisa.

## Qué no se probó

- [ ] **El Wi-Fi apagado de verdad.** La red se quitó por software (ver arriba). Para repetirlo: clonar,
  `uv sync --locked`, bajar los pesos, **apagar el Wi-Fi** y correr la tabla desde el paso 1.
- [ ] **Conectada a la corriente y sin otros programas abiertos.** Con eso, S09 debería dar `GIRAR_DER 12`,
  como en `docs/recorrido-real.md`.
- [ ] macOS y Linux. En Linux las 2 pruebas del problema 6 deberían pasar.
- [ ] Instalación con `pip` desde la copia limpia: se probó en T18.
