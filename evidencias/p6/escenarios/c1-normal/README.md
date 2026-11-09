# C1 · Operación normal

> Issue #22 (R6.1). Corrida `c1-20261109T042610Z` · commit del código `d5ab5971fd8b960018bd8d2c0f04bb5077a92132`
> (sin cambios pendientes) · `config_ref c574ee88333cbf676b469df9ddbb6f1cf2c1cf0df1d2c3499631fadbfecaff6c` ·
> `model_ref 0ebbc80d…6ee1`.

| | |
|---|---|
| **Entrada** | Segmento `c1`: 120–210 s del video de día «4K Road traffic video for object detection and tracking» (Karol Majek, CC BY, `MNn9qKG2UFI`), 90 frames a 1 fps del respaldo [`datos/p6/frames/c1/`](../../../../datos/p6/frames/c1/) (manifiesto con SHA-256). Es otro tramo que el de la referencia (0–90 s). |
| **Comando** | `uv run python -m monitor correr --segmento c1 --salida evidencias/p6/escenarios/c1-normal` (tiempo real, velocidad 1.0) |
| **Configuración** | [`config/p6/monitoreo.yaml`](../../../../config/p6/monitoreo.yaml): umbrales 0.30/0.60, ventanas de 10 s, mínimo de 20 candidatas, referencia 0.3808. Copia efectiva en [`run.json`](run.json) → `config_efectiva`. |
| **Esperado** | Inferencias reales; frames en zona aceptada; eventos persistidos y consultables; métricas coherentes con 1 fps; ninguna alerta si ninguna ventana cumple su regla. Nada se fabrica: las alertas siguen la regla. |
| **Observado** | 90 eventos `ok` (90 frames aceptados; 2050 candidatas). Proporción baja por ventana: 0.376, 0.339, 0.282, 0.380, 0.314, 0.353, 0.421, 0.419, 0.509, todas suficientes y por debajo de 0.60 (`baja-confianza-v1` no cumple) y de 0.58 (`cambio-sostenido-v1` no cumple). **0 alertas.** 9 capturas de muestra normal (1 de cada 10 frames), todas resueltas. Descartes: 2610 por muestreo y 0 por saturación. |
| **Métricas** ([`metricas.json`](metricas.json)) | G1 p95 499.05 ms · G2 1.006 fps · G3 384.2 MiB · G4 0.3859 · G5 1.0 (9/9) · G6 1.0 · G7 0 |
| **Recálculo** | [`../../recalculo/escenarios-c1-normal.txt`](../../recalculo/escenarios-c1-normal.txt): todo coincide. |
| **Portal** | [`01-eventos-c1.png`](../../portal/01-eventos-c1.png) (lista de eventos de C1), [`02-evento-c1-normal.png`](../../portal/02-evento-c1-normal.png) (evento `c1-20261109T042610Z-c1-f003870` con imagen, cajas y zonas), [`08-alertas-c1-vacio.png`](../../portal/08-alertas-c1-vacio.png) (sin alertas, con la aclaración de que eso no equivale a operación sana), [`09-corrida-c1.png`](../../portal/09-corrida-c1.png) (ventanas, reglas y métricas). |
| **Nivel de verificación** | Observado: corrida ejecutada con el modelo, el código y la configuración identificados. Recalculado: `recalcular.py`. |

Archivos: `run.json`, `eventos.jsonl`, `observaciones.jsonl`, `ventanas.jsonl`, `alertas.jsonl` (vacío),
`capturas.jsonl`, `capturas/`, `metricas.json`.
