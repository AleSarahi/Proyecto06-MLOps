# Evidencias previstas para el PR en borrador de P5-06

La lista original se preparó antes de publicar el PR #86. Se conserva a continuación
como inventario histórico; la evidencia Windows se recibió después.
La serie Mac original queda intacta; las correcciones de interpretación están en la auditoría.

## Evidencia Windows recibida después de abrir el PR

El ZIP funcional independiente para el commit `4fefb4adddb0e9d9a04379b7e5589a0e6d6758ff`
se conserva **fuera de Git**, sin cambios, con SHA-256
`8a8192fe0f91f7c72fb2d9e6ee557e79a6917818af4dcf03a7b7e59966c903d4`.
La copia pública depurada se encuentra en
`resultados/p5-06-validacion-windows-4fefb4a-2026-11-02/evidencia-publica.zip`
(SHA-256 `12addf5aeb48bd4b90d846e177360b8adc29631bcd30ca897159323a45ff0b42`).
Su `README.md` documenta procedencia, ocho archivos depurados, integridad, entorno,
desviaciones y resultados. El índice original contenía BOM UTF-8; sus 282 entradas se
verificaron con `utf-8-sig`. El índice público se regeneró en UTF-8 sin BOM y sus 282
hashes coinciden. El ZIP público no es idéntico al original.
Es evidencia funcional anterior al reloj de alta resolución. El benchmark oficial Windows
sigue pendiente; la diferencia numérica frente a Mac permanece pendiente de investigación.

### Revalidación funcional Windows del reloj

Andy revalidó el commit `e75533fd480a9cb9aa126ac7cc3b49011e605a09`. El paquete
original de Downloads permanece fuera de Git, con SHA-256
`cd7debd52c1908fcf8f8019576376c24d006e0c40b3571c252e5c8c05c0aa752`.
La copia pública depurada se conserva en
`resultados/p5-06-validacion-windows-e75533f-2026-11-02/evidencia-publica.zip`, con
SHA-256 `8fc143cfa5d2d8b2b898c4d7930427a79a9ea652ff4cb8bd416cb15cf3909c5a`.
El `README.md` de esa carpeta identifica los siete archivos depurados, el reemplazo de
67 apariciones del identificador local y la atribución reducida a «Andy». El índice público
UTF-8 sin BOM verificó 293/293 hashes; el ZIP público no es idéntico al original.
Se confirmó `QueryPerformanceCounter`, la prueba `spawn`, paridad local, contrato v1 y
50/50 timeouts y recuperaciones **simulados**. VS Code estaba abierto: esta evidencia no
es el benchmark oficial Windows, que sigue pendiente. La diferencia numérica frente a
P5-05 Mac permanece pendiente de investigación, sin tolerancia ni aprobación implícita.

### Serie oficial independiente Windows

Andy ejecutó una sola serie oficial sobre el commit
`83d81f262f8423e20832462e478222dc4129faa0`. El ZIP original recibido,
`p5-06-serie-oficial-windows-83d81f2.zip`, permanece intacto **fuera de Git**
en Downloads (SHA-256
`cca7a2b3b91cea9ec05046653b66e283677e1afee812d1da629b93b7d1e353b8`).
La copia pública depurada está en
`resultados/p5-06-benchmark-windows-andrea/evidencia-publica.zip` (SHA-256
`49b1f18d85267c40c3401b38a079dbac79ac48fad3f546ac3bcded72a0b4c407`).
El `README.md` de esa carpeta enumera los hashes originales y públicos de los seis
miembros, las 15 sustituciones autorizadas y el procedimiento. El SHA-256
original de `benchmark.json` sigue identificando el archivo conservado fuera de Git.
Ambos índices
`SHA256SUMS.txt` verifican 5/5 archivos; el público es UTF-8 sin BOM. El ZIP
público no es idéntico al original y conserva las muestras y resultados técnicos.

La ejecución registró 10 pares de calentamiento excluidos y 50 pares medidos
control → supervisado, 10 reinicios excluidos y 50 reinicios directos medidos.
Los límites numéricos de Karen se cumplen: Δp50 = **0.88705 ms** (≤5),
Δp95 = **0.71957 ms** (≤10), p95 supervisado = **58.9775 ms** (≤150),
máximo supervisado = **60.6622 ms** (≤200) y **0** solicitudes normales
superiores a 500 ms. Los 50 reinicios medidos tienen READY con hashes y dos
hilos correctos; su p50/p95 total es **4015.30725/4799.444585 ms**, sin
umbral numérico de aceptación. La paridad control-supervisado local es exacta.

Ante P5-05 Mac se observó la misma clase 41 y confianza, y diferencia máxima
de bbox de **0.00006103515625 px**. Según la decisión comunicada de Karen del
**2026-11-02**, se acepta exclusivamente esa diferencia numérica de plataforma;
no se agregan tolerancias, y cualquier diferencia distinta requiere otra
revisión. El `benchmark.json` original conserva su clasificación anterior
`diferencia_numerica_pendiente`; esta decisión se documenta aquí sin reescribirlo.

