"""Contraste del benchmark con los plazos de B (P5-16, E7).

Uso:
    python -m bench.limites mediciones/<run>/ [--config-control config/control/] [--periodo-ms 200]
    python -m bench.limites mediciones/final-1/ mediciones/final-2/ mediciones/final-3/ \
        --sobrecosto mediciones/final-sobrecosto/ --salida mediciones/final-contraste/

Lee `resumen.json` de una o varias corridas de `python -m bench` y `plazos.yaml` de B, y escribe
`contraste.json` y `contraste.md`: p50/p95/máximo frente a cada presupuesto, con veredicto y
razón. Lo declarado (los plazos de B y el ritmo de entrada de PEND-09) y lo reproducido (lo que
midió el benchmark) quedan en secciones aparte. Con una corrida se escriben junto a ella; con
varias, en `--salida`.

Con varias corridas se contrasta **la peor**: por etapa, el mayor p50, el mayor p95 y el mayor
máximo de todas (cada uno puede venir de una corrida distinta; queda anotado de cuál).

`--sobrecosto` es la carpeta de `python -m bench.sobrecosto`: lo que `infer` paga y el arnés no
mide (leer el JPEG y la preparación de Ultralytics). Su p50, p95 y máximo se suman a los de
`total_ms` en todas las filas, y la del timeout compara la solicitud completa (`total_ms` +
sobrecosto) en vez de `inferencia_ms`: el `detector_timeout_ms` de P5-06 cubre la solicitud
entera. Sumar máximos da una cota superior del máximo de la suma; sumar p95 es la misma
aproximación conservadora.

Veredicto de cada presupuesto:
- `cumple`: hasta el máximo observado queda dentro del plazo.
- `cumple en p95`: el p95 queda dentro, pero el máximo lo pasa; algún cuadro se pierde.
- `no cumple`: el p95 pasa el plazo.

La edad del cuadro depende de la cola: si procesar tarda más que el periodo de entrada, los
cuadros esperan, así que la fila de la edad nunca sale mejor que la del periodo.

Para salir con 0 hace falta que **el máximo** cumpla, no solo el p95: B decide cuadro por cuadro,
y un solo cuadro que pasa `max_frame_age_ms` o `detector_timeout_ms` ya es un STOP. El p95 queda
en la tabla, con su margen, como pide `plazos.yaml`.

Salida: 0 si todo cumple y las corridas son las del entregable (completas, sin fallos ni
advertencias, con el periodo declarado, los mismos plazos con que se midieron, sus CSV intactos,
el mismo detector y, si se da, un sobrecosto medido conectado con ese detector); 1 si algo no
cumple del todo o hay advertencias; 2 si no se puede leer una corrida, el sobrecosto, los plazos
o los argumentos. Con 2 no queda ningún `contraste.*` en la carpeta de salida, ni siquiera el de
una ejecución anterior.

Las rutas las elige quien corre el comando. Por eso las lecturas y escrituras con esas rutas
llevan `NOSONAR (S8707)`, como en `python -m bench`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from control.__main__ import CARPETA_CONFIG, NOMBRE_PLAZOS, cargar_plazos

from .arnes import PERIODO_MS, ruta_publicable, sha256_archivo

CUMPLE = "cumple"
CUMPLE_EN_P95 = "cumple en p95"
NO_CUMPLE = "no cumple"
GRAVEDAD = {CUMPLE: 0, CUMPLE_EN_P95: 1, NO_CUMPLE: 2}
ESTADISTICOS = ("p50", "p95", "maximo")
ARCHIVOS_CONTRASTE = ("contraste.json", "contraste.md")
ARCHIVO_SOBRECOSTO = "sobrecosto.json"
MEDIDA_SOBRECOSTO = "diferencia_ms"
FUENTE_PERIODO = "PEND-09, provisional: ≈ 5 fps hasta que B lo declare"

# Cada presupuesto: qué tiempo medido se compara, contra qué plazo y por qué importa.
# `intervalo` es el tiempo entre dos eventos (o comandos) seguidos: el periodo de entrada, o lo
# que tarde procesar un cuadro si tarda más que eso. Con cola, los eventos salen uno tras otro,
# cada `total_ms`, así que el intervalo sigue siendo ese.
PRESUPUESTOS = (
    {
        "id": "inferencia_vs_timeout",
        "medido": "inferencia_ms",
        "plazo": "detector_timeout_ms",
        "razon": (
            "Una inferencia más larga que el plazo hace que A emita status=error "
            "(detector_timeout) y B frene (C9)."
        ),
    },
    {
        "id": "total_vs_edad",
        "medido": "total_ms",
        "plazo": "max_frame_age_ms",
        "razon": (
            "El comando sale cuando el cuadro ya tiene al menos total_ms de edad; pasado "
            "max_frame_age_ms, B lo rechaza por viejo y frena (C8)."
        ),
    },
    {
        "id": "total_vs_periodo",
        "medido": "total_ms",
        "plazo": "periodo_entrada_ms",
        "razon": (
            "Si procesar un cuadro tarda más que el periodo de entrada, los cuadros se acumulan "
            "y cada uno llega más viejo que el anterior."
        ),
    },
    {
        "id": "intervalo_vs_validez",
        "medido": "intervalo",
        "plazo": "validez_orden_ms",
        "razon": (
            "Entre dos comandos pasa el periodo de entrada o lo que tarde procesar un cuadro; "
            "si eso pasa validez_orden_ms, el adaptador frena por su cuenta entre cuadros."
        ),
    },
    {
        "id": "intervalo_vs_watchdog",
        "medido": "intervalo",
        "plazo": "watchdog_ms",
        "razon": (
            "Si entre dos eventos pasa más que watchdog_ms, B emite STOP por falta de "
            "percepción aunque el detector siga funcionando."
        ),
    },
)

RAZON_TIMEOUT_SOLICITUD = (
    "El timeout de A cubre la solicitud completa de infer (total_ms + sobrecosto): si la pasa, A "
    "debe emitir status=error (detector_timeout) y B frena (C9). Hoy infer no lo aplica (P5-06): "
    "la respuesta de B sí está probada."
)

NOTA_COLA = {
    NO_CUMPLE: (
        "Limitado por la cola: con el p95 de total_ms arriba del periodo de entrada, los cuadros "
        "esperan cada vez más y la edad crece sin límite."
    ),
    CUMPLE_EN_P95: (
        "Limitado por la cola: los cuadros que llegan detrás de uno lento esperan, así que su "
        "edad pasa de total_ms."
    ),
}

NO_MEDIDO = (
    "Captura en la ESP32-CAM, transmisión por WiFi, lectura y decodificación del JPEG: el "
    "benchmark parte de la imagen ya en memoria, así que la edad real del cuadro es mayor que "
    "total_ms.",
    "Carga y calentamiento del modelo: el benchmark los deja fuera. En infer también deben quedar "
    "fuera del reloj del run; si no, el primer cuadro ya llega viejo (lo encontró T16).",
    "Frenado mecánico, distancia de frenado y movimiento del carro: el control es virtual y los "
    "comandos solo se registran.",
)
NO_MEDIDO_CON_SOBRECOSTO = (
    "Captura en la ESP32-CAM y transmisión por WiFi, ni el costo de comunicación de P5-06 si el "
    "detector corre en otro proceso: la edad real del cuadro es mayor que la de la tabla. La "
    "lectura y decodificación del JPEG sí entran, con el sobrecosto de infer."
)


class ErrorLimites(ValueError):
    """La corrida o los plazos no se pueden contrastar."""


def _numero_finito(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def _entero_no_negativo(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


def _validar_resumen(resumen: Any, nombre: str) -> None:
    """Revisa tipos y valores de lo que se usa; cualquier cosa rara es un error (salida 2)."""
    if not isinstance(resumen, dict):
        raise ErrorLimites(f"{nombre} debe ser un objeto JSON")
    if resumen.get("estado") not in ("completo", "incompleto"):
        raise ErrorLimites(f"{nombre}: estado debe ser 'completo' o 'incompleto'")
    etapas = resumen.get("etapas")
    if not isinstance(etapas, dict):
        raise ErrorLimites(f"{nombre} no tiene la sección etapas")
    necesarias = {p["medido"] for p in PRESUPUESTOS} - {"intervalo"}
    for etapa in sorted(necesarias):
        valores = etapas.get(etapa)
        if valores is None and resumen["estado"] == "incompleto":
            continue  # una corrida incompleta puede no tener mediciones: se advierte, no se rompe
        if not isinstance(valores, dict) or not all(
            _numero_finito(valores.get(e)) for e in ESTADISTICOS
        ):
            raise ErrorLimites(f"{nombre}: falta p50/p95/maximo finitos de {etapa}")
    conteos = resumen.get("conteos", {})
    if not isinstance(conteos, dict) or not all(
        _entero_no_negativo(conteos[c]) for c in ("mediciones", "fallos") if c in conteos
    ):
        raise ErrorLimites(f"{nombre}: conteos debe tener mediciones y fallos enteros >= 0")
    procedencia = resumen.get("procedencia", {})
    if not isinstance(procedencia, dict) or not isinstance(
        procedencia.get("config_b"), (dict, type(None))
    ):
        raise ErrorLimites(f"{nombre}: procedencia.config_b debe ser un objeto o null")
    if not isinstance(procedencia.get("detector", {}), dict):
        # El arnés siempre la escribe; sin ella no se sabe con qué detector se midió.
        raise ErrorLimites(f"{nombre}: procedencia.detector debe ser un objeto")
    advertencias = resumen.get("advertencias", [])
    if not isinstance(advertencias, list) or not all(isinstance(a, str) for a in advertencias):
        raise ErrorLimites(f"{nombre}: advertencias debe ser una lista de textos")
    if not isinstance(resumen.get("archivos", {}), dict):
        raise ErrorLimites(f"{nombre}: archivos debe ser un objeto")


def cargar_resumen(carpeta: Path) -> dict[str, Any]:
    """Lee `resumen.json` y revisa que traiga lo que se contrasta, con tipos y valores válidos."""
    ruta = carpeta / "resumen.json"
    try:
        resumen = json.loads(ruta.read_text(encoding="utf-8"))  # NOSONAR (S8707)
    except FileNotFoundError as exc:
        raise ErrorLimites(f"no hay {ruta_publicable(ruta)}: corre antes python -m bench") from exc
    except json.JSONDecodeError as exc:
        raise ErrorLimites(f"{ruta_publicable(ruta)} no es JSON válido: {exc}") from exc
    _validar_resumen(resumen, ruta_publicable(ruta))
    return resumen


def veredicto(p95: float, maximo: float, plazo: float) -> str:
    if maximo <= plazo:
        return CUMPLE
    if p95 <= plazo:
        return CUMPLE_EN_P95
    return NO_CUMPLE


def peor_de(
    resumenes: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, str]]]:
    """Por etapa, el mayor de cada estadístico entre las corridas, y de qué corrida salió."""
    etapas: dict[str, dict[str, float]] = {}
    origen: dict[str, dict[str, str]] = {}
    for nombre, resumen in resumenes.items():
        for etapa, valores in resumen["etapas"].items():
            if not isinstance(valores, dict) or not all(
                _numero_finito(valores.get(e)) for e in ESTADISTICOS
            ):
                continue
            for estadistico in ESTADISTICOS:
                actual = etapas.setdefault(etapa, {}).get(estadistico)
                if actual is None or valores[estadistico] > actual:
                    etapas[etapa][estadistico] = valores[estadistico]
                    origen.setdefault(etapa, {})[estadistico] = nombre
    return etapas, origen


def cargar_sobrecosto(carpeta: Path) -> dict[str, Any]:
    """Lee `sobrecosto.json` de `python -m bench.sobrecosto` y revisa lo que se suma."""
    ruta = carpeta / ARCHIVO_SOBRECOSTO
    nombre = ruta_publicable(ruta)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))  # NOSONAR (S8707)
    except FileNotFoundError as exc:
        raise ErrorLimites(f"no hay {nombre}: corre antes python -m bench.sobrecosto") from exc
    except json.JSONDecodeError as exc:
        raise ErrorLimites(f"{nombre} no es JSON válido: {exc}") from exc
    if not isinstance(datos, dict) or not isinstance(datos.get("resumen"), dict):
        raise ErrorLimites(f"{nombre} no tiene la sección resumen")
    diferencia = datos["resumen"].get(MEDIDA_SOBRECOSTO)
    if not isinstance(diferencia, dict) or not all(
        _numero_finito(diferencia.get(e)) for e in ESTADISTICOS
    ):
        raise ErrorLimites(f"{nombre}: falta p50/p95/maximo finitos de {MEDIDA_SOBRECOSTO}")
    advertencias = datos.get("advertencias", [])
    if not isinstance(advertencias, list) or not all(isinstance(a, str) for a in advertencias):
        raise ErrorLimites(f"{nombre}: advertencias debe ser una lista de textos")
    if not isinstance(datos.get("archivos", {}), dict):
        raise ErrorLimites(f"{nombre}: archivos debe ser un objeto")
    return datos


def _del_detector(resumenes: dict[str, dict[str, Any]], clave: str) -> set[Any]:
    return {r.get("procedencia", {}).get("detector", {}).get(clave) for r in resumenes.values()}


def advertencias_de_sobrecosto(
    sobrecosto: dict[str, Any], carpeta: Path, resumenes: dict[str, dict[str, Any]]
) -> list[str]:
    """Por qué el sobrecosto no sirve para estas corridas, si es el caso."""
    advertencias = []
    if sobrecosto.get("energia") != "corriente":
        advertencias.append(f"sobrecosto: energía {sobrecosto.get('energia')}, no conectada")
    if sobrecosto.get("hashes_comprobados") is not True:
        advertencias.append("sobrecosto: no comprobó los hashes del detector")
    if sobrecosto.get("advertencias"):
        advertencias.append("sobrecosto con advertencias: " + "; ".join(sobrecosto["advertencias"]))
    for clave in ("model_sha256", "config_sha256"):
        if _del_detector(resumenes, clave) != {sobrecosto.get(clave)}:
            advertencias.append(f"sobrecosto: su {clave} no es el de las corridas")
    archivos = sobrecosto.get("archivos") or {}
    if not archivos:
        advertencias.append("sobrecosto.json no registra el SHA-256 de su CSV")
    for nombre, esperado in sorted(archivos.items()):
        ruta = carpeta / nombre
        if not ruta.is_file():  # NOSONAR (S8707)
            advertencias.append(f"sobrecosto: falta {nombre}")
        elif sha256_archivo(ruta) != esperado:
            advertencias.append(f"sobrecosto: {nombre} cambió, su SHA-256 no coincide")
    return advertencias


def advertencias_entre_corridas(resumenes: dict[str, dict[str, Any]]) -> list[str]:
    """Varias corridas solo se combinan si son del mismo detector y del mismo equipo."""
    if len(resumenes) < 2:
        return []
    advertencias = [
        f"las corridas no tienen el mismo {clave}"
        for clave in ("model_sha256", "config_sha256")
        if len(_del_detector(resumenes, clave)) > 1
    ]
    if len({r.get("equipo") for r in resumenes.values()}) > 1:
        advertencias.append("las corridas no son del mismo equipo")
    return advertencias


def contrastar(
    resumen: dict[str, Any],
    plazos: dict[str, Any],
    periodo_ms: float,
    sobrecosto: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Una fila por presupuesto con datos: estadísticos, plazo, veredicto y margen del p95.

    Con `sobrecosto` (p50/p95/máximo de lo que `infer` paga de más), se suma a `total_ms`, y el
    timeout compara la solicitud completa (`total_ms` + sobrecosto) en vez de `inferencia_ms`.
    """
    etapas = resumen["etapas"]
    limites = {**plazos, "periodo_entrada_ms": periodo_ms}
    filas = []
    for presupuesto in PRESUPUESTOS:
        medido = presupuesto["medido"]
        etapa = "total_ms" if medido == "intervalo" else medido
        razon = presupuesto["razon"]
        if sobrecosto is not None and presupuesto["id"] == "inferencia_vs_timeout":
            etapa = medido = "total_ms"
            razon = RAZON_TIMEOUT_SOLICITUD
        if etapa not in etapas:
            continue
        medidos = {e: etapas[etapa][e] for e in ESTADISTICOS}
        if sobrecosto is not None and etapa == "total_ms":
            medidos = {e: v + sobrecosto[e] for e, v in medidos.items()}
            if medido != "intervalo":
                medido = f"{medido} + sobrecosto"
        if presupuesto["medido"] == "intervalo":
            medidos = {e: max(periodo_ms, v) for e, v in medidos.items()}
        plazo = limites[presupuesto["plazo"]]
        filas.append(
            {
                **presupuesto,
                "medido": medido,
                "razon": razon,
                **medidos,
                "plazo_ms": plazo,
                "margen_p95_ms": plazo - medidos["p95"],
                "veredicto": veredicto(medidos["p95"], medidos["maximo"], plazo),
            }
        )
    _limitar_por_cola(filas)
    return filas


