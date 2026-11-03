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
