# Comparación funcional P5-06 con detección no vacía

La entrada es `docs/carro/objeto_taza_centro_cerca.jpg`, una imagen versionada y
citada en `resultados/P5-05-ACEPTACION.md`. Su SHA-256 es
`670fec5473ceda61b5a6283711596d610d75577dfb1bc9d5ffc8de52c1e9cbcc`,
el mismo de `ensayo-0012.jpg` en P5-05. No se usaron S01–S08 ni `datos/cuadros/`.

Para repetir con el checkpoint oficial verificado, elegir un directorio de salida
nuevo y ejecutar desde la raíz de este worktree:

```sh
.venv/bin/python resultados/p5-06-validacion-detecciones.py \
  --weights '/ruta/local/yolo11n.pt' \
  --output resultados/p5-06-validacion-detecciones-replica
```

`un_proceso.jsonl` y `supervisado.jsonl` son los eventos A→B v1. El manifiesto
`p506-taza-supervisado.infer-run.json` registra READY, hashes, hilos, plazos y
cierre. `comparacion.json` guarda las detecciones de ambas rutas, la referencia
P5-05 y las diferencias por campo. La regla de aceptación exige investigar
cualquier diferencia en el mismo host y runtime; esta ejecución obtuvo igualdad
exacta. Los tiempos y la duración de READY son observaciones funcionales, no un
benchmark ni una medición de IPC.