def _limitar_por_cola(filas: list[dict[str, Any]]) -> None:
    """La edad del cuadro no sale mejor que el periodo: si hay cola, los cuadros esperan."""
    por_id = {f["id"]: f for f in filas}
    edad, cola = por_id.get("total_vs_edad"), por_id.get("total_vs_periodo")
    if edad and cola and GRAVEDAD[cola["veredicto"]] > GRAVEDAD[edad["veredicto"]]:
        edad["veredicto"] = cola["veredicto"]
        edad["razon"] = f"{edad['razon']} {NOTA_COLA[cola['veredicto']]}"


def _advertencias_de_archivos(resumen: dict[str, Any], carpeta: Path) -> list[str]:
    """Los CSV de la corrida deben ser los mismos que registró `resumen.json`."""
    archivos = resumen.get("archivos")
    if not archivos:
        return ["resumen.json no registra el SHA-256 de los CSV: no se puede comprobar la corrida"]
    advertencias = []
    for nombre, esperado in sorted(archivos.items()):
        ruta = carpeta / nombre
        if not ruta.is_file():  # NOSONAR (S8707)
            advertencias.append(f"falta {nombre}, que registra resumen.json")
        elif sha256_archivo(ruta) != esperado:
            advertencias.append(f"{nombre} cambió desde la corrida: su SHA-256 no coincide")
    return advertencias


