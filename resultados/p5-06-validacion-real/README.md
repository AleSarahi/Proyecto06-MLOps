# Validación funcional P5-06 con checkpoint real

Esta carpeta se generó con `resultados/p5-06-validacion-real.py`; no contiene
benchmark, series de latencia ni mediciones p50/p95. Las imágenes son JPEG
sintéticos creados por el script, sin usar S01–S08 ni `datos/cuadros/`.

Para repetir desde la raíz del worktree, obtener primero el checkpoint oficial
v8.3.0 según `resultados/P5-05-REVISION-A3.md` y verificar 5 613 764 bytes y
SHA-256 `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
Elegir una carpeta de salida **nueva**:

```sh
.venv/bin/python resultados/p5-06-validacion-real.py \
  --weights '/ruta/local/yolo11n.pt' \
  --output resultados/p5-06-validacion-real-replica
```

`un_proceso.jsonl` y `supervisado.jsonl` contienen los eventos A→B v1 de las
mismas imágenes. `p506-real-supervisado.infer-run.json` registra los plazos,
SHA-256, READY y cierre. `validacion.json` comprueba orden, IDs, dimensiones,
tiempos, contrato, hashes, hilos y detecciones por `frame_id`.

En esta ejecución, ambas rutas produjeron `ok` con `detections=[]` para los dos
JPEG. La igualdad de detecciones está demostrada **solo para esas escenas sin
detecciones**; no prueba equivalencia de cajas y confianza cuando el modelo ve
un objeto. El tiempo de READY se registra como observación de esta ejecución,
sin usarlo como benchmark ni criterio de rendimiento.
