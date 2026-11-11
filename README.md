# Proyecto 6 · Centro de monitoreo de computer vision

Entrega **individual** de Alejandra Rayas para ITESO MLOps. Un **video de YouTube** (CC BY) se reproduce como
stream a 1 fps. Cada frame pasa por **YOLO11n real** (detección, CPU) y produce un evento con zona de confianza.
El sistema captura imágenes vinculadas, calcula una métrica base por grupo G1–G7, evalúa reglas por ventana y
genera alertas. Un **portal web** permite consultar eventos y alertas y seguir cada alerta hasta sus eventos e
imágenes.

No se mide calidad predictiva (no hay etiquetas ni accuracy/mAP). Una puntuación alta es «aceptada por la
política», no «correcta».

| | |
|---|---|
| Tarea | Detección de objetos (persona, bicicleta, auto, moto, autobús, camión) |
| Modelo | YOLO11n preentrenado, `yolo11n.pt`, SHA-256 `0ebbc80d…6ee1` · [ficha](docs/p6/modelo.md) |
| Fuente | Videos de YouTube CC BY reproducidos a 1 fps, con respaldo de frames en el repo · [fuente](docs/p6/fuente.md) |
| Umbrales | inferior 0.30, superior 0.60 → zonas baja / duda / aceptada · [justificación](docs/p6/umbrales.md) |
| Ejecución | Local, CPU, Python 3.12 (`uv`). Windows, macOS o Linux. |
| Evidencias | [`evidencias/p6/indice.md`](evidencias/p6/indice.md): criterio → archivo → ID → commit |
| Autoría | [`docs/p6/autoria.md`](docs/p6/autoria.md) (aportación propia, componentes reutilizados de P5, terceros) |
| Extras | Vista en vivo, dashboard, exportación, métricas X1–X5 y escenarios S1/S2 · [inventario](docs/p6/extras.md) |

## Instalación

