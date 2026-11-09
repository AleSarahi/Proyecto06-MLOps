"""Ventanas de confianza, regla sostenida y alertas (issues #13, #16 y #17).

Cada ventana agrupa los eventos cuyo tiempo de video cae en [k*d, (k+1)*d) contado desde el inicio
del segmento. La unidad de análisis es la detección candidata:

    proporcion_baja = candidatas con s < inferior / candidatas puntuadas de la ventana

Una ventana con menos de `minimo_candidatas` es "insuficiente": no es normal ni alerta, no suma
ventanas consecutivas ni las reinicia, y no cierra una alerta abierta. Evidencia insuficiente no es
operación sana.

Reglas:
- proporcion_baja: cumple si proporcion_baja >= umbral.
- cambio_sostenido: cumple si proporcion_baja - referencia >= tolerancia. Sin referencia con el
  mismo config_ref el resultado es "sin_referencia".

Una alerta se abre cuando una regla cumple en `ventanas_consecutivas` ventanas suficientes seguidas
y no hay otra abierta de la misma regla (así no se repite por la misma condición). Se cierra con la
primera ventana suficiente que no cumple.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .config import ConfigMonitoreo, Regla

CUMPLE, NO_CUMPLE, INSUFICIENTE, SIN_REFERENCIA = (
    "cumple",
    "no_cumple",
    "insuficiente",
    "sin_referencia",
)


def resumen_ventana(eventos: list[dict[str, Any]], minimo: int) -> dict[str, Any]:
    n_cand = sum(e["n_candidatas"] for e in eventos)
    n_baja = sum(e["conteo_zonas"]["baja"] for e in eventos)
    return {
        "n_frames": len(eventos),
        "n_ok": sum(1 for e in eventos if e["status"] == "ok"),
        "n_sin_detecciones": sum(1 for e in eventos if e["status"] == "sin_detecciones"),
        "n_error": sum(1 for e in eventos if e["status"] == "error"),
        "n_candidatas": n_cand,
        "n_baja": n_baja,
        "n_duda": sum(e["conteo_zonas"]["duda"] for e in eventos),
        "n_aceptada": sum(e["conteo_zonas"]["aceptada"] for e in eventos),
        # Con cero candidatas no hay proporción (None), nunca 0.
        "proporcion_baja": (n_baja / n_cand) if n_cand else None,
        "estado": "suficiente" if n_cand >= minimo else "insuficiente",
    }


def resultado_regla(regla: Regla, resumen: dict[str, Any], referencia: float | None) -> str:
    if regla.tipo == "cambio_sostenido" and referencia is None:
        return SIN_REFERENCIA
    if resumen["estado"] == "insuficiente":
        return INSUFICIENTE
    p = resumen["proporcion_baja"]
    if regla.tipo == "proporcion_baja":
        return CUMPLE if p >= regla.umbral else NO_CUMPLE
    return CUMPLE if p - referencia >= regla.tolerancia else NO_CUMPLE


def _motivo(regla: Regla, ventanas: list[dict[str, Any]], inferior: float, ref: float | None):
    ult = ventanas[-1]
    base = (
        f"{ult['n_baja']}/{ult['n_candidatas']} candidatas con s < {inferior:g} "
        f"(proporción {ult['proporcion_baja']:.3f}) en la ventana {ult['indice']} "
        f"[{ult['inicio_ms'] / 1000:g} s, {ult['fin_ms'] / 1000:g} s)"
    )
    if regla.tipo == "proporcion_baja":
        return f"Baja confianza: {base}, umbral {regla.umbral:g}."
    props = ", ".join(f"{v['proporcion_baja']:.3f}" for v in ventanas)
    return (
        f"Cambio sostenido: {len(ventanas)} ventanas seguidas con proporción de baja confianza "
        f"({props}) al menos {regla.tolerancia:g} sobre la referencia {ref:.3f}. Última: {base}."
    )


@dataclass
class _EstadoRegla:
    consecutivas: int = 0
    cumplidas: list[dict[str, Any]] = field(default_factory=list)
    abierta: dict[str, Any] | None = None


class EvaluadorReglas:
    """Evalúa ventana por ventana y devuelve el registro de la ventana y las alertas cambiadas."""

    def __init__(
        self,
        cfg: ConfigMonitoreo,
        *,
        run_id: str,
        model_ref: str,
        referencia: float | None,
        reloj_utc: Callable[[], str],
    ):
        self.cfg = cfg
        self.run_id = run_id
        self.model_ref = model_ref
        self.referencia = referencia
        self.reloj_utc = reloj_utc
        self.reglas = cfg.reglas
        self.estado = {r.rule_id: _EstadoRegla() for r in self.reglas}

    def evaluar(
        self, indice: int, inicio_ms: float, fin_ms: float, eventos: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        ahora = self.reloj_utc()
        resumen = resumen_ventana(eventos, self.cfg.minimo_candidatas)
        datos_ventana = {"indice": indice, "inicio_ms": inicio_ms, "fin_ms": fin_ms, **resumen}
        cambiadas: list[dict[str, Any]] = []
        por_regla: dict[str, dict[str, Any]] = {}
        for regla in self.reglas:
            st = self.estado[regla.rule_id]
            res = resultado_regla(regla, resumen, self.referencia)
            if res == CUMPLE:
                st.consecutivas += 1
                st.cumplidas.append(
                    {**datos_ventana, "event_ids": [e["event_id"] for e in eventos]}
                )
                st.cumplidas = st.cumplidas[-regla.ventanas_consecutivas :]
                if st.abierta is None and st.consecutivas >= regla.ventanas_consecutivas:
                    st.abierta = self._abrir(regla, st.cumplidas, ahora)
                    cambiadas.append(st.abierta)
            elif res == NO_CUMPLE:
                st.consecutivas = 0
                st.cumplidas = []
                if st.abierta is not None:
                    st.abierta = {
                        **st.abierta,
                        "estado": "cerrada",
                        "cerrada_en": ahora,
                        "cerrada_por_ventana": indice,
                    }
                    cambiadas.append(st.abierta)
                    st.abierta = None
            # INSUFICIENTE / SIN_REFERENCIA: no cuenta, no reinicia y no cierra.
            por_regla[regla.rule_id] = {
                "resultado": res,
                "consecutivas": st.consecutivas,
                "alert_id": st.abierta["alert_id"] if st.abierta else None,
            }
        ventana = {
            "schema": "p6.ventana.v1",
            "run_id": self.run_id,
            "indice": indice,
            "inicio_ms": inicio_ms,
            "fin_ms": fin_ms,
            "config_ref": self.cfg.config_ref,
            **resumen,
            "referencia_proporcion_baja": self.referencia,
            "reglas": por_regla,
            "event_ids": [e["event_id"] for e in eventos],
            "alertas_activas": sum(1 for s in self.estado.values() if s.abierta is not None),
            "timestamp_utc": ahora,
        }
        return ventana, cambiadas

    def _abrir(self, regla: Regla, cumplidas: list[dict[str, Any]], ahora: str) -> dict[str, Any]:
        ultima = cumplidas[-1]["indice"]
        ventanas = [
            {
                k: v[k]
                for k in (
                    "indice",
                    "inicio_ms",
                    "fin_ms",
                    "n_candidatas",
                    "n_baja",
                    "proporcion_baja",
                )
            }
            for v in cumplidas
        ]
        return {
            "schema": "p6.alerta.v1",
            "alert_id": f"{self.run_id}-{regla.rule_id}-v{ultima:03d}",
            "rule_id": regla.rule_id,
            "run_id": self.run_id,
            "timestamp_utc": ahora,
            "severidad": regla.severidad,
            "motivo": _motivo(regla, cumplidas, self.cfg.inferior, self.referencia),
            "accion_sugerida": regla.accion_sugerida,
            "config_ref": self.cfg.config_ref,
            "model_ref": self.model_ref,
            "regla": {
                "rule_id": regla.rule_id,
                "tipo": regla.tipo,
                "descripcion": regla.descripcion,
                "umbral": regla.umbral,
                "tolerancia": regla.tolerancia,
                "ventanas_consecutivas": regla.ventanas_consecutivas,
                "umbral_inferior": self.cfg.inferior,
                "minimo_candidatas": self.cfg.minimo_candidatas,
                "referencia_proporcion_baja": self.referencia,
            },
            "ventanas": ventanas,
            "event_ids": [eid for v in cumplidas for eid in v["event_ids"]],
            "estado": "abierta",
            "cerrada_en": None,
            "cerrada_por_ventana": None,
        }

    def abiertas(self) -> list[dict[str, Any]]:
        return [s.abierta for s in self.estado.values() if s.abierta is not None]
