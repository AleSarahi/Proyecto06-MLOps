# P5-06 · guía propuesta para la validación independiente de Andrea en Windows

**Estado:** propuesta para la revalidación del reloj; esta versión de la guía no constituye evidencia de ejecución en Windows ni aprobación de P5-06. El commit `016d1867b886a1bc5d8ee6ffd2233d49df9b4ad8` es una base histórica del PR #86. Andy validó funcionalmente el commit anterior al cambio de reloj `4fefb4adddb0e9d9a04379b7e5589a0e6d6758ff`; su ZIP íntegro y desviaciones se documentan en `p5-06-validacion-windows-4fefb4a-2026-11-02/README.md`. La corrección del reloj tendrá otro commit, aún pendiente; Andrea debe anotar el SHA completo del commit que efectivamente valide en cada ejecución. Basada en `P5-06-DISENO-Y-ACEPTACION.md`, `P5-05-REVISION-A3.md`, los scripts y las pruebas de la rama. Usar PowerShell desde la raíz de un clon nuevo. No procesar S01–S08 ni `datos/cuadros/`.

## 1. Preparación y prerrequisitos

Windows x86_64, Git, espacio para PyTorch y Python **3.12** (`pyproject.toml`, `.python-version`). Instalar dependencias con `uv.lock`, sin cambiar versiones: Ultralytics 8.3.0, PyTorch 2.9.0, Torchvision 0.24.0, OpenCV 4.11.0.86 y NumPy 1.26.4. Registrar versión de Windows, CPU, RAM, Python, `uv` y paquetes. Si falta `uv`, usar el instalador PowerShell documentado en `P5-05-REVISION-A3.md` y volver a abrir PowerShell si el PATH no se actualiza. Se requiere conexión para clonar, instalar dependencias y obtener el checkpoint; la inferencia posterior usa archivos locales.

