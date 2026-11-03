# P5-06 · evidencia funcional independiente de Windows

Andy entregó `p5-06-evidencia-windows-4fefb4a.zip` el 2 de noviembre de 2026
para el commit `4fefb4adddb0e9d9a04379b7e5589a0e6d6758ff`. El original se conserva
**fuera de Git**, en Downloads, con 149 968 bytes y SHA-256
`8a8192fe0f91f7c72fb2d9e6ee557e79a6917818af4dcf03a7b7e59966c903d4`.
El archivo de esta carpeta, `evidencia-publica.zip`, es una **copia depurada**, con
150 017 bytes y SHA-256
`12addf5aeb48bd4b90d846e177360b8adc29631bcd30ca897159323a45ff0b42`.
No es idéntico al original. Esta evidencia precede al cambio del reloj.

## Integridad

Ambos ZIP contienen 283 archivos: 282 indexados y `SHA256SUMS.txt`. En el original,
PowerShell 5.1 escribió el índice con BOM UTF-8. Sus 282 entradas se verificaron con
`utf-8-sig`; el SHA-256 original de `ENTORNO.txt` es
`42f5f85120775edfee20875a5d7c8d464e35f6d2c79207ae584a02b4cb13971e`.
En la copia pública, `SHA256SUMS.txt` se regeneró en UTF-8 **sin BOM**: sus 282 entradas
corresponden a los 282 archivos y todos los hashes coinciden. No hay rutas ausentes,
entradas duplicadas ni archivos sin indexar; el CRC del ZIP es válido. El SHA-256 público
de `ENTORNO.txt` es
`7371e2b6c58d014c1c192c49b89ae89082f16b104fd6110e2a4e26da38ef0014`.

La depuración sustituyó **68 apariciones** del identificador de la cuenta local de
Windows por el marcador literal `<REDACTED>`, sin publicar el identificador. Se cambiaron
solo `ENTORNO.txt` y estos siete registros:

- `registros/detecciones-contrato.log`
- `registros/pytest-p506.log`
- `registros/pytest-todo.log`
- `registros/real-contrato.log`
- `registros/terminal-contrato.log`
- `registros/terminal.log`
- `registros/timeout-50.log`

Los registros conservan su codificación UTF-16; los nombres de entrada y los metadatos
del ZIP no contenían ese identificador y no se cambiaron. Los otros 274 archivos
indexados conservaron sus bytes. La sustitución afecta rutas y referencias al perfil
local, incluidos directorios temporales de pytest; no cambia resultados numéricos,
detecciones, duraciones, códigos ni hashes técnicos de checkpoint/configuración.

## Entorno y resultados registrados

`ENTORNO.txt` declara Windows 11 Home Single Language 64 bits, AMD Ryzen 7 8845HS,
61,75 GiB de RAM, Python 3.12.14, Ultralytics 8.3.0 y PyTorch 2.9.0. El checkpoint
`yolo11n.pt` se declaró con 5 613 764 bytes y SHA-256
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`;
la configuración efectiva registró SHA-256
`6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08`
y `torch_threads=2`. `plazos.yaml` registró SHA-256
`bd51e1c1d97d4d196eb476fbaefc37baf627c8de769b2aad0d9213a56b561e22`
y ambos plazos en 500 ms. El hash de la referencia P5-05 incluido en `comparacion.json`
coincide con el archivo versionado del repositorio.

- `comparacion.json`: READY y cierre limpio; control y supervisado produjeron exactamente
  una detección idéntica de clase 41 y confianza `0.9552612900733948`.
- Frente a P5-05 Mac, la confianza coincidió y la diferencia máxima de bbox fue
  `0.00006103515625` px. Su clasificación es `diferencia_numerica_pendiente`, con
  `revision_pendiente=true`. **No se aplicó tolerancia ni se aprobó la diferencia.**
- `validacion.json`: dos JPEG sintéticos, dos eventos `ok` sin detecciones por ruta,
  paridad local, contrato A→B v1 válido y cierre limpio.
- `p5-06-timeout-windows-andrea/muestras.jsonl`: 50 intentos simulados independientes,
  cada uno con un evento `detector_timeout`, publicación entre 515 y 531 ms y dos
  generaciones READY con hashes y dos hilos declarados por el trabajador simulado.
  Los 50 reinicios fueron correctos.
- `p5-06-terminal-windows-andrea/muestras.jsonl`: timeout inicial conservado, dos
  `detector_exception` para cuadros pendientes y código de salida inyectado distinto de cero.
- `registros/pytest-todo.log`: 1158 pruebas aprobadas, 22 omitidas y una fallida en
  `test_infer_preflight.py:156` por la lectura sin UTF-8 explícito. La corrección local
  posterior no forma parte de este ZIP ni del commit validado.

## Condiciones y alcance

Andrea registró VS Code abierto, batería al 37 % antes de empezar y conexión a corriente
en algún momento posterior, sin hora registrada. También consignó otros comandos locales
durante los primeros pasos y lecturas de `time.monotonic` cuantizadas a unos 15,625 ms en
su entorno. La guía PowerShell 5.1 requirió ajustar manualmente las comillas de `python -c`.
Se conservan estas desviaciones; no se atribuyen condiciones de AC a toda la validación.

Este paquete es **validación funcional**, con checkpoint real para las detecciones y
trabajador simulado para timeout, recuperación y fallo terminal. No contiene el benchmark
oficial intercalado de 10 calentamientos + 50 mediciones ni demuestra sus límites de
rendimiento. Andrea debe repetir la validación funcional sobre el futuro commit del reloj
antes de realizar la única serie oficial Windows en condiciones de preflight aprobadas.
