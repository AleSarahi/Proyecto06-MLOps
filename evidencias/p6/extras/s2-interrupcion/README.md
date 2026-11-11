# S2 · Interrupción y recuperación de la fuente (escenario adicional)

> Issue #33 · extra **S2**, nivel solicitado **10** (secuencia compuesta: fallo, diagnóstico y
> reacción, recuperación y verificación posterior). Corrida `s2-interrupcion-20261111T180638Z` ·
> commit `ac12754fb1f0382865da6c0cf5cc92203c69c97e` (sin cambios pendientes) · `config_ref c574ee88…ff6c` ·
> `vigilancia_ref` en [`run.json`](run.json).

| | |
|---|---|
| **Entrada** | Segmento `s2-interrupcion`: 240–300 s del video de día (60 frames a 1 fps del respaldo [`datos/p6/frames/s2-interrupcion/`](../../../../datos/p6/frames/s2-interrupcion/)). |
| **Fallo inyectado** | `--corte 20:40`: entre los 20 y los 40 s del segmento la fuente **no entrega** los frames (se pierden, como un stream cuya conexión se cae). El ritmo real continúa. En lugar de cada frame perdido, el monitor solo observa que a esa hora no llegó nada (latido `sin_senal` en `observaciones.jsonl`). La inyección queda declarada en `run.json → fuente.inyeccion`. Los demás frames no se alteran. |
| **Comando** | `uv run python -m monitor correr --segmento s2-interrupcion --corte 20:40 --salida evidencias/p6/extras/s2-interrupcion` (tiempo real), con `uv run python -m monitor portal` abierto para capturar la vista en vivo. |
| **Reglas** | [`config/p6/vigilancia.yaml`](../../../../config/p6/vigilancia.yaml): `fuente-sin-senal-v1`, crítica, se abre si pasan **más de 5 s** sin frames y se cierra tras **3 frames seguidos**. Las reglas de confianza no cambian. |
| **Esperado** | (1) Antes del corte: ventanas 0–1 normales, sin alertas. (2) Fallo: dejan de llegar frames a los 20 s. (3) Diagnóstico: la alerta se abre unos 6 s después del último frame, durante el corte, nombrando el último frame recibido. Las ventanas 2–3 quedan *insuficientes* (sin frames): no son «normales» ni abren o cierran alertas de confianza. (4) Recuperación: vuelven los frames a los 40 s y la alerta se cierra al tercero. (5) Verificación posterior: ventanas 4–5 suficientes y normales, alertas activas en 0. |

## Observado

| Etapa | Registro | Valor |
|---|---|---|
| Antes | ventanas 0–1 | 10 frames cada una, suficientes, proporción baja 0.234 y 0.308; 0 alertas |
| Fallo | `run.json → conteos.fuente` | 20 frames `sin_senal` perdidos, 20 intentos de reconexión fallidos, 1 reconexión; 40 recibidos |
| Diagnóstico | [`alertas.jsonl`](alertas.jsonl) | `s2-interrupcion-20261111T180638Z-fuente-sin-senal-v1-000`, **crítica**, abierta 18:07:20.998 UTC, «Sin frames de la fuente durante 6.0 s (umbral 5 s); último frame s2-interrupcion-f007770 (259.0 s del video).» `detectada_ms − sin_senal_desde_ms` = 32 607.7 − 26 607.7 = 6 000 ms; `deteccion_tardia: false` (se detectó durante el corte) |
| Reacción | ventanas 2–3 | `n_frames 0`, **insuficientes**, reglas de confianza `insuficiente` (no se cierran ni se abren), `alertas_activas 1` (G7) |
| Reacción | portal en vivo | [`vivo-2-sin-senal.png`](../portal/vivo-2-sin-senal.png): estado `sin_senal`, imagen congelada en el último frame y enlace a la alerta abierta |
| Recuperación | alerta | `recuperacion.primer_frame_ms` 47 607.7 → sin señal **21.0 s**; cerrada 18:07:38.293 UTC en la ventana 4 con los 3 frames de recuperación (`…f008400`, `…f008430`, `…f008460`); `frames_perdidos 20` |
| Verificación posterior | ventanas 4–5 | 10 frames cada una, suficientes, proporción baja 0.264 y 0.297, `alertas_activas 0`; [`vivo-4-recuperada.png`](../portal/vivo-4-recuperada.png) y [`vivo-5-terminada.png`](../portal/vivo-5-terminada.png) |

