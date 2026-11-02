import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bench.__main__ import main as bench
from bench.arnes import sha256_archivo
from bench.detector import DetectorFalso
from bench.limites import (
    CUMPLE,
    CUMPLE_EN_P95,
    NO_CUMPLE,
    ErrorLimites,
    cargar_resumen,
    contrastar,
    main,
    veredicto,
)

RAIZ = Path(__file__).resolve().parents[1]
PLAZOS = RAIZ / "config" / "control" / "plazos.yaml"
VALORES = {
    "max_frame_age_ms": 500,
    "detector_timeout_ms": 500,
    "watchdog_ms": 600,
    "validez_orden_ms": 400,
    "paso_reloj_ms": 100,
}


def etapa(p50, p95, maximo):
    return {"n": 100, "p50": p50, "p95": p95, "maximo": maximo, "minimo": p50, "media": p50}


def resumen_de(inferencia, total, advertencias=(), sha_plazos=None):
    return {
        "estado": "completo",
        "equipo": "pruebas",
        "energia": "corriente",
        "conteos": {"calentamientos": 10, "mediciones": 100, "fallos": 0},
        "procedencia": {
            "detector": {"comprobada": True},
            "config_b": {"plazos.yaml": sha_plazos or sha256_archivo(PLAZOS)},
        },
        "etapas": {"inferencia_ms": etapa(*inferencia), "total_ms": etapa(*total)},
        "advertencias": list(advertencias),
    }


@pytest.fixture
def corrida(tmp_path):
    def escribir(resumen):
        # Como el arnés: los CSV junto a la corrida y su SHA-256 en resumen.json.
        if isinstance(resumen, dict) and "archivos" not in resumen:
            for nombre in ("ejecuciones.csv", "fallos.csv"):
                (tmp_path / nombre).write_text(nombre, encoding="utf-8")
            resumen["archivos"] = {
                n: sha256_archivo(tmp_path / n) for n in ("ejecuciones.csv", "fallos.csv")
            }
        (tmp_path / "resumen.json").write_text(json.dumps(resumen), encoding="utf-8")
        return tmp_path

    return escribir


def leer(carpeta):
    return json.loads((carpeta / "contraste.json").read_text(encoding="utf-8"))


def test_veredictos():
    assert veredicto(p95=100, maximo=200, plazo=200) == CUMPLE
    assert veredicto(p95=150, maximo=250, plazo=200) == CUMPLE_EN_P95
    assert veredicto(p95=201, maximo=250, plazo=200) == NO_CUMPLE


def test_con_margen_todo_cumple_y_sale_con_cero(corrida):
    carpeta = corrida(resumen_de(inferencia=(80, 100, 155), total=(87, 113, 162)))
    assert main([str(carpeta)]) == 0
    contraste = leer(carpeta)
    assert {f["veredicto"] for f in contraste["contraste"]} == {CUMPLE}
    assert contraste["advertencias"] == []
    assert (carpeta / "contraste.md").read_text(encoding="utf-8").count("**cumple**") == 5


def test_el_intervalo_es_el_periodo_mientras_el_proceso_lo_alcance():
    filas = {
        f["id"]: f for f in contrastar(resumen_de((80, 100, 155), (87, 113, 162)), VALORES, 200)
    }
    assert filas["intervalo_vs_validez"]["p95"] == 200
    lento = {
        f["id"]: f for f in contrastar(resumen_de((80, 100, 155), (300, 450, 700)), VALORES, 200)
    }
    assert lento["intervalo_vs_validez"]["p95"] == 450
    assert lento["intervalo_vs_validez"]["veredicto"] == NO_CUMPLE
    assert lento["intervalo_vs_watchdog"]["veredicto"] == CUMPLE_EN_P95


