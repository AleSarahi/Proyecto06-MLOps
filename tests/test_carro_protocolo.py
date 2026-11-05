"""P5-20: reglas del protocolo de órdenes al carro (modelo `Placa`, sin red)."""

from __future__ import annotations

import pytest

from carro.protocolo import (
    MAX_BYTES,
    TOPE_VIGENCIA_MS,
    Orden,
    Placa,
    Respuesta,
    a_pwm,
    codificar_orden,
    codificar_respuesta,
    decodificar_orden,
    decodificar_respuesta,
    lados,
)


def _o(accion="AVANZAR", v=0.4, g=0.0, seq=2, sesion=7, vig=400) -> bytes:
    return codificar_orden(Orden(sesion, seq, accion, v, g, vig))


def _placa_en_sesion(sesion=7) -> Placa:
    p = Placa()
    assert p.recibir(_o("STOP", 0, 0, seq=1, sesion=sesion), 0).motivo == "OK"
    return p


def test_ida_y_vuelta_de_orden():
    orden, motivo = decodificar_orden(_o("GIRAR_IZQ", 0.4, -0.5))
    assert motivo == "OK"
    assert orden == Orden(7, 2, "GIRAR_IZQ", 0.4, -0.5, 400)
    assert _o() == b"P5C1,7,2,AVANZAR,0.400,0.000,400"


def test_giro_cero_negativo_no_sale_con_signo():
    assert b"-0.000" not in _o("STOP", 0, -0.0)


def test_ida_y_vuelta_de_respuesta():
    r = Respuesta(7, 2, "OK", "MOVIENDO", 118, 104, 123456)
    assert decodificar_respuesta(codificar_respuesta(r)) == r
    assert decodificar_respuesta(b"P5R1,7,2,QUIEN_SABE,MOVIENDO,1,1,1") is None
    assert decodificar_respuesta(b"\xff") is None


@pytest.mark.parametrize(
    "datos",
    [
        b"",
        b"P5C1,basura",
        b"P5C2,7,2,AVANZAR,0.400,0.000,400",  # otra versión
        b"P5C1,7,2,RETROCEDER,0.400,0.000,400",  # acción desconocida
        b"P5C1,7,2,AVANZAR,0.4,0,400,extra",
        b"P5C1,7,2,AVANZAR,nan,0.000,400",
        b"P5C1,7,2,AVANZAR,0.4000,0.000,400",  # más de 3 decimales
        b"P5C1,7,2,AVANZAR,0.400,0.000,400\n\n",
        "P5C1,7,2,AVANZAR,0.400,0.000,400ñ".encode(),
        b"P5C1," + b"9" * MAX_BYTES,
    ],
)
def test_mal_formadas(datos):
    assert decodificar_orden(datos)[1] == "MAL_FORMADA"


def test_acepta_salto_de_linea_final():
    assert decodificar_orden(_o() + b"\n")[1] == "OK"


@pytest.mark.parametrize(
    "orden",
    [
        Orden(0, 2, "AVANZAR", 0.4, 0, 400),  # sesión 0 está reservada
        Orden(7, 0, "AVANZAR", 0.4, 0, 400),
        Orden(2**32, 2, "AVANZAR", 0.4, 0, 400),
        Orden(7, 2, "AVANZAR", 1.5, 0, 400),
        Orden(7, 2, "GIRAR_DER", 0.4, 1.5, 400),
        Orden(7, 2, "AVANZAR", 0.4, 0, 0),
        Orden(7, 2, "AVANZAR", 0.4, 0, TOPE_VIGENCIA_MS + 1),
    ],
)
def test_fuera_de_rango(orden):
    assert decodificar_orden(codificar_orden(orden))[1] == "FUERA_RANGO"


@pytest.mark.parametrize(
    ("accion", "v", "g"),
    [
        ("STOP", 0.4, 0),
        ("STOP", 0, 0.5),
        ("AVANZAR", 0, 0),
        ("AVANZAR", 0.4, 0.5),
        ("GIRAR_IZQ", 0.4, 0.5),  # izquierda es giro negativo
        ("GIRAR_DER", 0.4, -0.5),
        ("GIRAR_IZQ", 0.4, 0),
    ],
)
def test_inconsistentes(accion, v, g):
    assert decodificar_orden(_o(accion, v, g))[1] == "INCONSISTENTE"


def test_lados_y_pwm():
    assert lados(0.4, 0) == (0.4, 0.4)
    izq, der = lados(0.4, -0.5)
    assert izq == pytest.approx(0.2)
    assert der == 0.4
    assert lados(0.4, 1) == (0.4, 0)
    assert a_pwm(0) == 0
    assert a_pwm(0.01, techo=160, minimo=90) == 91
    assert a_pwm(1, techo=160, minimo=90) == 160
    assert a_pwm(2, techo=160, minimo=90) == 160


def test_primera_orden_de_una_sesion_tiene_que_ser_stop():
    p = Placa()
    r = p.recibir(_o("AVANZAR", seq=1), 0)
    assert (r.motivo, r.estado) == ("SESION", "DETENIDO")
    assert p.recibir(_o("STOP", 0, 0, seq=1), 0).motivo == "OK"
    r = p.recibir(_o("AVANZAR", seq=2), 10)
    assert (r.motivo, r.estado) == ("OK", "MOVIENDO")


def test_giro_izquierda_frena_el_lado_izquierdo():
    p = _placa_en_sesion()
    r = p.recibir(_o("GIRAR_IZQ", 0.4, -0.5), 0)
    assert r.pwm_izq < r.pwm_der


