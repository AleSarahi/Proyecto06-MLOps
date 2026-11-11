# S1 · Cambio sostenido de confianza (escenario adicional)

> Issue #32 · extra **S1**, nivel solicitado **8** (secuencia temporal con transición, persistencia y
> recuperación). Corrida `s1-transicion-20261111T180825Z` · commit del código
> `ac12754fb1f0382865da6c0cf5cc92203c69c97e` (sin cambios pendientes) · **mismo**
> `config_ref c574ee88…ff6c`, `model_ref 0ebbc80d…6ee1` y referencia (0.3808) que C1 y C2.

| | |
|---|---|
| **Entrada** | Secuencia `s1-transicion` ([`config/p6/fuentes.yaml`](../../../../config/p6/fuentes.yaml)), 100 frames a 1 fps del respaldo [`datos/p6/frames/s1-transicion/`](../../../../datos/p6/frames/s1-transicion/), reproducidos como un solo stream de 100 s: **[0, 30) s** día (video `dia`, 210–240 s; tramo que no usan la referencia ni C1) → **[30, 50) s** noche (video `noche`, 0–20 s, el de C2) → **[50, 70) s** noche (video `noche2`, 0–20 s) → **[70, 100) s** día (video `dia`, 240–270 s). Ninguna imagen ni ningún score se alteró. |
| **Comando** | `uv run python -m monitor correr --segmento s1-transicion --salida evidencias/p6/extras/s1-transicion` (tiempo real; el portal estaba abierto en paralelo para F1) |
| **Condición probada** | Que la regla `cambio-sostenido-v1` (proporción baja − referencia ≥ 0.20 durante **3** ventanas suficientes seguidas) se abra solo después de la persistencia configurada, que ninguna alerta se repita mientras la condición dura y que las dos alertas se cierren cuando la escena vuelve a la normalidad. C2 no prueba esto: su regla es de 1 ventana y su video no llega a 3 ventanas suficientes. |
| **Esperado** | Ventanas 0–2 normales. Ventana 3: abre `baja-confianza-v1` (1 ventana) pero no la sostenida (1 de 3). Ventana 4: sigue abierta, sin repetirse; la sostenida va en 2 de 3. Ventana 5: abre `cambio-sostenido-v1`. Ventana 6: ambas siguen abiertas sin duplicarse. Ventana 7 (día): ambas se cierran. Ventanas 8–9 normales. |

## Observado ([`ventanas.jsonl`](ventanas.jsonl), [`alertas.jsonl`](alertas.jsonl))

| Ventana | Escena | Baja / candidatas | Proporción | − ref. | `baja-confianza-v1` | `cambio-sostenido-v1` | Alertas activas |
|---|---|---|---|---|---|---|---|
| 0 [0, 10) | día | 72/232 | 0.310 | −0.07 | no cumple | no cumple (0/3) | 0 |
| 1 [10, 20) | día | 59/144 | 0.410 | +0.03 | no cumple | no cumple (0/3) | 0 |
| 2 [20, 30) | día | 24/96 | 0.250 | −0.13 | no cumple | no cumple (0/3) | 0 |
| 3 [30, 40) | noche | 63/79 | **0.797** | +0.42 | **cumple → abre** | cumple (1/3) | 1 |
| 4 [40, 50) | noche | 36/43 | **0.837** | +0.46 | cumple (abierta) | cumple (2/3) | 1 |
| 5 [50, 60) | noche 2 | 150/211 | **0.711** | +0.33 | cumple (abierta) | **cumple (3/3) → abre** | 2 |
| 6 [60, 70) | noche 2 | 199/276 | **0.721** | +0.34 | cumple (abierta) | cumple (abierta) | 2 |
| 7 [70, 80) | día | 26/111 | 0.234 | −0.15 | **no cumple → cierra** | **no cumple → cierra** | 0 |
| 8 [80, 90) | día | 40/130 | 0.308 | −0.07 | no cumple | no cumple | 0 |
| 9 [90, 100) | día | 43/136 | 0.316 | −0.06 | no cumple | no cumple | 0 |

