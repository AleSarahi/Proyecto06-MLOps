# Contraste con los plazos de B (P5-16)

Generado por `python -m bench.limites`; no editar a mano.

## Reproducido (benchmark)

- Corrida: `mediciones/final-1` (`resumen.json` SHA-256 `883ec36a0149f8d0cc79efdf1d33bedcfafb350c78d4b334dee6a445631a0ec8`)
  - Equipo: laptop de A3 · energía: corriente · estado: completo · mediciones: 100 (sin calentamientos) · fallos aparte: 0
- Corrida: `mediciones/final-2` (`resumen.json` SHA-256 `84c8f45a18468dbb8c7d64fa0b194f6c350dbdddd2f1517c25dd11298b851cdc`)
  - Equipo: laptop de A3 · energía: corriente · estado: completo · mediciones: 100 (sin calentamientos) · fallos aparte: 0
- Corrida: `mediciones/final-3` (`resumen.json` SHA-256 `520768a9fe976b4acf93d15d5098c9479e37e9d4e4f388116b64ead79b837f6d`)
  - Equipo: laptop de A3 · energía: corriente · estado: completo · mediciones: 100 (sin calentamientos) · fallos aparte: 0

Se contrasta **la peor**: por etapa, el mayor p50, p95 y máximo de las 3 corridas.

| Etapa | p50 | p95 | Máximo |
|---|---|---|---|
| `preprocesamiento_ms` | 1.76 (`final-2`) | 2.43 (`final-2`) | 3.34 (`final-2`) |
| `inferencia_ms` | 85.15 (`final-2`) | 107.69 (`final-2`) | 138.49 (`final-2`) |
| `posprocesamiento_ms` | 5.10 (`final-2`) | 7.63 (`final-2`) | 9.60 (`final-2`) |
| `evento_ms` | 0.64 (`final-2`) | 0.89 (`final-2`) | 1.10 (`final-2`) |
| `politica_ms` | 2.07 (`final-2`) | 2.65 (`final-3`) | 3.64 (`final-2`) |
| `total_ms` | 94.87 (`final-2`) | 118.63 (`final-2`) | 154.38 (`final-2`) |

- Sobrecosto de `infer`: `mediciones/final-sobrecosto` (`sobrecosto.json` SHA-256 `785dea0f270a2cdc970dd5c6165fc8ac515747213919d64e25e12188b8545712`): p50 12.33, p95 14.70, máximo 16.49 ms. Se suma a `total_ms`, y la fila del timeout compara la solicitud completa.

## Declarado (plazos de B y ritmo de entrada)

- `config/control/plazos.yaml` (SHA-256 `bd51e1c1d97d4d196eb476fbaefc37baf627c8de769b2aad0d9213a56b561e22`)
- `detector_timeout_ms`: 500 ms
- `max_frame_age_ms`: 500 ms
- `validez_orden_ms`: 400 ms
- `watchdog_ms`: 600 ms
- `periodo_entrada_ms`: 200 ms (PEND-09, provisional: ≈ 5 fps hasta que B lo declare)

## Contraste

| Medido | p50 | p95 | Máximo | Plazo | Margen p95 | Veredicto | Razón |
|---|---|---|---|---|---|---|---|
| `total_ms + sobrecosto` | 107.21 | 133.33 | 170.87 | `detector_timeout_ms` = 500 | 366.67 | **cumple** | Una inferencia más larga que el plazo hace que A emita status=error (detector_timeout) y B frene (C9). |
| `total_ms + sobrecosto` | 107.21 | 133.33 | 170.87 | `max_frame_age_ms` = 500 | 366.67 | **cumple** | El comando sale cuando el cuadro ya tiene al menos total_ms de edad; pasado max_frame_age_ms, B lo rechaza por viejo y frena (C8). |
| `total_ms + sobrecosto` | 107.21 | 133.33 | 170.87 | `periodo_entrada_ms` = 200 | 66.67 | **cumple** | Si procesar un cuadro tarda más que el periodo de entrada, los cuadros se acumulan y cada uno llega más viejo que el anterior. |
| `intervalo` | 200.00 | 200.00 | 200.00 | `validez_orden_ms` = 400 | 200.00 | **cumple** | Entre dos comandos pasa el periodo de entrada o lo que tarde procesar un cuadro; si eso pasa validez_orden_ms, el adaptador frena por su cuenta entre cuadros. |
| `intervalo` | 200.00 | 200.00 | 200.00 | `watchdog_ms` = 600 | 400.00 | **cumple** | Si entre dos eventos pasa más que watchdog_ms, B emite STOP por falta de percepción aunque el detector siga funcionando. |

Todo en ms. `intervalo` = el mayor entre `periodo_entrada_ms` y `total_ms`: el tiempo entre dos eventos seguidos. Para salir con 0 debe cumplir el máximo, no solo el p95: un solo cuadro fuera de plazo ya es un STOP de B.

## No medido

- Captura en la ESP32-CAM y transmisión por WiFi, ni el costo de comunicación de P5-06 si el detector corre en otro proceso: la edad real del cuadro es mayor que la de la tabla. La lectura y decodificación del JPEG sí entran, con el sobrecosto de infer.
- Carga y calentamiento del modelo: el benchmark los deja fuera. En infer también deben quedar fuera del reloj del run; si no, el primer cuadro ya llega viejo (lo encontró T16).
- Frenado mecánico, distancia de frenado y movimiento del carro: el control es virtual y los comandos solo se registran.

## Advertencias

- Ninguna.
