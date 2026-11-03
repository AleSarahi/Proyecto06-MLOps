# Auditoría de la serie Mac P5-06 del 1 de noviembre de 2026

Esta auditoría no modifica `p5-06-benchmark-mac-2026-11-01/benchmark.json` ni sustituye
sus muestras. Su SHA-256 es
`83e0d2a4bfa8262bf9c7f389ab16ebc101f77db4cbf92cec2d757e8aacda4372`.

## Lo que registran los archivos

- `benchmark.json.procedimiento.orden` dice `control`, `supervisado`, `reinicio`; el
  script que produjo la serie tiene un bucle de 60 solicitudes de control seguido por
  otro de 60 supervisadas. **No hubo intercalado.** En cada bloque se excluyeron las
  primeras diez y se guardaron las siguientes 50.
- `reinicios_excluidos` tiene 10 entradas y `reinicios_medidos` tiene 50. El script
  llama a `medir_reinicio`, que inicia el reloj antes de `detener()`, termina al
  volver de `iniciar()` con READY verificado y conserva `detencion_ms`,
  `coordinacion_ms` y las fases de READY. **No se provocaron mediante timeout
  forzado.** El total incluye detener al hijo anterior y cerrar sus colas, crear
  nuevas colas/proceso, `spawn`, arranque del hijo, carga y verificación del
  checkpoint/configuración/hilos, calentamiento, entrega y verificación de READY.
  No incluye una solicitud vencida ni la publicación de su evento.
- No existe en esa carpeta una medición desde el inicio de la solicitud hasta la
  publicación de `detector_timeout`. Las muestras normales terminaron sin timeout;
  el conjunto de reinicios mide otra operación. La latencia exigida por la adenda
  de Karen queda pendiente de evidencia propia.
- `stats_ms.control.p95_lineal` vale **32.9998997 ms** sin redondear. Las 50 muestras
  se ordenan, y `numpy.percentile(..., 95, method="linear")` usa la posición
  `0.95 × (50−1) = 46.55` (índices desde cero). Los valores vecinos son
  `32.968916` y `33.02525` ms; su interpolación es `32.9998997` ms.

## Alimentación y causa de la discrepancia

`entorno-previo.json`, fechado `2026-11-02T04:33:53.073290+00:00`, guarda la
salida `pmset -g ps`: **AC Power**, batería al 79 % cargando. Las seis consultas
de `condiciones_series` en `benchmark.json`, entre `04:34:05` y `04:35:34` UTC,
también registran **AC Power**. `entorno-posterior.json` conserva otra consulta.
Ninguno de esos archivos registra el estado de ahorro de energía.

El comando y `host.modo_energia` dicen `bateria-descargando` porque el argumento
`--modo-energia` era texto manual. Una consulta en vivo anterior, no guardada en
estos archivos, había mostrado batería; el script no volvió a verificar ese
argumento contra `pmset`. **La causa comprobable de la discrepancia en el JSON
es el uso de una etiqueta manual desactualizada.** Los archivos no permiten
establecer cuándo, cómo ni por qué cambió físicamente la alimentación. La frase
de `observaciones.json` que sitúa el cambio «entre el preflight y control_inicio»
es incompatible con el preflight formal guardado, que ya indica AC. Se conserva
ese archivo como evidencia histórica y esta auditoría corrige su interpretación.

## Preflight nuevo, aplicable solo a futuras series

El benchmark consulta alimentación y ahorro directamente antes de cargar el
detector y en los límites de las etapas. En macOS usa `pmset -g ps` para la fuente
de alimentación y `pmset -g` para `lowpowermode` activo. En Windows usa
`GetSystemPowerStatus`: `ACLineStatus` y `SystemStatusFlag`, y `tasklist` para
comprobar que OneDrive y VS Code estén cerrados. Un valor desconocido, un fallo
de consulta, batería o ahorro activado bloquea la serie; el resultado y su fuente
quedan en un archivo de preflight separado. No se ejecutó otra serie oficial para
verificar este cambio.

El script `resultados/p5-06-benchmark.py` se actualizó **después** de la serie
original para intercalar rutas y aplicar este preflight. Por tanto, el comando
histórico del README Mac conserva lo que se ejecutó entonces, pero la versión
actual del script ya no reproduce su orden en bloques ni acepta el argumento
manual `--modo-energia`. Los datos brutos y el procedimiento registrado permiten
auditar la serie; no se guardó una copia byte a byte del script anterior como
artefacto independiente. Esta limitación de reproducción debe quedar visible en
el PR.

Fuentes de las APIs de energía:
[Apple, `ProcessInfo.isLowPowerModeEnabled`](https://developer.apple.com/documentation/foundation/processinfo/islowpowermodeenabled?changes=_9),
[Microsoft, `GetSystemPowerStatus`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getsystempowerstatus) y
[Microsoft, `SYSTEM_POWER_STATUS`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-system_power_status).
