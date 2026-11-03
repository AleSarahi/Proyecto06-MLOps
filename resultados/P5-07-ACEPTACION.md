# P5-07 · evidencia de aceptación (2026-11-02)

Rama `p5-07-paquete-detector`, PR #93, issue #9. La ficha del modelo está en
[`modelo/README.md`](../modelo/README.md) y el comando de descarga en
[`src/infer/descarga.py`](../src/infer/descarga.py).

## Entorno

- MacBook Air `Mac14,2`, Apple M2, 24 GB de RAM, macOS 26.6.2 arm64. Es una prueba **macOS**; falta Windows.
- uv 0.12.19, Python 3.12.12, `uv.lock` del repo.
- Pesos: `yolo11n.pt` de la release v8.3.0 de `ultralytics/assets`, 5 613 764 B, SHA-256
  `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.

## Copia limpia

`git clone` de la rama en una carpeta nueva, en el commit `7fe2393`, sin `modelo/descargas/` y sin
`.venv`. `<clon>` sustituye la ruta local.

```text
$ uv run --locked python -m infer.descarga
<clon>/modelo/descargas/yolo11n.pt: descargado, 5613764 B, SHA-256 0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1 OK
# salida 0
$ uv run --locked python -m infer.descarga
<clon>/modelo/descargas/yolo11n.pt: ya estaba, 5613764 B, SHA-256 0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1 OK
$ P5_05_YOLO11N_PT=modelo/descargas/yolo11n.pt uv run --locked --no-build pytest -q
1168 passed
$ git status --short
# (vacío: los pesos quedan fuera de Git)
```

Con `--url` apuntando a otro checkpoint de la misma release (`yolov8n.pt`), el comando sale con 2
(`la descarga pasa de 5613764 B: no es el checkpoint`) y no deja nada en la ruta final.

## Matriz de aceptación

| Criterio del issue #9 | Evidencia | Estado |
|---|---|---|
| Desde una copia limpia, un solo comando recupera los pesos y verifica el hash | `uv run --locked python -m infer.descarga` en el clon (arriba). Pruebas sin red de bytes de más, de menos, con otro hash, con la fuente caída y con otro archivo en la ruta final (`tests/test_descarga.py`) | **Cumplido en macOS** |
| Origen y licencia documentados, y el hash coincide con el de `config/` | Ficha: URL de la release, metadatos del checkpoint y AGPL-3.0 de código y pesos. El comando toma el SHA-256 de `config/detector.json`, y `test_ficha_del_modelo_coincide_con_descarga_y_config` exige que la ficha diga lo mismo | **Cumplido** |
| La documentación basta para identificar el modelo sin preguntar | Ficha con modelo, archivo, origen, metadatos, tamaño, SHA-256, ruta, clases, pre y posprocesamiento, runtime y licencia | **Cumplido; lo confirma A2 al revisar** |
| Pesos en Git o descarga automatizable con hash (PEND-11) | Fuera de Git, con descarga y hash; razón en la ficha | **Propuesto; lo confirman PM A y PM B** |
| Entorno fijado con lockfile y versiones documentadas (D-02) | `uv.lock` y tabla de runtime en la ficha. `infer` rechaza otras versiones | **Cumplido** |

Los metadatos del checkpoint (`license` "AGPL-3.0 License (https://ultralytics.com/license)",
`version` 8.2.100 y `date` 2024-09-25T21:10:26) se leyeron de `yolo11n/data.pkl` dentro del `.pt`, sin
deserializarlo. `test_pesos_reales_coinciden_con_tamano_config_y_licencia` los revisa cuando
`P5_05_YOLO11N_PT` está definida.

## Lo que no se probó

- **Windows**: falta correr `uv run --locked python -m infer.descarga` en Git Bash o PowerShell. El código
  solo usa la biblioteca estándar (`urllib`, `hashlib`, `tempfile`, `os.replace`).
- **Detrás de un proxy o sin certificados del sistema**: la descarga usa la configuración TLS por omisión
  de Python. Si falla, se puede bajar el archivo a mano y ponerlo en `modelo/descargas/`: correr el
  comando otra vez lo verifica sin red.