Instalador de `uv` **solo si aún no está instalado**, tal como figura en P5-05:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/0.13.6/install.ps1 | iex"
```

```powershell
$Repo = Join-Path $HOME 'Proyecto05-MLOPS-P5-06'
git clone --branch p5-06-errores-detector --single-branch https://github.com/karenelizabg/Proyecto05-MLOPS.git $Repo
Set-Location $Repo
$ExpectedHead = Read-Host 'SHA completo del commit de P5-06 que se va a validar (Andy: 4fefb4a; reloj: pendiente)'
if ($ExpectedHead -notmatch '^[0-9a-f]{40}$') { throw 'Se requiere un SHA completo de 40 caracteres hexadecimales' }
git checkout --detach $ExpectedHead
$Head = (git rev-parse HEAD).Trim()
if ($Head -ne $ExpectedHead) { throw "HEAD distinto al commit aprobado: $Head" }
git status --short
uv --version
uv python install 3.12
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw 'uv sync --locked falló' }
$Python = Join-Path (Get-Location).Path '.venv\Scripts\python.exe'
& $Python --version
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture,@{Name='RAM_GiB';Expression={[math]::Round($_.TotalVisibleMemorySize / 1MB, 2)}}
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
$PythonCode = @'
import sys
import importlib.metadata as m
print(sys.version)
print({p: m.version(p) for p in ("ultralytics", "torch", "torchvision", "opencv-python", "numpy", "pillow")})
'@
$PythonCode | & $Python -
if ($LASTEXITCODE -ne 0) { throw 'consulta de versiones de Python o paquetes falló' }
```

Para la **revalidación del reloj**, introducir el SHA completo del futuro commit que lo publique, no el SHA `4fefb4a` del paquete histórico. Registrar el HEAD comprobado. Si el commit no está disponible en el clon, detenerse y conservar el error; no validar un HEAD distinto por accidente. Si el lockfile no instala, detenerse y guardar el error; no editar `uv.lock` para continuar.

El checkpoint está **fuera del repositorio**. `P5-05-REVISION-A3.md` documenta la descarga manual desde la release oficial `v8.3.0` de Ultralytics y su verificación. Reutilizar un checkpoint ya verificado o ejecutar este bloque de ese procedimiento; detenerse si falla el tamaño o el hash.

```powershell
$WeightsDir = Join-Path $env:LOCALAPPDATA 'P5-05'
New-Item -ItemType Directory -Force -Path $WeightsDir | Out-Null
$Weights = Join-Path $WeightsDir 'yolo11n.pt'
if (-not (Test-Path -LiteralPath $Weights -PathType Leaf)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt' -OutFile $Weights
}
$Expected = '0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1'
$Actual = (Get-FileHash -LiteralPath $Weights -Algorithm SHA256).Hash.ToLowerInvariant()
$Size = (Get-Item -LiteralPath $Weights).Length
if ($Actual -ne $Expected -or $Size -ne 5613764) { throw "Checkpoint incorrecto: SHA=$Actual; bytes=$Size" }
"Checkpoint verificado: SHA=$Actual; bytes=$Size"
```

Si el archivo ya existe, el bloque no lo descarga otra vez y verifica sus bytes. `config/detector.json` debe permanecer intacto; su configuración efectiva debe dar `6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08` y `torch_threads=2`. `config/control/plazos.yaml` debe conservar `detector_timeout_ms: 500` y `max_frame_age_ms: 500`; registrar su SHA-256 por separado.

```powershell
$PythonCode = @'
from infer.config import cargar_config_detector
c = cargar_config_detector()
assert c.config_sha256 == "6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08"
assert c.expected_model_sha256 == "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
assert c.torch_threads == 2
print(c.config_sha256, c.torch_threads, c.expected_model_sha256)
'@
$PythonCode | & $Python -
if ($LASTEXITCODE -ne 0) { throw 'configuración efectiva o dos hilos incorrectos' }
$PythonCode = @'
from infer.plazos import cargar_plazos_infer_con_hash
p, h = cargar_plazos_infer_con_hash()
assert p.detector_timeout_ms == 500 and p.max_frame_age_ms == 500
print(p.detector_timeout_ms, p.max_frame_age_ms, h)
'@
$PythonCode | & $Python -
if ($LASTEXITCODE -ne 0) { throw 'plazos compartidos incorrectos' }
(Get-FileHash -LiteralPath '.\config\control\plazos.yaml' -Algorithm SHA256).Hash.ToLowerInvariant()
```

## 2. Comprobaciones funcionales, separadas del benchmark

El script de comparación funcional usa el JPEG versionado `docs/carro/objeto_taza_centro_cerca.jpg` (SHA-256 `670fec5473ceda61b5a6283711596d610d75577dfb1bc9d5ffc8de52c1e9cbcc`), con detección no vacía y referencia P5-05 `ensayo-0012`. Elegir un destino **nuevo** para no sobrescribir evidencias. El script verifica ambos caminos, contrato v1, dimensiones, IDs, paridad exacta en el mismo host/runtime, READY con hashes y dos hilos y cierre limpio.

```powershell
(Get-FileHash -LiteralPath '.\docs\carro\objeto_taza_centro_cerca.jpg' -Algorithm SHA256).Hash.ToLowerInvariant()
& $Python .\resultados\p5-06-validacion-detecciones.py --weights $Weights --output (Join-Path $Repo 'resultados\p5-06-validacion-detecciones-windows-andrea')
if ($LASTEXITCODE -ne 0) { throw 'comparación real falló; conservar comparacion.json y los JSONL si existen' }
& $Python -m contrato .\resultados\p5-06-validacion-detecciones-windows-andrea\un_proceso.jsonl .\resultados\p5-06-validacion-detecciones-windows-andrea\supervisado.jsonl
if ($LASTEXITCODE -ne 0) { throw 'contrato v1 falló en comparación real' }
```

Revisar `comparacion.json`, ambos JSONL y `p506-taza-supervisado.infer-run.json`: `generaciones` debe tener READY con SHA-256 de modelo/configuración y `torch_threads=2`, y `cierre_limpio` debe ser verdadero. El script exige igualdad exacta entre las rutas **locales**. Frente a P5-05 Mac conserva la referencia completa, su SHA-256, valores originales, deltas firmadas de confianza y bbox y máximos absolutos. Una diferencia solo numérica queda como `diferencia_numerica_pendiente` sin abortar la recopilación; `revision_pendiente=true` **no es aprobación**. Un cambio estructural o semántico aborta después de escribir `comparacion.json`. Investigar cualquier discrepancia Windows/macOS; no cambiar umbrales, modelo o checkpoint para forzar igualdad.

La prueba con dos JPEG sintéticos y detecciones vacías tiene otro script y destino nuevo:

```powershell
& $Python .\resultados\p5-06-validacion-real.py --weights $Weights --output (Join-Path $Repo 'resultados\p5-06-validacion-real-windows-andrea')
if ($LASTEXITCODE -ne 0) { throw 'validación funcional con JPEG sintéticos falló' }
& $Python -m contrato .\resultados\p5-06-validacion-real-windows-andrea\un_proceso.jsonl .\resultados\p5-06-validacion-real-windows-andrea\supervisado.jsonl
if ($LASTEXITCODE -ne 0) { throw 'contrato v1 falló en JPEG sintéticos' }
```

Las pruebas automatizadas ejercitan timeout con trabajador bloqueado, reinicio exitoso y fallido, clasificación de pendientes, prioridad error > stale > ok, ausencia de duplicados, hashes/hilos, contrato y `detector_timeout` → STOP de B. Usan predictores simulados para las fallas; **no son una medición oficial de 500–600 ms de publicación**.

Como parte de la revalidación funcional del nuevo commit, verificar que padre e
hijo `spawn` comparten el reloj `perf_counter_ns` y registrar sus características. En Windows
`implementacion` debe identificar `QueryPerformanceCounter`; `resolucion_reportada_s` es la
resolución informada por Python, no una medida independiente. Conservar la salida del test y
revisar `reloj` en los manifiestos `.infer-run.json`. Las claves históricas
`inicio_monotonic_s` y `publicado_monotonic_s` de las trazas siguen existiendo, pero los
nuevos valores se toman de `perf_counter()`.

```powershell
& $Python -m pytest -q tests/test_infer_reloj.py
if ($LASTEXITCODE -ne 0) { throw 'prueba del reloj entre procesos falló; no iniciar benchmark' }
$PythonCode = @'
from infer.reloj import descripcion_reloj
print(descripcion_reloj())
assert "QueryPerformanceCounter" in descripcion_reloj()["implementacion"]
'@
$PythonCode | & $Python -
if ($LASTEXITCODE -ne 0) { throw 'reloj de alta resolución de Windows no verificado' }
```

```powershell
& $Python -m pytest -q tests/test_infer_reloj.py tests/test_infer_trabajador.py tests/test_infer_benchmark.py tests/test_infer_preflight.py tests/test_infer_control_integracion.py
if ($LASTEXITCODE -ne 0) { throw 'pruebas específicas fallaron; no iniciar benchmark' }
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'suite completa falló; no iniciar benchmark' }
```

Conservar salida completa, número de pruebas y fallos. Si un test falla en Windows, registrar el fallo y el entorno antes de cambiar código. El manifiesto funcional y los JSONL dan evidencia de spawn, calentamiento, READY, plazos, hashes, eventos únicos y cierre; las pruebas cubren fallas y reinicios simulados.

La herramienta separada de timeout usa un predictor simulado con `spawn`. Ejecutar cada comando
con un directorio **nuevo**; conservar sus muestras, JSONL y manifiestos. El segundo comando
inyecta un fallo de reinicio, sin tocar el checkpoint real. La herramienta termina con código 0
si la comprobación del fallo esperado fue correcta; `muestras.jsonl` registra que la política
del CLI devolvió un código distinto de cero con el resultado de ese run inyectado.

```powershell
& $Python .\resultados\p5-06-validacion-timeout.py --output (Join-Path $Repo 'resultados\p5-06-timeout-windows-andrea') --intentos 50
if ($LASTEXITCODE -ne 0) { throw 'validación de 50 recuperaciones simuladas falló' }
& $Python .\resultados\p5-06-validacion-timeout.py --output (Join-Path $Repo 'resultados\p5-06-terminal-windows-andrea') --intentos 1 --terminal
if ($LASTEXITCODE -ne 0) { throw 'validación del fallo terminal simulado falló' }
& $Python -m contrato (Join-Path $Repo 'resultados\p5-06-terminal-windows-andrea\timeout-0001.jsonl')
if ($LASTEXITCODE -ne 0) { throw 'contrato v1 falló en el caso terminal' }
$TimeoutDir = Join-Path $Repo 'resultados\p5-06-timeout-windows-andrea'
$TimeoutSummary = Get-Content -LiteralPath (Join-Path $TimeoutDir 'resumen.json') -Raw | ConvertFrom-Json
if ($TimeoutSummary.intentos_completados -ne 50 -or $TimeoutSummary.recuperaciones_correctas -ne 50 -or $TimeoutSummary.publicaciones_500_600_ms -ne 50 -or -not $TimeoutSummary.funcional_valido -or -not $TimeoutSummary.simulado) { throw 'criterios simulados 50/50 incumplidos' }
Get-ChildItem -LiteralPath $TimeoutDir -Filter 'timeout-*.jsonl' | ForEach-Object {
    & $Python -m contrato $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "contrato v1 falló: $($_.FullName)" }
}
$TerminalDir = Join-Path $Repo 'resultados\p5-06-terminal-windows-andrea'
$TerminalSample = (Get-Content -LiteralPath (Join-Path $TerminalDir 'muestras.jsonl') -Raw | ConvertFrom-Json)
if (-not $TerminalSample.fallo_terminal -or $TerminalSample.codigo_cli_con_resultado_inyectado -eq 0) { throw 'fallo terminal o política de salida incorrectos' }
```

La evidencia Mac existente de este recorrido se conserva en
`resultados/p5-06-timeout-simulado-mac-2026-11-02/`, con 50/50 publicaciones entre 500 y 600 ms,
50/50 recuperaciones simuladas con READY y duración de 503.0183750204742 a
525.7063750177622 ms. Andrea debe registrar sus propios resultados de Windows; no se trasladan
estas duraciones ni los READY simulados a la validación del checkpoint oficial. Revisar la
metodología y los riesgos de `flush` en `resultados/P5-06-VALIDACION-TIMEOUT.md`.
El contador del resumen no basta por sí solo: revisar también las 50 duraciones individuales
en `muestras.jsonl`, el código de error, cada `frame_id` y los dos READY de cada manifiesto.
El script registra todas las duraciones aunque alguna quede fuera de 500–600 ms; su código de
salida puede ser 0 si la función se comportó bien pero falló el criterio temporal. La
comprobación PowerShell anterior rechaza ese caso. Los 50 intentos son runs independientes,
no una secuencia continua de 50 cuadros; las pruebas de cuadros pendientes son separadas.

## 3. Serie oficial de latencia y reinicio

Andrea debe intervenir para verificar que la laptop está en **AC**, el ahorro de batería está **desactivado**, OneDrive y VS Code están **cerrados**, y no hay carga interferente relevante. Registrar el estado observado y los procesos/carga. `src/infer/preflight.py` consulta `GetSystemPowerStatus` (`ACLineStatus`, `SystemStatusFlag`) y `tasklist`; el script bloquea la serie si cualquier condición es falsa o no verificable y guarda `benchmark.preflight.json` junto al `benchmark.json` propuesto. No cambiar configuración para mejorar tiempos.

El comando siguiente usa la interfaz actual de `resultados/p5-06-benchmark.py`. **Es una instrucción propuesta; no se ejecutó aquí.** Usar un archivo de salida nuevo, en una carpeta controlada por Andrea. Ejecutarlo una sola vez por máquina; ante fallo conservar la evidencia parcial y detenerse, sin repetir selectivamente por cercanía al límite.
Solo iniciar esta serie tras revalidar el nuevo commit con paridad local, contrato y pruebas
funcionales favorables, confirmar el reloj entre procesos y superar el preflight. Investigar
las diferencias numéricas frente a Mac conforme a la política multiplataforma; completar
el benchmark no las aprueba. `benchmark.json` y el manifiesto
guardarán `reloj.nombre`, `reloj.implementacion` y `reloj.resolucion_reportada_s`.

```powershell
$BenchmarkPath = Join-Path $Repo 'resultados\p5-06-benchmark-windows-andrea\benchmark.json'
& $Python .\resultados\p5-06-benchmark.py --weights $Weights --output $BenchmarkPath --responsable Andrea
if ($LASTEXITCODE -ne 0) { throw 'serie oficial incompleta; conservar benchmark.json y benchmark.preflight.json si existen' }
$Benchmark = Get-Content -LiteralPath $BenchmarkPath -Raw | ConvertFrom-Json
if ($Benchmark.muestras_ms.control.Count -ne 50 -or $Benchmark.muestras_ms.supervisado.Count -ne 50) { throw 'faltan muestras medidas' }
if ($Benchmark.calentamientos_excluidos_ms.control.Count -ne 10 -or $Benchmark.calentamientos_excluidos_ms.supervisado.Count -ne 10) { throw 'faltan calentamientos excluidos' }
if ($Benchmark.reinicios_medidos.Count -ne 50 -or $Benchmark.reinicios_excluidos.Count -ne 10) { throw 'faltan reinicios medidos o excluidos' }
if (@($Benchmark.reinicios_medidos | Where-Object { $_.ready.estado -ne 'ready' -or $_.ready.model_sha256 -ne $Expected -or $_.ready.config_sha256 -ne '6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08' -or $_.ready.torch_threads -ne 2 }).Count -ne 0) { throw 'READY de reinicio inválido' }
$DeltaP50 = $Benchmark.stats_ms.supervisado.p50 - $Benchmark.stats_ms.control.p50
$DeltaP95 = $Benchmark.stats_ms.supervisado.p95_lineal - $Benchmark.stats_ms.control.p95_lineal
if ($DeltaP50 -gt 5 -or $DeltaP95 -gt 10 -or $Benchmark.stats_ms.supervisado.p95_lineal -gt 150 -or $Benchmark.stats_ms.supervisado.max -gt 200 -or $Benchmark.solicitudes_sobre_500_ms.supervisado -ne 0) { throw 'al menos un límite de rendimiento de Karen no se cumplió; conservar evidencia completa' }
"Delta p50=$DeltaP50 ms; Delta p95=$DeltaP95 ms"
```

El script verifica checkpoint (5 613 764 bytes y SHA aprobado), configuración, dos hilos y JPEG fijo; prepara ambas rutas y mide **10 pares control→supervisado de calentamiento excluidos y 50 pares medidos**. Control: desde antes de decodificar el JPEG hasta retorno validado de `_evento_cuadro`. Supervisado: desde antes de `solicitar` en el padre hasta recibir respuesta completa verificada; incluye supervisión, IPC, lectura, inferencia y validación. No incluye publicación JSONL, carga ni reinicio. Conserva cada muestra, p50 como mediana y p95 con `numpy.percentile(method="linear")`, diferencias absoluta/porcentual, máximo y solicitudes normales superiores a 500 ms. Exige igualdad exacta entre rutas locales para cada par y registra diferencias frente a P5-05 Mac por muestra. Una diferencia numérica entre plataformas no descarta la duración; queda pendiente de revisión. Una discrepancia estructural o local detiene la serie, conserva `benchmark.json` parcial con fase, índice y muestras obtenidas, y exige investigación. No reiniciar automáticamente la única serie oficial.
Los `if` de PowerShell comprueban los umbrales sin redondear; el script Python registra las
estadísticas, pero no declara por sí mismo la aceptación de Karen. Revisar además
`paridad_detecciones.revision_pendiente` y las `comparaciones` de los 60 pares; cualquier
diferencia numérica frente a Mac requiere investigación aunque todos los límites pasen.
Si falla una condición,
conservar todos los archivos y la salida de consola; no seleccionar otra serie por cercanía
al límite. Un preflight rechazado escribe `benchmark.preflight.json` y no inicia la serie;
corregir el entorno, conservar ese rechazo y usar un destino nuevo si se vuelve a intentar.

Después mide por separado **10 reinicios directos excluidos y 50 reinicios directos medidos** mediante `detener()`/`iniciar()`, desde antes de detener hasta READY verificado. Guarda duración total y fases de detención, coordinación, creación/spawn, arranque, carga/verificación, calentamiento y entrega de READY, con solapamientos. Estos reinicios **no son provocados por timeout**. Si la serie falla, el JSON contiene fase, índice y muestras parciales; no presentar percentiles incompletos como resultado. El reinicio no tiene umbral numérico; comunicar duraciones a P5-16.

Aplicar todos los límites sobre cifras sin redondear: `p50_supervisado − p50_control ≤ 5 ms`, `p95_supervisado − p95_control ≤ 10 ms`, `p95_supervisado ≤ 150 ms`, `máximo_supervisado ≤ 200 ms`, cero solicitudes normales mayores que 500 ms. La validación decisiva es la de Andrea en Windows.

## 4. Evidencia por entregar

- SHA completo del commit comprobado en cada ejecución (Andy validó `4fefb4adddb0e9d9a04379b7e5589a0e6d6758ff`; registrar por separado el futuro commit del reloj); Windows/CPU/RAM; versiones de Python, `uv`, PyTorch, Ultralytics, Torchvision, OpenCV, NumPy; estado de AC/ahorro, OneDrive, VS Code, carga del host, salida de los comandos y cualquier desviación.
- Ubicación externa, tamaño y SHA-256 del checkpoint; SHA-256 efectivo de configuración, SHA-256 de `plazos.yaml`, valor de los dos plazos y del JPEG permitido.
- De cada validación funcional: `comparacion.json` o `validacion.json`, ambos JSONL, JPEG sintéticos cuando corresponda, manifiesto `.infer-run.json`, salida de `python -m contrato`, resultado de pytest y cualquier error. Registrar READY, hilos, hashes, IDs, dimensiones, estados, ausencia de duplicados, cierre, características del reloj y resultado de la prueba `spawn` padre–hijo–padre.
- De la serie oficial: `benchmark.json`, `benchmark.preflight.json`, las 50 muestras de cada ruta, 10 calentamientos por ruta, 50 reinicios medidos y 10 excluidos, fases, percentiles sin redondear, fallos/descartes y salida de terminal. Guardar evidencia parcial si aborta. Indicar expresamente que la medición de reinicio fue directa.
- Para la validación separada de timeout forzado: `muestras.jsonl`, `resumen.json`, JSONL y manifiesto de cada uno de los 50 intentos, marcas monotónicas de inicio de solicitud y publicación del evento, duración individual, `frame_id`, READY, continuidad y resultado de contrato. Del caso terminal, conservar sus tres eventos, manifiesto y `codigo_cli_con_resultado_inyectado`. Registrar SHA-256 de los archivos entregados. Usar `resultados/P5-06-VALIDACION-TIMEOUT.md`; el benchmark normal no produce estos datos.

No repetir ni reemplazar `resultados/p5-06-benchmark-mac-2026-11-01/`, `p5-06-validacion-real/` ni `p5-06-validacion-detecciones/`: son evidencia histórica del PR. Los nuevos destinos deben ser únicos.

## 5. Procedimientos aún insuficientes para aceptación completa

1. `resultados/P5-06-VALIDACION-TIMEOUT.md` describe la herramienta separada que provoca 50 timeouts y recuperaciones con trabajador simulado, mide la publicación después del `flush` y comprueba el fallo terminal. Andrea debe ejecutarla de forma independiente en Windows; sus resultados no se infieren de la serie Mac. `flush` no demuestra durabilidad de disco como `fsync`, y una escritura fallida no permite afirmar que se publicó el evento.
2. Los 50 reinicios del benchmark normal siguen siendo directos. Los resultados de la herramienta de timeout, las pruebas de cuadros pendientes y el benchmark deben reportarse por separado. El trabajador simulado declara los hashes esperados; la verificación criptográfica y el calentamiento con checkpoint real pertenecen a la validación funcional aparte.
3. No hay procedimiento que induzca un fallo terminal **del modelo real** en Windows sin alterar pesos o configuración. El caso se verifica con fábrica simulada y con la política de salida del CLI; no atribuirle una ejecución real del checkpoint en fallo.
4. El benchmark solo guarda `preflight` del sistema y `tasklist` para procesos bloqueantes; Andrea debe registrar por separado la carga/procesos que juzgue interferentes y cualquier desviación. La serie Mac anterior se ejecutó en bloques y permanece como referencia histórica, no como réplica de este procedimiento.
5. El commit histórico `016d1867` todavía exigía igualdad numérica exacta frente a Mac. Andy validó el commit posterior `4fefb4a`, que contiene la política de comparación multiplataforma. La corrección del reloj tiene un commit futuro pendiente; anotar su SHA cuando exista y verificar el HEAD antes de validarlo. Estos bloques PowerShell se revisaron estáticamente, pero no se ejecutaron en Windows durante la preparación. La validación independiente debe registrar cualquier incompatibilidad real de PowerShell, `spawn`, dependencias o preflight. No hay un comando que pruebe el fallo terminal del modelo real sin inyección ni una serie de 50 timeouts en una sola secuencia continua; la herramienta usa 50 runs independientes.
