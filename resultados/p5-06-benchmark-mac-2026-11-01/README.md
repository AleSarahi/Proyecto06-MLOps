# Serie oficial Mac P5-06 · 1 de noviembre de 2026

`benchmark.json` es la salida bruta de una sola ejecución del benchmark P5-06
(SHA-256 `83e0d2a4bfa8262bf9c7f389ab16ebc101f77db4cbf92cec2d757e8aacda4372`).
Contiene las 50 muestras de cada ruta, 10 calentamientos excluidos por ruta, 10
reinicios excluidos, 50 reinicios medidos y todas sus fases. `resumen.json` es
derivado. `entorno-previo.json` y `entorno-posterior.json` conservan hardware,
energía, carga y procesos. `observaciones.json` documenta las desviaciones.

Se usó `docs/carro/objeto_taza_centro_cerca.jpg`, idéntico por SHA-256 al
`ensayo-0012.jpg` de P5-05, con el checkpoint oficial v8.3.0 verificado. El orden
fue control → supervisado → reinicio. La diferencia entre las dos primeras rutas
mide el conjunto de supervisión e IPC, no solo el transporte.

Comando ejecutado desde la raíz de este worktree:

```sh
.venv/bin/python resultados/p5-06-benchmark.py \
  --weights '/Users/heribertovs/Library/Application Support/P5-05/yolo11n.pt' \
  --output resultados/p5-06-benchmark-mac-2026-11-01/benchmark.json \
  --responsable A1 \
  --modo-energia bateria-descargando
```

Para reproducir, verificar previamente los hashes y usar un destino **nuevo**.
El argumento de energía refleja el preflight. Las instantáneas en
`benchmark.json` muestran que las tres etapas se ejecutaron con alimentación
AC; `observaciones.json` conserva esta corrección sin modificar la salida bruta.
El preflight detectó procesos de Codex y WindowServer con uso notable de CPU.
No hubo solicitudes fallidas ni muestras descartadas. Esta serie Mac no
constituye aprobación de rendimiento: faltan los umbrales de Karen y la
validación independiente en Windows.
