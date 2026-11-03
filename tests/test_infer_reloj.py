"""Coherencia del reloj de P5-06 al usar multiprocessing con spawn."""

from __future__ import annotations

import multiprocessing as mp
import sys

from infer.reloj import descripcion_reloj, leer_reloj_ns, leer_reloj_s


def _lectura_hija(canal) -> None:
    canal.put(leer_reloj_ns())


def test_perf_counter_ns_es_comparable_entre_procesos_spawn() -> None:
    contexto = mp.get_context("spawn")
    canal = contexto.Queue()
    proceso = contexto.Process(target=_lectura_hija, args=(canal,))
    inicio_padre = leer_reloj_ns()
    try:
        proceso.start()
        lectura_hija = canal.get(timeout=15)
        fin_padre = leer_reloj_ns()
        proceso.join(timeout=15)
        assert proceso.exitcode == 0
        assert inicio_padre <= lectura_hija <= fin_padre
    finally:
        if proceso.is_alive():
            proceso.terminate()
            proceso.join(timeout=5)
        canal.close()
        canal.join_thread()


def test_descripcion_reporta_el_reloj_real_sin_medicion_inventada() -> None:
    metadatos = descripcion_reloj()
    assert metadatos["nombre"] == "perf_counter"
    assert isinstance(metadatos["implementacion"], str) and metadatos["implementacion"]
    assert metadatos["resolucion_reportada_s"] > 0
    assert isinstance(leer_reloj_s(), float)
    assert isinstance(leer_reloj_ns(), int)
    if sys.platform == "win32":
        assert "QueryPerformanceCounter" in metadatos["implementacion"]
