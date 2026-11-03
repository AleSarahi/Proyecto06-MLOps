# P5-08 · evidencia de aceptación (2026-11-02)

Issue #10. El primer recorrido con el detector real ya lo hizo T16 con B3 en una laptop Windows
([`docs/recorrido-real.md`](../docs/recorrido-real.md), PR #76, #83 y #88). Aquí se junta lo que cubre
cada parte de P5-08 y se agrega lo que faltaba: **el mismo ejemplo en una segunda máquina**.

## Lo que pide P5-08 y dónde está

| Alcance o criterio | Evidencia | Estado |
|---|---|---|
| Un cuadro real trazado: `frame_id` → detecciones → estado → decisión → comando | `S09_f0012` de punta a punta en [`docs/recorrido-real.md`](../docs/recorrido-real.md#un-cuadro-seguido-de-punta-a-punta). Los 24 cuadros de esta repetición, en `p5-08-mac/{izq,der}/traza.txt` | **Cumplido** |
| Izquierda y derecha dan comandos opuestos | Windows (T16): `GIRAR_DER` en los 12 cuadros de S09 y `GIRAR_IZQ` en 10 de S10 (los otros 2, STOP por `cuadro_viejo`). Mac (aquí): `GIRAR_DER` 12 y `GIRAR_IZQ` 12 | **Cumplido** |
| Una secuencia completa de cada tipo | Izquierda S09, derecha S10 y centro S02 (T16). Despejada: S01 y S08 en C1 (T20), que pasa (`resultados/casos/C1/veredicto.json`) | **Cumplido** |
| Un ejemplo compartido da lo mismo en las dos máquinas | S09 y S10 repetidos en Mac y comparados con Windows (abajo) | **Cumplido** |
| Los dos PM presenciaron o verificaron el recorrido | Lo confirman Karen (PM A) y Ale V. (PM B) en el PR | **Pendiente de las PM** |

## Repetición en una segunda máquina

- **Windows (T16):** la laptop de la copia limpia, código de #75 (`d3a2f1c`). Archivos en
  `resultados/recorrido-real/{izq,der}/`.
- **Mac (aquí):** MacBook Air `Mac14,2`, Apple M2, 24 GB, macOS 26.6.2 arm64, Python 3.12.12. `main`
  en `5b0c4de`. Archivos en `resultados/p5-08-mac/{izq,der}/`.
- Mismos JPEG (`datos/pruebas-b/S09` y `S10`), mismos `--capture-ms` (los `t_capture_ms` de cada
  `captura.jsonl`), mismos pesos (`model_sha256` `0ebbc80d…6ee1`) y misma configuración
  (`config_sha256` `6428a259…4e08`).
- Entre `config-detector-v1` y `5b0c4de` no cambia nada de `src/infer/`, `src/contrato/`,
  `config/detector.json`, `config/control/`, `pyproject.toml` ni `uv.lock`. En `src/control/` solo
  cambió que los registros se escriben con `newline="\n"` (LF también en Windows), sin cambio de
  comportamiento.

Comandos, para cada lado (`izq` con S09, `der` con S10):

```bash
uv run --locked python -m infer --input datos/pruebas-b/S09 --config config/detector.json \
    --weights <ruta local>/yolo11n.pt --output resultados/p5-08-mac/izq/detector.jsonl \
    --run-id p5-08-mac-izq --sequence-id S09 \
    --capture-ms 0 --capture-ms 203 --capture-ms 484 --capture-ms 687 --capture-ms 906 --capture-ms 1140 \
    --capture-ms 1390 --capture-ms 1593 --capture-ms 1812 --capture-ms 2031 --capture-ms 2297 --capture-ms 2531
uv run --locked python -m contrato resultados/p5-08-mac/izq/detector.jsonl
uv run --locked python -m control --entrada resultados/p5-08-mac/izq/detector.jsonl \
    --config config/control/ --salida resultados/p5-08-mac/izq/
uv run --locked python -m control.traza --salida resultados/p5-08-mac/izq/ > resultados/p5-08-mac/izq/traza.txt
uv run --locked python resultados/p5-08-comparar.py
```

Para S10, los `--capture-ms` son 0 250 500 750 985 1188 1391 1688 1954 2157 2360 2563.

### Resultado

`resultados/p5-08-comparar.py` compara cuadro por cuadro y sale con 0:

| Secuencia | Cuadros | Detecciones y clases | Máx. diferencia de confianza | Máx. diferencia de caja | Acciones Windows | Acciones Mac |
|---|---|---|---|---|---|---|
| izq (S09) | 12 | Iguales: `cup` (41) en los 12 | 3.0 × 10⁻⁶ | 6.1 × 10⁻⁵ px | `GIRAR_DER` 12 | `GIRAR_DER` 12 |
| der (S10) | 12 | Iguales: `cup` (41) en los 12 | 4.8 × 10⁻⁷ | 6.1 × 10⁻⁵ px | `GIRAR_IZQ` 10, STOP 2 | `GIRAR_IZQ` 12 |

`contrato`: 12 eventos OK en cada una. `control`: 13 comandos y 0 errores en cada una (el 13 es el
STOP de cierre).

Las detecciones son las mismas en las dos máquinas: las diferencias son de redondeo de punto
flotante, muy por debajo de lo que cambiaría una zona o un umbral. Lo único distinto es el tiempo. En
Windows, `S10_f0011` y `S10_f0012` llegaron con 515 y 609 ms y B los paró por `cuadro_viejo`, como
debe (`max_frame_age_ms` es 500). En esta Mac la edad de los cuadros fue de 48 a 74 ms y esos dos
dieron `GIRAR_IZQ`, como los otros diez. Es la misma diferencia de carga que ya explica
[`docs/recorrido-real.md`](../docs/recorrido-real.md#diferencias-encontradas): no se toca ningún
plazo ni se escoge la corrida que salió mejor.

## Para cerrar

Falta solo el tercer criterio: que las dos PM digan en el PR que verificaron el recorrido (por
ejemplo, siguiendo un cuadro con `python -m control.traza --frame-id`).
