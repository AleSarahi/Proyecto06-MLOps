# Proyecto 6 · Eventos, capturas, ventanas y alertas

> Issues #3, #14 y #15 (R4.1, R4.2 y R4.3). Esquemas: [`config/p6/contratos/`](../../config/p6/contratos/).
> Ejemplos: [`config/p6/contratos/ejemplos/`](../../config/p6/contratos/ejemplos/). Cada registro se valida
> contra su esquema antes de guardarse (`monitor.almacen`).

## Evento de inferencia (`evento.v1`, un evento por frame procesado)

| Lo que pide la guía | Campo |
|---|---|
| Identidad | `event_id` = `<run_id>-<frame_id>` |
| Ejecución | `run_id` |
| Frame | `frame_id`, `video_pos_ms`, `image_width`, `image_height` |
| Fecha | `timestamp_utc` (reloj de pared, UTC) y `t_mono_ms` (reloj monotónico de la corrida) |
| Fuente | `source_id` (`youtube-<segmento>`) y `segmento` |
| Tarea | `task` = `detection` |
| Modelo | `model_ref` (SHA-256 de los pesos) |
| Estado | `status`: `ok` · `sin_detecciones` · `error` (con `error.code` y `error.message`) |
| Predicción | `detecciones[]`: `class_id`, `class_name`, `score`, `bbox` (xyxy, px), `zona` |
| Confianza | `score` por candidata, `score_max`, `zona_frame`, `conteo_zonas`, `n_candidatas` |
| Configuración | `config_ref` (con él se reconstruyen los umbrales desde `run.json → config_efectiva`) |
| Imagen | `image_ref` (`capturas/<event_id>.jpg`, o `null` si no se capturó) |
| Tiempos | `tiempos_ms`: llegada, inicio y fin de la inferencia, inferencia y cola |

Un frame sin detecciones es `sin_detecciones`, con lista vacía y `score_max`/`zona_frame` en `null`. Un fallo es
`error`, también sin confianza. El esquema rechaza las combinaciones incoherentes (por ejemplo, `ok` sin
detecciones o `sin_detecciones` con score 0).

## Captura (`captura.v1`) y política de conservación (R4.3)

Se guarda la imagen de un frame cuando ocurre cualquiera de estos casos (`config/p6/monitoreo.yaml → captura`):

1. su zona de frame es `baja` o `duda` (motivos `zona_baja` y `zona_duda`);
2. no tiene detecciones (`sin_detecciones`);
3. es uno de cada 10 frames procesados: muestra de operación normal (`muestra_normal`);
4. pertenece a una ventana que abrió una alerta (`alerta`).

- **Qué se guarda:** los mismos bytes JPEG que se infirieron, en `<corrida>/capturas/<event_id>.jpg`. El registro
  guarda `image_id`, `event_id`, `ruta`, `sha256`, `bytes`, `motivos`, la fecha y `config_ref`; el evento guarda
  `image_ref`, así que el vínculo funciona en los dos sentidos.
- **Sin expiración automática:** ningún código borra, rota ni limpia capturas. Las capturas de la referencia, C1 y
  C2 están en Git, dentro de `evidencias/p6/` (sin LFS: 9 MB en total).
- **Verificación:** `uv run python -m monitor verificar-capturas <corrida>` comprueba que cada archivo exista, su
  hash y los dos vínculos. Resultados: referencia 9/9, C1 9/9, C2 23/23, sin problemas.
- No se guarda cada frame: en C1, de 90 frames (todos aceptados) se guardaron las 9 muestras normales; en C2, 23
  de 24 (todos los de baja confianza y de duda, más los de la ventana de la alerta).

## Ventana (`ventana.v1`) y alerta (`alerta.v1`)

- **Ventana:** conteos (frames, candidatas, baja, duda, aceptada, sin detecciones, errores), `proporcion_baja`,
  `estado` (suficiente o insuficiente), el resultado de cada regla con sus ventanas consecutivas, `event_ids` y
  `alertas_activas`.
- **Alerta:** `alert_id`, `rule_id`, momento, severidad, motivo con cifras, acción sugerida, `config_ref`,
  `model_ref`, la regla con sus parámetros, las ventanas que la originaron, `event_ids`, estado y cierre. Las
  reglas están en [`umbrales.md`](umbrales.md#reglas-de-alerta-r51).

## Persistencia y consulta (R4.2)

- **Base:** SQLite (`datos/p6/monitoreo.sqlite`, que la corrida escribe mientras procesa). Tablas: corridas,
  eventos, capturas, ventanas, alertas y alerta_eventos. Un `event_id` repetido no se inserta otra vez y se cuenta
  como duplicado (`run.json → conteos.duplicados`).
- **Exportación recalculable:** al terminar, la corrida exporta desde la base `eventos.jsonl`, `ventanas.jsonl`,
  `alertas.jsonl` y `capturas.jsonl`. `python -m monitor importar <carpetas>` reconstruye la base a partir de esos
  archivos (la base no va en Git). `test_reimportar_desde_la_exportacion_da_lo_mismo` comprueba que se obtiene lo
  mismo.
- **Portal:** `python -m monitor portal` → <http://127.0.0.1:8000>. Páginas `/eventos` (filtros por corrida, zona
  y estado), `/eventos/<id>` (detecciones con su zona, imagen con cajas, ventana, alertas, corrida y
  configuración), `/alertas`, `/alertas/<id>` (regla, ventanas y eventos de origen con sus imágenes) y
  `/corridas/<id>` (commit, entorno, configuración efectiva, ventanas y métricas). Si no hay datos muestra un estado
  vacío; si falta la base responde 503 con instrucciones; si un ID no existe, 404.
