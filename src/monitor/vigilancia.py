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
from typing import Any


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
