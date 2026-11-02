# P5-06 · borrador de guía para la validación independiente de Andrea en Windows

**Estado:** borrador local para revisión; no constituye evidencia de ejecución en Windows ni aprobación de P5-06. Basado en `P5-06-DISENO-Y-ACEPTACION.md`, `P5-05-REVISION-A3.md`, los scripts y las pruebas de esta rama. Usar PowerShell desde la raíz de un clon limpio del PR #86. No procesar S01–S08 ni `datos/cuadros/`.

## 1. Preparación y prerrequisitos

Windows x86_64, Git, espacio para PyTorch y Python **3.12** (`pyproject.toml`, `.python-version`). Instalar dependencias con `uv.lock`, sin cambiar versiones: Ultralytics 8.3.0, PyTorch 2.9.0, Torchvision 0.24.0, OpenCV 4.11.0.86 y NumPy 1.26.4. Registrar versión de Windows, CPU, RAM, Python, `uv` y paquetes. La preparación de `uv` en Windows está detallada en `P5-05-REVISION-A3.md`; si falta, usar ese procedimiento antes de seguir.

```powershell
$Repo = Join-Path $HOME 'Proyecto05-MLOPS-P5-06'
git clone --branch p5-06-errores-detector --single-branch https://github.com/karenelizabg/Proyecto05-MLOPS.git $Repo
Set-Location $Repo
git rev-parse HEAD
git status --short
uv --version
uv python install 3.12
uv sync --locked
$Python = Join-Path (Get-Location).Path '.venv\Scripts\python.exe'
& $Python --version
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture,@{Name='RAM_GiB';Expression={[math]::Round($_.TotalVisibleMemorySize / 1MB, 2)}}
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
& $Python -c 'import sys, importlib.metadata as m; print(sys.version); print({p:m.version(p) for p in ("ultralytics","torch","torchvision","opencv-python","numpy","pillow")})'
```

Registrar el HEAD realmente revisado y comparar con el commit del PR elegido para la revisión. Si el lockfile no instala, detenerse y guardar el error; no editar `uv.lock` para continuar.

El checkpoint está **fuera del repositorio**. `P5-05-REVISION-A3.md` documenta la descarga manual desde la release oficial `v8.3.0` de Ultralytics y su verificación. Reutilizar un checkpoint ya verificado o ejecutar este bloque de ese procedimiento; detenerse si falla el tamaño o el hash.

```powershell
$WeightsDir = Join-Path $env:LOCALAPPDATA 'P5-05'
New-Item -ItemType Directory -Force -Path $WeightsDir | Out-Null
$Weights = Join-Path $WeightsDir 'yolo11n.pt'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt' -OutFile $Weights
$Expected = '0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1'
$Actual = (Get-FileHash -LiteralPath $Weights -Algorithm SHA256).Hash.ToLowerInvariant()
$Size = (Get-Item -LiteralPath $Weights).Length
if ($Actual -ne $Expected -or $Size -ne 5613764) { throw "Checkpoint incorrecto: SHA=$Actual; bytes=$Size" }
"Checkpoint verificado: SHA=$Actual; bytes=$Size"
```

Si el archivo ya existe, omitir la descarga y ejecutar solamente las líneas de verificación. `config/detector.json` debe permanecer intacto; su configuración efectiva debe dar `6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08` y `torch_threads=2`. `config/control/plazos.yaml` debe conservar `detector_timeout_ms: 500` y `max_frame_age_ms: 500`; registrar su SHA-256 por separado.

```powershell
& $Python -c 'from infer.config import cargar_config_detector; c=cargar_config_detector(); print(c.config_sha256, c.torch_threads, c.expected_model_sha256)'
(Get-FileHash -LiteralPath '.\config\control\plazos.yaml' -Algorithm SHA256).Hash.ToLowerInvariant()
```

## 2. Comprobaciones funcionales, separadas del benchmark

El script de comparación funcional usa el JPEG versionado `docs/carro/objeto_taza_centro_cerca.jpg` (SHA-256 `670fec5473ceda61b5a6283711596d610d75577dfb1bc9d5ffc8de52c1e9cbcc`), con detección no vacía y referencia P5-05 `ensayo-0012`. Elegir un destino **nuevo** para no sobrescribir evidencias. El script verifica ambos caminos, contrato v1, dimensiones, IDs, paridad exacta en el mismo host/runtime, READY con hashes y dos hilos y cierre limpio.

```powershell
(Get-FileHash -LiteralPath '.\docs\carro\objeto_taza_centro_cerca.jpg' -Algorithm SHA256).Hash.ToLowerInvariant()
& $Python .\resultados\p5-06-validacion-detecciones.py --weights $Weights --output (Join-Path $Repo 'resultados\p5-06-validacion-detecciones-windows-andrea')
& $Python -m contrato .\resultados\p5-06-validacion-detecciones-windows-andrea\un_proceso.jsonl .\resultados\p5-06-validacion-detecciones-windows-andrea\supervisado.jsonl
```

