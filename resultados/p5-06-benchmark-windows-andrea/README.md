# P5-06 · serie oficial independiente en Windows

Andy entregó esta serie para el commit
`83d81f262f8423e20832462e478222dc4129faa0`. El ZIP recibido el 2 de noviembre
de 2026 permanece intacto en Downloads, **fuera de Git**:
`~/Downloads/p5-06-serie-oficial-windows-83d81f2.zip`, SHA-256
`cca7a2b3b91cea9ec05046653b66e283677e1afee812d1da629b93b7d1e353b8`.
Esta carpeta contiene una **copia pública depurada**, `evidencia-publica.zip`, SHA-256
`49b1f18d85267c40c3401b38a079dbac79ac48fad3f546ac3bcded72a0b4c407`.
No es idéntica al original. Ambos ZIP tienen seis miembros; sus cinco entradas
indexadas en `SHA256SUMS.txt` coinciden (5/5), sin BOM UTF-8 ni errores CRC.

## Depuración y trazabilidad

El original contenía un identificador de cuenta local en `benchmark.json`,
`consola.txt` y `p506-serie-oficial.ps1`; la transcripción también contenía el
nombre del equipo. Se sustituyeron ocho apariciones de la cuenta, tres del
nombre del equipo y cuatro referencias personales en comentarios y mensajes
del script. Las **15** sustituciones usan exclusivamente `<REDACTED>`. No había un
identificador personal en nombres de miembros ni metadatos del ZIP. La revisión
no encontró correos, claves privadas ni patrones de tokens o credenciales.
Los nombres de Andy, Andrea y Karen usados como atribución de funciones del proyecto
se conservaron.

| Miembro del ZIP | SHA-256 original | SHA-256 público | Sustituciones | Tipo |
| --- | --- | --- | ---: | --- |
| `benchmark.json` | `e29d4be288e8413f690e3b7414e6b78fced2fde0f772d3efaeb7ab80d85f7726` | `d4442e44e92db93b401803fbf0c7e664286f2d939e3b6f98717c4f26b8e08ce3` | 2 | Cuenta en `comando` |
| `benchmark.preflight.json` | `5b3fc16f9069f2d4c02caef292fa8892c78c5d66a64701bed2101be123396452` | `5b3fc16f9069f2d4c02caef292fa8892c78c5d66a64701bed2101be123396452` | 0 | Ninguno |
| `consola.txt` | `2f02d41b86b7e3049d432e58ee4d82debf2a8d20fc9ef14334c547dc62dc466e` | `495e4e9355cfa1aa1203abbd805ca0fbf29f7eaabda85fa16313fd4b2b8807ef` | 8 | Cuenta (5) y equipo (3) |
| `LEEME.txt` | `2aaa8e69516d910493c04303deb4a0e0b23df46b668938db340ac740456b0e01` | `2aaa8e69516d910493c04303deb4a0e0b23df46b668938db340ac740456b0e01` | 0 | Ninguno |
| `p506-serie-oficial.ps1` | `a06f0885959a5b6666fcbbc935e3a459e59c884cb123b1859db80d0f10c2d915` | `eae8c422a88358816f50d4a9dbb03871e44f1d471e0fccae729d0a76fe80ccf0` | 5 | Cuenta (1) y referencia personal (4) |
| `SHA256SUMS.txt` | `97e15b0c780ad39d46f69e66532e8ad64686f14e68786ef45ed7279078fad3d2` | `f1a2e29b80bd93d6424ea84c7144ff6323a5b3795ca3e34c5a0a912be0f58d1f` | 0 | Índice regenerado en UTF-8 sin BOM |


