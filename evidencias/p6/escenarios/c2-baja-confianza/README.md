# C2 · Baja confianza

> Issue #23 (R6.2). Corrida `c2-20261109T042757Z` · commit del código `d5ab5971fd8b960018bd8d2c0f04bb5077a92132`
> (sin cambios pendientes) · **mismo** `config_ref c574ee88…ff6c` y `model_ref 0ebbc80d…6ee1` que la referencia y C1.

| | |
|---|---|
| **Entrada** | Segmento `c2`: 0–24 s del video «Night Traffic» (Chalie Juno, CC BY, `jKl0o9Ydi5Q`), 24 frames a 1 fps del respaldo [`datos/p6/frames/c2/`](../../../../datos/p6/frames/c2/). La condición es de **poca luz** (noche, faros, objetos lejanos). No se alteró ninguna imagen ni ninguna puntuación. |
| **Comando** | `uv run python -m monitor correr --segmento c2 --salida evidencias/p6/escenarios/c2-baja-confianza` (tiempo real) |
| **Umbrales y ventana** | inferior 0.30 / superior 0.60, fijados antes de la corrida ([`docs/p6/umbrales.md`](../../../../docs/p6/umbrales.md)); ventanas de 10 s con mínimo de 20 candidatas. Regla `baja-confianza-v1`: proporción baja ≥ 0.60 en 1 ventana suficiente. |
| **Esperado** | Las salidas reales de YOLO11n caen en las zonas baja y duda; la política las clasifica; se guardan los eventos y sus imágenes; se genera la alerta de baja confianza cuando una ventana suficiente cumple la condición. |
| **Salidas del modelo** | [`eventos.jsonl`](eventos.jsonl): 24 eventos `ok`, 141 candidatas (scores entre 0.100 y 0.626). Frames por zona: **9 baja**, 13 duda, 2 aceptadas. |
| **Ventanas** ([`ventanas.jsonl`](ventanas.jsonl)) | v0 [0,10) s: 63/79 bajas = **0.797** → cumple · v1 [10,20) s: 36/43 = **0.837** → cumple (la alerta sigue abierta y no se repite) · v2 [20,24) s: 19 candidatas < 20 → **insuficiente** (no se cuenta como normal y no cierra la alerta). La regla sostenida llega a 2 de las 3 ventanas que necesita y no se dispara. |
| **Alerta** ([`alertas.jsonl`](alertas.jsonl)) | `c2-20261109T042757Z-baja-confianza-v1-v000` · 2026-11-09T04:28:08.121Z · severidad **advertencia** · motivo «Baja confianza: 63/79 candidatas con s < 0.3 (proporción 0.797) en la ventana 0 [0 s, 10 s), umbral 0.6.» · acción sugerida: revisar iluminación, oclusión, distancia y escena · vinculada con los 10 eventos de la ventana 0, la regla, el `config_ref` y el `model_ref`. |
| **Imágenes vinculadas** | 23 capturas (motivos: 9 `zona_baja`, 13 `zona_duda`, 10 `alerta`, 2 `muestra_normal`), 23/23 resueltas con su SHA-256. Ejemplo: evento `c2-20261109T042757Z-c2-f000210` (9 candidatas, todas bajas; máx. 0.221) → `capturas/c2-20261109T042757Z-c2-f000210.jpg`. |
| **Métricas** | G1 484.42 ms · G2 1.031 fps · G3 377.18 MiB · G4 **0.8298** · G5 1.0 (23/23) · G6 1.0 · G7 1 |
| **Recálculo** | [`../../recalculo/escenarios-c2-baja-confianza.txt`](../../recalculo/escenarios-c2-baja-confianza.txt): recuenta las zonas desde los scores, confirma que la alerta corresponde a una ventana suficiente que cumple y que sus eventos existen. Todo coincide. |
| **Portal** | [`03-alertas.png`](../../portal/03-alertas.png) (lista con momento, motivo, severidad y acción), [`04-alerta-c2.png`](../../portal/04-alerta-c2.png) (alerta → ventana → 10 eventos con miniaturas), [`05-evento-c2-baja.png`](../../portal/05-evento-c2-baja.png) (evento f000210: imagen con cajas rojas de zona baja, scores, ventana y enlace a la alerta), [`06-eventos-c2-baja.png`](../../portal/06-eventos-c2-baja.png) (filtro zona = baja), [`07-corrida-c2.png`](../../portal/07-corrida-c2.png) (ventanas, reglas «insuficiente», métricas y configuración). |
| **Nivel de verificación** | Observado (corrida con el modelo real) y recalculado. La lógica de las reglas también tiene pruebas sintéticas (`tests/test_p6_unidad.py`), que **complementan** C2 pero no lo sustituyen. |
