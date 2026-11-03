# Serie oficial Mac P5-06 · 1 de noviembre de 2026

`benchmark.json` es la salida bruta de una sola ejecución del benchmark P5-06
(SHA-256 `83e0d2a4bfa8262bf9c7f389ab16ebc101f77db4cbf92cec2d757e8aacda4372`).
Contiene las 50 muestras de cada ruta, 10 calentamientos excluidos por ruta, 10
reinicios excluidos, 50 reinicios medidos y todas sus fases. `resumen.json` es
derivado. `entorno-previo.json` y `entorno-posterior.json` conservan hardware,
energía, carga y procesos. `observaciones.json` documenta las desviaciones.

Se usó `docs/carro/objeto_taza_centro_cerca.jpg`, idéntico por SHA-256 al
`ensayo-0012.jpg` de P5-05, con el checkpoint oficial v8.3.0 verificado. El orden
fue control → supervisado → reinicio. La diferencia entre las dos primeras rutas
mide el conjunto de supervisión e IPC, no solo el transporte.

Comando ejecutado desde la raíz de este worktree:

```sh
.venv/bin/python resultados/p5-06-benchmark.py \
  --weights '/Users/<REDACTED>/Library/Application Support/P5-05/yolo11n.pt' \
  --output resultados/p5-06-benchmark-mac-2026-11-01/benchmark.json \
  --responsable A1 \
  --modo-energia bateria-descargando
```

Para reproducir, verificar previamente los hashes y usar un destino **nuevo**.
El argumento de energía refleja el preflight. Las instantáneas en
`benchmark.json` muestran que las tres etapas se ejecutaron con alimentación
AC; `observaciones.json` conserva esta corrección sin modificar la salida bruta.
El preflight detectó procesos de Codex y WindowServer con uso notable de CPU.
No hubo solicitudes fallidas ni muestras descartadas. Esta serie Mac no
constituye aprobación de rendimiento: faltan los umbrales de Karen y la
validación independiente en Windows.

## Depuración de rutas personales para la copia pública

La única depuración de los cuatro archivos fue sustituir el identificador de la cuenta
local en rutas `/Users/…/` por `<REDACTED>`. No cambiaron las demás partes de esas rutas,
los procesos, las muestras, los tiempos, las detecciones ni los resultados numéricos.
Se guardaron copias intactas fuera del repositorio. Los originales también permanecen
en el historial público del commit `b6692c6` y pueden recuperarse con
`git show b6692c6:resultados/p5-06-benchmark-mac-2026-11-01/<archivo>`.

| Archivo | Sustituciones | SHA-256 original | SHA-256 público |
| --- | ---: | --- | --- |
| `README.md` | 1 | `4ab5a1945b96596a102186962de3d0167bd7950f69d393893ccbd9eaa2cdfedd` | Véase la nota de autorreferencia. |
| `benchmark.json` | 1 | `83e0d2a4bfa8262bf9c7f389ab16ebc101f77db4cbf92cec2d757e8aacda4372` | `2418bc8a6a9310cf65ffae786c5b445d3086df5008b7512d47f75baf87bd873f` |
| `entorno-previo.json` | 10 | `743a8f99a6aad338ffd425405d4dd50559f1e07556a39569964b660bea1d4b63` | `02e1663ee3568ba4e3ebccfe6b6bf86298aa362d2630d8c2c2e2bb2b5dbb370e` |
| `entorno-posterior.json` | 10 | `8ef9136c29da311b3750e50772590416db45323f72f19165c7c9827cbbde65bb` | `30cd3b43a79da64e39de0d8880693cd3aad52da0a2494b707da132b0d9a43e64` |

El SHA-256 del `README.md` público completo se informa fuera del propio archivo: incluirlo
aquí cambiaría ese mismo SHA-256. El contenido del README inmediatamente después de la
sustitución y antes de añadir esta sección tenía SHA-256
`67977cb0ba801900453e62205377cb4a118177787e8380e4b93f69f8f3781df5`.

Los hashes históricos citados en `resumen.json`, `observaciones.json`,
`entorno-posterior.json` y la auditoría de preflight siguen describiendo los archivos
**originales**. Se conservaron sin recalcular ni reemplazar para mantener la
trazabilidad de la medición inicial.
