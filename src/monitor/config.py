"""Carga y validación de la configuración del Proyecto 6 (issue #4).

`config_ref` identifica todo lo que decide el monitoreo: el contenido efectivo de
config/p6/monitoreo.yaml (sin `muestreo.velocidad`, que solo cambia el ritmo de reproducción) más
el config_sha256 del detector. Mismo contenido -> mismo config_ref; cualquier cambio lo modifica.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[2]
RUTA_MONITOREO = RAIZ / "config" / "p6" / "monitoreo.yaml"
RUTA_FUENTES = RAIZ / "config" / "p6" / "fuentes.yaml"

ZONAS = ("baja", "duda", "aceptada")
TIPOS_REGLA = {"proporcion_baja", "cambio_sostenido"}
SEVERIDADES = {"info", "advertencia", "critica"}


class ErrorConfig(ValueError):
    """La configuración no es válida; el mensaje dice qué campo y por qué."""


@dataclass(frozen=True)
class Regla:
    rule_id: str
    tipo: str
    descripcion: str
    severidad: str
    accion_sugerida: str
    ventanas_consecutivas: int
    umbral: float | None = None
    tolerancia: float | None = None


@dataclass(frozen=True)
class ConfigMonitoreo:
    datos: dict[str, Any]
    ruta: Path
    detector_ruta: Path
    detector_config_sha256: str
    config_ref: str

    @property
    def inferior(self) -> float:
        return self.datos["umbrales"]["inferior"]

    @property
    def superior(self) -> float:
        return self.datos["umbrales"]["superior"]

    @property
    def cada_n_frames(self) -> int:
        return self.datos["muestreo"]["cada_n_frames"]

    @property
    def velocidad(self) -> float:
        return self.datos["muestreo"]["velocidad"]

    @property
    def atraso_max_ms(self) -> float:
        return self.datos["muestreo"]["atraso_max_ms"]

    @property
    def ventana_ms(self) -> float:
        return self.datos["ventanas"]["duracion_s"] * 1000.0

    @property
    def minimo_candidatas(self) -> int:
        return self.datos["ventanas"]["minimo_candidatas"]

    @property
    def ruta_referencia(self) -> Path:
        return _resolver(self.datos["referencia"]["ruta"])

    @property
    def captura(self) -> dict[str, Any]:
        return self.datos["captura"]

    @property
    def reglas(self) -> tuple[Regla, ...]:
        return tuple(Regla(**r) for r in self.datos["reglas"])

    def efectiva(self) -> dict[str, Any]:
        """Lo que entra a config_ref, también guardado en run.json para reconstruirla."""
        return _efectiva(self.datos, self.detector_config_sha256)


def _resolver(ruta: str | Path) -> Path:
    p = Path(ruta)
    return p if p.is_absolute() else RAIZ / p


def _efectiva(datos: dict[str, Any], detector_sha: str) -> dict[str, Any]:
    copia = json.loads(json.dumps(datos))
    copia["muestreo"].pop("velocidad", None)
    copia["detector_config_sha256"] = detector_sha
    return copia


def _hash(obj: Any) -> str:
    texto = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _num(valor: Any, nombre: str, *, minimo: float | None = None, maximo: float | None = None):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        raise ErrorConfig(f"{nombre}: se requiere un número finito, no {valor!r}")
    if minimo is not None and valor < minimo:
        raise ErrorConfig(f"{nombre}: debe ser >= {minimo}, no {valor}")
    if maximo is not None and valor > maximo:
        raise ErrorConfig(f"{nombre}: debe ser <= {maximo}, no {valor}")
    return float(valor)


def _entero(valor: Any, nombre: str, *, minimo: int = 1) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo:
        raise ErrorConfig(f"{nombre}: se requiere un entero >= {minimo}, no {valor!r}")
    return valor


def _texto(valor: Any, nombre: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorConfig(f"{nombre}: se requiere un texto no vacío")
    return valor.strip()


def _seccion(datos: dict[str, Any], nombre: str, claves: set[str]) -> dict[str, Any]:
    sec = datos.get(nombre)
    if not isinstance(sec, dict):
        raise ErrorConfig(f"{nombre}: falta la sección")
    sobran, faltan = set(sec) - claves, claves - set(sec)
    if sobran or faltan:
        raise ErrorConfig(f"{nombre}: claves de más {sorted(sobran)} / faltan {sorted(faltan)}")
    return sec


def validar(datos: Any) -> dict[str, Any]:
    """Valida tipos y rangos y devuelve una copia normalizada (números como float/int)."""
    if not isinstance(datos, dict):
        raise ErrorConfig("la configuración debe ser un mapa YAML")
    esperadas = {
        "version",
        "detector",
        "muestreo",
        "umbrales",
        "zona_frame",
        "ventanas",
        "referencia",
        "reglas",
        "captura",
    }
    sobran, faltan = set(datos) - esperadas, esperadas - set(datos)
    if sobran or faltan:
        raise ErrorConfig(f"claves de más {sorted(sobran)} / faltan {sorted(faltan)}")
    if datos["version"] != 1:
        raise ErrorConfig("version: solo se reconoce la 1")
    detector = _texto(datos["detector"], "detector")

    m = _seccion(datos, "muestreo", {"cada_n_frames", "velocidad", "atraso_max_ms"})
    muestreo = {
        "cada_n_frames": _entero(m["cada_n_frames"], "muestreo.cada_n_frames"),
        "velocidad": _num(m["velocidad"], "muestreo.velocidad", minimo=0),
        "atraso_max_ms": _num(m["atraso_max_ms"], "muestreo.atraso_max_ms", minimo=0),
    }

    u = _seccion(datos, "umbrales", {"inferior", "superior"})
    inferior = _num(u["inferior"], "umbrales.inferior", minimo=0, maximo=1)
    superior = _num(u["superior"], "umbrales.superior", minimo=0, maximo=1)
    if not inferior < superior:
        raise ErrorConfig(
            f"umbrales: se requiere 0 <= inferior < superior <= 1 (inferior={inferior}, "
            f"superior={superior})"
        )
    if datos["zona_frame"] != "max_score":
        raise ErrorConfig("zona_frame: el único valor admitido es max_score")

    v = _seccion(datos, "ventanas", {"duracion_s", "minimo_candidatas"})
    ventanas = {
        "duracion_s": _num(v["duracion_s"], "ventanas.duracion_s", minimo=0.001),
        "minimo_candidatas": _entero(v["minimo_candidatas"], "ventanas.minimo_candidatas"),
    }
    r = _seccion(datos, "referencia", {"ruta"})
    referencia = {"ruta": _texto(r["ruta"], "referencia.ruta")}

    if not isinstance(datos["reglas"], list) or not datos["reglas"]:
        raise ErrorConfig("reglas: se requiere al menos una regla")
    reglas, ids = [], set()
    for i, regla in enumerate(datos["reglas"]):
        nombre = f"reglas[{i}]"
        if not isinstance(regla, dict):
            raise ErrorConfig(f"{nombre}: debe ser un mapa")
        tipo = regla.get("tipo")
        if tipo not in TIPOS_REGLA:
            raise ErrorConfig(f"{nombre}.tipo: debe ser uno de {sorted(TIPOS_REGLA)}")
        extra = "umbral" if tipo == "proporcion_baja" else "tolerancia"
        claves = {
            "rule_id",
            "tipo",
            "descripcion",
            "severidad",
            "accion_sugerida",
            "ventanas_consecutivas",
            extra,
        }
        sobran, faltan = set(regla) - claves, claves - set(regla)
        if sobran or faltan:
            raise ErrorConfig(f"{nombre}: claves de más {sorted(sobran)} / faltan {sorted(faltan)}")
        rid = _texto(regla["rule_id"], f"{nombre}.rule_id")
        if rid in ids:
            raise ErrorConfig(f"{nombre}.rule_id: {rid} está repetido")
        ids.add(rid)
        if regla["severidad"] not in SEVERIDADES:
            raise ErrorConfig(f"{nombre}.severidad: debe ser una de {sorted(SEVERIDADES)}")
        reglas.append(
            {
                "rule_id": rid,
                "tipo": tipo,
                "descripcion": _texto(regla["descripcion"], f"{nombre}.descripcion"),
                "severidad": regla["severidad"],
                "accion_sugerida": _texto(regla["accion_sugerida"], f"{nombre}.accion_sugerida"),
                "ventanas_consecutivas": _entero(
                    regla["ventanas_consecutivas"], f"{nombre}.ventanas_consecutivas"
                ),
                extra: _num(regla[extra], f"{nombre}.{extra}", minimo=0, maximo=1),
            }
        )

    c = _seccion(
        datos, "captura", {"zonas", "sin_detecciones", "muestra_cada", "alerta", "calidad_jpeg"}
    )
    if not isinstance(c["zonas"], list) or not set(c["zonas"]) <= set(ZONAS):
        raise ErrorConfig(f"captura.zonas: lista con valores de {list(ZONAS)}")
    for clave in ("sin_detecciones", "alerta"):
        if not isinstance(c[clave], bool):
            raise ErrorConfig(f"captura.{clave}: debe ser true o false")
    captura = {
        "zonas": sorted(set(c["zonas"]), key=ZONAS.index),
        "sin_detecciones": c["sin_detecciones"],
        "muestra_cada": _entero(c["muestra_cada"], "captura.muestra_cada"),
        "alerta": c["alerta"],
        "calidad_jpeg": _entero(c["calidad_jpeg"], "captura.calidad_jpeg"),
    }
    if captura["calidad_jpeg"] > 100:
        raise ErrorConfig("captura.calidad_jpeg: debe estar entre 1 y 100")

    return {
        "version": 1,
        "detector": detector,
        "muestreo": muestreo,
        "umbrales": {"inferior": inferior, "superior": superior},
        "zona_frame": "max_score",
        "ventanas": ventanas,
        "referencia": referencia,
        "reglas": reglas,
        "captura": captura,
    }


def leer_yaml(ruta: str | Path) -> Any:
    try:
        return yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ErrorConfig(f"no se pudo leer {ruta}: {exc}") from exc


def cargar(ruta: str | Path = RUTA_MONITOREO, *, velocidad: float | None = None) -> ConfigMonitoreo:
    """Carga monitoreo.yaml, valida el detector y comprueba piso de salida < umbral inferior."""
    from infer.config import ErrorConfigDetector, cargar_config_detector

    ruta = Path(ruta)
    datos = validar(leer_yaml(ruta))
    if velocidad is not None:
        datos["muestreo"]["velocidad"] = _num(velocidad, "--velocidad", minimo=0)
    ruta_det = _resolver(datos["detector"])
    try:
        det = cargar_config_detector(ruta_det, clases_aprobadas=set(range(80)))
    except ErrorConfigDetector as exc:
        raise ErrorConfig(f"detector: {exc}") from exc
    piso = det.effective["postprocess"]["confidence"]
    if not piso < datos["umbrales"]["inferior"]:
        raise ErrorConfig(
            f"el piso de salida del detector ({piso}) debe ser menor que el umbral inferior "
            f"({datos['umbrales']['inferior']}); si no, la zona baja no se puede observar"
        )
    return ConfigMonitoreo(
        datos=datos,
        ruta=ruta,
        detector_ruta=ruta_det,
        detector_config_sha256=det.config_sha256,
        config_ref=_hash(_efectiva(datos, det.config_sha256)),
    )


def _tramo(datos: dict[str, Any], t: Any, nombre: str) -> tuple[float, float]:
    if not isinstance(t, dict) or t.get("video") not in datos["videos"]:
        valor = t.get("video") if isinstance(t, dict) else t
        raise ErrorConfig(f"{nombre}.video: no existe {valor!r}")
    inicio = _num(t.get("inicio_s"), f"{nombre}.inicio_s", minimo=0)
    fin = _num(t.get("fin_s"), f"{nombre}.fin_s", minimo=0)
    if not inicio < fin:
        raise ErrorConfig(f"{nombre}: inicio_s debe ser menor que fin_s")
    return inicio, fin


def cargar_fuentes(ruta: str | Path = RUTA_FUENTES) -> dict[str, Any]:
    """Lee fuentes.yaml. Un segmento es un tramo de un video (video, inicio_s, fin_s) o una
    secuencia de tramos (`tramos`) que se reproducen uno tras otro como un solo stream; en ese caso
    el segmento va de 0 a la suma de las duraciones."""
    datos = leer_yaml(ruta)
    if not isinstance(datos, dict) or not {"videos", "segmentos"} <= set(datos):
        raise ErrorConfig("fuentes: se requieren las secciones videos y segmentos")
    for nombre, seg in datos["segmentos"].items():
        if "tramos" in seg:
            if not isinstance(seg["tramos"], list) or not seg["tramos"]:
                raise ErrorConfig(f"segmentos.{nombre}.tramos: se requiere una lista no vacía")
            total = 0.0
            for k, t in enumerate(seg["tramos"]):
                a, b = _tramo(datos, t, f"segmentos.{nombre}.tramos[{k}]")
                total += b - a
            seg["inicio_s"], seg["fin_s"] = 0, total
        else:
            _tramo(datos, seg, f"segmentos.{nombre}")
    return datos


RUTA_VIGILANCIA = RAIZ / "config" / "p6" / "vigilancia.yaml"


def cargar_vigilancia(ruta: str | Path = RUTA_VIGILANCIA) -> dict[str, Any]:
    """Vigilancia técnica de la fuente (extra #33). Va aparte de monitoreo.yaml para no cambiar el
    config_ref de la serie de confianza; su identidad es `vigilancia_ref`."""
    datos = leer_yaml(ruta)
    if not isinstance(datos, dict) or datos.get("version") != 1:
        raise ErrorConfig("vigilancia: se requiere version: 1")
    r = _seccion(
        datos,
        "fuente_sin_senal",
        {
            "rule_id",
            "descripcion",
            "sin_frames_ms",
            "frames_recuperacion",
            "severidad",
            "accion_sugerida",
        },
    )
    if r["severidad"] not in SEVERIDADES:
        raise ErrorConfig(f"fuente_sin_senal.severidad: debe ser una de {sorted(SEVERIDADES)}")
    regla = {
        "rule_id": _texto(r["rule_id"], "fuente_sin_senal.rule_id"),
        "descripcion": _texto(r["descripcion"], "fuente_sin_senal.descripcion"),
        "sin_frames_ms": _num(r["sin_frames_ms"], "fuente_sin_senal.sin_frames_ms", minimo=1),
        "frames_recuperacion": _entero(
            r["frames_recuperacion"], "fuente_sin_senal.frames_recuperacion"
        ),
        "severidad": r["severidad"],
        "accion_sugerida": _texto(r["accion_sugerida"], "fuente_sin_senal.accion_sugerida"),
    }
    efectiva: dict[str, Any] = {"version": 1, "fuente_sin_senal": regla}
    sobran = set(datos) - {"version", "fuente_sin_senal", "errores_inferencia", "saturacion"}
    if sobran:
        raise ErrorConfig(f"vigilancia: secciones desconocidas {sorted(sobran)}")
    # Reglas técnicas por ventana (extras S3/S4, issue #37). Son opcionales.
    for nombre in ("errores_inferencia", "saturacion"):
        if nombre not in datos:
            continue
        t = _seccion(
            datos,
            nombre,
            {"rule_id", "descripcion", "umbral", "minimo_frames", "severidad", "accion_sugerida"},
        )
        if t["severidad"] not in SEVERIDADES:
            raise ErrorConfig(f"{nombre}.severidad: debe ser una de {sorted(SEVERIDADES)}")
        efectiva[nombre] = {
            "rule_id": _texto(t["rule_id"], f"{nombre}.rule_id"),
            "descripcion": _texto(t["descripcion"], f"{nombre}.descripcion"),
            "umbral": _num(t["umbral"], f"{nombre}.umbral", minimo=0, maximo=1),
            "minimo_frames": _entero(t["minimo_frames"], f"{nombre}.minimo_frames"),
            "severidad": t["severidad"],
            "accion_sugerida": _texto(t["accion_sugerida"], f"{nombre}.accion_sugerida"),
        }
    return {**efectiva, "vigilancia_ref": _hash(efectiva), "ruta": str(ruta)}