Revisar `comparacion.json`, ambos JSONL y `p506-taza-supervisado.infer-run.json`: `generaciones` debe tener READY con SHA-256 de modelo/configuración y `torch_threads=2`, y `cierre_limpio` debe ser verdadero. El script detiene la validación si encuentra diferencias. Registrar diferencias entre Windows y P5-05 sin presumir identidad exacta entre plataformas.

La prueba con dos JPEG sintéticos y detecciones vacías tiene otro script y destino nuevo:

```powershell
& $Python .\resultados\p5-06-validacion-real.py --weights $Weights --output (Join-Path $Repo 'resultados\p5-06-validacion-real-windows-andrea')
& $Python -m contrato .\resultados\p5-06-validacion-real-windows-andrea\un_proceso.jsonl .\resultados\p5-06-validacion-real-windows-andrea\supervisado.jsonl
```

Las pruebas automatizadas ejercitan timeout con trabajador bloqueado, reinicio exitoso y fallido, clasificación de pendientes, prioridad error > stale > ok, ausencia de duplicados, hashes/hilos, contrato y `detector_timeout` → STOP de B. Usan predictores simulados para las fallas; **no son una medición oficial de 500–600 ms de publicación**.

```powershell
& $Python -m pytest -q tests/test_infer_trabajador.py tests/test_infer_benchmark.py tests/test_infer_preflight.py tests/test_infer_control_integracion.py
& $Python -m pytest -q
```

Conservar salida completa, número de pruebas y fallos. Si un test falla en Windows, registrar el fallo y el entorno antes de cambiar código. El manifiesto funcional y los JSONL dan evidencia de spawn, calentamiento, READY, plazos, hashes, eventos únicos y cierre; las pruebas cubren fallas y reinicios simulados.

La herramienta separada de timeout usa un predictor simulado con `spawn`. Ejecutar cada comando
con un directorio **nuevo**; conservar sus muestras, JSONL y manifiestos. El segundo comando
inyecta un fallo de reinicio, sin tocar el checkpoint real. La herramienta termina con código 0
si la comprobación del fallo esperado fue correcta; `muestras.jsonl` registra que la política
del CLI devolvió un código distinto de cero con el resultado de ese run inyectado.

```powershell
& $Python .\resultados\p5-06-validacion-timeout.py --output (Join-Path $Repo 'resultados\p5-06-timeout-windows-andrea') --intentos 50
& $Python .\resultados\p5-06-validacion-timeout.py --output (Join-Path $Repo 'resultados\p5-06-terminal-windows-andrea') --intentos 1 --terminal
& $Python -m contrato (Join-Path $Repo 'resultados\p5-06-terminal-windows-andrea\timeout-0001.jsonl')
```

La evidencia Mac existente de este recorrido se conserva en
`resultados/p5-06-timeout-simulado-mac-2026-11-02/`, con 50/50 publicaciones entre 500 y 600 ms,
50/50 recuperaciones simuladas con READY y duración de 503.0183750204742 a
525.7063750177622 ms. Andrea debe registrar sus propios resultados de Windows; no se trasladan
estas duraciones ni los READY simulados a la validación del checkpoint oficial. Revisar la
metodología y los riesgos de `flush` en `resultados/P5-06-VALIDACION-TIMEOUT.md`.

## 3. Serie oficial de latencia y reinicio

Andrea debe intervenir para verificar que la laptop está en **AC**, el ahorro de batería está **desactivado**, OneDrive y VS Code están **cerrados**, y no hay carga interferente relevante. Registrar el estado observado y los procesos/carga. `src/infer/preflight.py` consulta `GetSystemPowerStatus` (`ACLineStatus`, `SystemStatusFlag`) y `tasklist`; el script bloquea la serie si cualquier condición es falsa o no verificable y guarda `benchmark.preflight.json` junto al `benchmark.json` propuesto. No cambiar configuración para mejorar tiempos.

El comando siguiente usa la interfaz actual de `resultados/p5-06-benchmark.py`. **Es una instrucción propuesta; no se ejecutó aquí.** Usar un archivo de salida nuevo, en una carpeta controlada por Andrea. Ejecutarlo una sola vez por máquina; ante fallo conservar la evidencia parcial y detenerse, sin repetir selectivamente por cercanía al límite.

```powershell
& $Python .\resultados\p5-06-benchmark.py --weights $Weights --output (Join-Path $Repo 'resultados\p5-06-benchmark-windows-andrea\benchmark.json') --responsable Andrea
```

