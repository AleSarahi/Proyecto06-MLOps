# Límites del sistema (P5-16, E7)

Qué acredita este proyecto y qué no, y cómo se contrastan los tiempos medidos con los plazos de B. Los números
salen de las 3 corridas finales de P5-15 (`python -m bench`, #82), de lo que `infer` paga de más
(`python -m bench.sobrecosto`) y de `python -m bench.limites`, que escribe
[`final-contraste/contraste.md`](final-contraste/contraste.md). Aquí no se copian a mano los veredictos: se
enlaza el contraste.

> **Estado:** medición final hecha el 2026-11-01 con `config-detector-v1` (paso 2 de #13, `config_sha256`
> `6428a259…`) sobre S01–S08 de `datos-evaluacion-v1`. Los cinco plazos **cumplen hasta el máximo**.

## Qué acredita el control virtual

- Que el detector, **en CPU y en el equipo declarado (PEND-05)**, procesa un cuadro de 640×480 dentro de los
  plazos de B, con p50, p95 y máximo medidos sobre 100 ejecuciones después de 10 calentamientos.
- Que cada cuadro de las secuencias produce un evento del contrato v1 y que B responde con el comando que
  dicta su política, incluidos los casos de cuadro viejo, timeout del detector y ausencia de cuadros (C8, C9).
  Del timeout, solo **el lado de B**: responde a un evento `status=error` con `detector_timeout` armado en el
  caso. Que `infer` lo emita cuando la solicitud pasa `detector_timeout_ms` es de P5-06, que todavía no se
  fusiona; *pendiente* comprobarlo entonces.
- Que todo lo anterior se reproduce desde los archivos del repositorio con los hashes registrados:
  `bench.limites` comprueba que los CSV de la corrida tengan el SHA-256 que registró `resumen.json`.

## Qué no acredita

- **Movimiento físico:** el control es virtual; los comandos se registran y nunca mueven el carro.
- **Frenado:** no hay distancia de frenado, tiempo de reacción mecánico ni velocidad máxima segura. No se
  declara ninguna distancia.
- **Un FPS universal:** los tiempos valen para el equipo de PEND-05, conectado a la corriente, con el runtime
  y los hilos registrados en `resumen.json`. En otra máquina, o en batería, cambian (ver *Lo que ya se vio*).
- **La cadena completa de la cámara:** el benchmark parte de la imagen en memoria. La lectura y
  decodificación del JPEG se suman aparte (`bench.sobrecosto`), pero no se mide la captura en la ESP32-CAM, la
  transmisión por WiFi ni lo que agrega P5-06 (#86) al correr el predictor supervisado en otro proceso
  (comunicación entre procesos, supervisión y publicación del evento), así que la edad real de un cuadro al
  llegar a B es mayor que la de la tabla.
- **Escenas fuera del dominio:** el detector solo se probó con los objetos, la escena y la luz de PEND-04.

## Contraste con los plazos

```bash
uv run python -m bench.limites mediciones/final-1/ mediciones/final-2/ mediciones/final-3/ \
  --sobrecosto mediciones/final-sobrecosto/ --salida mediciones/final-contraste/
```

compara las corridas con `config/control/plazos.yaml`. Sigue la regla fijada antes de medir
([`README.md`](README.md#corrida-final-regla-fija-antes-de-medir)): se reportan las 3 y se contrasta **la
peor**, es decir, por etapa, el mayor p50, p95 y máximo de las tres (queda anotado de qué corrida salió cada
uno). A eso se suma lo que `infer` paga y el arnés no mide: leer el JPEG y la preparación de Ultralytics
(`final-sobrecosto`). Son dos mediciones distintas, así que la suma de sus p95 o de sus máximos es una
**estimación** del lado local, no un p95 medido de la solicitud (el p95 de una suma no es la suma de los p95).

**Alcance (Heri en #82):** todo se midió en un solo proceso, con el detector local de `bench.yolo` y
`DetectorJPEG`. P5-06 (#86) corre el predictor supervisado en otro proceso, y ni el arnés ni
`bench.sobrecosto` miden la comunicación entre procesos, la supervisión ni la publicación del evento. Por eso
este contraste dice cuánto margen deja el lado local; comprobar que la ruta supervisada cumple los plazos queda
a cargo de P5-06.

El sobrecosto **se midió con las 11 fotos de `docs/carro/`, no con S01–S08**: se decidió antes del paso 2 de
#13, cuando aún no se podía correr el detector sobre el conjunto. Son de celular (~1200×1600) y los cuadros del
conjunto, de 640×480; como casi todo el sobrecosto es leer el JPEG, con los cuadros del conjunto debería salir
menor. No cambia ningún veredicto.

| Medido | Plazo | Por qué importa |
|---|---|---|
| `total_ms` + sobrecosto (la solicitud completa de `infer`) | `detector_timeout_ms` (500) | Según lo planeado para P5-06 (Heri en #13), el timeout de A cubrirá la solicitud entera; si la pasa, A debe emitir `detector_timeout` y B frena (C9). Hoy `infer` no lo aplica: *pendiente* de P5-06. Sin `--sobrecosto` se compara `inferencia_ms`. |
| `total_ms` + sobrecosto | `max_frame_age_ms` (500) | El comando sale cuando el cuadro ya tiene al menos esa edad; si pasa el plazo, B lo rechaza (C8). |
| `total_ms` + sobrecosto | periodo de entrada (200, PEND-09) | Si procesar tarda más que el periodo, los cuadros se acumulan y llegan cada vez más viejos. |
| intervalo entre comandos | `validez_orden_ms` (400) | Si entre dos comandos pasa más, el adaptador frena por su cuenta. |
| intervalo entre eventos | `watchdog_ms` (600) | Si entre dos eventos pasa más, B frena por falta de percepción. |

El intervalo es el mayor entre el periodo de entrada y `total_ms` (+ sobrecosto). Cada fila lleva un
veredicto: **cumple** (hasta el máximo queda dentro), **cumple en p95** (el máximo lo pasa: algún cuadro se
pierde o llega tarde) o **no cumple** (el p95 lo pasa).

Las filas no son independientes:

- **La edad depende de la cola.** Si procesar tarda más que el periodo de entrada, cada cuadro espera a que
  termine el anterior, así que su edad pasa de `total_ms`. Por eso la fila de la edad nunca sale mejor que la
  del periodo: si el p95 pasa el periodo, la cola crece sin límite y la edad **no cumple** aunque `total_ms`
  esté lejos de 500 ms.
- **El intervalo no cambia con la cola.** Con cola, los eventos salen uno tras otro, cada `total_ms`, así que
  la validez de la orden y el watchdog se comparan igual.

**Para salir con `0` debe cumplir el máximo, no solo el p95.** `plazos.yaml` pide contrastar el p95, y la
tabla lo hace (con su margen), pero B decide cuadro por cuadro: un solo cuadro que pasa `max_frame_age_ms` o
`detector_timeout_ms` ya es un STOP. Un **cumple en p95** se reporta tal cual, con salida `1`, para que se vea
y se explique en vez de esconderlo en un percentil.

**Resultado** ([`final-contraste/contraste.md`](final-contraste/contraste.md), salida `0`, sin advertencias):

| Medido | p50 | p95 | Máximo | Plazo | Margen p95 | Veredicto |
|---|---|---|---|---|---|---|
| `total_ms` + sobrecosto | 107.21 | 133.33 | 170.87 | `detector_timeout_ms` = 500 | 366.67 | **cumple** |
| `total_ms` + sobrecosto | 107.21 | 133.33 | 170.87 | `max_frame_age_ms` = 500 | 366.67 | **cumple** |
| `total_ms` + sobrecosto | 107.21 | 133.33 | 170.87 | periodo de entrada = 200 | 66.67 | **cumple** |
| intervalo | 200.00 | 200.00 | 200.00 | `validez_orden_ms` = 400 | 200.00 | **cumple** |
| intervalo | 200.00 | 200.00 | 200.00 | `watchdog_ms` = 600 | 400.00 | **cumple** |

En ms. Casi todos los números de la peor salen de `final-2` (`total_ms` p95 118.63 y máximo 154.38); solo el
p95 de `politica_ms` sale de `final-3`. El sobrecosto suma p50 12.33, p95 14.70 y máximo 16.49 ms. Lo más
ajustado es el **periodo de entrada**: el peor cuadro queda a 29 ms de los 200 ms, y el p95 a 67 ms. La edad
y el timeout quedan a más de 300 ms. La fila del timeout dice que el tiempo medido cabe en los 500 ms de
`plazos.yaml`, no que `infer` ya los aplique (pendiente de P5-06).

Las tres corridas, por separado:

| Corrida | `total_ms` p50 / p95 / máx |
|---|---|
| [`final-1`](final-1/resumen.json) | 92.78 / 101.71 / 111.05 |
| [`final-2`](final-2/resumen.json) | 94.87 / 118.63 / 154.38 |
| [`final-3`](final-3/resumen.json) | 92.42 / 99.04 / 106.90 |

**Condiciones, tal cual:** conectada, VS Code cerrado y OneDrive en pausa; el registro de procesos al empezar
todavía mostró procesos de `chrome`, `msedge` y `OneDrive`, posiblemente en segundo plano. No se repitió
ninguna corrida.

## Declarado y reproducido

| | Qué es | Dónde está |
|---|---|---|
| **Declarado** | Plazos de B y ritmo de entrada (≈ 5 fps, provisional hasta que B cierre PEND-09). | `config/control/plazos.yaml` (su SHA-256 queda en `contraste.json`) |
| **Declarado** | Equipo de PEND-05. | [`README.md`](README.md#equipo-declarado-pend-05) |
| **Reproducido** | p50/p95/máximo por etapa, fallos aparte, hardware y energía de cada corrida. | `mediciones/final-1/`, `final-2/` y `final-3/`: `resumen.json`, `ejecuciones.csv`, `fallos.csv` |
| **Reproducido** | Lo que `infer` paga de más (leer el JPEG, preparación de Ultralytics). | `mediciones/final-sobrecosto/sobrecosto.json` y `sobrecosto.csv` |
| **Reproducido** | La peor de las tres, el veredicto de cada plazo y de qué corrida salió cada número. | `mediciones/final-contraste/contraste.md` y `contraste.json` |

`bench.limites` avisa (y no sale con `0`) si una corrida tiene advertencias, quedó incompleta, tuvo fallos
(aunque no entren en p50/p95), no midió la etapa de B, se contrasta con otro periodo que el de PEND-09, o si
`plazos.yaml` o los CSV cambiaron desde que se midió. Con varias corridas también avisa si no son del mismo
detector o equipo, y con `--sobrecosto`, si se midió en batería, sin comprobar los hashes, con otro detector o
si su CSV cambió.

## Lo que ya se vio (antes de la medición final)

Prueba de compatibilidad de YOLO11n (checkpoint v8.3.0, Ultralytics 8.3.0, PyTorch 2.9.0 en CPU) en el equipo
de PEND-05, para P5-04. **No es la medición del entregable:** se hizo fuera del arnés, con una sola imagen de
ejemplo a 640×480, y no hay archivos en el repositorio que la reproduzcan.

| Condición | Mediana | p95 | Máximo |
|---|---|---|---|
| Conectada, 1 hilo | 142 ms | 179 ms | 210 ms |
| Conectada, 7 hilos (los que fija Ultralytics) | 87 ms | 113 ms | 162 ms |
| En batería | 352 ms | 708 ms | 2382 ms |

Lo que deja: en batería no se cumplen los plazos, así que la corrida final va conectada (el arnés lo registra y
lo advierte). El número de hilos cambia el resultado a casi la mitad, así que el detector de P5-05 debe fijarlo y
`resumen.json` registrarlo.

### Cuántos hilos (decisión del PM A, 2026-10-31)

Con 1 hilo, la evidencia de P5-05 en macOS dio p95 244 ms y máximo 314 ms, por encima del periodo de 200 ms.
Karen fijó la regla **antes de medir**: el menor número de hilos con p95 ≤ 150 ms y máximo ≤ 200 ms; si
ninguno cumple, 7. Se midió en el equipo de PEND-05, conectado, con el procedimiento de
`resultados/p5-05-benchmark.py` de #75 (`calentar()`, 10 calentamientos y 50 mediciones de
`detector_total_ms` sobre `docs/carro/objeto_taza_centro_cerca.jpg`), una configuración por proceso:

| Hilos | Mediana | p95 | Máximo | Regla |
|---|---|---|---|---|
| 1 | 141 ms | 158 ms | 210 ms | no cumple |
| **2** | **101 ms** | **138 ms** | **189 ms** | **cumple: se elige** |
| 4 | 97 ms | 129 ms | 168 ms | cumple |
| 7 | 83 ms | 161 ms | 218 ms | no cumple |

Se midió una sola vez y no se repitió para escoger. Dos cosas que la medición final tiene que confirmar:

- **El máximo con 2 hilos queda a 11 ms del límite.** Un cuadro lento basta para pasarlo.
- **Las colas varían entre corridas.** Con 7 hilos, la prueba de P5-04 dio p95 113 ms y máximo 162 ms, y esta
  dio 161 y 218 ms. Con más hilos compiten más con el sistema.

**Repetición sobre `8d86f44` (2026-11-01).** Al revisar el cambio a 2 hilos en #75 se repitió el mismo
procedimiento, conectada, con el plan de energía Equilibrado y OneDrive y VS Code abiertos:

| Serie | Mediana | p95 | Máximo |
|---|---|---|---|
| 2 hilos, `detector.json` tal cual (4 procesos) | 93–153 ms | 104–206 ms | 137–264 ms |
| 2 hilos, como la medición de la tabla (2 procesos) | 95 ms | 120–123 ms | 155–158 ms |
| 1 hilo | 146 ms | 160 ms | 181 ms |
| 4 hilos | 94 ms | 98 ms | 162 ms |

1 hilo vuelve a fallar el p95, así que la regla sigue dando 2. Pero en 3 de las 4 series de 2 hilos con la
configuración tal cual, el p95 o el máximo pasaron la regla: las colas dependen de lo que más corra en el
equipo. Por eso la corrida final se hizo con las demás aplicaciones cerradas y con una regla fija antes de
medir (siempre 3 corridas, todas reportadas, se contrasta la peor), en vez de "si sale cerca, se repite", que
dejaría la decisión para después de ver el número (revisión de Karen en #82).

**Lo que confirmó la medición final.** Con 2 hilos, las 3 corridas del arnés dieron `inferencia_ms` p95 de
89.67 a 107.69 ms y máximo de 98.20 a 138.49 ms: dentro de la regla de hilos en las tres. No se comparan uno a
uno con la tabla de arriba: aquella mide `detector_total_ms` de `infer` sobre una sola foto, y el arnés,
`inferencia_ms` sobre los 107 cuadros de S01–S08.

Los hilos no cambian las detecciones (7 contra 1 hilo: Δconf ≤ 1.3e-6), pero sí el `config_sha256`, por eso
se decidió antes del paso 2.

### Otros hallazgos, ya corregidos en P5-05 (#75)

- **El reloj de `infer`:** en el primer recorrido real (T16, `docs/recorrido-real.md`) los cuadros llegaron a
  B con unos 35 s de edad y todos terminaron en STOP por `cuadro_viejo`, porque la carga y el calentamiento
  del modelo entraban en el reloj del run. Con #75 el reloj empieza después de `calentar()`: el primer cuadro
  sale con unos 15 ms de edad.
- **Los hilos de `infer`:** `config/detector.json` pedía 1 hilo, pero Ultralytics lo cambiaba a 7 al preparar
  el predictor. Con #75, `DetectorJPEG` vuelve a fijar el de la configuración y falla si no queda.
  `bench.yolo` usa ese mismo detector, no tiene opción para cambiar los hilos y registra los que de verdad
  quedaron. `resumen.json` también muestra `OMP_NUM_THREADS=1`: lo pone Ultralytics al importarse, y no
  cambia los hilos de PyTorch, que `DetectorJPEG` fija después.
- **El `frame_id`:** `infer` numeraba los cuadros por posición (`f000001`) y el conjunto usa el nombre de la
  captura (`S01_f0001`), así que no se unía ningún cuadro con sus anotaciones. Con #75 usa el nombre del JPEG.

## Conjunto, umbrales y condiciones

- **Conjunto:** 8 secuencias (S01–S08), todas de evaluación (D-06), con 107 cuadros anotados en P5-10: 71 con
  obstáculo y 36 despejados. E3 pide al menos 60. Congelado en el tag `datos-evaluacion-v1` (P5-11, #13), con
  SHA-256 `8a75e271…` del manifiesto y `7e842784…` de `anotaciones.jsonl`. Es un conjunto chico: las métricas
  tienen la incertidumbre de una muestra así. S09 y S10 son solo para las pruebas de B y no cuentan.
- **Una excepción a D-06, declarada en #13:** antes de congelar se corrió el detector sobre S01, una toma
  fallida de S01 y la primera S02, que después se repitió.
- **Umbrales:** `conf` 0.25 e `iou` 0.70, propuestos en P5-04 (`modelo/configuracion.p5-04.propuesta.json`),
  fijados antes de correr sobre los cuadros. Con 2 hilos, `config_sha256` es
  `6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08` (#75), registrado en el paso 2 de #13
  con el tag `config-detector-v1`.
- **Objetos y escena (PEND-04):** botella (39) y taza (41), según P5-03; interior, piso plano, buena luz.
- **Iluminación:** luz de día por ventana, sin luz directa del sol sobre el piso (`datos/DOMINIO.md`); S8, en
  otro cuarto con otra luz. No se probó con poca luz, contraluz ni exteriores.

## Lo que el equipo no pudo probar

- La cadena en vivo ESP32-CAM → detector → B con tiempos medidos de punta a punta.
- El carro moviéndose con los comandos de B.
- Otros equipos distintos al de PEND-05.
- Que `infer` emita `detector_timeout` cuando una solicitud pasa el plazo: llega con P5-06.
- El p95 de la ruta completa con el predictor supervisado en otro proceso: lo valida P5-06.