El preflight registró AC y ahorro desactivado. La transcripción muestra
`OneDrive.Sync.Service` y `com.docker.backend` activos en la captura inicial de
procesos, aunque el preflight reportó `procesos_bloqueantes=[]`. La condición
se documenta sin declararla invalidante y queda para revisión de Karen antes
de afirmar aceptación integral de la serie. Este benchmark normal y sus
reinicios directos son distintos de la validación funcional simulada de
50 timeouts; no se repitieron mediciones ni se descartaron muestras.

## Inventario original del PR

- `resultados/P5-06-AUDITORIA-PREFLIGHT.md`
- `resultados/P5-06-DISENO-Y-ACEPTACION.md`
- `resultados/P5-06-EVIDENCIAS-PR.md`
- `resultados/p5-06-benchmark-mac-2026-11-01/README.md`
- `resultados/p5-06-benchmark-mac-2026-11-01/benchmark.json`
- `resultados/p5-06-benchmark-mac-2026-11-01/entorno-posterior.json`
- `resultados/p5-06-benchmark-mac-2026-11-01/entorno-previo.json`
- `resultados/p5-06-benchmark-mac-2026-11-01/observaciones.json`
- `resultados/p5-06-benchmark-mac-2026-11-01/resumen.json`
- `resultados/p5-06-benchmark.py`
- `resultados/p5-06-integracion/README.md`
- `resultados/p5-06-integracion/detector_exception/comandos.jsonl`
- `resultados/p5-06-integracion/detector_exception/errores.jsonl`
- `resultados/p5-06-integracion/detector_exception/percepcion.jsonl`
- `resultados/p5-06-integracion/detector_exception/resultado.json`
- `resultados/p5-06-integracion/invalid_output/comandos.jsonl`
- `resultados/p5-06-integracion/invalid_output/errores.jsonl`
- `resultados/p5-06-integracion/invalid_output/percepcion.jsonl`
- `resultados/p5-06-integracion/invalid_output/resultado.json`
- `resultados/p5-06-integracion/ok_envejecido_en_transporte/comandos.jsonl`
- `resultados/p5-06-integracion/ok_envejecido_en_transporte/errores.jsonl`
- `resultados/p5-06-integracion/ok_envejecido_en_transporte/percepcion.jsonl`
- `resultados/p5-06-integracion/ok_envejecido_en_transporte/resultado.json`
- `resultados/p5-06-integracion/sin_cuadro/comandos.jsonl`
- `resultados/p5-06-integracion/sin_cuadro/errores.jsonl`
- `resultados/p5-06-integracion/sin_cuadro/percepcion.jsonl`
- `resultados/p5-06-integracion/sin_cuadro/resultado.json`
- `resultados/p5-06-integracion/sin_cuadro_tics_periodicos/comandos.jsonl`
- `resultados/p5-06-integracion/sin_cuadro_tics_periodicos/errores.jsonl`
- `resultados/p5-06-integracion/sin_cuadro_tics_periodicos/percepcion.jsonl`
- `resultados/p5-06-integracion/sin_cuadro_tics_periodicos/resultado.json`
- `resultados/p5-06-integracion/stale/comandos.jsonl`
- `resultados/p5-06-integracion/stale/errores.jsonl`
- `resultados/p5-06-integracion/stale/percepcion.jsonl`
- `resultados/p5-06-integracion/stale/resultado.json`
- `resultados/p5-06-integracion/unreadable_image/comandos.jsonl`
- `resultados/p5-06-integracion/unreadable_image/errores.jsonl`
- `resultados/p5-06-integracion/unreadable_image/percepcion.jsonl`
- `resultados/p5-06-integracion/unreadable_image/resultado.json`
- `resultados/p5-06-validacion-detecciones/README.md`
- `resultados/p5-06-validacion-detecciones/comparacion.json`
- `resultados/p5-06-validacion-detecciones/p506-taza-supervisado.infer-run.json`
- `resultados/p5-06-validacion-detecciones/supervisado.jsonl`
- `resultados/p5-06-validacion-detecciones/un_proceso.jsonl`
- `resultados/p5-06-validacion-detecciones.py`
- `resultados/p5-06-validacion-real/README.md`
- `resultados/p5-06-validacion-real/jpeg_sinteticos/sintetico_geometria.jpg`
- `resultados/p5-06-validacion-real/jpeg_sinteticos/sintetico_negro.jpg`
- `resultados/p5-06-validacion-real/p506-real-supervisado.infer-run.json`
- `resultados/p5-06-validacion-real/supervisado.jsonl`
- `resultados/p5-06-validacion-real/un_proceso.jsonl`
- `resultados/p5-06-validacion-real/validacion.json`
- `resultados/p5-06-validacion-real.py`
