# Proyecto 6 · Configuración

> Issue #4. Archivos: [`config/p6/monitoreo.yaml`](../../config/p6/monitoreo.yaml) (monitoreo),
> [`config/p6/detector.json`](../../config/p6/detector.json) (modelo) y [`config/p6/fuentes.yaml`](../../config/p6/fuentes.yaml)
> (de dónde salen las imágenes).

| Sección | Qué controla | Documentación |
|---|---|---|
| `detector` | Ruta de la configuración del detector | [`modelo.md`](modelo.md) |
| `muestreo` | 1 de cada N frames, velocidad de reproducción, atraso máximo | [`fuente.md`](fuente.md) |
| `umbrales`, `zona_frame` | Dos umbrales y la zona de cada frame | [`umbrales.md`](umbrales.md) |
| `ventanas` | Duración y mínimo de candidatas | [`umbrales.md`](umbrales.md) |
| `referencia` | Ruta de `referencia.json` | [`umbrales.md`](umbrales.md) |
| `reglas` | Reglas de alerta | [`umbrales.md`](umbrales.md#reglas-de-alerta-r51) |
| `captura` | Política de captura | [`contratos.md`](contratos.md) |

- **Validación:** `monitor.config.cargar` rechaza claves desconocidas o ausentes, tipos y rangos inválidos,
  umbrales que no cumplan `0 ≤ inferior < superior ≤ 1`, reglas repetidas o sin parámetros, y un piso del
  detector que no quede por debajo del umbral inferior. La corrida no arranca con una configuración inválida.
- **`config_ref`:** es el SHA-256 de la configuración efectiva (sin `muestreo.velocidad`, que solo cambia el ritmo)
  más el `config_sha256` del detector. Va en cada evento, captura, ventana y alerta, y la configuración completa
  queda en `run.json → config_efectiva`, así que se puede reconstruir desde los registros.
- **Cambiar un valor** cambia `config_ref`. La referencia guardada deja de ser comparable y C1/C2 se niegan a
  correr hasta que se vuelva a correr la referencia (series separadas).
- `fuentes.yaml` no entra en `config_ref`: describe el origen de los frames, cuya identidad (SHA-256) queda en el
  manifiesto del respaldo y en `run.json → fuente`.
