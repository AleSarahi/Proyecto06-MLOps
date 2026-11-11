"""Una corrida del centro de monitoreo: fuente -> inferencia -> zonas -> eventos/capturas ->
ventanas/alertas -> métricas. Todo queda en la carpeta de salida y en la base SQLite.

Archivos de la carpeta de la corrida:
    run.json              identidad: run_id, commit, entorno, config, modelo, fuente, conteos
    eventos.jsonl         un evento por frame procesado (contrato evento.v1)
    observaciones.jsonl   tiempos por etapa y RAM por frame; descartes por saturación
    ventanas.jsonl        evaluación de cada ventana y de cada regla (contrato ventana.v1)
    alertas.jsonl         alertas con su estado final (contrato alerta.v1)
    capturas.jsonl        capturas con SHA-256 y motivos (contrato captura.v1)
    capturas/*.jpg        imágenes vinculadas, sin expiración
    metricas.json         métricas base G1-G7 por ventana y por corrida
    metricas_extra.json   métricas adicionales X1-X5 (extra #31)

Extras: con `vigilancia` se vigila la fuente (alerta «sin señal», #33) y en la tabla `vivo` de la
base queda el último frame procesado para la vista en vivo del portal (#29).
"""

from __future__ import annotations

import json
import math
import os
import platform
import subprocess
from collections import deque
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import psutil

from . import capturas as cap_mod
from . import zonas as z
from .almacen import Almacen, escribir_jsonl, leer_jsonl
from .config import RAIZ, ConfigMonitoreo, ErrorConfig
from .metricas import calcular as calcular_metricas
from .metricas_extra import calcular as calcular_extra
from .reglas import EvaluadorReglas
from .vigilancia import Vigilante

CAMPOS_VIVO = (
    "event_id",
    "timestamp_utc",
    "frame_id",
    "video_pos_ms",
    "status",
    "zona_frame",
    "score_max",
    "n_candidatas",
    "conteo_zonas",
    "image_width",
    "image_height",
)


def ahora_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _git() -> dict[str, Any]:
    def g(*args: str) -> str | None:
        try:
            r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True)
            return r.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    estado = g("status", "--porcelain", "--untracked-files=no")
    return {
        "commit": g("rev-parse", "HEAD"),
        "rama": g("rev-parse", "--abbrev-ref", "HEAD"),
        "cambios_sin_commit": bool(estado) if estado is not None else None,
    }


def entorno() -> dict[str, Any]:
    paquetes = {}
    for p in (
        "ultralytics",
        "torch",
        "torchvision",
        "opencv-python",
        "numpy",
        "flask",
        "psutil",
        "yt-dlp",
    ):
        try:
            paquetes[p] = version(p)
        except PackageNotFoundError:
            paquetes[p] = None
    return {
        "so": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor() or platform.machine(),
        "nucleos_logicos": os.cpu_count(),
        "ram_total_bytes": psutil.virtual_memory().total,
        "dispositivo": "cpu",
        "paquetes": paquetes,
    }


def cargar_referencia(cfg: ConfigMonitoreo) -> dict[str, Any]:
    ruta = cfg.ruta_referencia
    if not ruta.is_file():
        raise ErrorConfig(
            f"no existe la referencia {ruta}; corre primero el segmento referencia y "
            "`python -m monitor referencia`"
        )
    ref = json.loads(ruta.read_text(encoding="utf-8"))
    if ref["config_ref"] != cfg.config_ref:
        raise ErrorConfig(
            f"la referencia tiene config_ref {ref['config_ref'][:12]}… y la configuración actual "
            f"{cfg.config_ref[:12]}…: son series distintas. Vuelve a correr la referencia."
        )
    return ref