La alerta enlaza 4 eventos: el último antes del corte y los 3 de la recuperación
([`../portal/15-alerta-fuente-s2.png`](../portal/15-alerta-fuente-s2.png)).

**Resultado: coincide con lo esperado en las cinco etapas.**

Métricas de la corrida:

- **Base** ([`metricas.json`](metricas.json)): G1 294.57 ms · G2 **0.676 fps** (40 frames en ~59 s:
  el corte reduce el throughput de toda la corrida) · G3 382.25 MiB · G4 0.276 · G5 1.0 (4/4) ·
  G6 1.0 · G7 1.
- **Adicionales** ([`metricas_extra.json`](metricas_extra.json)): X5 disponibilidad por ventana
  **1.0, 1.0, 0.0, 0.0, 1.0, 1.0** (corrida 0.667 = 40/60); X3 `null` (insuficiente) en las ventanas
  sin frames, no 0; X1 `null` en esas ventanas por la misma razón.

Ver también [`../portal/12-dashboard-s2-x5.png`](../portal/12-dashboard-s2-x5.png) (X5 con la
caída sombreada) y [`../portal/18-corrida-s2.png`](../portal/18-corrida-s2.png).

## Vista en vivo durante la corrida (F1)

Capturas de `/vivo` tomadas mientras corría S2, cada una con el JSON de `/api/vivo` de ese instante:

| Momento | Captura | `vista` | Procesados |
|---|---|---|---|
| Antes del corte | [`vivo-1-en-vivo.png`](../portal/vivo-1-en-vivo.png) / [`.json`](../portal/vivo-1-en-vivo.json) | `en_vivo` | 12 |
| Durante el corte | [`vivo-2-sin-senal.png`](../portal/vivo-2-sin-senal.png) / [`.json`](../portal/vivo-2-sin-senal.json) | `sin_senal` | 20 |
| Primer frame de vuelta | [`vivo-3-recuperando.png`](../portal/vivo-3-recuperando.png) / [`.json`](../portal/vivo-3-recuperando.json) | `recuperando` | 21 |
| Recuperada | [`vivo-4-recuperada.png`](../portal/vivo-4-recuperada.png) / [`.json`](../portal/vivo-4-recuperada.json) | `en_vivo` | 30 |
| Fin | [`vivo-5-terminada.png`](../portal/vivo-5-terminada.png) / [`.json`](../portal/vivo-5-terminada.json) | `terminada` | 40 |

La captura de pantalla se toma unos 2 s después de la condición. Por eso la de «recuperando» puede
mostrar ya el siguiente estado; el JSON es el del instante exacto.

## Verificación

- `python evidencias/p6/recalcular_extras.py evidencias/p6/extras/s2-interrupcion` → todo coincide
  ([`../../recalculo/x-s2-interrupcion.txt`](../../recalculo/x-s2-interrupcion.txt)). Recalcula desde
  `observaciones.jsonl`:
  - el hueco supera el umbral;
  - el último frame es el de la alerta;
  - los frames perdidos son los 20 latidos;
  - la recuperación son los 3 primeros frames posteriores y la alerta cierra en la ventana del
    tercero;
  - X1–X5.
- `python evidencias/p6/recalcular.py evidencias/p6/extras/s2-interrupcion` → todo coincide
  ([`../../recalculo/extras-s2-interrupcion.txt`](../../recalculo/extras-s2-interrupcion.txt)): G1–G7
  y ventanas.
- `uv run python -m monitor verificar-capturas evidencias/p6/extras/s2-interrupcion` → 4/4.
- La lógica también se prueba con un reloj falso en `tests/test_p6_extras.py`:
  - apertura con latidos;
  - detección tardía sin latidos;
  - que una inferencia lenta (4.9 s) no se confunda con una caída;
  - que un latido en medio reinicie la recuperación.

  Estas pruebas complementan la corrida real, no la sustituyen.

**Límite:** el corte es una inyección controlada en el lector de frames, no una caída de red real.
Se eligió así para que sea reproducible: el mismo comando da el mismo corte.