@pytest.mark.parametrize(
    ("malo", "motivo"),
    [
        (b"P5C1,basura", "MAL_FORMADA"),
        (_o(v=1.5, seq=3), "FUERA_RANGO"),
        (_o(g=0.5, seq=3), "INCONSISTENTE"),
        (_o(seq=2), "SEQ_VIEJA"),  # repetida
        (_o(seq=1), "SEQ_VIEJA"),  # vieja
        (_o(seq=3, sesion=8), "SESION"),  # otra sesión, no STOP
    ],
)
def test_todo_rechazo_frena(malo, motivo):
    p = _placa_en_sesion()
    assert p.recibir(_o(seq=2), 0).estado == "MOVIENDO"
    r = p.recibir(malo, 50)
    assert (r.motivo, r.estado, r.pwm_izq, r.pwm_der) == (motivo, "DETENIDO", 0, 0)
    assert p.tick(10_000) is None  # ya no hay orden que venza


def test_rechazo_no_avanza_la_secuencia():
    p = _placa_en_sesion()
    p.recibir(_o(seq=5, v=1.5), 0)  # fuera de rango: no cuenta
    assert p.recibir(_o(seq=3), 10).motivo == "OK"


def test_otra_sesion_con_stop_toma_el_control():
    p = _placa_en_sesion(7)
    p.recibir(_o(seq=50, sesion=7), 0)
    assert p.recibir(_o("STOP", 0, 0, seq=1, sesion=8), 10).motivo == "OK"
    assert p.recibir(_o(seq=2, sesion=8), 20).motivo == "OK"
    assert p.recibir(_o(seq=51, sesion=7), 30).motivo == "SESION"


def test_paro_automatico_con_la_vigencia():
    p = _placa_en_sesion()
    p.recibir(_o(seq=2, vig=400), 1000)
    assert p.tick(1399) is None
    r = p.tick(1400)
    assert r is not None
    assert (r.motivo, r.estado, r.seq) == ("VENCIDA", "DETENIDO", 2)
    assert p.tick(1500) is None  # avisa una sola vez


def test_orden_nueva_renueva_la_vigencia():
    p = _placa_en_sesion()
    p.recibir(_o(seq=2, vig=400), 0)
    p.recibir(_o(seq=3, vig=400), 300)
    assert p.tick(500) is None
    assert p.tick(700).motivo == "VENCIDA"


def test_stop_cancela_sin_aviso_de_vencida():
    p = _placa_en_sesion()
    p.recibir(_o(seq=2), 0)
    assert p.recibir(_o("STOP", 0, 0, seq=3), 100).estado == "DETENIDO"
    assert p.tick(1000) is None


def test_stop_atrasado_de_sesion_anterior_no_la_revive():
    """Regresión de la revisión del #102: S7 STOP/AVANZAR, S8 STOP, luego llegan tarde de S7."""
    p = Placa()
    assert p.recibir(_o("STOP", 0, 0, seq=1, sesion=7), 0).motivo == "OK"
    assert p.recibir(_o(seq=2, sesion=7), 10).estado == "MOVIENDO"
    assert p.recibir(_o("STOP", 0, 0, seq=1, sesion=8), 20).motivo == "OK"
    r = p.recibir(_o("STOP", 0, 0, seq=1, sesion=7), 30)
    assert (r.motivo, r.estado) == ("SESION", "DETENIDO")
    r = p.recibir(_o(seq=3, sesion=7), 40)
    assert (r.motivo, r.estado) == ("SESION", "DETENIDO")
    assert p.sesion == 8
    assert p.recibir(_o(seq=2, sesion=8), 50).motivo == "OK"  # la sesión 8 sigue viva


def test_sesion_nueva_tiene_que_ser_mayor():
    p = _placa_en_sesion(100)
    assert p.recibir(_o("STOP", 0, 0, seq=1, sesion=99), 0).motivo == "SESION"
    assert p.recibir(_o("STOP", 0, 0, seq=1, sesion=101), 0).motivo == "OK"


def test_recien_encendida_acepta_cualquier_stop():
    assert Placa().recibir(_o("STOP", 0, 0, seq=1, sesion=1), 0).motivo == "OK"


@pytest.mark.parametrize(
    "datos",
    [
        b"P5R1,7,2,OK,MOVIENDO,256,118,1",  # PWM fuera de 0 a 255
        b"P5R1,7,2,OK,MOVIENDO,-1,118,1",
        b"P5R1,7,2,OK,MOVIENDO,0,0,1",  # moviendo sin motores
        b"P5R1,7,2,OK,DETENIDO,104,0,1",  # detenido con motores
        b"P5R1,7,2,VENCIDA,MOVIENDO,104,118,1",  # vencida pero moviendo
        b"P5R1,7,2,SEQ_VIEJA,MOVIENDO,104,118,1",  # todo rechazo frena
    ],
)
def test_respuestas_incoherentes_se_rechazan(datos):
    assert decodificar_respuesta(datos) is None


def test_placa_siempre_contesta_coherente():
    p = _placa_en_sesion()
    for datos in (_o(seq=2), _o("GIRAR_IZQ", 0.4, -1, seq=3), b"basura", _o(seq=3)):
        assert decodificar_respuesta(codificar_respuesta(p.recibir(datos, 0))) is not None
    p.recibir(_o(seq=9), 0)
    assert decodificar_respuesta(codificar_respuesta(p.tick(1000))) is not None
