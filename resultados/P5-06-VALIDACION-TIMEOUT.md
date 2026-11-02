# P5-06 · validación funcional de publicación y recuperación

Esta herramienta usa JPEG sintéticos y un predictor simulado compatible con `spawn`. El hijo confirma los hashes y dos hilos en READY, pero **no carga ni verifica criptográficamente el checkpoint real**. La validación con pesos aprobados sigue en `p5-06-validacion-detecciones.py`. No es el benchmark oficial de latencia normal y no modifica la serie Mac histórica. Las muestras locales ya obtenidas están preservadas, con SHA-256 por archivo, en `p5-06-timeout-simulado-mac-2026-11-02/`.

Desde la raíz del worktree, elegir un directorio de salida nuevo:

```sh
.venv/bin/python resultados/p5-06-validacion-timeout.py --output /ruta/nueva/p5-06-timeout-50 --intentos 50
.venv/bin/python resultados/p5-06-validacion-timeout.py --output /ruta/nueva/p5-06-terminal --intentos 1 --terminal
.venv/bin/python -m contrato /ruta/nueva/p5-06-terminal/timeout-0001.jsonl
```

En Windows PowerShell, con `$Python = Join-Path (Get-Location).Path '.venv\Scripts\python.exe'`:

```powershell
& $Python .\resultados\p5-06-validacion-timeout.py --output 'C:\ruta\nueva\p5-06-timeout-50' --intentos 50
& $Python .\resultados\p5-06-validacion-timeout.py --output 'C:\ruta\nueva\p5-06-terminal' --intentos 1 --terminal
& $Python -m contrato 'C:\ruta\nueva\p5-06-terminal\timeout-0001.jsonl'
```

El script crea un run independiente por intento, cada uno con una solicitud que bloquea más de 500 ms y obliga al supervisor a publicar `detector_timeout` y reiniciar. Los 50 runs dan 50 recuperaciones provocadas por timeout; no se confunden con los 50 reinicios directos del benchmark. Cada run guarda el JSONL A→B v1 y el manifiesto de READY. `muestras.jsonl` conserva duración desde el inicio exacto de la solicitud, que fija su deadline, hasta después del `flush`, IDs, códigos, READY y éxito de recuperación. `resumen.json` cuenta éxitos y publicaciones en 500–600 ms. Si un intento falla, se guarda una fila de fallo y la herramienta termina sin repetirlo. Las duraciones individuales permiten auditar desviaciones.

En modo `--terminal`, el segundo arranque falla por inyección controlada; el primer timeout debe permanecer en JSONL, seguido por errores de los cuadros pendientes. La herramienta verifica también la asignación de código no cero de `infer.__main__.main` con el resultado del run ya producido. Esa comprobación usa sustitución de la llamada a `ejecutar_run_supervisado` **solo para examinar la política de salida del CLI**; el JSONL y el manifiesto provienen de la ejecución real del publicador con trabajador simulado. No se toca el checkpoint ni la configuración.

La marca de publicación se toma después del `flush` del JSONL y no representa `fsync`: no se afirma persistencia ante apagado o caída. Ante fallo de escritura o de `flush`, la ejecución aborta y la traza no registra una publicación completada. Guardar fallos y desviaciones; no seleccionar repeticiones por cercanía al límite.

Para READY con el checkpoint oficial, ejecutar por separado la validación documentada en `p5-06-validacion-detecciones/README.md`: verifica SHA-256 del archivo, hashes recibidos, dos hilos, calentamiento, detecciones y cierre. No atribuir esa comprobación a los runs simulados. Los cuadros viejos, ilegibles y vigentes tras recuperación se prueban con escenarios de `tests/test_infer_trabajador.py`; la herramienta de 50 intentos usa un JPEG nuevo por run y no sustituye esas pruebas de clasificación.
