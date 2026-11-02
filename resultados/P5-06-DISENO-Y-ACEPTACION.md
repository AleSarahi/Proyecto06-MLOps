# P5-06 · diseño del predictor supervisado y regla de aceptación

**Estado:** regla escrita antes de implementar el trabajador y antes de medir. Las decisiones de
arquitectura y el plazo de 500 ms provienen de Karen; este documento no presenta resultados nuevos.
La evidencia local A→B ya disponible está en `resultados/p5-06-integracion/`. P5-05 aporta las
corridas `p5-05-aceptacion-2h-a.jsonl` y `p5-05-aceptacion-2h-b.jsonl`, y las series
`p5-05-latencia-2h-a.json` y `p5-05-latencia-2h-b.json`. Ninguna contiene aún coste de IPC.

## Fuentes y límites vigentes

- `config/control/plazos.yaml`: `detector_timeout_ms=500`, `max_frame_age_ms=500`. La carga de A
  ya los valida en `src/infer/plazos.py`, sin incorporarlos a `config_sha256`.
- Contrato A→B v1: un evento por `frame_id`; `t_capture_ms` estrictamente creciente por secuencia;
  `t_emit_ms >= t_capture_ms`; `stale` lleva dimensiones originales válidas, detecciones vacías y
  ningún `error`; `error` lleva `error.code` y detecciones vacías. Si no se logró leer la imagen,
  las dimensiones pueden ser `null`. B trata `stale` y `error` como STOP.
- Hoy `src/infer/eventos.py` decodifica en el principal y llama al predictor en el mismo proceso.
  Después publica el JSONL; el calentamiento ocurre antes del origen del reloj del run. La nueva
  ruta debe conservar los IDs, validación, orden y una sola publicación por JPEG.
- `src/control/__main__.py` escribe el `run.json` **de B**, con SHA del archivo de plazos bajo
  `config.plazos.yaml`. A registrará sus propios plazos en un manifiesto separado y no escribirá
  ni alterará el `run.json` de B.

## Modelo de confianza de rutas locales y revisión manual S8707

**Alcance actual.** Un operador local de confianza ejecuta `python -m infer` y selecciona
`--input`, `--weights` y `--output`. En los dos scripts de validación P5-06, el operador selecciona
`--weights` y `--output`; los JPEG de prueba se generan o se toman de rutas fijas del proyecto.
La posibilidad de escribir evidencias fuera del repositorio es deliberada y está documentada en
P5-05. Los argumentos CLI no son confiables por el mero hecho de ser argumentos: este modelo
depende de **quién los proporciona**. No se encontró en el repositorio una ruta desde JSONL,
peticiones de red o código de Grupo B que construya esos argumentos. Una automatización externa
podría invocar el CLI con valores de otra procedencia; antes de hacerlo debe revisar este límite.

El proceso principal y el trabajador `spawn` operan con los permisos de la cuenta que los
ejecuta; el código no eleva privilegios. El CLI **no debe utilizarse como servicio privilegiado**
que procese rutas aportadas por terceros. El operador debe elegir directorios de salida bajo su
control y protegerlos, incluidos sus directorios padres, contra modificaciones concurrentes de
usuarios no confiables. Si otro actor puede sustituir archivos o enlaces mientras corre el
script, las comprobaciones por ruta no aseguran que una lectura posterior alcance el mismo
archivo. La creación exclusiva impide sobrescribir el nombre final existente; `O_NOFOLLOW` se
usa donde existe, pero no protege todos los componentes padres ni la lectura posterior de los
JSONL. Los JPEG sintéticos tienen nombres fijos y `cv2.imwrite` no ofrece creación exclusiva.

**Integraciones futuras.** Si un invocador recibe rutas de una fuente externa no confiable,
deberá imponer una raíz de salida obligatoria y realizar las operaciones respecto a directorios
abiertos o con un mecanismo equivalente resistente al reemplazo de enlaces simbólicos. La
opción `raiz_restringida` actual hace una comprobación de pertenencia al resolver la ruta, pero
es opcional y por sí sola no cierra una carrera si un atacante puede cambiar componentes padres.
La protección nueva y sus pruebas de enlaces, carreras y permisos deberán verificarse en macOS
y Windows antes de conectar tal invocador. Esto no cambia la interfaz local ni obliga a guardar
las evidencias actuales dentro del repositorio.

