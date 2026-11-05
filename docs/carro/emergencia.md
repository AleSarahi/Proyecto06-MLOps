# Emergencia y matriz de fallos (P5-22)

Qué hace el sistema ante cada fallo, cuánto tarda el carro en quedar detenido y qué hacer a
mano si algo sale mal con el carro real. El protocolo PC → carro está en
[`protocolo.md`](protocolo.md) y los plazos en
[`config/control/plazos.yaml`](../../config/control/plazos.yaml).

## Procedimiento de emergencia físico

**Antes de cada prueba con el carro en el piso:**

1. Ruedas en el aire para la primera orden del día. Comprobar que `STOP` las detiene.
2. Una persona solo para la emergencia, con la mano libre y cerca del carro. No es la misma que
   opera la PC.
3. La batería de motores va apagada al encender la placa, y se prende después de ver la IP en el
   Monitor Serie (`protocolo.md`, *Hardware*).
4. Velocidad baja: `TECHO` del PWM calibrado en la fase 2, no el máximo.

**Si el carro hace algo inesperado**, en este orden:

1. **La tecla de emergencia del lazo** (P5-21). Llama a `Supervisor.emergencia()`: `STOP`
   inmediato y enclavado. *Pendiente: anotar aquí la tecla cuando el lazo exista.*
2. Si no frena en menos de un segundo, o la PC no responde: **levantar el carro** del piso.
3. **Desconectar la batería de motores.** La placa y la cámara pueden seguir encendidas; los
   motores ya no.
4. Cerrar el lazo con Ctrl+C. Al salir manda `STOP` (fallo 8 de la matriz).

**Para volver a arrancar después de una emergencia:** el rearme es explícito y pide un cuadro
fresco de la cámara (fallo 7). Primero se rearma y después, con cuadros libres, el carro vuelve a
moverse. Antes de rearmar, revisar por qué se activó.

**Se prueba en la fase 2** con Andy y Angel: las ruedas en el aire primero y después en el piso,
con el tiempo de paro medido en video a 60 fps.

## Matriz de fallos

Las pruebas automáticas están en [`tests/test_matriz_fallos.py`](../../tests/test_matriz_fallos.py).
Corren el supervisor, la política y los plazos reales de `control` contra el carro simulado
(`python -m simulador`), con UDP real en localhost. Del lado de la PC usan un puente mínimo,
`simulador/puente.py`, que es el `AdaptadorVirtual` más el emisor de P5-20. Ese puente no es el
adaptador de P5-21.

**Qué se mide:** el tiempo, con el reloj de la placa simulada, desde que empieza el fallo hasta
que el carro queda `DETENIDO`. El límite es `watchdog_ms`, 600 ms.

```bash
uv run python -m simulador.matriz                      # los 9, con la tabla
uv run python -m simulador.matriz 4 9 --salida m/      # algunos, y guarda matriz.json y bitácoras
```

| # | Fallo | Qué debe pasar | Cómo se provoca | Desde dónde se mide | Medido | Límite |
|---|---|---|---|---|---|---|
| 1 | Cámara cortada | STOP por watchdog o por orden vencida | Dejan de llegar cuadros | Último cuadro | 416 ms | 600 ms |
| 2 | Cuadro con más de 500 ms de edad | STOP al recibirlo (`cuadro_viejo` o `stale`) | Un `ok` de 600 ms de edad y un `stale` | Llegada del cuadro | 3 ms | 600 ms |
| 3 | Detector con excepción, timeout, imagen ilegible o salida inválida | STOP (`error_detector:<code>`) | Un evento `error` con cada uno de los 4 códigos del contrato | Llegada del error | 2 ms | 600 ms |
| 4 | El carro no responde | La PC lo anota y avisa (`avisos.jsonl`); el carro para solo | El carro deja de recibir mientras la PC sigue mandando `AVANZAR` | Inicio del fallo | 205 ms | 600 ms |
| 5 | Orden repetida o fuera de orden | La vieja no se aplica y frena (`SEQ_VIEJA`) | Duplicar y desordenar datagramas | Inicio del fallo | 215 ms | 600 ms |
| 6 | Comando fuera de rango o no finito | Se rechaza y hay STOP | Política que da velocidad 1.5, NaN o infinito, y una orden de 1.5 directo a la placa | Llegada del cuadro | 3 ms | 600 ms |
| 7 | Emergencia | STOP inmediato y enclavado hasta un rearme explícito con percepción fresca | `Supervisor.emergencia()`, cuadros libres, rearme con un cuadro viejo y luego con uno fresco | Emergencia | 1 ms | 600 ms |
| 8 | Cierre del programa o excepción | STOP antes de salir | Cierre normal y una excepción dentro del lazo | Cierre | 1 ms | 600 ms |
| 9 | WiFi cortado a mitad de una orden | El carro para solo | Se corta el WiFi del carro con un `AVANZAR` vigente | Corte | 3 ms | 600 ms |

Medido el 2026-11-04 en la laptop de A3 (Windows 11, Intel i5-1135G7). Cuando un fallo tiene
varias variantes, se reporta la peor. Los números cambian unos milisegundos entre corridas; la
prueba solo exige que no pasen de 600 ms.

**Cómo leer los tiempos largos:**

- **Fallo 1 (416 ms):** el carro ya frenó solo cuando venció la orden (400 ms desde que llegó). El
  supervisor manda además su STOP de reloj (`orden_vencida`).
- **Fallo 4 (205 ms):** la última orden aceptada ya llevaba unos 200 ms cuando empezó el fallo.
  Medido desde esa orden, son los 400 ms de su vigencia. La PC no puede frenar un carro que no la
  oye: lo detiene la placa.
- **Fallo 5 (215 ms):** es lo que tarda en llegar el siguiente datagrama, a 5 fps.

**Lo que esta matriz no cubre:**

- La latencia real del WiFi, la inercia del carro y la distancia de frenado: se miden en P5-23.
- El firmware real. El simulador repite las reglas de `Placa`, el modelo de referencia, y el
  firmware se prueba aparte (P5-20).
- **Fallo 9:** en el carro real, al perder la asociación con el punto de acceso la placa frena de
  inmediato (`protocolo.md`). Si la red sigue asociada pero no pasan paquetes, es el fallo 4: frena
  por vigencia, en 510 ms o menos.

## Notas de diseño

- **Una orden vieja frena el carro.** El protocolo v1 frena ante cualquier rechazo, también
  `SEQ_VIEJA`. Por eso un paquete que el WiFi duplique detiene el carro hasta la siguiente orden.
  Es seguro, pero puede verse como un tirón en el video.
- **No se rechazan órdenes "vencidas" al llegar.** El protocolo no manda la hora de la PC: la
  vigencia se cuenta desde que la orden llega a la placa. Las órdenes atrasadas se cubren con la
  regla de `seq` y el tope de 500 ms.
