# Proyecto 6 · Umbrales, referencia, ventanas y reglas de alerta

> Issues #11, #12, #13 y #16 (R3.1, R3.2, R3.3 y R5.1). Configuración:
> [`config/p6/monitoreo.yaml`](../../config/p6/monitoreo.yaml), con `config_ref`
> `c574ee88333cbf676b469df9ddbb6f1cf2c1cf0df1d2c3499631fadbfecaff6c`. Los umbrales se fijaron **antes** de correr
> C1 y C2 y no cambiaron entre las corridas.

## Política de zonas (R3.2)

| Zona | Condición | Qué significa |
|---|---|---|
| `baja` | s < 0.30 | Baja confianza: se registra, se captura y cuenta para la regla de alerta. |
| `duda` | 0.30 ≤ s < 0.60 | Caso dudoso: se registra y se captura. |
| `aceptada` | s ≥ 0.60 | Aceptada **por la política**; no afirma que la detección sea correcta. |

- La igualdad con el inferior es duda y la igualdad con el superior es aceptada (lo prueba
  `tests/test_p6_unidad.py::test_bordes_de_zona`).
- **Por candidata:** cada detección del evento tiene su `score` y su `zona`.
- **Por frame:** `zona_frame` es la zona de la candidata de mayor score; el evento también guarda `conteo_zonas`
  (baja, duda, aceptada) y `n_candidatas`, que dan el contexto del frame.
- **Estados aparte:** `sin_detecciones` (cero candidatas) y `error` (imagen ilegible o fallo del modelo) no tienen
  zona ni confianza; `score_max` es `null`, nunca 0. En detección no existe «candidata sin puntuación»: toda
  detección trae score.
- **Filtro de salida del detector** ([`config/p6/detector.json`](../../config/p6/detector.json)): piso de
  confianza 0.10, NMS con IoU 0.7, `max_det` 300, entrada de 640 px con letterbox. El piso está **por debajo** del
  inferior (`monitor.config.cargar` falla si no), así que la zona baja se puede observar: en C2 hay candidatas
  desde 0.100.
- **Denominador:** las proporciones se calculan **por candidata**. Los conteos de frames se reportan aparte, sin
  mezclar las dos unidades.

## Referencia y elección de umbrales (R3.1)

Corrida de referencia: segmento `referencia` (minutos 0:00–1:30 del video de día, en condiciones
representativas), `run_id referencia-20261109T042407Z`, commit `d5ab597`, mismo modelo y configuración que C1 y
C2. Resultado: [`evidencias/p6/referencia/referencia.json`](../../evidencias/p6/referencia/referencia.json).

| Observación de referencia | Valor |
|---|---|
| Candidatas / frames | 1715 / 90 |
| Cuantiles del score por candidata (p10 / p25 / p50 / p75 / p90) | 0.138 / 0.211 / 0.407 / 0.650 / 0.730 |
| Cuantiles del score máximo por frame (p5 / p50 / p95) | 0.707 / 0.784 / 0.888 |
| Frames por zona | 90 aceptados, 0 duda, 0 baja |
| Proporción de baja confianza (s < 0.30) | **0.3808** (653/1715) |
| Proporción baja por ventana (min / media / max, σ) | 0.212 / 0.351 / 0.527, σ 0.093 |

Por qué se eligieron estos valores:

- **Superior = 0.60.** En la referencia, el score máximo de cada frame está siempre por encima de 0.70 (p5 = 0.707).
  Con 0.60, todo frame de operación normal tiene al menos una detección aceptada y queda margen de 0.10 antes de
  que un frame normal pase a duda. Aun así, el 68.7 % de las candidatas queda por debajo de 0.60 (p75 = 0.650): el umbral clasifica cada candidata, no solo el frame.
- **Inferior = 0.30.** Separa las candidatas débiles (objetos lejanos o parciales) de las dudosas. En la referencia
  cae cerca del cuartil 25–50 (p25 = 0.211, p50 = 0.407), así que la proporción baja normal está alrededor de 0.38.
  Esa proporción es estable entre ventanas (σ 0.093), lo que la hace útil como indicador.
- **Umbral de la alerta de baja confianza = 0.60.** Ninguna ventana de la referencia lo alcanzó (máximo 0.527).
  Queda 0.07 sobre el peor caso observado y 0.22 sobre la media (unas 2.7 σ).
- **Tolerancia de la regla sostenida = 0.20** sobre la referencia (umbral efectivo 0.58): más de 2 σ por ventana,
  y además debe repetirse en 3 ventanas, así que una variación normal aislada no la dispara.
- **Mínimo de 20 candidatas por ventana:** la referencia tiene entre 104 y 315 por ventana. Con menos de 20, una
  sola detección mueve la proporción más de 0.05.

La exploración previa con el modelo real sobre los videos candidatos (día ≈ 0.28–0.46 bajo 0.30; noche ≈
0.75–0.94) se usó para escoger los segmentos. La justificación formal es la referencia de arriba.

## Ventanas, mínimo y evidencia insuficiente (R3.3)

- **Ventanas** de 10 s de video sin traslape (10 frames a 1 fps).
- **Mínimo:** 20 candidatas puntuadas. Por debajo, la ventana queda `insuficiente`. Eso **no es normal ni
  alerta**: no suma ventanas consecutivas, no reinicia la cuenta y no cierra una alerta abierta. En C2, la ventana
  2 (4 frames, 19 candidatas) es insuficiente y la alerta sigue abierta.
- **Identidad de la serie:** la referencia guarda su `config_ref` y su `model_ref`. Una corrida con otro
  `config_ref` falla al cargar la referencia (`corrida.cargar_referencia`): si cambian el modelo, el
  preprocesamiento o la configuración, la serie es otra y hay que volver a correr la referencia.

## Reglas de alerta (R5.1)

| rule_id | Condición | Ventana / persistencia | Datos insuficientes | Severidad | Acción sugerida |
|---|---|---|---|---|---|
| `baja-confianza-v1` | proporción baja de la ventana ≥ 0.60 | 1 ventana suficiente | Resultado `insuficiente`: no alerta, no cierra | advertencia | Revisar las capturas de la ventana (iluminación, oclusión, distancia, escena) y comparar con la referencia antes de concluir algo del modelo. |
| `cambio-sostenido-v1` | proporción baja − referencia (0.3808) ≥ 0.20 | 3 ventanas suficientes seguidas (las insuficientes no cuentan ni reinician) | `insuficiente`; sin referencia válida → `sin_referencia` | crítica | Investigar la fuente (cámara, horario, clima) y el preprocesamiento; la confianza no confirma drift ni pérdida de calidad. |

- **Apertura:** cuando la regla cumple en el número de ventanas requerido y no hay otra alerta abierta de la misma
  regla. Mientras la condición siga, no se repite.
- **Cierre:** la primera ventana *suficiente* que no cumple; queda `cerrada_en` y `cerrada_por_ventana`.
- **Vínculos:** cada alerta guarda `rule_id`, la regla con sus parámetros, `config_ref`, `model_ref`, las ventanas
  que la originaron (con n y proporción) y los `event_ids` de esas ventanas.
- **Pruebas de lógica** (datos sintéticos, que no reemplazan a C2): `tests/test_p6_unidad.py` (insuficiente,
  transitorio, sostenido, cierre, sin referencia) y `tests/test_p6_integracion.py`.
- **Lo que no se afirma:** una alerta inicia una investigación. Una baja confianza no prueba un error del modelo
  ni drift, y no se propone reentrenar.
