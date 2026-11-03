# P5-06 · revalidación funcional independiente en Windows

Andy entregó el ZIP original `p5-06-evidencia-windows-e75533f.zip` para el commit
`e75533fd480a9cb9aa126ac7cc3b49011e605a09`, generado el 2 de noviembre de 2026.
El original permanece **fuera de Git**, sin modificar, en Downloads: 162 163 bytes y
SHA-256 `cd7debd52c1908fcf8f8019576376c24d006e0c40b3571c252e5c8c05c0aa752`.
La copia de esta carpeta, `evidencia-publica.zip`, fue depurada para su publicación:
162 239 bytes y SHA-256
`8fc143cfa5d2d8b2b898c4d7930427a79a9ea652ff4cb8bd416cb15cf3909c5a`.
**No es idéntica al paquete recibido.**

## Integridad y depuración

Ambos paquetes tienen 294 archivos, incluido `SHA256SUMS.txt`. En el original, las 293
entradas del índice UTF-8 sin BOM coinciden con los 293 archivos indexados y sus SHA-256.
El índice usa `/` y los nombres internos del ZIP usan `\`; se normalizó el separador
solo al comparar rutas. En la copia pública se regeneró `SHA256SUMS.txt` en UTF-8 sin BOM:
**293/293 hashes correctos**, sin entradas duplicadas o ausentes y con CRC válido.
Los nombres de entrada y los metadatos del ZIP se conservaron.

Se sustituyeron **67 apariciones** del identificador de la cuenta local de Windows por
`<REDACTED>`. En `ENTORNO.txt`, la línea con el nombre completo de la persona responsable
se redujo a `Responsable: Andy`. Los siete archivos cuyo contenido cambió son:

- `ENTORNO.txt`
- `registros/detecciones-contrato.log`
- `registros/extra-jpeg-ausente.log`
- `registros/real-contrato.log`
- `registros/terminal-contrato.log`
- `registros/terminal.log`
- `registros/timeout-50.log`

Los registros modificados conservan su codificación UTF-16. Los otros **286 archivos
indexados** conservaron sus bytes. La transformación se limita al identificador de la
cuenta y a la línea de atribución: no cambian detecciones, marcas temporales, resultados
numéricos, códigos, hashes técnicos del modelo/configuración ni pruebas. No se encontró
el identificador en los nombres de entrada ni en los metadatos del ZIP.

## Entorno, resultados y desviaciones

`ENTORNO.txt` registra Windows 11 Home Single Language, AMD Ryzen 7 8845HS, 61,75 GiB
de RAM, Python 3.12.14, Ultralytics 8.3.0 y PyTorch 2.9.0. El checkpoint figura con
5 613 764 bytes y SHA-256
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`;
`config_sha256` es
`6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08`,
`torch_threads=2` y ambos plazos son de 500 ms. El reloj reportado es
`perf_counter` / `QueryPerformanceCounter()`, con resolución **reportada por Python**
de `1e-07` s. La prueba `spawn` aprobó (2 pruebas del módulo de reloj).

- `comparacion.json` registra READY y cierre limpio, una detección idéntica de clase 41
  en control y supervisado, y contrato v1 válido. Frente a P5-05 Mac, la diferencia
  máxima de bbox es `0.00006103515625` px; permanece clasificada como
  `diferencia_numerica_pendiente`, con `revision_pendiente=true`. No se adoptó tolerancia
  ni se aprobó automáticamente esa diferencia.
- `validacion.json` registra dos JPEG sintéticos por ruta, paridad local exacta,
  contrato v1 válido y cierre limpio.
- `registros/pytest-especificas.log`: 57 pruebas aprobadas. La suite completa registró
  1164 aprobadas y 22 omitidas, sin fallos.
- `p5-06-timeout-windows-andrea/muestras.jsonl`: **50 intentos simulados independientes**,
  cada uno con un único `detector_timeout`, dos READY y recuperación correcta. Las 50
  duraciones desde solicitud hasta publicación están entre
  `500.8899999993446` y `528.8297000006423` ms; las muestras individuales quedan en
  el JSONL. El resumen indica 50/50 dentro de 500–600 ms.
- `p5-06-terminal-windows-andrea/muestras.jsonl`: timeout inicial conservado, dos
  `detector_exception` para cuadros pendientes y código de salida inyectado 1.

Andy registró alimentación AC al inicio (93 %) y al final (96 %), con VS Code abierto y
OneDrive ausente de la lista inicial de procesos. Se usó un clon nuevo en una carpeta
distinta de la guía, `python -m uv` en lugar del ejecutable `uv`, y un script que
registró los códigos de los pasos en vez de detenerse con `throw`; los pasos previstos
terminaron sin fallos. También ejecutó cinco veces pruebas adicionales de eventos y
probó un JPEG inexistente, que produjo `unreadable_image` y salida 1 como se esperaba.

Esta es **evidencia funcional**, con checkpoint real para la comparación de detecciones
y trabajador simulado para timeout, recuperación y fallo terminal. No incluye la serie
oficial de latencia intercalada ni demuestra sus límites de rendimiento. VS Code estaba
abierto y no se aplicó el preflight de la serie oficial. La diferencia numérica Mac/Windows
sigue pendiente de investigación; completar esta revalidación no la declara aprobada.
