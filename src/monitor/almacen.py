"""Persistencia de corridas, eventos, capturas, ventanas y alertas en SQLite (issue #14).

La base guarda cada registro completo (columna `json`) más las columnas por las que consulta el
portal. Un evento con un event_id ya guardado no se inserta otra vez: se cuenta como duplicado.
Cada registro se valida contra su contrato antes de guardarse. Los archivos JSONL de la carpeta de
la corrida son la exportación recalculable; `importar` reconstruye la base desde ellos.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from . import contratos

ESQUEMA = """
CREATE TABLE IF NOT EXISTS corridas (
    run_id TEXT PRIMARY KEY, dir TEXT NOT NULL, segmento TEXT, config_ref TEXT,
    inicio_utc TEXT, json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eventos (
    event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, frame_id TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL, video_pos_ms REAL NOT NULL, source_id TEXT NOT NULL,
    status TEXT NOT NULL, zona_frame TEXT, score_max REAL, n_candidatas INTEGER NOT NULL,
    image_ref TEXT, config_ref TEXT NOT NULL, model_ref TEXT NOT NULL, json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS eventos_run ON eventos(run_id, video_pos_ms);
CREATE TABLE IF NOT EXISTS capturas (
    image_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, run_id TEXT NOT NULL, ruta TEXT NOT NULL,
    sha256 TEXT NOT NULL, json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ventanas (
    run_id TEXT NOT NULL, indice INTEGER NOT NULL, json TEXT NOT NULL,
    PRIMARY KEY (run_id, indice)
);
CREATE TABLE IF NOT EXISTS alertas (
    alert_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, rule_id TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL, severidad TEXT NOT NULL, estado TEXT NOT NULL,
    motivo TEXT NOT NULL, json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerta_eventos (
    alert_id TEXT NOT NULL, event_id TEXT NOT NULL, PRIMARY KEY (alert_id, event_id)
);
CREATE TABLE IF NOT EXISTS vivo (
    run_id TEXT PRIMARY KEY, actualizado_utc TEXT NOT NULL, estado TEXT NOT NULL,
    estado_fuente TEXT NOT NULL, event_id TEXT, jpeg BLOB, json TEXT NOT NULL
);
"""


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


class Almacen:
    def __init__(self, ruta: str | Path, *, solo_lectura: bool = False):
        self.ruta = Path(ruta)
        if solo_lectura:
            if not self.ruta.is_file():
                raise FileNotFoundError(self.ruta)
            self.con = sqlite3.connect(
                f"{self.ruta.resolve().as_uri()}?mode=ro",
                uri=True,
                check_same_thread=False,
                timeout=5,
            )
        else:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self.con = sqlite3.connect(self.ruta, timeout=5)
        self.con.row_factory = sqlite3.Row
        if not solo_lectura:
            # WAL: el portal puede leer mientras una corrida escribe (vista en vivo, extra #29).
            self.con.execute("PRAGMA journal_mode=WAL")
            self.con.executescript(ESQUEMA)
        self.duplicados = 0

    def cerrar(self) -> None:
        self.con.commit()
        self.con.close()

    def __enter__(self) -> Almacen:
        return self

    def __exit__(self, *exc: object) -> None:
        self.cerrar()

    # --- escritura -----------------------------------------------------------------------------

    def guardar_corrida(self, run: dict[str, Any], carpeta: Path) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO corridas VALUES (?,?,?,?,?,?)",
            (
                run["run_id"],
                str(Path(carpeta).resolve()),
                run.get("segmento"),
                run.get("config_ref"),
                run.get("inicio_utc"),
                _dump(run),
            ),
        )
        self.con.commit()

    def guardar_evento(self, ev: dict[str, Any]) -> bool:
        """True si se guardó; False si el event_id ya existía (duplicado)."""
        contratos.validar("evento", ev)
        cur = self.con.execute(
            "INSERT OR IGNORE INTO eventos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ev["event_id"],
                ev["run_id"],
                ev["frame_id"],
                ev["timestamp_utc"],
                ev["video_pos_ms"],
                ev["source_id"],
                ev["status"],
                ev["zona_frame"],
                ev["score_max"],
                ev["n_candidatas"],
                ev["image_ref"],
                ev["config_ref"],
                ev["model_ref"],
                _dump(ev),
            ),
        )
        if cur.rowcount == 0:
            self.duplicados += 1
            return False
        self.con.commit()
        return True

    def fijar_imagen(self, event_id: str, image_ref: str) -> None:
        fila = self.con.execute("SELECT json FROM eventos WHERE event_id=?", (event_id,)).fetchone()
        ev = json.loads(fila["json"])
        ev["image_ref"] = image_ref
        contratos.validar("evento", ev)
        self.con.execute(
            "UPDATE eventos SET image_ref=?, json=? WHERE event_id=?",
            (image_ref, _dump(ev), event_id),
        )
        self.con.commit()

    def guardar_captura(self, cap: dict[str, Any]) -> None:
        contratos.validar("captura", cap)
        self.con.execute(
            "INSERT OR REPLACE INTO capturas VALUES (?,?,?,?,?,?)",
            (
                cap["image_id"],
                cap["event_id"],
                cap["run_id"],
                cap["ruta"],
                cap["sha256"],
                _dump(cap),
            ),
        )
        self.con.commit()

    def guardar_ventana(self, ven: dict[str, Any]) -> None:
        contratos.validar("ventana", ven)
        self.con.execute(
            "INSERT OR REPLACE INTO ventanas VALUES (?,?,?)",
            (ven["run_id"], ven["indice"], _dump(ven)),
        )
        self.con.commit()

    def guardar_alerta(self, al: dict[str, Any]) -> None:
        tipo = {
            "p6.alerta_fuente.v1": "alerta_fuente",
            "p6.alerta_tecnica.v1": "alerta_tecnica",
        }.get(al["schema"], "alerta")
        contratos.validar(tipo, al)
        self.con.execute(
            "INSERT OR REPLACE INTO alertas VALUES (?,?,?,?,?,?,?,?)",
            (
                al["alert_id"],
                al["run_id"],
                al["rule_id"],
                al["timestamp_utc"],
                al["severidad"],
                al["estado"],
                al["motivo"],
                _dump(al),
            ),
        )
        self.con.executemany(
            "INSERT OR IGNORE INTO alerta_eventos VALUES (?,?)",
            [(al["alert_id"], eid) for eid in al["event_ids"]],
        )
        self.con.commit()

    def guardar_vivo(
        self,
        run_id: str,
        *,
        actualizado_utc: str,
        estado: str,
        estado_fuente: str,
        evento: dict[str, Any] | None,
        jpeg: bytes | None,
        datos: dict[str, Any],
    ) -> None:
        """Último frame procesado de una corrida, para la vista en vivo (extra #29). Si no hay
        frame nuevo (latido o cierre) conserva la imagen y el evento anteriores."""
        previo = self.con.execute(
            "SELECT event_id, jpeg FROM vivo WHERE run_id=?", (run_id,)
        ).fetchone()
        event_id = evento["event_id"] if evento else (previo["event_id"] if previo else None)
        if jpeg is None and previo is not None:
            jpeg = previo["jpeg"]
        self.con.execute(
            "INSERT OR REPLACE INTO vivo VALUES (?,?,?,?,?,?,?)",
            (run_id, actualizado_utc, estado, estado_fuente, event_id, jpeg, _dump(datos)),
        )
        self.con.commit()

    def vivo(self, run_id: str) -> dict[str, Any] | None:
        f = self.con.execute(
            "SELECT run_id, actualizado_utc, estado, estado_fuente, event_id, json, "
            "jpeg IS NOT NULL AS hay_imagen FROM vivo WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if f is None:
            return None
        fila = dict(f)
        return {**json.loads(fila.pop("json")), **fila}

    def vivo_jpeg(self, run_id: str) -> bytes | None:
        f = self.con.execute("SELECT jpeg FROM vivo WHERE run_id=?", (run_id,)).fetchone()
        return f["jpeg"] if f else None

    def corridas_vivo(self) -> list[str]:
        return [
            f["run_id"]
            for f in self.con.execute("SELECT run_id FROM vivo ORDER BY actualizado_utc DESC")
        ]

    def borrar_corrida(self, run_id: str) -> None:
        """Solo para reimportar una corrida desde su exportación (no toca las imágenes)."""
        for tabla in ("eventos", "capturas", "ventanas", "alertas", "corridas", "vivo"):
            self.con.execute(f"DELETE FROM {tabla} WHERE run_id=?", (run_id,))
        self.con.execute(
            "DELETE FROM alerta_eventos WHERE alert_id NOT IN (SELECT alert_id FROM alertas)"
        )
        self.con.commit()

    # --- lectura -------------------------------------------------------------------------------

    def _json(self, sql: str, args: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return [json.loads(f["json"]) for f in self.con.execute(sql, tuple(args))]

    def corridas(self) -> list[dict[str, Any]]:
        filas = self.con.execute("SELECT dir, json FROM corridas ORDER BY inicio_utc").fetchall()
        return [{**json.loads(f["json"]), "_dir": f["dir"]} for f in filas]

    def corrida(self, run_id: str) -> dict[str, Any] | None:
        f = self.con.execute("SELECT dir, json FROM corridas WHERE run_id=?", (run_id,)).fetchone()
        return {**json.loads(f["json"]), "_dir": f["dir"]} if f else None

    def eventos(
        self,
        *,
        run_id: str | None = None,
        zona: str | None = None,
        status: str | None = None,
        limite: int = 100,
        desplazamiento: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        condiciones, args = [], []
        if run_id:
            condiciones.append("run_id=?")
            args.append(run_id)
        if zona:
            condiciones.append("zona_frame=?")
            args.append(zona)
        if status:
            condiciones.append("status=?")
            args.append(status)
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        total = self.con.execute(f"SELECT COUNT(*) FROM eventos {where}", args).fetchone()[0]
        filas = self._json(
            f"SELECT json FROM eventos {where} ORDER BY run_id, video_pos_ms LIMIT ? OFFSET ?",
            [*args, limite, desplazamiento],
        )
        return filas, total

    def evento(self, event_id: str) -> dict[str, Any] | None:
        r = self._json("SELECT json FROM eventos WHERE event_id=?", [event_id])
        return r[0] if r else None

    def captura_de_evento(self, event_id: str) -> dict[str, Any] | None:
        r = self._json("SELECT json FROM capturas WHERE event_id=?", [event_id])
        return r[0] if r else None

    def captura(self, image_id: str) -> dict[str, Any] | None:
        r = self._json("SELECT json FROM capturas WHERE image_id=?", [image_id])
        return r[0] if r else None

    def alertas_de_evento(self, event_id: str) -> list[dict[str, Any]]:
        return self._json(
            "SELECT a.json FROM alertas a JOIN alerta_eventos x ON a.alert_id=x.alert_id "
            "WHERE x.event_id=? ORDER BY a.timestamp_utc",
            [event_id],
        )

    def ventana_de_evento(self, ev: dict[str, Any]) -> dict[str, Any] | None:
        for v in self._json("SELECT json FROM ventanas WHERE run_id=?", [ev["run_id"]]):
            if ev["event_id"] in v["event_ids"]:
                return v
        return None

    def alertas(
        self, *, run_id: str | None = None, severidad: str | None = None
    ) -> list[dict[str, Any]]:
        condiciones, args = [], []
        if run_id:
            condiciones.append("run_id=?")
            args.append(run_id)
        if severidad:
            condiciones.append("severidad=?")
            args.append(severidad)
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        return self._json(f"SELECT json FROM alertas {where} ORDER BY timestamp_utc DESC", args)

    def alerta(self, alert_id: str) -> dict[str, Any] | None:
        r = self._json("SELECT json FROM alertas WHERE alert_id=?", [alert_id])
        return r[0] if r else None

    def ventanas(self, run_id: str) -> list[dict[str, Any]]:
        return self._json("SELECT json FROM ventanas WHERE run_id=? ORDER BY indice", [run_id])


# --- exportación e importación -----------------------------------------------------------------


def escribir_jsonl(ruta: Path, registros: Iterable[dict[str, Any]]) -> int:
    n = 0
    with Path(ruta).open("w", encoding="utf-8", newline="\n") as f:
        for r in registros:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n


def leer_jsonl(ruta: Path) -> Iterator[dict[str, Any]]:
    ruta = Path(ruta)
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                yield json.loads(linea)


def importar(almacen: Almacen, carpeta: Path) -> str:
    """Carga en la base una corrida exportada (run.json + JSONL). Reemplaza la anterior."""
    carpeta = Path(carpeta)
    run = json.loads((carpeta / "run.json").read_text(encoding="utf-8"))
    almacen.borrar_corrida(run["run_id"])
    almacen.guardar_corrida(run, carpeta)
    for ev in leer_jsonl(carpeta / "eventos.jsonl"):
        almacen.guardar_evento(ev)
    for cap in leer_jsonl(carpeta / "capturas.jsonl"):
        almacen.guardar_captura(cap)
    for ven in leer_jsonl(carpeta / "ventanas.jsonl"):
        almacen.guardar_ventana(ven)
    for al in leer_jsonl(carpeta / "alertas.jsonl"):
        almacen.guardar_alerta(al)
    return run["run_id"]