Las cuatro observaciones siguientes son **vulnerabilidades abiertas reportadas por SonarCloud**,
no *security hotspots*. Su flujo señalado parte de `--output` de
`resultados/p5-06-validacion-real.py`; la descripción genérica de SonarCloud menciona HTTP, pero
ese script usa `argparse` y no recibe una petición HTTP. Esta justificación prepara una revisión
manual, **sin marcar ninguna observación como falso positivo o aceptada**. En cada revisión se
debe confirmar quién invoca el CLI, cómo obtiene la ruta y con qué permisos corre.

| Observación S8707 | Origen real y operación | Controles actuales y riesgo condicionado | Riesgo residual para revisión |
|---|---|---|---|
| [`validacion-real.py:38`](https://sonarcloud.io/project/issues?pullRequest=86&open=AaGavGW9NBQiGCnbuTlJ&id=karenelizabg_Proyecto05-MLOPS) | `--output` pasa por `directorio_evidencia` y `ejecutar_run`; `_leer_jsonl` lee la ruta devuelta del JSONL generado. Su contenido no se utiliza como ruta. | La salida nace en un directorio nuevo y el JSONL se crea de forma exclusiva. Bajo el uso local, la ruta base la elige el operador. Un tercero que imponga `--output` podría elegir dónde se genera la evidencia, pero la lectura normal sigue sobre ese JSONL recién creado. | Un actor que pueda modificar el directorio podría sustituir el JSONL antes de `read_text`; no hay una verificación de identidad del archivo para esa lectura. |
| [`validacion-real.py:42`](https://sonarcloud.io/project/issues?pullRequest=86&open=AaGavGW9NBQiGCnbuTlK&id=karenelizabg_Proyecto05-MLOPS) | `--output` forma `salida / "jpeg_sinteticos"`; `_crear_jpeg` ejecuta `carpeta.mkdir()` y después escribe JPEG de nombres fijos. | `salida` se crea con `exist_ok=False`; la subcarpeta también debe ser nueva. Un argumento impuesto por un tercero podría crearla fuera de la ubicación prevista, dentro de los permisos del proceso. | Un enlace en un directorio padre o una sustitución concurrente de los archivos nuevos podría desviar las escrituras de `cv2.imwrite`. |
| [`rutas_seguras.py:21`](https://sonarcloud.io/project/issues?pullRequest=86&open=AaGavGMHNBQiGCnbuTlG&id=karenelizabg_Proyecto05-MLOPS) | `args.output` llega a `directorio_evidencia`; `Path(ruta)` llega a `mkdir(parents=True, exist_ok=False)`. Ambos scripts llaman sin `raiz_restringida`. | No sobrescribe el directorio final existente. Una raíz opcional rechaza un escape observado al resolver la ruta, pero el uso local permite deliberadamente destinos externos. | Sin raíz obligatoria, un invocador no confiable puede elegir cualquier destino escribible. La comprobación de raíz, cuando se usa, no evita cambios concurrentes de enlaces padres. |
| [`rutas_seguras.py:29`](https://sonarcloud.io/project/issues?pullRequest=86&open=AaGavGMHNBQiGCnbuTlH&id=karenelizabg_Proyecto05-MLOPS) | Una ruta derivada de `--output` llega a `abrir_exclusivo` desde los scripts o el principal de A; `os.open` crea JSONL, manifiesto o resumen. | `O_CREAT|O_EXCL` impide reemplazar el nombre final existente; `O_NOFOLLOW` se añade donde el SO lo ofrece. El proceso solo puede escribir donde su cuenta tenga permiso. | No se restringen directorios padres; enlaces o cambios concurrentes en ellos pueden redirigir la creación. Una automatización con más privilegios que el proveedor de la ruta ampliaría el impacto. |

**Criterio para la revisión:** si se comprueba que una fuente menos confiable controla `--output`
en un uso actual, la observación correspondiente requiere protección de código y pruebas de la
integración. Si el uso queda limitado al operador local y a sus permisos, documentar esa
evidencia y evaluar cada flujo individualmente antes de decidir su estado en SonarCloud. No se
desactivan reglas ni se excluyen archivos para obtener una calificación.

## Arquitectura propuesta

1. **Principal de A.** Enumera los JPEG y sus `capture_ms`, valida IDs y plazos, mantiene un
   registro ordenado de cuadros pendientes, controla el reloj monotónico relativo al run y es el
   **único** escritor del JSONL de percepción. Conserva el hash esperado del modelo y el hash de
   configuración efectiva para todo el run. Ninguna respuesta del trabajador escribe un evento.
2. **Trabajador persistente.** Se crea con `multiprocessing` y método `spawn` en Windows, macOS
   y Linux. Recibe una referencia local al JPEG junto con `run_id`, `frame_id`, `request_id` y
   generación del proceso, el origen monotónico del run y el instante de captura. Lee y decodifica
   el JPEG, comunica las dimensiones originales cuando las obtiene, vuelve a comprobar la edad
   con el mismo reloj monotónico antes de inferir, ejecuta el predictor CPU/FP32 si sigue vigente
   y devuelve detecciones o un fallo clasificado.
   Atiende una solicitud a la vez; no hay una cola de inferencias en el trabajador.
3. **Canal IPC.** Dos `multiprocessing.Queue` privadas **por generación**, una para solicitudes
   y otra para respuestas, con capacidad de una solicitud en vuelo;
   mensajes pequeños con versión interna, generación, `request_id`, `frame_id`, tipo y payload.
   El principal usa `put_nowait`: inicia el cronómetro **inmediatamente antes** de entregar
   la solicitud al canal, sin esperar bloqueado en una llamada de envío sin límite. Una sola
   solicitud en vuelo permite medir desde antes del traspaso al hilo alimentador; la medición
   incluye espera y serialización IPC. Una respuesta
   solo se acepta si coinciden generación, ID y cuadro. Colas antiguas se cierran tras matar al
   proceso; respuestas tardías o duplicadas se descartan y nunca generan un segundo evento.
4. **Preparación y reinicio.** Antes de aceptar el primer cuadro y tras cada reinicio, el
   trabajador verifica SHA-256 del checkpoint mediante `cargar_pesos`, carga la configuración
   efectiva y comprueba su SHA-256 esperado, construye `DetectorJPEG`, verifica
   `torch.get_num_threads()==2` después de `setup_model` y tras calentar, y completa el
   calentamiento sintético. Solo entonces envía `READY` con ambos hashes y hilos efectivos;
   el principal coteja esos valores antes de enviar otro cuadro. Un `READY` parcial no habilita
   inferencia. Carga y calentamiento se cronometran aparte del plazo de solicitud.
5. **Supervisión.** Al vencer la solicitud, el principal emite `error/detector_timeout` para ese
   cuadro, termina el trabajador bloqueado, espera su salida con un límite controlado y, si hace
   falta, lo mata. No reutiliza sus canales ni espera indefinidamente. Crea una nueva generación
   y vuelve a exigir `READY`. Un cierre o fallo de IPC sin vencimiento se clasifica como
   `detector_exception`, conservando el error original que ya se conozca. Si no puede terminar
   el proceso o reiniciarlo con seguridad, se aplica la ruta de fallo de recuperación.

### Plazo, reloj y clasificación

Para la solicitud `i`, `inicio_i` es el `monotonic()` del principal justo antes de entregar el
mensaje al canal; `fin_i` es el instante en que el principal **recibe la respuesta final completa**.
El límite es `inicio_i + detector_timeout_ms`, con el mismo reloj para ambos extremos. El tiempo
de IPC, lectura JPEG, decodificación, inferencia y respuesta queda dentro. Una respuesta recibida
después del límite no se acepta; al llegar exactamente al límite se acepta y se evalúa su estado.
La salida de la función de envío también consume presupuesto. Una llamada IPC bloqueante sin
supervisión no cumple esta regla. Carga, calentamiento, terminación y reinicio quedan fuera del
cronómetro de **esa** solicitud, pero se miden y registran por separado. No se reinicia el plazo
de una solicitud para ocultar un bloqueo anterior.

El instante de captura y el de publicación siguen siendo los observados por el reloj del run;
no se sustituyen por el deadline ni se corrigen con `max()`. Al recibir la respuesta, el principal
evalúa de nuevo la edad justo antes de serializar/publicar. Precedencia obligatoria:

| Resultado conocido | Evento publicable |
|---|---|
| Fallo de lectura/decodificación confirmado antes del plazo | `error/unreadable_image`, dimensiones `null` si no se obtuvieron |
| Solicitud vencida, aunque el cuadro también esté viejo | `error/detector_timeout` |
| Predictor lanza excepción inesperada | `error/detector_exception` |
| Predictor devuelve datos inválidos | `error/invalid_output` |
| Cuadro legible sin error, edad `> max_frame_age_ms` | `stale`, dimensiones originales, `detections=[]`, sin `error` |
| Cuadro legible y válido, edad `<= max_frame_age_ms` | `ok`, con detecciones incluso si son `[]` |

La prioridad es **error > stale > ok**. Una respuesta que incluye fallo específico recibido a
tiempo no se reemplaza por `stale` aunque el cuadro haya envejecido. Si el trabajador ya comunicó
dimensiones, el principal las conserva para un eventual error o `stale`; no relee el JPEG para
recuperarlas. Si el proceso muere mientras lee, no se afirman dimensiones que nunca se obtuvieron.
Un bloqueo de lectura sin diagnóstico recibido antes del deadline se clasifica como
`detector_timeout`, no como una supuesta imagen ilegible.
El tiempo de escritura del JSONL se observa por separado; `t_emit_ms` se toma al publicar, tan
cerca de la escritura como permita la ruta actual, sin fingir que la escritura ocurrió antes.

### Recuperación y cola de cuadros

- El principal conserva el orden de entrada. A lo sumo hay una solicitud en vuelo; los siguientes
  JPEG permanecen en la cola del principal con sus IDs y capturas ya asignados. Cada cuadro tiene
  estado de publicación pendiente/publicado; solo la transición única a publicado escribe JSONL.
  Se validan el evento y el flujo antes de escribir, y se vacía el archivo por evento.
- Tras un timeout, el cuadro que venció obtiene su evento de error. Los demás conservan su turno.
  Cuando el nuevo trabajador está listo, cada cuadro pendiente se **decodifica sin inferir** si
  ya excede `max_frame_age_ms`; si la lectura funciona, se publica `stale` con dimensiones válidas.
  Si es ilegible, `unreadable_image`. Esta solicitud de solo lectura también tiene su propio plazo
  de 500 ms desde envío hasta respuesta; si vence, se publica `detector_timeout`. Si el cuadro
  sigue vigente tras lectura, se ejecuta la inferencia normal dentro de la misma solicitud.
- El tiempo transcurrido durante reinicio cuenta para la **edad** de los cuadros, aunque no cuenta
  en el plazo de una solicitud que aún no se ha enviado. No se infiere sobre un cuadro ya viejo.
  Si un cuadro envejece durante la predicción terminada, se publica `stale`, salvo error conocido.
- Si reiniciar o verificar `READY` falla, el principal emite un evento `error/detector_exception`
  por cada cuadro pendiente no enviado; conserva las dimensiones ya conocidas y usa `null` solo
  cuando no se logró leer. Para capturas explícitas futuras espera el instante real de captura
  antes de publicar, de modo que `t_emit_ms >= t_capture_ms` siga siendo cierto. Cierra con
  **código distinto de 0 solo después de registrar y validar esos eventos**. El cuadro vencido
  conserva `detector_timeout`; no se reclasifica por el fallo posterior del reinicio.
- La garantía de un evento por JPEG aplica al conjunto de entradas enumeradas tras validar run,
  configuración y tiempos. Un archivo ausente con extensión JPEG sigue siendo una entrada. Un
  fallo antes de disponer de IDs, plazos o hashes válidos es un error de configuración y debe
  informarse sin producir eventos contractualmente falsos. Se probará por separado.

### Riesgos y alternativas descartadas para esta etapa

- Un hilo con cancelación cooperativa no puede detener con certeza una llamada bloqueada de
  PyTorch, OpenCV o Ultralytics. Un proceso nuevo por JPEG sí se puede terminar, pero repetiría
  carga y calentamiento en cada cuadro y alteraría la latencia; el persistente aprobado evita ese
  coste normal y paga reinicio solo después de fallas.
- La cola IPC puede bloquear o atrasar el envío. Por eso el principal no hace un `send()`
  indefinido y empieza el plazo antes de entregar el mensaje al canal. Un solo cuadro en vuelo y
  canales por generación limitan respuestas antiguas. La implementación deberá comprobar en
  Windows y macOS que cerrar las colas y matar el proceso desbloquea el supervisor.
- El `spawn` carga el runtime en cada reinicio y el checkpoint puede haber cambiado o desaparecido.
  Un hash discrepante impide `READY`; la recuperación falla de forma visible y se publican los
  errores pendientes. El tiempo de recuperación puede volver viejos los cuadros en cola.
- El contrato exige dimensiones válidas para `stale`. Si la decodificación no concluye antes del
  plazo, solo se conoce un timeout; no se debe fabricar un `stale` con dimensiones ficticias.
- Los relojes monotónicos de principal y trabajador deben referir el mismo reloj del host al
  comprobar edad. La prueba multiproceso verificará esa correspondencia en Windows y macOS;
  el principal mantiene la autoridad final sobre `t_capture_ms` y `t_emit_ms`.

## Evidencia del run

A escribirá un manifiesto propio, por ejemplo `<run_id>.infer-run.json` junto al JSONL, sin
colisionar con el `run.json` de B. Contendrá `detector_timeout_ms`, `max_frame_age_ms`, SHA-256
de los **bytes** de `config/control/plazos.yaml`, hash efectivo del detector, hash del modelo,
versiones/runtime, origen del reloj, conteos de eventos por estado y cronología de generaciones,
timeout, terminación y reinicio (duraciones reales, éxito o fallo). El manifiesto debe identificar
el JSONL y su SHA-256. Se calcula el hash de los mismos bytes que se analizan como YAML para
evitar registrar un archivo distinto al aplicado. `plazos_sha256` se guarda como campo separado:
no altera `config_sha256`, el contrato v1 ni `config/detector.json`. La evidencia de recuperación
incluye también stderr y código de salida local, con rutas privadas redactadas al compartirla.

## Regla de aceptación funcional, fijada antes de medir

Cada escenario utiliza JPEG sintéticos o copias autorizadas fuera de las secuencias oficiales.
Pruebas deterministas inyectan reloj, transporte y trabajador falso para provocar límites sin
esperar 500 ms reales; pruebas de proceso usan un trabajador real controlado que se bloquea.

| Escenario obligatorio | Criterio de aprobación |
|---|---|
| JPEG válido con y sin detecciones; JPEG vacío, truncado y ausente | Un evento v1 por JPEG, `ok` o `unreadable_image` correcto, dimensiones y continuidad |
| Excepción, NaN/clase/bbox inválidos | `detector_exception` o `invalid_output`; causa y dimensiones conservadas; error prevalece sobre edad |
| Respuesta antes, exactamente en y después de 500 ms; envío o lectura bloqueados | Clasificación según deadline medido de extremo a extremo; proceso bloqueado termina y no publica tarde |
| Reinicio correcto | Nuevos hashes y `torch_threads=2` comprobados, calentamiento completo antes de recibir cuadro |
| Cuadro pendiente viejo tras reinicio | `stale` con dimensiones originales, sin llamada al predictor; ilegible sigue siendo error |
| Cuadro pendiente vigente tras reinicio | Inferencia normal, aunque el anterior haya terminado por timeout |
| Reinicio fallido, salida tardía, IPC roto, varias entradas pendientes | Un evento por `frame_id` en orden, sin duplicados ni huecos; salida distinta de 0 tras escribir errores |
| Edad 499, 500 y 501 ms; errores con cuadro viejo | Límite `>` exacto y precedencia error > stale > ok; tiempos monotónicos reales |
| Entrega a B de `detector_timeout` y `stale` | STOP y error registrado por B, sin cambiar Grupo B |
| Manifiesto de A | Dos plazos y SHA de YAML correctos; hashes separados; JSONL y conteos verificables |

Se rechaza la implementación si falta un evento, hay duplicados, se permite una respuesta tardía
como `ok`, se deja un proceso bloqueado vivo sin control, se infiere un cuadro viejo tras reinicio,
se cambian hashes/contrato/Grupo B, o se declara éxito tras un reinicio fallido sin registrar todos
los pendientes. Los eventos y comandos deben pasar los validadores v1. La CI de Ubuntu ejecutará
las pruebas deterministas y de proceso compatibles; Andrea repetirá de forma independiente en
Windows. La validación en macOS cubrirá el mismo conjunto funcional.

## Regla histórica de benchmark y comparación con P5-05

Este apartado conserva la metodología redactada antes de la serie Mac del 1 de noviembre. La
adenda de Karen al final fija los criterios y el procedimiento para evidencia posterior.

**No ejecutar ni modificar esta regla después de ver los resultados sin registrar una desviación.**
En cada máquina, usar el mismo checkpoint, configuración efectiva de dos hilos, Python/runtime,
JPEG byte a byte, dispositivo CPU y condiciones de energía/carga documentadas para dos rutas:

1. **Un proceso, control emparejado:** misma lectura JPEG, `DetectorJPEG.inferir`, validación de
   resultado y solicitud completa, sin IPC ni carga/calentar en cada muestra.
2. **Proceso persistente:** desde antes de enviar la solicitud hasta recibir la respuesta final,
   con IPC, lectura, inferencia y validación; sin carga/calentar en cada muestra.

Preparar ambas rutas con verificación de SHA, construcción y calentamiento sintético. Después
hacer **10 solicitudes JPEG de calentamiento excluidas** y **50 solicitudes medidas** por ruta.
Guardar cada duración monotónica y calcular p50 (mediana) y p95 por interpolación lineal, como
`resultados/p5-05-benchmark.py`. Hacer series independientes y conservar orden de ejecución,
sin mezclar muestras de distintas máquinas o versiones. La diferencia de coste IPC se reporta
como `p50_persistente - p50_un_proceso` y `p95_persistente - p95_un_proceso`, en ms, además de
ambos valores absolutos y máximo. El control emparejado es necesario: los JSON de P5-05 miden
`DetectorJPEG.inferir` y **no** incluyen IPC ni toda la misma envoltura de solicitud. Sus series
Mac de dos hilos (p50 31.00/35.00 ms, p95 40.72/46.86 ms) son referencia histórica, no una
resta válida contra una medición nueva en otra máquina. Los p95 138 ms y máximo 189 ms
comunicados por Andrea para Windows tampoco son una medición IPC.

La instrumentación P5-06 usa `_evento_cuadro` para el control, desde la marca monotónica
inmediatamente anterior a la lectura del JPEG hasta su retorno tras validar el resultado. El
predictor supervisado usa esa misma función en el hijo; su muestra comienza inmediatamente
antes de llamar a `solicitar` y termina tras recibir y verificar la respuesta final en el
principal. Dentro de `solicitar`, el plazo funcional comienza antes de `put_nowait`.
Ambas rutas usan la misma imagen, plazos, configuración, checkpoint y diez solicitudes JPEG de
calentamiento. La muestra supervisada incluye el protocolo de colas, la respuesta de
dimensiones, lectura, inferencia, validación y comprobación de identidad de la respuesta. La
diferencia es el coste conjunto de supervisión e IPC, no una medición aislada del transporte.
La publicación JSONL queda fuera de ambos límites y se verifica en pruebas funcionales. Cada
muestra usa una captura del instante real de entrada; no se restan calentamiento ni reinicio.

Comparar las detecciones por `frame_id` con las corridas P5-05 de dos hilos: estado, orden,
cantidad, clase, confianza y bbox, excluyendo IDs de run y tiempos. Guardar diferencias por
campo y el hash de cada JPEG. En el mismo host/runtime y con el mismo JPEG se exige que la
arquitectura no cambie el resultado; toda diferencia requiere investigación y aprobación antes
de declarar equivalencia. Entre plataformas se reportan las diferencias sin suponer identidad
bit a bit. No usar S01–S08 ni `datos/cuadros/`; los 29 JPEG de P5-05 son copias privadas fuera
del repositorio y solo se usarán si siguen autorizadas y disponibles. Si no lo están, se
documentará la ausencia y no se afirmará comparación completa con P5-05.

La comparación implementada para la revisión Windows exige igualdad estricta de estado,
dimensiones y detecciones (cantidad, orden, clase, confianza y cada coordenada bbox) entre
control y supervisado **en el mismo host**. Frente al JSONL histórico P5-05 conserva los
valores originales, su SHA-256, diferencias firmadas por confianza y coordenada, y máximos
absolutos. Clasifica coincidencia exacta, diferencia numérica pendiente o discrepancia
estructural. Una diferencia numérica entre plataformas se registra sin descartar la muestra;
**no queda aprobada** por completar la serie ni se aplica tolerancia implícita. Un cambio de
estado, dimensiones, cantidad, clase u orden detiene la serie tras guardar la evidencia
parcial. También la detienen un evento inválido o una diferencia entre rutas locales. Toda
discrepancia requiere investigación antes de declarar equivalencia o aceptación funcional.
El benchmark conserva los mismos 10 pares excluidos y 50 medidos; el comparador se ejecuta
fuera del intervalo cronometrado y no cambia los límites de latencia de Karen.

Medir el reinicio **por separado** desde la decisión de terminar el trabajador hasta recibir
`READY` verificado del reemplazo; desglosar terminación, creación, hashes/carga y calentamiento.
Hacer 10 reinicios de estabilización excluidos y 50 reinicios medidos en macOS y Windows, guardar
cada muestra y p50/p95; registrar también
fallos, sin eliminarlos de la evidencia. Esas duraciones no se descuentan de la edad del cuadro.
El total de cada reinicio comienza justo antes de `detener()` y termina al verificar el nuevo
`READY`. Se registran detención e `iniciar()` por separado. Esta última se descompone con marcas
del mismo reloj monotónico del host: creación de colas/proceso y `spawn`, arranque del hijo,
carga y verificación de configuración/modelo/hilos, calentamiento y entrega de READY al
principal. Se conserva el intervalo de coordinación entre detener e iniciar para que las fases
sumen el total observado salvo redondeo; si el hijo empieza a cargar antes de que `start()`
retorne, se registra y resta el solapamiento real de ambos procesos. Estas marcas no alteran
el plazo de 500 ms de las
solicitudes. El archivo de benchmark conservará muestras individuales en orden, fases de cada
reinicio, hashes, versiones, datos del host y energía, método de percentil lineal de NumPy y
detecciones frente a P5-05. p50 es la mediana; p95 usa interpolación lineal. El porcentaje de
coste adicional divide la diferencia de percentiles entre el percentil del control emparejado.
El ejecutable preparado es `resultados/p5-06-benchmark.py`: recibe la ruta local verificada del
checkpoint, un destino nuevo, responsable y modo de energía documentado. Fija la misma copia
versionada de la taza central (SHA-256 de P5-05) para las dos series en el mismo orden de 60
solicitudes y conserva también las diez duraciones excluidas. Si hay un fallo, escribe evidencia
parcial con fase, índice y muestras completadas, sin presentar percentiles incompletos como
resultado. El script no se ejecutará hasta autorizar las series oficiales.
La CI Ubuntu comprueba funcionalidad, no reemplaza las mediciones independientes Windows de
Andrea ni la medición macOS. Registrar SO, CPU, RAM, Python, Torch, Ultralytics, OpenCV, modo de
energía, versiones, hashes, hilos efectivos, imagen y SHA, comandos, muestras brutas, método de
percentil, fecha, responsable y cualquier desviación del procedimiento. Mantener por separado
resultados de detección, coste IPC, latencia total y reinicio.

### Decisión pendiente al redactar la regla histórica

El límite funcional de timeout es **500 ms por solicitud**, y el plazo de edad también es
**500 ms**; no se relajan por el coste IPC. Karen aún no definió un máximo admisible para
`Δp50`, `Δp95`, p95/máximo de la solicitud completa, ni para el tiempo de reinicio en Windows
o macOS. Esos umbrales quedan **pendientes de decisión de Karen antes de emitir una aprobación de
rendimiento**. No se traslada automáticamente la regla histórica de P5-05 para seleccionar hilos
(p95 ≤150 ms y máximo ≤200 ms) a estas métricas nuevas. Un resultado sin muestras brutas, sin
control emparejado, sin verificación de hashes/hilos, sin medición Windows independiente o con
desviaciones no explicadas no puede declararse aprobado. Los fallos funcionales anteriores sí
son rechazo inmediato, aunque la latencia agregada parezca buena.

## Adenda de Karen: criterios oficiales posteriores a la serie Mac del 1 de noviembre

Esta decisión se registró **después** de la serie Mac conservada en
`resultados/p5-06-benchmark-mac-2026-11-01/`. No cambia sus muestras ni convierte su
procedimiento en uno intercalado. Esa serie ejecutó control y supervisado en bloques y los
reinicios se provocaron directamente con `detener()`/`iniciar()`, sin timeout forzado. No midió
desde el inicio de una solicitud hasta publicar `detector_timeout`. El argumento manual de
energía decía batería; el preflight formal guardado y las etapas medidas muestran AC. La causa
del cambio entre la consulta previa y el preflight formal no está registrada. La aceptación
según esta adenda requiere evidencia adicional; no se infiere de la serie Mac previa.

Para una nueva serie oficial, ejecutar **pares intercalados** control→supervisado con el mismo
JPEG, checkpoint, configuración, CPU y dos hilos: 10 pares de calentamiento excluidos y 50 pares
medidos (50 muestras por ruta). Conservar cada muestra y usar p50 mediana y p95 lineal sin
redondear al compararlos con los límites. El coste observado incluye supervisión e IPC, no solo
transporte. Se exige simultáneamente:

- `p50_supervisado − p50_control ≤ 5 ms`.
- `p95_supervisado − p95_control ≤ 10 ms`.
- `p95_supervisado ≤ 150 ms` y `máximo_supervisado ≤ 200 ms`.
- Cero solicitudes normales de más de 500 ms.

En cada caso de **timeout forzado**, medir con reloj monotónico desde el inicio de la solicitud
hasta la publicación del evento `error/detector_timeout`. Todos deben quedar entre **500 y
600 ms**, inclusive, y la secuencia debe continuar sin eventos perdidos o duplicados. Este
intervalo incluye la publicación; la serie de latencia normal y los tiempos de reinicio no
sustituyen esta medición.

La recuperación debe lograr **50 de 50 reinicios** verificados con SHA-256 de modelo y
configuración, `torch_threads=2` y calentamiento antes de READY. Verificar clasificación de JPEG
durante recuperación (`stale`, `unreadable_image` o inferencia vigente) y terminación controlada
con eventos pendientes registrados si el reinicio falla. El reinicio no tiene umbral numérico:
guardar todas sus duraciones y comunicarlas a P5-16.

Se conserva **una sola serie oficial por máquina**, con datos brutos, fallos, descartes,
condiciones y desviaciones. El preflight debe obtener del sistema alimentación AC y ahorro
desactivado, registrar fuente y bloquear la serie si cualquiera es desconocido o falla. En
Windows se exige además OneDrive y VS Code cerrados. La validación decisiva será la ejecución
independiente de Andrea en Windows. Los umbrales anteriores sustituyen la nota previa de
"decisión pendiente" solo para esta adenda; no se aplican retroactivamente para afirmar que la
serie Mac en bloques cumple el nuevo procedimiento.

## Evidencia posterior: publicación de timeout y recuperación simulada

La corrección posterior a la regla de aceptación publica y vacía con `flush()` el evento
`error/detector_timeout` **antes** de detener y reiniciar al trabajador. El siguiente cuadro
espera READY verificado. Si la publicación falla durante `write` o `flush`, el run aborta y la
traza no declara el evento publicado. El instante inicial de la traza es la misma lectura del
reloj monotónico que fija el deadline inmediatamente antes del envío; la marca final se toma
después del `flush`. La duración y el resultado de recuperación se guardan fuera del evento
A→B v1. No se modificó el plazo de 500 ms ni la prioridad error > stale > ok.

`resultados/p5-06-validacion-timeout.py` y `resultados/P5-06-VALIDACION-TIMEOUT.md` describen
los comandos para Mac y Windows. La evidencia local original se conserva en
`resultados/p5-06-timeout-simulado-mac-2026-11-02/`, con `SHA256SUMS`, muestras individuales,
JSONL y manifiestos. En Mac se observaron 50/50 publicaciones entre 500 y 600 ms, 50/50
recuperaciones con READY y duraciones de 503.0183750204742 a 525.7063750177622 ms. El fallo
terminal simulado conservó el timeout y emitió dos errores para los cuadros pendientes; la
política de salida del CLI devolvió 1 al recibir ese resultado mediante sustitución controlada
de la llamada. Son **trabajadores simulados**, con hashes declarados: estos recorridos no
demuestran carga ni hash criptográfico del checkpoint real. La validación previa con el modelo
oficial y la futura repetición independiente de Andrea en Windows son evidencias separadas.

`flush()` no equivale a `fsync()`: esta validación mide entrega al sistema operativo, no
durabilidad tras una caída. Un error de escritura impide garantizar la publicación de los
cuadros pendientes en ese mismo JSONL. La serie de latencia normal y los 50 reinicios directos
del benchmark Mac histórico permanecen distintos de estos 50 reinicios provocados por timeout;
sus datos brutos no se alteraron.
