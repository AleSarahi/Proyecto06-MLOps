"""Vigilancia técnica de la fuente: alerta «sin señal» y recuperación (extra, issue #33).

Usa el reloj de la corrida, no el tiempo del video: lo que importa es cuánto tiempo real lleva el
monitor sin recibir frames. Reglas (config/p6/vigilancia.yaml):

- Se abre una alerta cuando han pasado más de `sin_frames_ms` desde el último frame recibido. Se
  detecta en un latido (la fuente sigue sin entregar) o, si no hubo latidos, al llegar el siguiente
  frame (`deteccion_tardia: true`).
- Se cierra cuando llegan `frames_recuperacion` frames seguidos; un latido en medio reinicia la
  cuenta. Si la corrida termina sin recuperarse, la alerta queda abierta.

Una caída no es baja confianza: las ventanas sin frames quedan «insuficientes» en las reglas de
confianza, que no se abren ni se cierran por ella.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar


class Vigilante:
    def __init__(
        self,
        vigilancia: dict[str, Any],
        *,
        run_id: str,
        config_ref: str,
        model_ref: str,
        reloj_utc: Callable[[], str],
    ):
        self.regla = vigilancia["fuente_sin_senal"]
        self.vigilancia_ref = vigilancia["vigilancia_ref"]
        self.run_id = run_id
        self.config_ref = config_ref
        self.model_ref = model_ref
        self.reloj_utc = reloj_utc
        self.ultimo: dict[str, Any] | None = None
        self.t_ultimo: float | None = None
        self.abierta: dict[str, Any] | None = None
        self.recuperando: list[tuple[float, str]] = []
        self.perdidos_desde_ultimo = 0
        self.n_alertas = 0

    @property
    def activas(self) -> int:
        return 1 if self.abierta is not None else 0

    def _abrir(self, t_ms: float, ventana: int, tardia: bool) -> dict[str, Any]:
        r = self.regla
        desde = self.t_ultimo if self.t_ultimo is not None else t_ms
        hueco = t_ms - desde
        ult = self.ultimo
        motivo = (
            f"Sin frames de la fuente durante {hueco / 1000:.1f} s (umbral "
            f"{r['sin_frames_ms'] / 1000:g} s)"
            + (
                f"; último frame {ult['frame_id']} ({ult['video_pos_ms'] / 1000:.1f} s del video)"
                if ult
                else ""
            )
            + (". Detectada al volver la señal (sin latidos)." if tardia else ".")
        )
        alerta = {
            "schema": "p6.alerta_fuente.v1",
            "alert_id": f"{self.run_id}-{r['rule_id']}-{self.n_alertas:03d}",
            "rule_id": r["rule_id"],
            "run_id": self.run_id,
            "timestamp_utc": self.reloj_utc(),
            "severidad": r["severidad"],
            "motivo": motivo,
            "accion_sugerida": r["accion_sugerida"],
            "config_ref": self.config_ref,
            "vigilancia_ref": self.vigilancia_ref,
            "model_ref": self.model_ref,
            "regla": {"tipo": "fuente_sin_senal", **r},
            "ultimo_frame": (
                {
                    "event_id": ult["event_id"],
                    "t_llegada_ms": round(self.t_ultimo, 3),
                    "video_pos_ms": ult["video_pos_ms"],
                }
                if ult
                else None
            ),
            "sin_senal_desde_ms": round(desde, 3),
            "detectada_ms": round(t_ms, 3),
            "deteccion_tardia": tardia,
            "frames_perdidos": self.perdidos_desde_ultimo,
            "ventanas": [ventana],
            "recuperacion": None,
            "event_ids": [ult["event_id"]] if ult else [],
            "estado": "abierta",
            "cerrada_en": None,
            "cerrada_por_ventana": None,
        }
        self.n_alertas += 1
        return alerta

    def latido(self, t_ms: float, ventana: int) -> list[dict[str, Any]]:
        """La fuente no entregó el frame que tocaba a esta hora."""
        self.perdidos_desde_ultimo += 1
        self.recuperando = []
        if self.abierta is not None:
            a = self.abierta
            a["frames_perdidos"] = self.perdidos_desde_ultimo
            if ventana not in a["ventanas"]:
                a["ventanas"].append(ventana)
            return []
        desde = self.t_ultimo
        if desde is not None and t_ms - desde > self.regla["sin_frames_ms"]:
            self.abierta = self._abrir(t_ms, ventana, tardia=False)
            if not self.abierta["event_ids"]:
                self.abierta = None  # sin ningún evento previo no hay a qué vincularla
                return []
            return [dict(self.abierta)]
        return []

    def frame(self, t_ms: float, ventana: int, evento: dict[str, Any]) -> list[dict[str, Any]]:
        """Llegó un frame real y ya se registró su evento."""
        cambiadas: list[dict[str, Any]] = []
        if (
            self.abierta is None
            and self.t_ultimo is not None
            and t_ms - self.t_ultimo > self.regla["sin_frames_ms"]
        ):
            self.abierta = self._abrir(t_ms, ventana, tardia=True)
            cambiadas.append(dict(self.abierta))
        if self.abierta is not None:
            a = self.abierta
            self.recuperando.append((t_ms, evento["event_id"]))
            if ventana not in a["ventanas"]:
                a["ventanas"].append(ventana)
            if len(self.recuperando) >= self.regla["frames_recuperacion"]:
                primero = self.recuperando[0][0]
                ids = [eid for _, eid in self.recuperando]
                a.update(
                    {
                        "recuperacion": {
                            "primer_frame_ms": round(primero, 3),
                            "duracion_sin_senal_ms": round(primero - a["sin_senal_desde_ms"], 3),
                            "event_ids": ids,
                        },
                        "event_ids": [*a["event_ids"], *ids],
                        "estado": "cerrada",
                        "cerrada_en": self.reloj_utc(),
                        "cerrada_por_ventana": ventana,
                    }
                )
                cambiadas.append(dict(a))
                self.abierta = None
                self.recuperando = []
        self.ultimo = evento
        self.t_ultimo = t_ms
        self.perdidos_desde_ultimo = 0
        return cambiadas

    def senal(self, t_ms: float) -> None:
        """Llegó un frame que no se registró (descarte por saturación): la fuente sí entrega."""
        self.t_ultimo = t_ms
        self.perdidos_desde_ultimo = 0

    def estado_fuente(self) -> str:
        if self.abierta is not None:
            return "recuperando" if self.recuperando else "sin_senal"
        return "con_senal"


class ReglasTecnicas:
    """Reglas técnicas por ventana (extras S3 y S4, issue #37): `errores-inferencia-v1` (fracción de
    frames procesados con status error) y `saturacion-v1` (fracción de frames llegados que se
    descartaron por saturación). Igual que las de confianza: una ventana con menos de
    `minimo_frames` es insuficiente (no abre ni cierra); se abre cuando la tasa llega al umbral en
    una ventana, no se repite mientras sigue abierta y se cierra en la primera ventana suficiente
    por debajo del umbral."""

    TIPOS: ClassVar[dict[str, str]] = {
        "errores_inferencia": "tasa_errores",
        "saturacion": "tasa_saturacion",
    }

    def __init__(
        self,
        vigilancia: dict[str, Any],
        *,
        run_id: str,
        config_ref: str,
        model_ref: str,
        reloj_utc: Callable[[], str],
    ):
        self.reglas = {
            seccion: {**vigilancia[seccion], "tipo": tipo}
            for seccion, tipo in self.TIPOS.items()
            if seccion in vigilancia
        }
        self.vigilancia_ref = vigilancia["vigilancia_ref"]
        self.run_id = run_id
        self.config_ref = config_ref
        self.model_ref = model_ref
        self.reloj_utc = reloj_utc
        self.abiertas: dict[str, dict[str, Any]] = {}
        self.ultimo_evento: str | None = None

    @property
    def activas(self) -> int:
        return len(self.abiertas)

    def _medir(self, seccion, eventos, n_saturacion):
        if seccion == "errores_inferencia":
            errores = [e for e in eventos if e["status"] == "error"]
            return len(eventos), len(errores), errores
        return len(eventos) + n_saturacion, n_saturacion, eventos

    def _diagnostico(self, seccion, eventos, relevantes) -> dict[str, Any]:
        if seccion == "errores_inferencia":
            codigos: dict[str, int] = {}
            for e in relevantes:
                codigos[e["error"]["code"]] = codigos.get(e["error"]["code"], 0) + 1
            return {
                "codigos": codigos,
                "ejemplos": [
                    {
                        "event_id": e["event_id"],
                        "code": e["error"]["code"],
                        "message": e["error"]["message"],
                    }
                    for e in relevantes[:3]
                ],
                "frames_ok_en_ventana": sum(1 for e in eventos if e["status"] != "error"),
            }
        colas = sorted(
            e["tiempos_ms"]["cola"] for e in eventos if e["tiempos_ms"]["cola"] is not None
        )
        inf = sorted(
            e["tiempos_ms"]["inferencia"]
            for e in eventos
            if e["tiempos_ms"]["inferencia"] is not None
        )
        return {
            "cola_max_ms": colas[-1] if colas else None,
            "cola_mediana_ms": colas[len(colas) // 2] if colas else None,
            "inferencia_mediana_ms": inf[len(inf) // 2] if inf else None,
            "frames_procesados_en_ventana": len(eventos),
        }

    def evaluar(
        self,
        indice: int,
        inicio_ms: float,
        fin_ms: float,
        eventos: list[dict[str, Any]],
        n_saturacion: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Resultado por regla (para observaciones.jsonl) y alertas que cambiaron."""
        if eventos:
            self.ultimo_evento = eventos[-1]["event_id"]
        resultados: dict[str, Any] = {}
        cambiadas: list[dict[str, Any]] = []
        for seccion, r in self.reglas.items():
            n, num, relevantes = self._medir(seccion, eventos, n_saturacion)
            tasa = num / n if n else None
            if n < r["minimo_frames"]:
                res = "insuficiente"
            elif tasa >= r["umbral"]:
                res = "cumple"
            else:
                res = "no_cumple"
            abierta = self.abiertas.get(seccion)
            if res == "cumple" and abierta is None:
                ids = [e["event_id"] for e in relevantes] or (
                    [self.ultimo_evento] if self.ultimo_evento else []
                )
                if ids:
                    nueva = self._abrir(
                        r,
                        seccion,
                        indice,
                        inicio_ms,
                        fin_ms,
                        n,
                        num,
                        tasa,
                        eventos,
                        relevantes,
                        ids,
                    )
                    self.abiertas[seccion] = nueva
                    cambiadas.append(dict(nueva))
            elif res == "cumple" and abierta is not None:
                abierta["ventanas"].append(
                    {
                        "indice": indice,
                        "inicio_ms": inicio_ms,
                        "fin_ms": fin_ms,
                        "n": n,
                        "numerador": num,
                        "tasa": round(tasa, 4),
                    }
                )
                cambiadas.append(dict(abierta))
            elif res == "no_cumple" and abierta is not None:
                abierta.update(
                    {
                        "estado": "cerrada",
                        "cerrada_en": self.reloj_utc(),
                        "cerrada_por_ventana": indice,
                    }
                )
                cambiadas.append(dict(abierta))
                del self.abiertas[seccion]
            resultados[r["rule_id"]] = {
                "resultado": res,
                "n": n,
                "numerador": num,
                "tasa": None if tasa is None else round(tasa, 4),
                "alert_id": self.abiertas[seccion]["alert_id"]
                if seccion in self.abiertas
                else None,
            }
        return resultados, cambiadas

    def _abrir(self, r, seccion, indice, inicio_ms, fin_ms, n, num, tasa, eventos, relevantes, ids):
        que = (
            "frames con error de inferencia"
            if seccion == "errores_inferencia"
            else ("frames descartados por saturación (llegaron con más atraso que el máximo)")
        )
        return {
            "schema": "p6.alerta_tecnica.v1",
            "alert_id": f"{self.run_id}-{r['rule_id']}-v{indice:03d}",
            "rule_id": r["rule_id"],
            "run_id": self.run_id,
            "timestamp_utc": self.reloj_utc(),
            "severidad": r["severidad"],
            "motivo": (
                f"{num}/{n} {que} en la ventana {indice} "
                f"[{inicio_ms / 1000:g} s, {fin_ms / 1000:g} s): "
                f"tasa {tasa:.3f}, umbral {r['umbral']:g}."
            ),
            "accion_sugerida": r["accion_sugerida"],
            "config_ref": self.config_ref,
            "vigilancia_ref": self.vigilancia_ref,
            "model_ref": self.model_ref,
            "regla": {
                k: r[k] for k in ("rule_id", "tipo", "descripcion", "umbral", "minimo_frames")
            },
            "ventanas": [
                {
                    "indice": indice,
                    "inicio_ms": inicio_ms,
                    "fin_ms": fin_ms,
                    "n": n,
                    "numerador": num,
                    "tasa": round(tasa, 4),
                }
            ],
            "diagnostico": self._diagnostico(seccion, eventos, relevantes),
            "event_ids": ids,
            "estado": "abierta",
            "cerrada_en": None,
            "cerrada_por_ventana": None,
        }

    def abiertas_ids(self) -> list[str]:
        return [a["alert_id"] for a in self.abiertas.values()]
