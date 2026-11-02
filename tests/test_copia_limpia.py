"""T19 · Lo que está en Git sirve en una copia limpia, en otra máquina.

Revisa los archivos versionados: ninguno trae rutas de la máquina de quien lo generó ni llaves, los
enlaces relativos de los `.md` llevan a archivos que existen y cada `run.json` de `resultados/`
apunta a sus entradas con rutas relativas a la raíz del repo. Cómo se probó la copia limpia:
`docs/copia-limpia.md`.
"""

import importlib.util
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

from control.__main__ import main as correr_control

RAIZ = Path(__file__).resolve().parents[1]

# casos/ no es un paquete: se carga el archivo.
_spec = importlib.util.spec_from_file_location("runner_copia_limpia", RAIZ / "casos" / "runner.py")
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)

# Carpetas de usuario de Windows, macOS y Linux, y discos montados en WSL.
RUTA_DE_MAQUINA = re.compile(
    r"[A-Za-z]:[\\/]{1,2}(Users|Documents and Settings)[\\/]|/(home|Users)/[A-Za-z]|/mnt/[a-z]/"
)
NOMBRES_SECRETOS = re.compile(
    r"(^|/)(\.env(\..+)?|id_rsa|id_ed25519|credentials?(\..+)?)$|\.(pem|key|p12)$"
)
ENLACE = re.compile(r"\]\(([^)\s]+)\)")


def versionados() -> list[str]:
    try:
        salida = subprocess.run(
            ["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, check=True, text=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("no es un clon de Git")
    return [nombre for nombre in salida.split("\0") if nombre]


def texto(nombre: str) -> str | None:
    """El contenido si es texto UTF-8; None si es binario (JPEG, PNG...)."""
    try:
        return (RAIZ / nombre).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return None


def test_ningun_archivo_versionado_trae_rutas_de_una_maquina():
    encontrados = []
    for nombre in versionados():
        if nombre == "uv.lock" or nombre == "tests/test_copia_limpia.py":
            continue
        contenido = texto(nombre)
        for n, linea in enumerate((contenido or "").splitlines(), 1):
            if RUTA_DE_MAQUINA.search(linea):
                encontrados.append(f"{nombre}:{n}")
    assert encontrados == []


def test_no_se_versionan_llaves_ni_env():
    assert [n for n in versionados() if NOMBRES_SECRETOS.search(n) and n != ".env.example"] == []


def test_los_enlaces_relativos_de_los_md_existen():
    rotos = []
    for nombre in versionados():
        if not nombre.endswith(".md"):
            continue
        sin_bloques = re.sub(r"```.*?```", "", texto(nombre) or "", flags=re.S)
        for enlace in ENLACE.findall(sin_bloques):
            destino = urllib.parse.unquote(enlace.split("#", 1)[0])
            if not destino or re.match(r"[a-z]+:", enlace):
                continue  # ancla en la misma página o URL
            if not (RAIZ / nombre).parent.joinpath(destino).exists():
                rotos.append(f"{nombre}: {enlace}")
    assert rotos == []


def rutas(dato):
    """Cada valor de una clave "ruta" dentro de un run.json."""
    if isinstance(dato, dict):
        for clave, valor in dato.items():
            if clave == "ruta" and isinstance(valor, str):
                yield valor
            else:
                yield from rutas(valor)
    elif isinstance(dato, list):
        for valor in dato:
            yield from rutas(valor)


def test_los_run_json_de_resultados_apuntan_a_archivos_del_repo():
    revisados, malos = 0, []
    for nombre in versionados():
        if not (nombre.startswith("resultados/") and nombre.endswith("run.json")):
            continue
        revisados += 1
        for ruta in rutas(json.loads(texto(nombre))):
            if Path(ruta).is_absolute() or not (RAIZ / ruta).is_file():
                malos.append(f"{nombre}: {ruta}")
    assert revisados > 0
    assert malos == []


def test_control_y_runner_escriben_lf_tambien_en_windows(tmp_path):
    # .gitattributes pide LF. Con CRLF, correr los casos en Windows marca resultados/casos/ como
    # modificado aunque el contenido sea el mismo.
    flujo = RAIZ / "config" / "contrato" / "ejemplos" / "flujo.jsonl"
    config = RAIZ / "config" / "control"
    salida_control = tmp_path / "control"
    argv = ["--entrada", str(flujo), "--config", str(config), "--salida", str(salida_control)]
    assert correr_control(argv) == 0
    assert runner.main(["C8", "C10", "--salida", str(tmp_path / "casos")]) == 0
    escritos = [p for p in tmp_path.rglob("*") if p.is_file()]
    esperados = {"comandos.jsonl", "errores.jsonl", "run.json", "veredicto.json", "resumen.txt"}
    assert {p.name for p in escritos} >= esperados
    con_crlf = [p.relative_to(tmp_path).as_posix() for p in escritos if b"\r\n" in p.read_bytes()]
    assert con_crlf == []
