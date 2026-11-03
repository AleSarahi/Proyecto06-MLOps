# Integración A→B de P5-06 (C8 y C9)

Estas evidencias se generaron con `tests/test_infer_control_integracion.py`. En cada carpeta,
`percepcion.jsonl` contiene la salida del publicador de A; `comandos.jsonl` y `errores.jsonl`
son las salidas del supervisor y adaptador virtual de B; `resultado.json` enlaza evento,
`frame_id`, causa, acción esperada y acción observada.

Para reproducir desde la raíz del worktree P5-06:

```sh
P5_06_EVIDENCIA_DIR="$PWD/resultados/p5-06-integracion" \
  .venv/bin/pytest -q -p no:cacheprovider tests/test_infer_control_integracion.py
```

Las imágenes son JPEG sintéticos creados por la prueba. La predicción se sustituye por un
doble determinista para provocar cada estado; la lectura JPEG, la construcción y validación
de eventos A→B, la política, el supervisor y el adaptador virtual son código del proyecto.
El `model_sha256` de `a` repetida es un identificador de prueba, no un hash de pesos reales.
No se ejecutó inferencia del modelo sobre S01–S08 ni sobre `datos/cuadros/`.

En `sin_cuadro`, se llama directamente a `tick()` después de superar `watchdog_ms` y B
registra `watchdog_vencido`. En `sin_cuadro_tics_periodicos`, se usa `paso_reloj_ms=100`:
la orden de 400 ms vence primero y B registra `orden_vencida` a los 500 ms. Ambos recorridos
terminan en STOP sin crear un evento de percepción para la ausencia de cuadro.

En `ok_envejecido_en_transporte`, A publica `b_ok_tardio` como `ok` con 0 ms de edad.
B lo recibe a los 701 ms, cuando tiene 501 ms desde la captura, y registra
`cuadro_viejo` y STOP. Es distinto del `stale` que A publica cuando el cuadro ya
supera el plazo antes de salir de A. La entrada armada de `casos/C8/` también
incluye un `ok` de 540 ms al emitirlo; B lo rechaza por la misma regla de edad.

`detector_timeout` queda pendiente de P5-06; estas evidencias no lo implementan ni lo simulan.
Son resultados de pruebas locales, sin confirmación atribuida a B2 o B3.