def test_maximo_sobre_el_periodo_es_cumple_en_p95(corrida):
    # Los tiempos de 1 hilo en la laptop de A3: el máximo pasa los 200 ms de un cuadro.
    carpeta = corrida(resumen_de(inferencia=(134, 167, 203), total=(142, 179, 210)))
    assert main([str(carpeta)]) == 1
    filas = {f["id"]: f for f in leer(carpeta)["contraste"]}
    assert filas["total_vs_periodo"]["veredicto"] == CUMPLE_EN_P95
    assert filas["total_vs_periodo"]["margen_p95_ms"] == pytest.approx(21)
    # 210 ms está lejos de los 500 de edad, pero el cuadro que llega detrás del lento espera.
    assert filas["total_vs_edad"]["veredicto"] == CUMPLE_EN_P95
    assert "cola" in filas["total_vs_edad"]["razon"]


def test_con_cola_que_crece_la_edad_no_cumple(corrida):
    # total_ms nunca pasa los 500 ms de edad, pero el p95 pasa el periodo: la cola no tiene fin.
    carpeta = corrida(resumen_de(inferencia=(200, 300, 350), total=(250, 300, 480)))
    assert main([str(carpeta)]) == 1
    filas = {f["id"]: f for f in leer(carpeta)["contraste"]}
    assert filas["total_vs_periodo"]["veredicto"] == NO_CUMPLE
    assert filas["total_vs_edad"]["veredicto"] == NO_CUMPLE
    assert "crece sin límite" in filas["total_vs_edad"]["razon"]
    # Con cola, los eventos salen uno tras otro: el intervalo sigue siendo total_ms.
    assert filas["intervalo_vs_watchdog"]["veredicto"] == CUMPLE


def test_en_bateria_no_cumple(corrida):
    carpeta = corrida(resumen_de(inferencia=(329, 689, 2350), total=(352, 708, 2382)))
    assert main([str(carpeta)]) == 1
    filas = {f["id"]: f for f in leer(carpeta)["contraste"]}
    assert filas["inferencia_vs_timeout"]["veredicto"] == NO_CUMPLE
    assert filas["total_vs_edad"]["veredicto"] == NO_CUMPLE


def test_otro_periodo_de_entrada_se_advierte(corrida):
    # A 250 ms todo cumpliría, pero no es el periodo declarado: no puede salir con 0.
    carpeta = corrida(resumen_de(inferencia=(134, 167, 203), total=(142, 179, 210)))
    assert main([str(carpeta), "--periodo-ms", "250"]) == 1
    contraste = leer(carpeta)
    assert {f["veredicto"] for f in contraste["contraste"]} == {CUMPLE}
    assert contraste["plazos"]["periodo_entrada_ms"] == 250
    assert "PEND-09 declara 200" in contraste["plazos"]["fuente_periodo"]
    assert any("--periodo-ms" in a for a in contraste["advertencias"])


def test_fallos_no_salen_con_cero(corrida):
    resumen = resumen_de((80, 100, 155), (87, 113, 162))
    resumen["conteos"]["fallos"] = 10
    carpeta = corrida(resumen)
    assert main([str(carpeta)]) == 1
    assert any("10 ejecuciones fallaron" in a for a in leer(carpeta)["advertencias"])


def test_incompleta_sin_mediciones_advierte(corrida):
    resumen = resumen_de((80, 100, 155), (87, 113, 162))
    resumen["estado"], resumen["etapas"] = "incompleto", {}
    resumen["conteos"].update(mediciones=0, fallos=11)
    carpeta = corrida(resumen)
    assert main([str(carpeta)]) == 1
    contraste = leer(carpeta)
    assert contraste["contraste"] == []
    assert any("incompleta" in a for a in contraste["advertencias"])
    assert any("sin mediciones de" in a for a in contraste["advertencias"])


def test_un_csv_que_cambio(corrida):
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162)))
    (carpeta / "fallos.csv").write_text("otro", encoding="utf-8")
    (carpeta / "ejecuciones.csv").unlink()
    assert main([str(carpeta)]) == 1
    advertencias = leer(carpeta)["advertencias"]
    assert any("fallos.csv cambió" in a for a in advertencias)
    assert any("falta ejecuciones.csv" in a for a in advertencias)