def advertencias_de_corrida(
    resumen: dict[str, Any], sha_plazos: str, carpeta: Path, periodo_ms: float
) -> list[str]:
    """Por qué esta corrida no sirve como la medición del entregable, si es el caso."""
    advertencias = []
    if resumen["estado"] != "completo":
        advertencias.append("la corrida quedó incompleta: demasiados fallos")
    faltan = sorted({p["medido"] for p in PRESUPUESTOS} - {"intervalo"} - set(resumen["etapas"]))
    if faltan:
        advertencias.append(f"sin mediciones de {', '.join(faltan)}: esos plazos no se contrastan")
    fallos = resumen.get("conteos", {}).get("fallos", 0)
    if fallos:
        advertencias.append(
            f"{fallos} ejecuciones fallaron (fallos.csv): no entran en p50/p95/máximo, así que "
            "los tiempos no muestran esos cuadros"
        )
    if resumen.get("advertencias"):
        advertencias.append(
            "la corrida tiene advertencias, no es la medición del entregable: "
            + "; ".join(resumen["advertencias"])
        )
    config_b = resumen.get("procedencia", {}).get("config_b")
    if not config_b:
        advertencias.append("la corrida no midió la etapa de B (--sin-politica)")
    elif config_b.get(NOMBRE_PLAZOS) != sha_plazos:
        advertencias.append(
            "plazos.yaml cambió desde la corrida: se contrasta con plazos distintos a los medidos"
        )
    if periodo_ms != PERIODO_MS:
        advertencias.append(
            f"periodo de entrada de {periodo_ms:g} ms por --periodo-ms, distinto de los "
            f"{PERIODO_MS} ms declarados en PEND-09"
        )
    return advertencias + _advertencias_de_archivos(resumen, carpeta)