Requiere [uv](https://docs.astral.sh/uv/) 0.12.13 (o `python -m pip install "uv==0.12.13"`). Python 3.12 queda
fijado en `.python-version`, y las versiones exactas de todas las dependencias están en `uv.lock`.

```bash
uv sync --locked                          # crea .venv con exactamente lo de uv.lock
uv run --locked python -m infer.descarga  # una vez, con red: pesos de YOLO11n verificados por SHA-256
```

Si `uv` no se reconoce después de instalarlo (por ejemplo en Windows sin permisos de administrador),
`python -m uv …` hace lo mismo.

## Ver el portal con la evidencia entregada (sin correr el modelo)

```bash
uv run python -m monitor importar evidencias/p6/referencia/corrida evidencias/p6/escenarios/c1-normal evidencias/p6/escenarios/c2-baja-confianza evidencias/p6/extras/s1-transicion evidencias/p6/extras/s2-interrupcion evidencias/p6/extras/s3-error-inferencia evidencias/p6/extras/s4-saturacion
uv run python -m monitor portal          # http://127.0.0.1:8000  (/eventos, /alertas, /corridas, /vivo, /dashboard)
```

`importar` reconstruye la base SQLite (`datos/p6/monitoreo.sqlite`, que no va en Git) a partir de los JSONL
exportados.

## Reproducir la referencia y los escenarios C1 y C2

Los escenarios leen el respaldo de frames de `datos/p6/frames/` (en Git), así que **no necesitan YouTube**. Para
comprobar que el respaldo y los videos están íntegros: `uv run python -m monitor video verificar`. Para descargar
los videos originales y comprobar su hash: `uv run python -m monitor video descargar`.

```bash
# 0. (Opcional) otra carpeta de salida para no pisar la evidencia entregada: cambia evidencias/p6/... por tmp/...
# 1. Referencia (1.5 min en tiempo real) y su resumen
uv run python -m monitor correr --segmento referencia --salida tmp/referencia --sin-referencia
uv run python -m monitor referencia tmp/referencia --salida tmp/referencia.json
# 2. C1 · operación normal y C2 · baja confianza (usan config/p6/monitoreo.yaml y la referencia de
#    evidencias/p6/referencia/referencia.json, que tiene el mismo config_ref)
uv run python -m monitor correr --segmento c1 --salida tmp/c1
uv run python -m monitor correr --segmento c2 --salida tmp/c2
# 3. Verificaciones
uv run python -m monitor verificar-capturas tmp/c1 tmp/c2
python evidencias/p6/recalcular.py tmp/c1 tmp/c2     # recálculo independiente (solo stdlib)
```

- `--velocidad 0` procesa sin esperar el tiempo real; cambia los tiempos (G1/G2) pero no qué frames se infieren.
- `--modo video` lee el MP4 descargado en lugar del respaldo.
- Cada corrida escribe `run.json` (commit, entorno, configuración efectiva, modelo y fuente), `eventos.jsonl`,
  `observaciones.jsonl`, `ventanas.jsonl`, `alertas.jsonl`, `capturas.jsonl`, `capturas/*.jpg` y
  `metricas.json`, y además guarda todo en la base del portal.

Resultados entregados (commit del código `d5ab597`, `config_ref c574ee88…`):

| Corrida | Frames | Zonas de frame | Proporción baja (candidatas) | Alertas |
|---|---|---|---|---|
| [Referencia](evidencias/p6/referencia/) | 90 | 90 aceptadas | 0.3808 | — |
| [C1 · normal](evidencias/p6/escenarios/c1-normal/) | 90 | 90 aceptadas | 0.3859 (ventanas 0.28–0.51) | ninguna |
| [C2 · baja confianza](evidencias/p6/escenarios/c2-baja-confianza/) | 24 | 9 baja · 13 duda · 2 aceptadas | 0.8298 (ventanas 0.80 / 0.84 / insuficiente) | `baja-confianza-v1` (advertencia) |

## Extras (puntos adicionales)

Detalle, niveles solicitados y control de doble conteo: [`docs/p6/extras.md`](docs/p6/extras.md). No cambian
`config/p6/monitoreo.yaml` ni `config_ref`.

```bash
# S1 · cambio sostenido: día -> noche -> noche -> día (100 s)
uv run python -m monitor correr --segmento s1-transicion --salida tmp/s1
# S2 · la fuente se cae de 20 a 40 s y se recupera (60 s); con el portal abierto, ver /vivo
uv run python -m monitor correr --segmento s2-interrupcion --corte 20:40 --salida tmp/s2
# S3 · el modelo falla de 20 a 35 s; S4 · la inferencia tarda 2 s más de 20 a 40 s (60 s cada uno)
uv run python -m monitor correr --segmento s3-error-inferencia --error-inferencia 20:35 --salida tmp/s3
uv run python -m monitor correr --segmento s4-saturacion --lentitud 20:40 --lentitud-ms 2000 --salida tmp/s4
# Verificaciones
python evidencias/p6/recalcular.py tmp/s1 tmp/s2 tmp/s3 tmp/s4
python evidencias/p6/recalcular_extras.py tmp/s1 tmp/s2 tmp/s3 tmp/s4   # X1-X7 y alertas técnicas (solo stdlib)
uv run python -m monitor metricas-extra evidencias/p6/escenarios/c1-normal   # X1-X5 de otra corrida
```

| Extra | Qué es | Evidencia |
|---|---|---|
| F1 · En vivo (`/vivo`) | Último frame con cajas, estado de corrida y fuente, alertas abiertas; cada segundo | [capturas durante S2](evidencias/p6/extras/portal/) |
| F2 · Dashboard (`/dashboard`) | G1–G7 y X1–X5 por ventana, varias corridas, rango, alertas sombreadas | `portal/10…14` |
| F3 · Exportación | `/exportar/eventos.csv` y `.jsonl` con filtros validados | [`exportacion/`](evidencias/p6/extras/exportacion/) |
| M1–M5 · X1–X5 | Candidatas/frame, frames sin detecciones, PSI vs. referencia, latencia e2e, disponibilidad | `metricas_extra.json` de cada corrida |
| S1 · Cambio sostenido | La regla de 3 ventanas abre en la 3.ª, nada se repite, todo cierra al volver el día | [ficha](evidencias/p6/extras/s1-transicion/README.md) |
| S2 · Interrupción | Corte de 20 s → alerta de fuente → recuperación → verificación | [ficha](evidencias/p6/extras/s2-interrupcion/README.md) |
| S3 · Error de inferencia | El modelo falla 15 s → alerta con diagnóstico → recuperación | [ficha](evidencias/p6/extras/s3-error-inferencia/README.md) |
| S4 · Saturación | Inferencia lenta → cola y descartes → alerta → la cola se vacía | [ficha](evidencias/p6/extras/s4-saturacion/README.md) |
| M6–M7 · X6–X7 | Tasa de errores de inferencia y tasa de descarte por saturación | `metricas_extra.json` |

## Arquitectura

```text
YouTube (CC BY) ─yt-dlp+SHA-256─▶ video ─extraer 1/30─▶ datos/p6/frames (respaldo, Git)
  ▶ Fuente (1 fps)  ▶ YOLO11n (CPU)  ▶ zonas  ▶ evento + captura  ▶ ventana 10 s / reglas  ▶ alerta
        │                  │                        │                        │
        └── observaciones (tiempos, RAM) ───────────┴── SQLite + JSONL ──────┴──▶ métricas G1–G7 · portal
```

Detalle y decisiones: [`docs/p6/arquitectura.md`](docs/p6/arquitectura.md). Código: [`src/monitor/`](src/monitor/).

| Documento | Contenido | Criterio |
|---|---|---|
| [`fuente.md`](docs/p6/fuente.md) | Videos, licencias, segmentos, muestreo, respaldo | R1.1 |
| [`modelo.md`](docs/p6/modelo.md) | Artefacto, clases, preprocesamiento, piso/NMS, entorno | R1.3 |
| [`metricas.md`](docs/p6/metricas.md) | Inventario G1–G7 con M1–M5 y resultados | R2 |
| [`umbrales.md`](docs/p6/umbrales.md) | Zonas, referencia, ventanas, regla sostenida, reglas de alerta | R3, R5.1 |
| [`contratos.md`](docs/p6/contratos.md) | Evento, captura, ventana y alerta; política de capturas; portal | R4, R5 |
| [`configuracion.md`](docs/p6/configuracion.md) | `config/p6/`, validación y `config_ref` | R7.1 |
| [`autoria.md`](docs/p6/autoria.md) | Autoría individual y componentes reutilizados | R7.3 |

## Pruebas

```bash
uv run pytest -q tests/test_p6_*.py     # P6: configuración, zonas, contratos, reglas, cadena completa, portal
uv run ruff check . && uv run ruff format --check .
```

`tests/test_p6_modelo.py` corre YOLO11n sobre frames reales y se salta si faltan los pesos. La prueba de la cadena
usa un detector *doble* solo para verificar la lógica; la evidencia de C1 y C2 viene siempre del modelo real.

## Límites conocidos

- Las puntuaciones describen salidas del modelo; no se afirma acierto ni drift. Una alerta inicia una investigación.
- Hay una sola fuente por corrida y la ejecución es local. No hay notificaciones externas ni reconocimiento de
  alertas (la rúbrica no los pide).
- G1 depende de la carga: en tiempo real (1 fps) el p95 ronda 500 ms porque la CPU baja de frecuencia entre
  frames; con `--velocidad 0` ronda 220 ms.
- En C1 y C2 no hubo frames sin detecciones ni errores. Esos estados existen y están probados
  (`tests/test_p6_integracion.py`), pero no aparecen en la evidencia real.
- Si YouTube cambia el archivo, `video descargar` falla por el hash; los escenarios siguen funcionando con el respaldo.

## Proyecto 5 (material heredado)

Este repositorio parte del Proyecto 5 (equipo). Su README está en [`README-P5.md`](README-P5.md) y su código
(`src/control`, `casos/`, `src/metricas`, `firmware/`, ...) se conserva como historial. Los casos `casos/C1`–`C10`
son de P5 y **no** son los escenarios C1/C2 de este proyecto.