def test_sin_hashes_de_los_csv(corrida):
    resumen = resumen_de((80, 100, 155), (87, 113, 162))
    resumen["archivos"] = {}
    carpeta = corrida(resumen)
    assert main([str(carpeta)]) == 1
    assert any("no registra el SHA-256" in a for a in leer(carpeta)["advertencias"])


def test_corrida_con_advertencias_no_es_la_del_entregable(corrida):
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162), advertencias=["en batería"]))
    assert main([str(carpeta)]) == 1
    assert "en batería" in leer(carpeta)["advertencias"][0]


def test_plazos_distintos_a_los_medidos(corrida):
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162), sha_plazos="0" * 64))
    assert main([str(carpeta)]) == 1
    assert any("plazos.yaml cambió" in a for a in leer(carpeta)["advertencias"])


def test_sin_politica(corrida):
    resumen = resumen_de((80, 100, 155), (87, 113, 162))
    resumen["procedencia"]["config_b"] = None
    carpeta = corrida(resumen)
    assert main([str(carpeta)]) == 1
    assert any("--sin-politica" in a for a in leer(carpeta)["advertencias"])


def test_plazos_de_otra_carpeta(corrida, tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    shutil.copy(PLAZOS, config / "plazos.yaml")
    texto = (config / "plazos.yaml").read_text(encoding="utf-8")
    (config / "plazos.yaml").write_text(
        texto.replace("detector_timeout_ms: 500", "detector_timeout_ms: 90"), encoding="utf-8"
    )
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162)))
    assert main([str(carpeta), "--config-control", str(config)]) == 1
    filas = {f["id"]: f for f in leer(carpeta)["contraste"]}
    assert filas["inferencia_vs_timeout"]["veredicto"] == NO_CUMPLE


def test_sin_resumen_no_se_contrasta(tmp_path, capsys):
    assert main([str(tmp_path)]) == 2
    assert "corre antes python -m bench" in capsys.readouterr().err
    assert not (tmp_path / "contraste.json").exists()


def test_resumen_sin_etapas(corrida):
    resumen = resumen_de((80, 100, 155), (87, 113, 162))
    del resumen["etapas"]["inferencia_ms"]
    carpeta = corrida(resumen)
    with pytest.raises(ErrorLimites, match="inferencia_ms"):
        cargar_resumen(carpeta)
    assert main([str(carpeta)]) == 2


def test_resumen_que_no_es_json(tmp_path):
    (tmp_path / "resumen.json").write_text("{", encoding="utf-8")
    with pytest.raises(ErrorLimites, match="no es JSON"):
        cargar_resumen(tmp_path)


@pytest.mark.parametrize("periodo", ["0", "-5", "nan", "inf", "abc"])
def test_periodo_invalido(corrida, periodo):
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162)))
    with pytest.raises(SystemExit) as salida:
        main([str(carpeta), "--periodo-ms", periodo])
    assert salida.value.code == 2


def _nan_en_etapas(r):
    r["etapas"]["total_ms"]["p95"] = float("nan")


def _bool_en_etapas(r):
    r["etapas"]["inferencia_ms"]["maximo"] = True


def _conteos_null(r):
    r["conteos"] = None


def _fallos_negativos(r):
    r["conteos"]["fallos"] = -1


def _config_b_texto(r):
    r["procedencia"]["config_b"] = "plazos"


def _sin_estado(r):
    del r["estado"]


def _no_es_objeto(r):
    r.clear()


