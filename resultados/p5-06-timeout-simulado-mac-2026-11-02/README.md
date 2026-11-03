# P5-06 · timeout y recuperación simulados en Mac, 2 de noviembre de 2026

Evidencia funcional posterior a la regla de aceptación de Karen. Se usó `multiprocessing` con `spawn`, JPEG sintéticos y un predictor **simulado** que se bloquea más de 500 ms. No se cargó el checkpoint real ni se ejecutó el benchmark oficial de latencia. No se utilizaron S01–S08 ni `datos/cuadros/`.

Comandos ejecutados desde la raíz del worktree con el entorno Python 3.12 instalado:

```sh
MPLCONFIGDIR=/tmp/p506-mpl YOLO_CONFIG_DIR=/tmp/p506-yolo .venv/bin/python resultados/p5-06-validacion-timeout.py --output /tmp/p506-50-recuperaciones-20261102-final --intentos 50
MPLCONFIGDIR=/tmp/p506-mpl YOLO_CONFIG_DIR=/tmp/p506-yolo .venv/bin/python resultados/p5-06-validacion-timeout.py --output /tmp/p506-terminal-validacion-20261102-final --intentos 1 --terminal
```

Los destinos de esos comandos ya existen: para repetir, elegir **otros** destinos nuevos. Se copiaron byte a byte los archivos originales relevantes de `/tmp` a `recuperaciones-50/` y `fallo-terminal/`. `SHA256SUMS` enumera los 210 archivos copiados con su hash, calculado y comparado con el origen. Se excluyeron 51 archivos `.contador` temporales del simulador. Los JPEG y archivos `control-*.json` son entradas sintéticas de cada run; los JSONL y manifiestos son salidas de A; `muestras.jsonl` y `resumen.json` registran la validación. No se incluyó ningún checkpoint.

Resultados observados:

| Recorrido | Resultado |
|---|---|
| 50 intentos | 50/50 eventos `detector_timeout`; 50/50 publicaciones entre 500 y 600 ms después del `flush`; 50/50 reinicios con READY; cada run tiene un solo JPEG y un solo evento. Duraciones mínima 503.0183750204742 ms y máxima 525.7063750177622 ms. |
| Fallo terminal | `cuadro-0001` conserva `detector_timeout`; `pendiente-0000` y `pendiente-0001` reciben `detector_exception`. El resultado del run indica fallo de reinicio. La política de `infer.__main__.main` devolvió 1 al recibir ese resultado por sustitución controlada de la llamada; la herramienta de validación terminó con 0 porque sus comprobaciones fueron correctas. Duración del timeout publicado: 525.216291891411 ms. |

Cada `muestras.jsonl` guarda las marcas monotónicas del proceso padre, `frame_id`, generación, código y resultado de reinicio. Cada manifiesto registra READY, hashes declarados, dos hilos y cierre. Esos hashes del trabajador simulado no demuestran lectura criptográfica del checkpoint real; la validación funcional con el checkpoint oficial está separada en `resultados/p5-06-validacion-detecciones/`. Tampoco se han ejecutado estas herramientas en Windows.

Hashes principales:

| Archivo | SHA-256 |
|---|---|
| `SHA256SUMS` | `4ea75b4a197b071d36f8e177a9e8a04ec12e413e9e64b2b65146b14621431df0` |
| `recuperaciones-50/muestras.jsonl` | `b26b0e0c52c217a893ce6c682a95b816888cd855d8cda3844953aade0a8980d0` |
| `recuperaciones-50/resumen.json` | `2cdeddedea2e8e7d70c5bd9460079f7711030c1b3f7203304436696b84ca2754` |
| `fallo-terminal/muestras.jsonl` | `210ff67899720ee8dd47c50fc3e86f27121af56bb4f9f70b827359e4b27a01bf` |
| `fallo-terminal/resumen.json` | `785c8e29257963c88bfa585c8093d4a3757466dc692c44f6515a1d912034bcdd` |

La marca de publicación se toma después de `flush()`, que vacía el búfer de Python al sistema operativo. No hay `fsync`; esta prueba no demuestra persistencia tras una caída del sistema. Si `write` o `flush` falla, el run aborta y la traza no marca publicación exitosa. Las pruebas de regresión cubren ambos fallos.