La comparación byte a byte verificó que esas sustituciones y el índice regenerado
son los únicos cambios de contenido. `benchmark.preflight.json` y `LEEME.txt`
son idénticos. En `benchmark.json`, los otros 28 campos de nivel superior son
idénticos al original; solo se depuraron dos rutas del campo `comando`.
Se preservaron muestras, tiempos, estadísticas, detecciones, comparaciones,
reinicios, condiciones técnicas y resultados. La copia del script conserva su
lógica; las referencias personales cambiadas están en comentarios y mensajes.
Cualquier referencia histórica al SHA-256 original de `benchmark.json`
(`e29d4be288e8413f690e3b7414e6b78fced2fde0f772d3efaeb7ab80d85f7726`)
describe el archivo original conservado fuera de Git, no la copia pública.
La búsqueda final, insensible a mayúsculas y minúsculas, examinó UTF-8 y UTF-16
en los archivos preparados para esta publicación, incluido el ZIP de esta serie,
sus miembros y nombres de entrada: quedaron **0** apariciones de los tres
identificadores originales autorizados. Los ZIP funcionales publicados antes
permanecen intactos y se revisarán por separado con Andy.

## Resultados y criterios

El manifiesto registra Windows 11, Python 3.12.14, reloj `perf_counter` respaldado
por `QueryPerformanceCounter()` y resolución reportada de `1e-07` s. El SHA-256
del checkpoint es
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`,
`config_sha256` es
`6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08`
y `torch_threads=2`. Se hicieron diez pares control → supervisado excluidos y
50 pares medidos intercalados, con el mismo JPEG y configuración. El p95 usa
interpolación lineal de NumPy. Recalculamos p50 y p95 desde las muestras
individuales y coinciden con el manifiesto.

| Medida | Control | Supervisado | Criterio de Karen |
| --- | ---: | ---: | --- |
| p50 | 48.77265 ms | 49.6597 ms | Δp50 = 0.88705 ms ≤ 5 ms |
| p95 | 58.25793 ms | 58.9775 ms | Δp95 = 0.71957 ms ≤ 10 ms; p95 supervisado ≤ 150 ms |
| Máximo | 61.3049 ms | 60.6622 ms | Máximo supervisado ≤ 200 ms |
| Solicitudes normales >500 ms | 0 | 0 | Cero en supervisado |

Se excluyeron diez reinicios de estabilización y se midieron 50 por separado.
Los 50 registros medidos contienen READY, SHA-256 de modelo/configuración y dos
hilos correctos. El tiempo total de reinicio tiene p50 de 4015.30725 ms y p95
de 4799.444585 ms; Karen no fijó umbral numérico para reinicio. Estos reinicios
son directos, distintos de las recuperaciones provocadas por timeout de la
evidencia funcional previa. `desviaciones` en el JSON original es una lista vacía.

Las 60 comparaciones locales (incluidos calentamientos) registran igualdad exacta
entre control y supervisado. Frente a P5-05 Mac, coinciden la clase 41 y la
confianza; la mayor diferencia de bbox es **0.00006103515625 px**. El JSON original
conserva la clasificación `diferencia_numerica_pendiente` y
`revision_pendiente=true` que tenía al generarse: no se editó. Según la decisión
comunicada de Karen del **2026-11-02**, se acepta exclusivamente esa diferencia
observada entre plataformas. La paridad local sigue exigiendo igualdad estricta;
no se agregó tolerancia. Cualquier otra diferencia requiere una nueva revisión
de Karen.

## Condiciones y alcance de la evidencia

El preflight y las cuatro instantáneas de fases registran alimentación AC,
ahorro desactivado y estado aprobado. La transcripción muestra `com.docker.backend`
y `OneDrive.Sync.Service` en la lista de procesos al inicio. El preflight
registró `procesos_bloqueantes=[]`, y el script verificó el proceso `OneDrive`;
la observación del servicio de sincronización y Docker se conserva para revisión
sin afirmar que invalide la serie. No hay evidencia de que esos procesos
persistieran durante toda la medición.

Esta es la **serie oficial de latencia normal y reinicios directos** de Windows,
separada de las pruebas funcionales de timeout forzado. Cumple los límites
numéricos registrados arriba. La condición ambiental de OneDrive queda visible
para que Karen determine su tratamiento antes de declarar aceptación integral.
No se repitió la serie ni se descartaron muestras. El script incluido documenta
el procedimiento ejecutado; sus rutas personales se depuraron y deben adaptarse
si se utiliza en otra máquina. La regla permite una sola serie oficial por
máquina y conserva el ZIP original fuera de Git para auditoría.