@pytest.mark.parametrize(
    "romper",
    [
        _nan_en_etapas,
        _bool_en_etapas,
        _conteos_null,
        _fallos_negativos,
        _config_b_texto,
        _sin_estado,
        _no_es_objeto,
    ],
)
def test_entradas_invalidas_salen_con_dos(corrida, romper, capsys):
    resumen = resumen_de((80, 100, 155), (87, 113, 162))
    romper(resumen)
    carpeta = corrida(resumen)
    assert main([str(carpeta)]) == 2
    assert "no se contrasta" in capsys.readouterr().err
    assert not (carpeta / "contraste.json").exists()


def test_salida_dos_borra_el_contraste_anterior(corrida):
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162)))
    assert main([str(carpeta)]) == 0
    (carpeta / "resumen.json").write_text("{", encoding="utf-8")
    assert main([str(carpeta)]) == 2
    assert not (carpeta / "contraste.json").exists()
    assert not (carpeta / "contraste.md").exists()


def test_sobre_una_corrida_real_del_arnes(tmp_path, monkeypatch):
    monkeypatch.setattr("bench.__main__.energia", lambda: "corriente")
    imagenes = tmp_path / "imagenes"
    imagenes.mkdir()
    for i in range(3):
        (imagenes / f"{i}.jpg").write_bytes(b"\xff\xd8" + bytes([i]) * 10 + b"\xff\xd9")
    salida = tmp_path / "run"
    falso = DetectorFalso()
    argumentos = [
        "--entradas", str(imagenes), "--salida", str(salida), "--equipo", "pruebas",
        "--model-sha256", falso.model_sha256, "--config-sha256", falso.config_sha256, "--prueba",
    ]  # fmt: skip
    assert bench(argumentos) == 1
    # El detector falso es casi instantáneo: cumple, pero la corrida es de prueba.
    assert main([str(salida)]) == 1
    contraste = leer(salida)
    assert {f["veredicto"] for f in contraste["contraste"]} == {CUMPLE}
    assert any("modo de prueba" in a for a in contraste["advertencias"])
    assert contraste["corridas"][0]["resumen_sha256"] == sha256_archivo(salida / "resumen.json")


def test_la_consola_de_windows_puede_imprimir_el_resumen(corrida):
    # cp1252 es la codificación por omisión de la consola en Windows: el resumen no debe tronar.
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162)))
    resultado = subprocess.run(
        [sys.executable, "-m", "bench.limites", str(carpeta)],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr.decode("cp1252", "replace")


def escribir_corrida(carpeta, resumen):
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre in ("ejecuciones.csv", "fallos.csv"):
        (carpeta / nombre).write_text(nombre, encoding="utf-8")
    resumen["archivos"] = {
        n: sha256_archivo(carpeta / n) for n in ("ejecuciones.csv", "fallos.csv")
    }
    (carpeta / "resumen.json").write_text(json.dumps(resumen), encoding="utf-8")
    return carpeta


def con_hashes(resumen, model="a" * 64, config="b" * 64):
    resumen["procedencia"]["detector"].update(model_sha256=model, config_sha256=config)
    return resumen


def escribir_sobrecosto(carpeta, p50, p95, maximo, **cambios):
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "sobrecosto.csv").write_text("csv", encoding="utf-8")
    datos = {
        "energia": "corriente",
        "hashes_comprobados": True,
        "model_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "resumen": {"diferencia_ms": etapa(p50, p95, maximo)},
        "archivos": {"sobrecosto.csv": sha256_archivo(carpeta / "sobrecosto.csv")},
        "advertencias": [],
        **cambios,
    }
    (carpeta / "sobrecosto.json").write_text(json.dumps(datos), encoding="utf-8")
    return carpeta


def tres_corridas(tmp_path):
    tiempos = {
        "final-1": ((80, 90, 100), (90, 100, 110)),
        "final-2": ((85, 108, 138), (95, 119, 154)),
        "final-3": ((83, 89, 98), (96, 99, 107)),
    }
    return [
        escribir_corrida(tmp_path / nombre, con_hashes(resumen_de(inferencia, total)))
        for nombre, (inferencia, total) in tiempos.items()
    ]