def _fmt(valor: float) -> str:
    return f"{valor:.2f}"


def reporte_md(contraste: dict[str, Any]) -> str:
    plazos = contraste["plazos"]
    lineas = [
        "# Contraste con los plazos de B (P5-16)",
        "",
        "Generado por `python -m bench.limites`; no editar a mano.",
        "",
        "## Reproducido (benchmark)",
        "",
    ]
    for corrida in contraste["corridas"]:
        lineas += [
            f"- Corrida: `{corrida['carpeta']}` (`resumen.json` SHA-256 "
            f"`{corrida['resumen_sha256']}`)",
            f"  - Equipo: {corrida['equipo']} · energía: {corrida['energia']} · estado: "
            f"{corrida['estado']} · mediciones: {corrida['mediciones']} (sin calentamientos) · "
            f"fallos aparte: {corrida['fallos']}",
        ]
    if len(contraste["corridas"]) > 1:
        lineas += [
            "",
            "Se contrasta **la peor**: por etapa, el mayor p50, p95 y máximo de las "
            f"{len(contraste['corridas'])} corridas.",
            "",
            "| Etapa | p50 | p95 | Máximo |",
            "|---|---|---|---|",
        ]
        for etapa, origen in contraste["peor_de"].items():
            valores = contraste["etapas"][etapa]
            celdas = " | ".join(f"{_fmt(valores[e])} (`{origen[e]}`)" for e in ESTADISTICOS)
            lineas.append(f"| `{etapa}` | {celdas} |")
    sobrecosto = contraste.get("sobrecosto")
    if sobrecosto:
        diferencia = sobrecosto[MEDIDA_SOBRECOSTO]
        lineas += [
            "",
            f"- Sobrecosto de `infer`: `{sobrecosto['carpeta']}` (`sobrecosto.json` SHA-256 "
            f"`{sobrecosto['sha256']}`): p50 {_fmt(diferencia['p50'])}, p95 "
            f"{_fmt(diferencia['p95'])}, máximo {_fmt(diferencia['maximo'])} ms. Se suma a "
            "`total_ms`, y la fila del timeout compara la solicitud completa.",
        ]
    lineas += [
        "",
        "## Declarado (plazos de B y ritmo de entrada)",
        "",
        f"- `{plazos['archivo']}` (SHA-256 `{plazos['sha256']}`)",
    ]
    lineas += [f"- `{k}`: {v} ms" for k, v in plazos["valores"].items()]
    lineas += [
        f"- `periodo_entrada_ms`: {plazos['periodo_entrada_ms']:g} ms ({plazos['fuente_periodo']})",
        "",
        "## Contraste",
        "",
        "| Medido | p50 | p95 | Máximo | Plazo | Margen p95 | Veredicto | Razón |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for fila in contraste["contraste"]:
        lineas.append(
            f"| `{fila['medido']}` | {_fmt(fila['p50'])} | {_fmt(fila['p95'])} | "
            f"{_fmt(fila['maximo'])} | `{fila['plazo']}` = {fila['plazo_ms']:g} | "
            f"{_fmt(fila['margen_p95_ms'])} | **{fila['veredicto']}** | {fila['razon']} |"
        )
    lineas += [
        "",
        "Todo en ms. `intervalo` = el mayor entre `periodo_entrada_ms` y `total_ms`: el tiempo "
        "entre dos eventos seguidos. Para salir con 0 debe cumplir el máximo, no solo el p95: un "
        "solo cuadro fuera de plazo ya es un STOP de B.",
        "",
        "## No medido",
        "",
        *(f"- {texto}" for texto in contraste["no_medido"]),
        "",
        "## Advertencias",
        "",
        *(f"- {texto}" for texto in contraste["advertencias"] or ["Ninguna."]),
        "",
    ]
    return "\n".join(lineas)


def _periodo(texto: str) -> float:
    valor = float(texto)
    if not math.isfinite(valor) or valor <= 0:
        raise argparse.ArgumentTypeError("debe ser un número finito mayor que 0")
    return valor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bench.limites", description="Contrasta un benchmark con los plazos de B."
    )
    parser.add_argument(
        "corridas", type=Path, nargs="+", help="carpetas de salida de python -m bench"
    )
    parser.add_argument(
        "--sobrecosto", type=Path, help="carpeta de python -m bench.sobrecosto (se suma)"
    )
    parser.add_argument(
        "--salida",
        type=Path,
        help="dónde escribir el contraste (por omisión, la corrida; obligatoria con varias)",
    )
    parser.add_argument(
        "--config-control",
        type=Path,
        default=CARPETA_CONFIG,
        help="carpeta con plazos.yaml (por omisión config/control/)",
    )
    parser.add_argument(
        "--periodo-ms",
        type=_periodo,
        default=PERIODO_MS,
        help=f"periodo de entrada (por omisión {PERIODO_MS}, el declarado en PEND-09)",
    )
    return parser


