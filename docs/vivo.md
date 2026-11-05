# Lazo en vivo (P5-21)

`python -m vivo` conecta la cámara del carro, el detector, la política y el carro con lo que ya
está calificado. No cambia `src/infer`, `src/control` ni `src/captura`: reutiliza sus piezas.

```
ESP32-CAM :81/stream ─▶ LectorStream ─▶ DetectorEnVivo ─▶ Supervisor + política ─▶ AdaptadorWifi ─▶ UDP :4210
   (cuadro más nuevo)    (infer.cuadro)   (mismos pesos)     (control, sin cambios)   (comandos.jsonl)   (carro)
                                                  ▲
                              hilo del reloj: tic cada 100 ms (watchdog y vigencia)
```

## Cómo se corre

La IP del carro va por `--ip` o por la variable `P5_CARRO_IP`. No hay credenciales y ningún archivo
del repo lleva la IP. El stream (`:81`) y las órdenes (`:4210`) son de la misma placa.

```bash
export P5_CARRO_IP=<ip del carro>
```

**Modo seco (omisión).** Lee el stream real, corre detector, política y supervisor, y registra
todo, pero no abre el socket del carro ni manda nada. Es lo primero que se corre con cualquier
stream nuevo:

```bash
uv run python -m vivo --salida resultados/vivo-seco --duracion-s 600
```

**Con motores.** Pide `--enviar`, una terminal con teclado (para el paro) y escribir la palabra de
confirmación de `config/vivo.yaml`. Con las ruedas en el aire la primera vez:

```bash
uv run python -m vivo --salida resultados/vivo-1 --enviar
```

`--salida` tiene que ser una carpeta nueva. Otras opciones: `--run-id`, `--guardar-cuadros` (deja
cada JPEG atendido en `<salida>/_cuadros/`), `--pesos`, `--config-detector`, `--config-vivo` y
`--config` (carpeta con `plazos.yaml` y `politica.yaml`).

## Paro

| Qué | Cómo | Qué pasa |
|---|---|---|
| Emergencia | tecla `e` | STOP inmediato y enclavado: ningún cuadro mueve el carro |
| Rearme | tecla `r` | Quita la emergencia solo si el último cuadro es válido y fresco. Manda STOP; el carro se mueve hasta el siguiente cuadro fresco |
| Salir | tecla `q`, Ctrl+C, `--duracion-s`, SIGTERM | STOP final y cierre |
| Excepción | cualquiera, en cualquier hilo | STOP final, mensaje `FALLO`, salida 1 |
| Cámara desconectada | el stream deja de llegar | El hilo del reloj da STOP (`orden_vencida` o `watchdog_vencido`); el lector se reconecta solo |
| Detector muerto o colgado | timeout o fallo del predictor | Evento `error`, el supervisor da STOP (`error_detector:<código>`) y el predictor se reinicia |

Al cerrar, el STOP va antes que cualquier otra cosa: primero el supervisor y luego el emisor, que
deja tres STOP por si UDP pierde uno. Si el programa muere sin poder hacerlo, la placa frena sola al
vencer la orden (≤ 510 ms, `docs/carro/protocolo.md`).

## Qué queda en la carpeta de salida

| Archivo | Contenido |
|---|---|
| `detecciones.jsonl` | Un evento de percepción v1 por cuadro atendido |
| `decisiones.jsonl` | Qué se decidió en cada cuadro o tic, y quién (política o supervisor) |
| `comandos.jsonl` | Cada comando que recibió el adaptador, con `received`, `t_command_ms` y `valid_until_ms` |
| `errores.jsonl` | Cada STOP por falla, y los envíos que fallaron o no eran válidos para la placa |
| `respuestas.jsonl` | Lo que contestó la placa, con `rtt_ms` de comando a respuesta |
| `carro.jsonl` | Bitácora del emisor (solo con `--enviar`) |
| `vivo.json` | Hashes de modelo y configuración, conteos, latencias p50/p95/max y motivo de cierre |

```bash
uv run python -m contrato resultados/vivo-seco/detecciones.jsonl
```

## Qué se mide

- `latencia_cuadro_a_comando_ms`: de `t_capture_ms` (el JPEG terminó de llegar) a `t_command_ms`
  (el comando salió al adaptador). Criterio de aceptación: **p95 < 500 ms**.
- `rtt_comando_a_respuesta_ms`: de que sale la orden a que la placa contesta `OK`. Es el dato que
  necesita la calibración (P5-23).
- `stream.descartados`: cuadros que llegaron y el detector no alcanzó a tomar. Si el detector
  tarda más que el periodo entre cuadros, se descartan los viejos en vez de hacer cola.

## Los mismos hashes que lo calificado

`config/vivo.yaml` guarda los SHA-256 del modelo (`0ebbc80d…`) y de `config/detector.json`
(`6428a259…`). Si el detector que arranca no trae los dos, `python -m vivo` no corre (salida 2).
Cada evento y `vivo.json` repiten los hashes del run.

## Dónde está cada cosa

| Archivo | Para qué |
|---|---|
| `src/infer/cuadro.py` | `DetectorEnVivo`: entrada por cuadro del `PredictorSupervisado`; es nuevo y no cambia nada de `infer` |
| `src/vivo/lector.py` | Hilo del stream: siempre el cuadro más nuevo |
| `src/vivo/corrida.py` | La `Corrida` de T14 con reloj real, cerrojo y el adaptador del carro |
| `src/vivo/adaptador_wifi.py` | **El único archivo que conoce el protocolo del carro** |
| `src/vivo/lazo.py` | Hilos, línea por cuadro, paro y cierre |
| `src/vivo/teclado.py` | Teclas sueltas (macOS, Linux y Windows) |
| `config/vivo.yaml` | Parámetros propios del lazo en vivo |

Si el protocolo cambia, se cambia `adaptador_wifi.py` y nada más.

## Pendiente de la fase 2 (con el carro)

Estas pruebas necesitan el carro y no se hicieron en el PR:

1. 10 minutos en modo seco con el stream real: revisar `latencia_cuadro_a_comando_ms.p95`.
2. Conectado, con las ruedas en el aire junto con el dev del firmware: STOP por cámara
   desconectada, emergencia y cierre.
3. Pasar `rtt_comando_a_respuesta_ms` y la latencia al dev 4 para la calibración.