def test_varias_corridas_contrastan_la_peor_de_cada_una(tmp_path):
    salida = tmp_path / "contraste"
    assert main([*map(str, tres_corridas(tmp_path)), "--salida", str(salida)]) == 0
    contraste = leer(salida)
    assert [c["carpeta"] for c in contraste["corridas"]] == ["final-1", "final-2", "final-3"]
    # Cada estadístico es el mayor de las tres, aunque venga de corridas distintas.
    assert contraste["etapas"]["total_ms"] == {"p50": 96, "p95": 119, "maximo": 154}
    assert contraste["peor_de"]["total_ms"] == {
        "p50": "final-3",
        "p95": "final-2",
        "maximo": "final-2",
    }
    edad = next(f for f in contraste["contraste"] if f["id"] == "total_vs_edad")
    assert (edad["p95"], edad["maximo"]) == (119, 154)
    assert "final-2" in (salida / "contraste.md").read_text(encoding="utf-8")


def test_varias_corridas_piden_salida(tmp_path):
    with pytest.raises(SystemExit) as salida:
        main([*map(str, tres_corridas(tmp_path))])
    assert salida.value.code == 2


def test_la_misma_corrida_dos_veces(tmp_path):
    carpeta = tres_corridas(tmp_path)[0]
    assert main([str(carpeta), str(carpeta), "--salida", str(tmp_path / "c")]) == 2


def test_corridas_de_otro_detector_se_advierten(tmp_path):
    corridas = tres_corridas(tmp_path)
    resumen = json.loads((corridas[2] / "resumen.json").read_text(encoding="utf-8"))
    escribir_corrida(corridas[2], con_hashes(resumen, config="c" * 64))
    assert main([*map(str, corridas), "--salida", str(tmp_path / "c")]) == 1
    assert "las corridas no tienen el mismo config_sha256" in leer(tmp_path / "c")["advertencias"]


def test_una_corrida_con_advertencias_lleva_su_nombre(tmp_path):
    corridas = tres_corridas(tmp_path)
    resumen = json.loads((corridas[1] / "resumen.json").read_text(encoding="utf-8"))
    resumen["energia"] = "bateria"
    resumen["advertencias"] = ["el equipo está en batería"]
    del resumen["archivos"]
    escribir_corrida(corridas[1], resumen)
    assert main([*map(str, corridas), "--salida", str(tmp_path / "c")]) == 1
    assert any(a.startswith("final-2: ") for a in leer(tmp_path / "c")["advertencias"])


def test_el_sobrecosto_se_suma_al_total_y_al_timeout(tmp_path):
    sobrecosto = escribir_sobrecosto(tmp_path / "sobrecosto", 12, 15, 17)
    salida = tmp_path / "contraste"
    argumentos = [*map(str, tres_corridas(tmp_path)), "--sobrecosto", str(sobrecosto)]
    assert main([*argumentos, "--salida", str(salida)]) == 0
    contraste = leer(salida)
    filas = {f["id"]: f for f in contraste["contraste"]}
    # El timeout cubre la solicitud entera de infer: total + lo que infer paga de más.
    assert filas["inferencia_vs_timeout"]["medido"] == "total_ms + sobrecosto"
    assert (filas["inferencia_vs_timeout"]["p95"], filas["inferencia_vs_timeout"]["maximo"]) == (
        119 + 15,
        154 + 17,
    )
    assert filas["total_vs_edad"]["maximo"] == 154 + 17
    assert filas["intervalo_vs_watchdog"]["maximo"] == 200  # el periodo sigue siendo mayor
    assert contraste["sobrecosto"]["diferencia_ms"] == {"p50": 12, "p95": 15, "maximo": 17}