El script verifica checkpoint (5 613 764 bytes y SHA aprobado), configuración, dos hilos y JPEG fijo; prepara ambas rutas y mide **10 pares control→supervisado de calentamiento excluidos y 50 pares medidos**. Control: desde antes de decodificar el JPEG hasta retorno validado de `_evento_cuadro`. Supervisado: desde antes de `solicitar` en el padre hasta recibir respuesta completa verificada; incluye supervisión, IPC, lectura, inferencia y validación. No incluye publicación JSONL, carga ni reinicio. Conserva cada muestra, p50 como mediana y p95 con `numpy.percentile(method="linear")`, diferencias absoluta/porcentual, máximo y solicitudes normales superiores a 500 ms. Compara cada resultado con P5-05 en el mismo JPEG.

Después mide por separado **10 reinicios directos excluidos y 50 reinicios directos medidos** mediante `detener()`/`iniciar()`, desde antes de detener hasta READY verificado. Guarda duración total y fases de detención, coordinación, creación/spawn, arranque, carga/verificación, calentamiento y entrega de READY, con solapamientos. Estos reinicios **no son provocados por timeout**. Si la serie falla, el JSON contiene fase, índice y muestras parciales; no presentar percentiles incompletos como resultado. El reinicio no tiene umbral numérico; comunicar duraciones a P5-16.

Aplicar todos los límites sobre cifras sin redondear: `p50_supervisado − p50_control ≤ 5 ms`, `p95_supervisado − p95_control ≤ 10 ms`, `p95_supervisado ≤ 150 ms`, `máximo_supervisado ≤ 200 ms`, cero solicitudes normales mayores que 500 ms. La validación decisiva es la de Andrea en Windows.

## 4. Evidencia por entregar

- Commit revisado; Windows/CPU/RAM; versiones de Python, `uv`, PyTorch, Ultralytics, Torchvision, OpenCV, NumPy; estado de AC/ahorro, OneDrive, VS Code, carga del host y cualquier desviación.
- Ubicación externa, tamaño y SHA-256 del checkpoint; SHA-256 efectivo de configuración, SHA-256 de `plazos.yaml`, valor de los dos plazos y del JPEG permitido.
- De cada validación funcional: `comparacion.json` o `validacion.json`, ambos JSONL, JPEG sintéticos cuando corresponda, manifiesto `.infer-run.json`, salida de `python -m contrato`, resultado de pytest y cualquier error. Registrar READY, hilos, hashes, IDs, dimensiones, estados, ausencia de duplicados y cierre.
- De la serie oficial: `benchmark.json`, `benchmark.preflight.json`, las 50 muestras de cada ruta, 10 calentamientos por ruta, 50 reinicios medidos y 10 excluidos, fases, percentiles sin redondear, fallos/descartes y salida de terminal. Guardar evidencia parcial si aborta. Indicar expresamente que la medición de reinicio fue directa.
- Para la validación separada de timeout forzado: `muestras.jsonl`, `resumen.json`, JSONL y manifiesto de cada intento, marcas monotónicas de inicio de solicitud y publicación del evento, duración individual, `frame_id`, READY, continuidad y resultado de contrato. Usar `resultados/P5-06-VALIDACION-TIMEOUT.md`; el benchmark normal no produce estos datos.

No repetir ni reemplazar `resultados/p5-06-benchmark-mac-2026-11-01/`, `p5-06-validacion-real/` ni `p5-06-validacion-detecciones/`: son evidencia histórica del PR. Los nuevos destinos deben ser únicos.

## 5. Procedimientos aún insuficientes para aceptación completa

1. `resultados/P5-06-VALIDACION-TIMEOUT.md` describe la herramienta separada que provoca 50 timeouts y recuperaciones con trabajador simulado, mide la publicación después del `flush` y comprueba el fallo terminal. Andrea debe ejecutarla de forma independiente en Windows; sus resultados no se infieren de la serie Mac. `flush` no demuestra durabilidad de disco como `fsync`, y una escritura fallida no permite afirmar que se publicó el evento.
2. Los 50 reinicios del benchmark normal siguen siendo directos. Los resultados de la herramienta de timeout, las pruebas de cuadros pendientes y el benchmark deben reportarse por separado. El trabajador simulado declara los hashes esperados; la verificación criptográfica y el calentamiento con checkpoint real pertenecen a la validación funcional aparte.
3. No hay procedimiento que induzca un fallo terminal **del modelo real** en Windows sin alterar pesos o configuración. El caso se verifica con fábrica simulada y con la política de salida del CLI; no atribuirle una ejecución real del checkpoint en fallo.
4. El benchmark solo guarda `preflight` del sistema y `tasklist` para procesos bloqueantes; Andrea debe registrar por separado la carga/procesos que juzgue interferentes y cualquier desviación. La serie Mac anterior se ejecutó en bloques y permanece como referencia histórica, no como réplica de este procedimiento.