def _borrar_contraste_anterior(carpeta: Path) -> None:
    """Un contraste viejo junto a la corrida podría seguir diciendo `cumple`."""
    for nombre in ARCHIVOS_CONTRASTE:
        (carpeta / nombre).unlink(missing_ok=True)  # NOSONAR (S8707)


def _corrida(resumen: dict[str, Any], carpeta: Path) -> dict[str, Any]:
    conteos = resumen.get("conteos", {})
    return {
        "carpeta": ruta_publicable(carpeta),
        "resumen_sha256": sha256_archivo(carpeta / "resumen.json"),
        "equipo": resumen.get("equipo"),
        "energia": resumen.get("energia"),
        "estado": resumen["estado"],
        "mediciones": conteos.get("mediciones"),
        "fallos": conteos.get("fallos"),
    }


def _nombres(carpetas: Sequence[Path]) -> list[str]:
    """Cómo se llama cada corrida en el contraste: su carpeta, o la ruta si se repite."""
    if len({c.resolve() for c in carpetas}) != len(carpetas):
        raise ErrorLimites("la misma corrida aparece dos veces")
    nombres = [c.resolve().name for c in carpetas]
    if len(set(nombres)) != len(nombres):
        nombres = [c.resolve().as_posix() for c in carpetas]
    return nombres


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if len(args.corridas) > 1 and args.salida is None:
        parser.error("con varias corridas hace falta --salida")
    salida = args.salida or args.corridas[0]
    if salida.exists() and not salida.is_dir():  # NOSONAR (S8707)
        parser.error(f"{salida} no es una carpeta")

    ruta_plazos = args.config_control / NOMBRE_PLAZOS
    try:
        _borrar_contraste_anterior(salida)
        nombres = _nombres(args.corridas)
        carpetas = dict(zip(nombres, args.corridas, strict=True))
        resumenes = {n: cargar_resumen(c) for n, c in carpetas.items()}
        plazos = cargar_plazos(ruta_plazos)
        sha_plazos = sha256_archivo(ruta_plazos)
        etapas, origen = peor_de(resumenes)
        completas = all(r["estado"] == "completo" for r in resumenes.values())
        combinado = {"estado": "completo" if completas else "incompleto", "etapas": etapas}
        sobrecosto = cargar_sobrecosto(args.sobrecosto) if args.sobrecosto else None
        diferencia = sobrecosto["resumen"][MEDIDA_SOBRECOSTO] if sobrecosto else None
        filas = contrastar(combinado, plazos, args.periodo_ms, diferencia)
        advertencias = []
        for nombre, carpeta in carpetas.items():
            propias = advertencias_de_corrida(
                resumenes[nombre], sha_plazos, carpeta, args.periodo_ms
            )
            prefijo = f"{nombre}: " if len(carpetas) > 1 else ""
            advertencias += [prefijo + a for a in propias]
        advertencias += advertencias_entre_corridas(resumenes)
        if sobrecosto is not None:
            advertencias += advertencias_de_sobrecosto(sobrecosto, args.sobrecosto, resumenes)
        corridas = [_corrida(resumenes[n], c) for n, c in carpetas.items()]
        sha_sobrecosto = (
            sha256_archivo(args.sobrecosto / ARCHIVO_SOBRECOSTO) if sobrecosto else None
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"no se contrasta: {exc}", file=sys.stderr)
        return 2

    contraste = {
        "version": 2,
        "corridas": corridas,
        "etapas": etapas,
        "peor_de": origen,
        "sobrecosto": (
            {
                "carpeta": ruta_publicable(args.sobrecosto),
                "sha256": sha_sobrecosto,
                MEDIDA_SOBRECOSTO: {e: diferencia[e] for e in ESTADISTICOS},
            }
            if diferencia is not None
            else None
        ),
        "plazos": {
            "archivo": ruta_publicable(ruta_plazos),
            "sha256": sha_plazos,
            "valores": {
                p["plazo"]: plazos[p["plazo"]] for p in PRESUPUESTOS if p["plazo"] in plazos
            },
            "periodo_entrada_ms": args.periodo_ms,
            "fuente_periodo": (
                FUENTE_PERIODO
                if args.periodo_ms == PERIODO_MS
                else f"--periodo-ms; PEND-09 declara {PERIODO_MS} ms"
            ),
        },
        "contraste": filas,
        "no_medido": [NO_MEDIDO_CON_SOBRECOSTO, *NO_MEDIDO[1:]] if sobrecosto else list(NO_MEDIDO),
        "advertencias": advertencias,
    }

    texto = json.dumps(contraste, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    salida.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
    (salida / "contraste.json").write_text(  # NOSONAR (S8707)
        texto, encoding="utf-8", newline="\n"
    )
    (salida / "contraste.md").write_text(  # NOSONAR (S8707)
        reporte_md(contraste), encoding="utf-8", newline="\n"
    )

    for fila in filas:
        print(
            f"{fila['medido']} vs {fila['plazo']}: p95={_fmt(fila['p95'])} "
            f"máx={_fmt(fila['maximo'])} / {fila['plazo_ms']:g} ms: {fila['veredicto']}"
        )
    for advertencia in advertencias:
        print(f"advertencia: {advertencia}", file=sys.stderr)
    print(f"contraste en {salida.as_posix()}/contraste.md")
    todo_cumple = len(filas) == len(PRESUPUESTOS) and all(f["veredicto"] == CUMPLE for f in filas)
    return 0 if todo_cumple and not advertencias else 1


if __name__ == "__main__":
    raise SystemExit(main())