def test_el_sobrecosto_puede_hacer_que_no_cumpla(tmp_path):
    sobrecosto = escribir_sobrecosto(tmp_path / "sobrecosto", 40, 60, 60)
    corridas = tres_corridas(tmp_path)
    argumentos = [*map(str, corridas), "--sobrecosto", str(sobrecosto)]
    # 154 + 60 = 214 pasa el periodo de 200 ms: cumple en p95, no hasta el máximo.
    assert main([*argumentos, "--salida", str(tmp_path / "c")]) == 1
    filas = {f["id"]: f for f in leer(tmp_path / "c")["contraste"]}
    assert filas["total_vs_periodo"]["veredicto"] == CUMPLE_EN_P95


@pytest.mark.parametrize(
    ("cambios", "aviso"),
    [
        ({"energia": "bateria"}, "sobrecosto: energía bateria"),
        ({"hashes_comprobados": False}, "no comprobó los hashes"),
        ({"config_sha256": "c" * 64}, "su config_sha256 no es el de las corridas"),
        ({"archivos": {"sobrecosto.csv": "0" * 64}}, "sobrecosto.csv cambió"),
    ],
)
def test_un_sobrecosto_que_no_es_el_de_las_corridas(tmp_path, cambios, aviso):
    sobrecosto = escribir_sobrecosto(tmp_path / "sobrecosto", 12, 15, 17, **cambios)
    argumentos = [*map(str, tres_corridas(tmp_path)), "--sobrecosto", str(sobrecosto)]
    assert main([*argumentos, "--salida", str(tmp_path / "c")]) == 1
    assert any(aviso in a for a in leer(tmp_path / "c")["advertencias"])


def test_sobrecosto_ilegible_sale_con_dos(tmp_path):
    sobrecosto = escribir_sobrecosto(tmp_path / "sobrecosto", 12, 15, 17)
    (sobrecosto / "sobrecosto.json").write_text('{"resumen": {}}', encoding="utf-8")
    argumentos = [*map(str, tres_corridas(tmp_path)), "--sobrecosto", str(sobrecosto)]
    assert main([*argumentos, "--salida", str(tmp_path / "c")]) == 2
    assert not (tmp_path / "c" / "contraste.json").exists()


def test_con_sobrecosto_la_lectura_del_jpeg_ya_no_es_no_medido(tmp_path):
    sobrecosto = escribir_sobrecosto(tmp_path / "sobrecosto", 12, 15, 17)
    argumentos = [*map(str, tres_corridas(tmp_path)), "--sobrecosto", str(sobrecosto)]
    assert main([*argumentos, "--salida", str(tmp_path / "c")]) == 0
    assert "sí entran" in leer(tmp_path / "c")["no_medido"][0]
    assert main([*map(str, tres_corridas(tmp_path / "otra")), "--salida", str(tmp_path / "d")]) == 0
    assert "lectura y decodificación del JPEG:" in leer(tmp_path / "d")["no_medido"][0]


def test_con_sobrecosto_la_razon_del_timeout_habla_de_la_solicitud(tmp_path):
    sobrecosto = escribir_sobrecosto(tmp_path / "sobrecosto", 12, 15, 17)
    argumentos = [*map(str, tres_corridas(tmp_path)), "--sobrecosto", str(sobrecosto)]
    assert main([*argumentos, "--salida", str(tmp_path / "c")]) == 0
    fila = next(f for f in leer(tmp_path / "c")["contraste"] if f["id"] == "inferencia_vs_timeout")
    assert "solicitud completa" in fila["razon"]
    assert "Una inferencia" not in fila["razon"]


def test_procedencia_del_detector_nula_sale_con_dos(tmp_path, capsys):
    corridas = tres_corridas(tmp_path)
    resumen = json.loads((corridas[0] / "resumen.json").read_text(encoding="utf-8"))
    resumen["procedencia"]["detector"] = None
    (corridas[0] / "resumen.json").write_text(json.dumps(resumen), encoding="utf-8")
    assert main([*map(str, corridas), "--salida", str(tmp_path / "c")]) == 2
    assert "procedencia.detector" in capsys.readouterr().err