class Corrida:
    def __init__(
        self,
        cfg: ConfigMonitoreo,
        fuente: Any,
        inferidor: Any,
        *,
        segmento: str,
        inicio_segmento_ms: float,
        salida: Path,
        db: Path,
        referencia: dict[str, Any] | None,
        reloj_ms,
        comando: list[str] | None = None,
        run_id: str | None = None,
        vigilancia: dict[str, Any] | None = None,
        carpeta_referencia: Path | None = None,
    ):
        self.cfg = cfg
        self.fuente = fuente
        self.inferidor = inferidor
        self.segmento = segmento
        self.inicio_segmento_ms = inicio_segmento_ms
        self.salida = Path(salida)
        self.db = Path(db)
        self.referencia = referencia
        self.reloj_ms = reloj_ms
        self.comando = comando or []
        self.run_id = run_id or f"{segmento}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
        self.source_id = f"youtube-{segmento}"
        self.proc = psutil.Process()
        self.vigilancia = vigilancia
        self.carpeta_referencia = carpeta_referencia

    # --- utilidades ----------------------------------------------------------------------------

    def _ventana_de(self, pos_ms: float) -> int:
        return max(0, math.floor((pos_ms - self.inicio_segmento_ms) / self.cfg.ventana_ms))

    def _limites(self, i: int) -> tuple[float, float]:
        a = self.inicio_segmento_ms + i * self.cfg.ventana_ms
        return a, a + self.cfg.ventana_ms

    def _evento(self, frame, salida_inf, t_proceso: float) -> dict[str, Any]:
        cfg = self.cfg
        dets = [
            {**d, "zona": z.zona(d["score"], cfg.inferior, cfg.superior)}
            for d in salida_inf.detecciones
        ]
        scores = [d["score"] for d in dets]
        inf_ms = (
            salida_inf.fin_ms - salida_inf.inicio_ms if salida_inf.inicio_ms is not None else None
        )
        alto, ancho = frame.imagen.shape[:2] if frame.imagen is not None else (None, None)
        return {
            "schema": "p6.evento.v1",
            "event_id": f"{self.run_id}-{frame.frame_id}",
            "run_id": self.run_id,
            "frame_id": frame.frame_id,
            "timestamp_utc": ahora_utc(),
            "t_mono_ms": round(t_proceso, 3),
            "source_id": self.source_id,
            "segmento": self.segmento,
            "video_pos_ms": round(frame.video_pos_ms, 3),
            "task": "detection",
            "model_ref": self.inferidor.model_ref,
            "config_ref": cfg.config_ref,
            "status": salida_inf.status,
            "detecciones": dets,
            "n_candidatas": len(dets),
            "score_max": max(scores) if scores else None,
            "zona_frame": z.zona_frame(scores, cfg.inferior, cfg.superior),
            "conteo_zonas": z.conteo(d["zona"] for d in dets),
            "image_ref": None,
            "image_width": int(ancho) if ancho else None,
            "image_height": int(alto) if alto else None,
            "tiempos_ms": {
                "llegada": round(frame.t_llegada_ms, 3),
                "inicio_inferencia": _r3(salida_inf.inicio_ms),
                "fin_inferencia": _r3(salida_inf.fin_ms),
                "inferencia": _r3(inf_ms),
                "cola": _r3(
                    salida_inf.inicio_ms - frame.t_llegada_ms
                    if salida_inf.inicio_ms is not None
                    else None
                ),
            },
            "error": salida_inf.error,
        }

    # --- recorrido -----------------------------------------------------------------------------

    def correr(self) -> dict[str, Any]:
        from .inferencia import Salida

        if self.salida.exists() and any(self.salida.iterdir()):
            raise ErrorConfig(f"{self.salida} ya tiene archivos; usa una carpeta nueva")
        self.salida.mkdir(parents=True, exist_ok=True)
        cfg = self.cfg
        ref_valor = self.referencia["proporcion_baja"] if self.referencia else None
        evaluador = EvaluadorReglas(
            cfg,
            run_id=self.run_id,
            model_ref=self.inferidor.model_ref,
            referencia=ref_valor,
            reloj_utc=ahora_utc,
        )
        vigilante = (
            Vigilante(
                self.vigilancia,
                run_id=self.run_id,
                config_ref=cfg.config_ref,
                model_ref=self.inferidor.model_ref,
                reloj_utc=ahora_utc,
            )
            if self.vigilancia
            else None
        )
        run = {
            "schema": "p6.run.v1",
            "run_id": self.run_id,
            "segmento": self.segmento,
            "source_id": self.source_id,
            "inicio_utc": ahora_utc(),
            "comando": self.comando,
            "git": _git(),
            "entorno": entorno(),
            "config_ref": cfg.config_ref,
            "config_ruta": str(cfg.ruta.relative_to(RAIZ))
            if cfg.ruta.is_relative_to(RAIZ)
            else str(cfg.ruta),
            "config_efectiva": cfg.efectiva(),
            "velocidad": cfg.velocidad,
            "modelo": self.inferidor.ficha(),
            "model_ref_esperado": self.inferidor.model_ref,
            "fuente": self.fuente.descripcion(),
            "referencia": (
                {
                    "ruta": str(cfg.ruta_referencia.relative_to(RAIZ)),
                    "run_id": self.referencia["run_id"],
                    "proporcion_baja": ref_valor,
                }
                if self.referencia
                else None
            ),
            "vigilancia": (
                {
                    "vigilancia_ref": self.vigilancia["vigilancia_ref"],
                    "ruta": _relativa(Path(self.vigilancia["ruta"])),
                    "fuente_sin_senal": self.vigilancia["fuente_sin_senal"],
                }
                if self.vigilancia
                else None
            ),
        }
        (self.salida / "run.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        almacen = Almacen(self.db)
        almacen.borrar_corrida(self.run_id)
        almacen.guardar_corrida(run, self.salida)

        f_obs = (self.salida / "observaciones.jsonl").open("w", encoding="utf-8", newline="\n")
        buffers: deque[tuple[int, list[tuple[dict[str, Any], bytes | None]]]] = deque(
            maxlen=max(r.ventanas_consecutivas for r in cfg.reglas)
        )
        capturas: dict[str, dict[str, Any]] = {}
        ventana_actual: int | None = None
        procesados = 0
        saturacion = 0

        def obs(registro: dict[str, Any]) -> None:
            f_obs.write(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n")

        def capturar(ev: dict[str, Any], datos: bytes | None, razones: list[str]) -> None:
            if not razones or datos is None:
                return
            previa = capturas.get(ev["event_id"])
            if previa:
                nuevas = [r for r in razones if r not in previa["motivos"]]
                if not nuevas:
                    return
                previa = {**previa, "motivos": [*previa["motivos"], *nuevas]}
            else:
                previa = cap_mod.guardar(self.salida, ev, datos, razones, ahora_utc())
                ev["image_ref"] = previa["ruta"]
                almacen.fijar_imagen(ev["event_id"], previa["ruta"])
            capturas[ev["event_id"]] = previa
            almacen.guardar_captura(previa)

        ultimo_vivo: dict[str, Any] = {"resumen": None}

        def vivo(estado: str, ev: dict[str, Any] | None, datos: bytes | None, v: int | None):
            abiertas = [a["alert_id"] for a in evaluador.abiertas()]
            if vigilante and vigilante.abierta:
                abiertas.append(vigilante.abierta["alert_id"])
            if ev:
                resumen = {k: ev[k] for k in CAMPOS_VIVO}
                resumen["detecciones"] = [
                    {k: d[k] for k in ("class_name", "score", "zona", "bbox")}
                    for d in ev["detecciones"]
                ]
                ultimo_vivo["resumen"] = resumen
            # Sin frame nuevo (latido o cierre) se conserva el último frame mostrado.
            resumen = ultimo_vivo["resumen"]
            almacen.guardar_vivo(
                self.run_id,
                actualizado_utc=ahora_utc(),
                estado=estado,
                estado_fuente=vigilante.estado_fuente() if vigilante else "con_senal",
                evento=ev,
                jpeg=datos,
                datos={
                    "ultimo": resumen,
                    "ventana": v,
                    "procesados": procesados,
                    "alertas_abiertas": abiertas,
                    "segmento": self.segmento,
                },
            )

        def cerrar_ventana(i: int) -> None:
            eventos = buffers[-1][1] if buffers and buffers[-1][0] == i else []
            a, b = self._limites(i)
            ventana, cambiadas = evaluador.evaluar(
                i,
                a,
                b,
                [e for e, _ in eventos],
                otras_activas=vigilante.activas if vigilante else 0,
            )
            for alerta in cambiadas:
                almacen.guardar_alerta(alerta)
                if alerta["estado"] == "abierta" and cfg.captura["alerta"]:
                    ids = set(alerta["event_ids"])
                    for _, buf in buffers:
                        for ev, datos in buf:
                            if ev["event_id"] in ids:
                                capturar(ev, datos, ["alerta"])
            almacen.guardar_ventana(ventana)

        try:
            for frame in self.fuente:
                inicio = self.reloj_ms()
                cola = inicio - frame.t_llegada_ms
                v = self._ventana_de(frame.video_pos_ms)
                if ventana_actual is None:
                    ventana_actual = v
                while ventana_actual < v:
                    cerrar_ventana(ventana_actual)
                    ventana_actual += 1
                if not buffers or buffers[-1][0] != v:
                    buffers.append((v, []))
                if not frame.senal:
                    # Latido: a esta hora debía llegar un frame y la fuente no lo entregó.
                    obs(
                        {
                            "tipo": "sin_senal",
                            "run_id": self.run_id,
                            "ventana": v,
                            "video_pos_ms": frame.video_pos_ms,
                            "t_esperado_ms": round(frame.t_llegada_ms, 3),
                        }
                    )
                    if vigilante:
                        for alerta in vigilante.latido(frame.t_llegada_ms, v):
                            almacen.guardar_alerta(alerta)
                    vivo("en_curso", None, None, v)
                    continue
                if cola > cfg.atraso_max_ms:
                    saturacion += 1
                    obs(
                        {
                            "tipo": "descarte",
                            "motivo": "saturacion",
                            "run_id": self.run_id,
                            "frame_id": frame.frame_id,
                            "ventana": v,
                            "cola_ms": round(cola, 3),
                            "video_pos_ms": frame.video_pos_ms,
                        }
                    )
                    if vigilante:
                        vigilante.senal(frame.t_llegada_ms)
                    continue
                if frame.error is not None:
                    codigo = "unreadable_image"
                    salida_inf = Salida(
                        "error", [], None, None, {"code": codigo, "message": frame.error}
                    )
                else:
                    salida_inf = self.inferidor.inferir(frame.imagen)
                ev = self._evento(frame, salida_inf, inicio)
                procesados += 1
                almacen.guardar_evento(ev)
                datos = cap_mod.codificar(frame.imagen, frame.jpeg, cfg.captura["calidad_jpeg"])
                capturar(ev, datos, cap_mod.motivos(ev, procesados, cfg.captura))
                buffers[-1][1].append((ev, datos))
                if vigilante:
                    for alerta in vigilante.frame(frame.t_llegada_ms, v, ev):
                        almacen.guardar_alerta(alerta)
                vivo("en_curso", ev, datos, v)
                fin = self.reloj_ms()
                obs(
                    {
                        "tipo": "frame",
                        "run_id": self.run_id,
                        "frame_id": frame.frame_id,
                        "event_id": ev["event_id"],
                        "ventana": v,
                        "video_pos_ms": frame.video_pos_ms,
                        "status": ev["status"],
                        "model_ref": ev["model_ref"],
                        "config_ref": ev["config_ref"],
                        "t_llegada_ms": round(frame.t_llegada_ms, 3),
                        "t_inicio_inferencia_ms": _r3(salida_inf.inicio_ms),
                        "t_fin_inferencia_ms": _r3(salida_inf.fin_ms),
                        "t_fin_registro_ms": round(fin, 3),
                        "inferencia_ms": ev["tiempos_ms"]["inferencia"],
                        "cola_ms": round(cola, 3),
                        "rss_bytes": self.proc.memory_info().rss,
                    }
                )
            if ventana_actual is not None:
                cerrar_ventana(ventana_actual)
        except BaseException:
            vivo("fallida", None, None, ventana_actual)
            raise
        finally:
            f_obs.close()
        vivo("terminada", None, None, ventana_actual)

        # Exportación recalculable desde la base (lo persistido es lo exportado).
        evs, _ = almacen.eventos(run_id=self.run_id, limite=10**9)
        escribir_jsonl(self.salida / "eventos.jsonl", evs)
        escribir_jsonl(self.salida / "ventanas.jsonl", almacen.ventanas(self.run_id))
        escribir_jsonl(
            self.salida / "alertas.jsonl",
            sorted(almacen.alertas(run_id=self.run_id), key=lambda a: a["timestamp_utc"]),
        )
        escribir_jsonl(
            self.salida / "capturas.jsonl", sorted(capturas.values(), key=lambda c: c["event_id"])
        )
        run.update(
            {
                "fin_utc": ahora_utc(),
                "conteos": {
                    "fuente": self.fuente.contadores.como_dict(),
                    "procesados": procesados,
                    "descartes_saturacion": saturacion,
                    "eventos": len(evs),
                    "eventos_por_estado": _conteo(e["status"] for e in evs),
                    "eventos_por_zona": _conteo(e["zona_frame"] or e["status"] for e in evs),
                    "duplicados": almacen.duplicados,
                    "ventanas": len(almacen.ventanas(self.run_id)),
                    "alertas": len(almacen.alertas(run_id=self.run_id)),
                    "capturas": len(capturas),
                },
            }
        )
        (self.salida / "run.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        almacen.guardar_corrida(run, self.salida)
        almacen.cerrar()
        metricas = calcular_metricas(self.salida)
        (self.salida / "metricas.json").write_text(
            json.dumps(metricas, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        extra = calcular_extra(self.salida, self.carpeta_referencia)
        (self.salida / "metricas_extra.json").write_text(
            json.dumps(extra, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        return run


def _relativa(p: Path) -> str:
    p = p.resolve()
    return p.relative_to(RAIZ).as_posix() if p.is_relative_to(RAIZ) else str(p)


def _r3(v: float | None) -> float | None:
    return None if v is None else round(v, 3)


def _conteo(valores) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in valores:
        out[v] = out.get(v, 0) + 1
    return out


def resumen_texto(carpeta: Path) -> str:
    run = json.loads((Path(carpeta) / "run.json").read_text(encoding="utf-8"))
    alertas = list(leer_jsonl(Path(carpeta) / "alertas.jsonl"))
    c = run["conteos"]
    lineas = [
        f"run_id {run['run_id']}  config_ref {run['config_ref'][:12]}…  "
        f"model_ref {run['model_ref_esperado'][:12]}…",
        f"procesados {c['procesados']}  por estado {c['eventos_por_estado']}  "
        f"por zona {c['eventos_por_zona']}",
        f"ventanas {c['ventanas']}  capturas {c['capturas']}  alertas {c['alertas']}",
    ]
    lineas += [
        f"  alerta {a['alert_id']} [{a['severidad']}] {a['estado']}: {a['motivo']}" for a in alertas
    ]
    return "\n".join(lineas)