Todas las ventanas fueron suficientes (≥ 20 candidatas).

| Alerta | Abierta (UTC) | Severidad | Ventanas que la originaron | Eventos | Cerrada |
|---|---|---|---|---|---|
| `s1-transicion-20261111T180825Z-baja-confianza-v1-v003` | 18:09:25.081 | advertencia | 3 | 10 | 18:10:05.083, ventana 7 |
| `s1-transicion-20261111T180825Z-cambio-sostenido-v1-v005` | 18:09:45.082 | **crítica** | 3, 4, 5 (0.797, 0.837, 0.711) | 30 | 18:10:05.083, ventana 7 |

Motivo de la sostenida: «Cambio sostenido: 3 ventanas seguidas con proporción de baja confianza
(0.797, 0.837, 0.711) al menos 0.2 sobre la referencia 0.381. Última: 150/211 candidatas con
s < 0.3 (proporción 0.711) en la ventana 5 [50 s, 60 s).»

**Resultado: coincide con lo esperado.** La sostenida se abre 20 s después que la de una ventana, ni
antes ni con una ventana menos; ninguna se repite (2 alertas en 4 ventanas que cumplen) y la
primera ventana de día suficiente cierra las dos.

## Registros vinculados

- **Eventos:** 100 `ok` (80 frames aceptados, 14 en duda, 6 en zona baja, todos de noche, p. ej.
  `s1-transicion-20261111T180825Z-s1-transicion-t1-f000300`, máx. 0.150, a los 40 s).
- **Capturas:** 37/37 resueltas con SHA-256 (motivos: 30 `alerta`, 14 `zona_duda`, 10
  `muestra_normal`, 6 `zona_baja`). Las 30 de la alerta sostenida son los frames de las ventanas 3–5.
- **Métricas base** ([`metricas.json`](metricas.json)): G1 286.64 ms · G2 1.009 fps · G3 384.14 MiB ·
  G4 0.4883 · G5 1.0 · G6 1.0 · G7 **2** (ventanas 5 y 6).
- **Métricas adicionales** ([`metricas_extra.json`](metricas_extra.json)): el PSI de scores (X3) por
  ventana sigue la transición: 0.12, 0.24, 0.29 (día) → **1.89, 2.53, 0.61, 0.68** (noche) → 0.53,
  0.08, 0.13 (día). X5 = 1.0 en todas: no hubo pérdida de frames, el cambio es de la escena.
- **Portal:** [`../portal/s1/vivo-1-en-vivo.png`](../portal/s1/vivo-1-en-vivo.png) (a los 62 frames,
  con las dos alertas abiertas, tomado durante la corrida), [`../portal/16-alertas-s1.png`](../portal/16-alertas-s1.png),
  [`../portal/17-corrida-s1.png`](../portal/17-corrida-s1.png) y
  [`../portal/10-dashboard-s1-g4.png`](../portal/10-dashboard-s1-g4.png) (G4 por ventana con la
  referencia y las ventanas con alerta sombreadas).

## Verificación

- `python evidencias/p6/recalcular.py evidencias/p6/extras/s1-transicion` → todo coincide
  ([`../../recalculo/extras-s1-transicion.txt`](../../recalculo/extras-s1-transicion.txt)): zonas
  recontadas desde los scores, G1–G7 y cada ventana de cada alerta.
- `python evidencias/p6/recalcular_extras.py evidencias/p6/extras/s1-transicion` → todo coincide
  ([`../../recalculo/x-s1-transicion.txt`](../../recalculo/x-s1-transicion.txt)): X1–X5 y «la alerta
  sostenida abre en la ventana 5», la tercera suficiente seguida que cumple.
- `uv run python -m monitor verificar-capturas evidencias/p6/extras/s1-transicion` → 37/37.
- Las ventanas 3 y 4 son los mismos frames que las ventanas 0 y 1 de C2 y dan exactamente las mismas
  cuentas (63/79 y 36/43): la inferencia es determinista.
