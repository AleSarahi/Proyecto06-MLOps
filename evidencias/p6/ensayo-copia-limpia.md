# Ensayo de reproducción desde una copia limpia

> Issue #28. Fecha: 2026-11-09 (UTC). Equipo: el mismo Windows 11 de las corridas, en una carpeta nueva fuera
> del repositorio de trabajo.

Se clonó el repositorio en una carpeta vacía y se siguió solo el [`README.md`](../../README.md), en la rama
`p6-3-24-nucleo-monitoreo` y el commit `ecb67fd`.

| Paso | Comando | Resultado |
|---|---|---|
| Instalar | `uv sync --locked` | OK |
| Pesos | `uv run --locked python -m infer.descarga` | Descargados; SHA-256 `0ebbc80d…6ee1` OK |
| Respaldo | `uv run python -m monitor video verificar` | Respaldo de referencia, c1 y c2 OK. Sin videos locales, el comando indica cómo descargarlos. |
| Video (verificación del hash) | `uv run python -m monitor video descargar --video noche` | Descargado; SHA-256 `eb96b39d…b478d7` coincide |
| Portal con la evidencia | `monitor importar …` + rutas `/eventos`, `/alertas`, `/alertas/<id>`, `/eventos/<id>` y `/imagenes/<id>` | 3 corridas importadas; las 5 rutas responden 200 |
| Referencia | `monitor correr --segmento referencia … --sin-referencia --velocidad 0` + `monitor referencia` | Proporción baja 0.3808 (653/1715): igual que la entregada |
| C2 (tiempo real) | `monitor correr --segmento c2 --salida tmp/c2` | 24 eventos (9 baja, 13 duda, 2 aceptadas); la misma alerta `baja-confianza-v1` (63/79 = 0.797); 23 capturas |
| C1 (`--velocidad 0`) | `monitor correr --segmento c1 --salida tmp/c1 --velocidad 0` | 90 eventos aceptados, 0 alertas, 9 capturas |
| Verificaciones | `monitor verificar-capturas tmp/c1 tmp/c2` y `python evidencias/p6/recalcular.py tmp/c1 tmp/c2` | 9/9 y 23/23 sin problemas; recálculo: todo coincide |
| Comparación con la evidencia | Scores por candidata de `tmp/*/eventos.jsonl` frente a `evidencias/p6/escenarios/*/eventos.jsonl` | **Idénticos** en C1 y C2: la inferencia es determinista en CPU con el mismo respaldo |
| Pruebas | `uv run pytest -q tests/test_p6_*.py` | 58 pasan (incluida la prueba de humo con el modelo real) |

Diferencias encontradas y corregidas:

- `yt-dlp` mostraba su barra de progreso aunque estaba en modo silencioso. Se agregó `noprogress` en
  `src/monitor/video.py`. Solo cambia la salida de la consola; no cambia `config_ref` ni las inferencias.

No probado en este ensayo: otro sistema operativo (el CI corre las pruebas en Ubuntu, sin los pesos) y la descarga
del video de día (86 MB). Su hash se verificó al crearlo y el respaldo de sus frames está en el repo.
