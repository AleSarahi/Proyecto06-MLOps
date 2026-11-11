# ruff: noqa: E501  (plantillas HTML en línea)
"""Funciones opcionales del portal (extras; docs/p6/extras.md).

    /vivo                   F1 · stream en vivo: último frame con cajas, estado de la corrida y de
    /api/vivo               la fuente, alertas abiertas (se actualiza cada segundo)
    /vivo/<run>/frame.jpg
    /dashboard              F2 · gráficas históricas por ventana de G1-G7 y X1-X5, una o varias
                            corridas, rango de ventanas, alertas sombreadas
    /exportar/eventos.csv   F3 · exportación de eventos con los mismos filtros que /eventos
    /exportar/eventos.jsonl

Todo se lee de la base SQLite (solo lectura) y de los archivos de métricas de cada corrida.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, jsonify, request

ZONAS = ("baja", "duda", "aceptada")
ESTADOS = ("ok", "sin_detecciones", "error")
# Sin actualización de la corrida durante este tiempo, la vista avisa que el proceso no responde.
SIN_ACTUALIZAR_S = 5.0
COLORES = ("#1849a9", "#b54708", "#067647", "#b42318")


class FiltroInvalido(ValueError):
    pass


def filtros_eventos(args: Any) -> dict[str, str | None]:
    """Valida run/zona/status. Un valor desconocido es un error (400), no «todos»."""
    f = {k: (args.get(k) or None) for k in ("run", "zona", "status")}
    if f["zona"] and f["zona"] not in ZONAS:
        raise FiltroInvalido(f"zona desconocida {f['zona']!r}; usa una de {', '.join(ZONAS)}")
    if f["status"] and f["status"] not in ESTADOS:
        raise FiltroInvalido(f"estado desconocido {f['status']!r}; usa uno de {', '.join(ESTADOS)}")
    return f


def _edad_s(iso: str) -> float:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(UTC) - t).total_seconds()


def estado_vista(vivo: dict[str, Any]) -> tuple[str, str]:
    """Estado que muestra la vista en vivo y su explicación."""
    edad = _edad_s(vivo["actualizado_utc"])
    if vivo["estado"] == "terminada":
        return "terminada", "La corrida terminó; se muestra su último frame."
    if vivo["estado"] == "fallida":
        return (
            "fallida",
            "La corrida se detuvo con un error; se muestra el último frame registrado.",
        )
    if edad > SIN_ACTUALIZAR_S:
        return (
            "sin_actualizaciones",
            f"La corrida no se actualiza desde hace {edad:.0f} s: el proceso pudo detenerse.",
        )
    if vivo["estado_fuente"] == "sin_senal":
        return (
            "sin_senal",
            "La fuente no entrega frames: alerta de fuente abierta. Imagen congelada.",
        )
    if vivo["estado_fuente"] == "recuperando":
        return "recuperando", "La señal volvió; esperando frames seguidos para cerrar la alerta."
    return "en_vivo", "Recibiendo e infiriendo frames."


T_VIVO = """
<div class="panel"><form method="get"><label>Corrida<select name="run">
{% for r in corridas %}<option {{'selected' if r==run}}>{{r}}</option>{% endfor %}</select></label>
<button>Ver</button></form></div>
{% if not run %}<div class="panel"><div class="vacio">No hay corridas en vivo en la base. Inicia una con
<code>python -m monitor correr --segmento c1 --salida …</code> y abre esta página.</div></div>{% else %}
<div class="panel"><p><span id="estado" class="z neutro">cargando…</span> <span id="explica"></span></p>
<dl><dt>Corrida</dt><dd><a class="mono" href="/corridas/{{run}}">{{run}}</a></dd>
<dt>Frame</dt><dd id="frame">—</dd><dt>Zona del frame</dt><dd id="zona">—</dd>
<dt>Ventana</dt><dd id="ventana">—</dd><dt>Procesados</dt><dd id="procesados">—</dd>
<dt>Actualizado</dt><dd id="actualizado">—</dd><dt>Alertas abiertas</dt><dd id="alertas">—</dd></dl></div>
<div class="panel"><div class="figura" id="fig"><img id="img" alt="último frame" src="">
<svg id="cajas" preserveAspectRatio="none"></svg></div><div id="sinimg" class="vacio" hidden>
Todavía no hay frames procesados.</div></div>
<script>
const RUN = {{ run|tojson }};
let evento = null;
const ns = "http://www.w3.org/2000/svg";
async function tick() {
  let d;
  try {
    const r = await fetch("/api/vivo?run=" + encodeURIComponent(RUN), {cache: "no-store"});
    d = await r.json();
    if (!r.ok) throw new Error(d.error || r.status);
  } catch (e) {
    document.getElementById("estado").textContent = "portal sin respuesta";
    document.getElementById("estado").className = "z baja";
    document.getElementById("explica").textContent = String(e);
    return;
  }
  const est = document.getElementById("estado");
  est.textContent = d.vista; est.className = "z " + ({en_vivo: "aceptada", terminada: "neutro",
    recuperando: "duda"}[d.vista] || "baja");
  document.getElementById("explica").textContent = d.explicacion;
  document.getElementById("procesados").textContent = d.procesados;
  document.getElementById("ventana").textContent = d.ventana ?? "—";
  document.getElementById("actualizado").textContent = d.actualizado_utc + " (hace " + d.edad_s.toFixed(1) + " s)";
  const al = document.getElementById("alertas"); al.textContent = "";
  if (!d.alertas_abiertas.length) al.textContent = "ninguna";
  for (const a of d.alertas_abiertas) { const x = document.createElement("a");
    x.href = "/alertas/" + a; x.textContent = a; x.className = "mono"; al.append(x, " "); }
  const u = d.ultimo;
  document.getElementById("sinimg").hidden = !!u;
  document.getElementById("fig").hidden = !u;
  if (!u) return;
  const fr = document.getElementById("frame"); fr.textContent = "";
  const link = document.createElement("a"); link.href = "/eventos/" + u.event_id;
  link.textContent = u.frame_id + " · " + (u.video_pos_ms / 1000).toFixed(1) + " s del video";
  fr.append(link);
  document.getElementById("zona").textContent = (u.zona_frame || u.status) +
    (u.score_max != null ? " (máx. " + u.score_max.toFixed(3) + ")" : "") + " · " +
    u.conteo_zonas.baja + "/" + u.conteo_zonas.duda + "/" + u.conteo_zonas.aceptada + " baja/duda/acept.";
  if (u.event_id !== evento) {
    evento = u.event_id;
    document.getElementById("img").src = "/vivo/" + encodeURIComponent(RUN) + "/frame.jpg?e=" + encodeURIComponent(u.event_id);
    const svg = document.getElementById("cajas");
    svg.setAttribute("viewBox", "0 0 " + u.image_width + " " + u.image_height);
    svg.replaceChildren();
    for (const b of u.detecciones) { const r = document.createElementNS(ns, "rect");
      r.setAttribute("x", b.bbox[0]); r.setAttribute("y", b.bbox[1]);
      r.setAttribute("width", b.bbox[2] - b.bbox[0]); r.setAttribute("height", b.bbox[3] - b.bbox[1]);
      r.setAttribute("fill", "none"); r.setAttribute("stroke", "currentColor"); r.setAttribute("stroke-width", 3);
      r.setAttribute("class", b.zona); svg.append(r); }
  }
}
tick(); setInterval(tick, 1000);
</script>{% endif %}"""

T_DASHBOARD = """
<div class="panel"><form method="get">
<label>Corridas (una o varias)<select name="run" multiple size="4">
{% for c in corridas %}<option value="{{c.run_id}}" {{'selected' if c.run_id in sel}}>{{c.run_id}}</option>{% endfor %}
</select></label>
<label>Métrica<select name="metrica">{% for k, n in catalogo.items() %}
<option value="{{k}}" {{'selected' if k==metrica}}>{{k}} · {{n}}</option>{% endfor %}</select></label>
<label>Desde ventana<input name="desde" value="{{desde if desde is not none}}" size="4" inputmode="numeric"></label>
<label>Hasta ventana<input name="hasta" value="{{hasta if hasta is not none}}" size="4" inputmode="numeric"></label>
<button>Graficar</button></form></div>
{% if not corridas %}<div class="panel"><div class="vacio">No hay corridas en la base.</div></div>
{% elif not sel %}<div class="panel"><div class="vacio">Elige una o más corridas para graficar.</div></div>
{% else %}
{% for a in avisos %}<div class="panel err">{{a}}</div>{% endfor %}
<div class="panel"><h2 style="font-size:16px">{{metrica}} · {{nombre}} <span style="color:var(--sutil);font-weight:400">({{unidad}}, por ventana)</span></h2>
{% if not hay_datos %}<div class="vacio">Sin datos de {{metrica}} en este rango. Un valor nulo significa
«sin observaciones» (p. ej. ventana sin frames o insuficiente), no cero.</div>{% else %}{{ svg|safe }}
<p style="font-size:13px;color:var(--sutil)">{% for s in series %}<span style="color:{{s.color}}">■</span> {{s.run}} &nbsp; {% endfor %}
{% if linea %}<span>- - {{linea.texto}}</span>{% endif %}{% if sombras %} · franjas: ventanas con alerta de la corrida{% endif %}
· punto hueco: sin dato</p>{% endif %}</div>
<div class="panel"><table><tr><th>Ventana</th>{% for s in series %}<th>{{s.run}}</th>{% endfor %}</tr>
{% for i in indices %}<tr><td><a href="/corridas/{{series[0].run}}">{{i}}</a></td>
{% for s in series %}{% set p = s.puntos.get(i) %}<td>{% if p is none %}—{% elif p.valor is none %}sin dato
{% if p.estado %}({{p.estado}}){% endif %} · n={{p.n}}{% else %}{{p.valor}} · n={{p.n}}{% endif %}</td>{% endfor %}</tr>
{% else %}<tr><td colspan="9" class="vacio">Sin ventanas en el rango.</td></tr>{% endfor %}</table></div>
{% endif %}"""


def _catalogo() -> dict[str, tuple[str, str, str]]:
    from .metricas import DEFINICIONES as G
    from .metricas_extra import DEFINICIONES as X

    return {
        **{k: (v[1], v[2], "metricas.json") for k, v in G.items()},
        **{k: (v[1], v[2], "metricas_extra.json") for k, v in X.items()},
    }


def _entero_opcional(valor: str | None, nombre: str) -> int | None:
    if valor in (None, ""):
        return None
    try:
        n = int(valor)
    except ValueError as exc:
        raise FiltroInvalido(f"{nombre} debe ser un número de ventana, no {valor!r}") from exc
    if n < 0:
        raise FiltroInvalido(f"{nombre} no puede ser negativo")
    return n


def svg_lineas(
    series: list[dict[str, Any]],
    indices: list[int],
    *,
    linea: dict[str, Any] | None,
    sombras: list[int],
) -> str:
    """Gráfica de líneas en SVG. Nulos = huecos (la línea se corta) con punto hueco en la base."""
    an, al, mi, md, ms, mb = 860, 260, 56, 16, 14, 30
    valores = [p["valor"] for s in series for p in s["puntos"].values() if p["valor"] is not None]
    if linea:
        valores.append(linea["valor"])
    vmin, vmax = min(0.0, min(valores)), max(valores) or 1.0
    vmax = vmax + (vmax - vmin) * 0.08
    i0, i1 = indices[0], indices[-1]

    def x(i: int) -> float:
        return mi + (an - mi - md) * ((i - i0) / (i1 - i0) if i1 > i0 else 0.5)

    def y(v: float) -> float:
        return ms + (al - ms - mb) * (1 - (v - vmin) / (vmax - vmin))

    paso = (an - mi - md) / max(1, i1 - i0)
    partes = [
        f'<svg viewBox="0 0 {an} {al}" width="100%" role="img" aria-label="gráfica por ventana" style="max-width:{an}px;color:var(--sutil)">'
    ]
    for i in sombras:
        if i0 <= i <= i1:
            partes.append(
                f'<rect x="{x(i) - paso / 2:.1f}" y="{ms}" width="{paso:.1f}" height="{al - ms - mb}" fill="var(--baja)" opacity="0.10"/>'
            )
    for k in range(5):
        v = vmin + (vmax - vmin) * k / 4
        partes.append(
            f'<line x1="{mi}" x2="{an - md}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--borde)"/>'
            f'<text x="{mi - 6}" y="{y(v) + 4:.1f}" font-size="11" text-anchor="end" fill="currentColor">{v:.3g}</text>'
        )
    salto = max(1, len(indices) // 12)
    for i in indices[::salto]:
        partes.append(
            f'<text x="{x(i):.1f}" y="{al - 10}" font-size="11" text-anchor="middle" fill="currentColor">{i}</text>'
        )
    if linea:
        partes.append(
            f'<line x1="{mi}" x2="{an - md}" y1="{y(linea["valor"]):.1f}" y2="{y(linea["valor"]):.1f}" stroke="currentColor" stroke-dasharray="6 4"/>'
        )
    for s in series:
        tramo: list[str] = []
        segmentos: list[list[str]] = []
        for i in indices:
            p = s["puntos"].get(i)
            if p is None or p["valor"] is None:
                if tramo:
                    segmentos.append(tramo)
                tramo = []
                if p is not None:
                    partes.append(
                        f'<circle cx="{x(i):.1f}" cy="{al - mb:.1f}" r="4" fill="none" stroke="{s["color"]}"/>'
                    )
                continue
            tramo.append(f"{x(i):.1f},{y(p['valor']):.1f}")
            partes.append(
                f'<circle cx="{x(i):.1f}" cy="{y(p["valor"]):.1f}" r="3.5" fill="{s["color"]}"><title>{s["run"]} · ventana {i}: {p["valor"]} (n={p["n"]})</title></circle>'
            )
        if tramo:
            segmentos.append(tramo)
        for seg in segmentos:
            partes.append(
                f'<polyline points="{" ".join(seg)}" fill="none" stroke="{s["color"]}" stroke-width="2"/>'
            )
    partes.append(
        f'<text x="{(an + mi) / 2:.0f}" y="{al}" font-size="11" text-anchor="middle" fill="currentColor">ventana</text></svg>'
    )
    return "".join(partes)


def registrar(app: Flask, abrir, pagina) -> None:
    @app.errorhandler(FiltroInvalido)
    def filtro_invalido(exc):
        if request.path.startswith(("/api/", "/exportar/")):
            return Response(f"Filtro inválido: {exc}\n", 400, mimetype="text/plain")
        return pagina(
            "Filtro inválido",
            "<div class='panel err'><p>{{ m }}</p><p><a href='{{ v }}'>Quitar filtros</a></p></div>",
            400,
            m=str(exc),
            v=request.path,
        )

    # --- F1 · vivo ----------------------------------------------------------------------------

    @app.get("/vivo")
    def vivo():
        alm = abrir()
        try:
            corridas = alm.corridas_vivo()
        finally:
            alm.con.close()
        run = request.args.get("run") or (corridas[0] if corridas else None)
        if run and run not in corridas:
            abort(404, f"La corrida {run} no tiene estado en vivo.")
        return pagina("En vivo", T_VIVO, run=run, corridas=corridas)

    @app.get("/api/vivo")
    def api_vivo():
        run = request.args.get("run")
        alm = abrir()
        try:
            v = alm.vivo(run) if run else None
        finally:
            alm.con.close()
        if v is None:
            return jsonify({"error": f"sin estado en vivo para {run!r}"}), 404
        vista, explicacion = estado_vista(v)
        return jsonify(
            {
                "run_id": v["run_id"],
                "vista": vista,
                "explicacion": explicacion,
                "estado_corrida": v["estado"],
                "estado_fuente": v["estado_fuente"],
                "actualizado_utc": v["actualizado_utc"],
                "edad_s": round(_edad_s(v["actualizado_utc"]), 2),
                "procesados": v["procesados"],
                "ventana": v["ventana"],
                "alertas_abiertas": v["alertas_abiertas"],
                "ultimo": v["ultimo"],
            }
        )

    @app.get("/vivo/<run_id>/frame.jpg")
    def vivo_frame(run_id: str):
        alm = abrir()
        try:
            datos = alm.vivo_jpeg(run_id)
        finally:
            alm.con.close()
        if not datos:
            abort(404, f"La corrida {run_id} no tiene frame en vivo.")
        r = Response(datos, mimetype="image/jpeg")
        r.headers["Cache-Control"] = "no-store"
        return r

    # --- F2 · dashboard ------------------------------------------------------------------------

    @app.get("/dashboard")
    def dashboard():
        catalogo = _catalogo()
        metrica = request.args.get("metrica", "G4")
        if metrica not in catalogo:
            raise FiltroInvalido(
                f"métrica desconocida {metrica!r}; usa una de {', '.join(catalogo)}"
            )
        desde = _entero_opcional(request.args.get("desde"), "desde")
        hasta = _entero_opcional(request.args.get("hasta"), "hasta")
        if desde is not None and hasta is not None and desde > hasta:
            raise FiltroInvalido("«desde» debe ser menor o igual que «hasta»")
        sel = list(dict.fromkeys(request.args.getlist("run")))
        if len(sel) > len(COLORES):
            raise FiltroInvalido(f"elige como máximo {len(COLORES)} corridas")
        alm = abrir()
        try:
            corridas = alm.corridas()
            info = {}
            for r in sel:
                c = alm.corrida(r)
                if c is None:
                    abort(404, f"No existe la corrida {r}.")
                info[r] = (c, alm.alertas(run_id=r))
        finally:
            alm.con.close()
        nombre, unidad, archivo = catalogo[metrica]
        series, avisos, sombras, todos = [], [], set(), set()
        linea = None
        for k, r in enumerate(sel):
            c, alertas = info[r]
            ruta = Path(c["_dir"]) / archivo
            if not ruta.is_file():
                avisos.append(
                    f"{r} no tiene {archivo}: corre `python -m monitor "
                    f"{'metricas' if archivo == 'metricas.json' else 'metricas-extra'} <carpeta>`."
                )
                continue
            datos = json.loads(ruta.read_text(encoding="utf-8"))["metricas"][metrica]["por_ventana"]
            puntos = {
                p["ventana"]: {
                    "valor": p["valor"],
                    "n": p["n"],
                    "estado": p.get("estado") or p.get("estado_ventana"),
                }
                for p in datos
                if (desde is None or p["ventana"] >= desde)
                and (hasta is None or p["ventana"] <= hasta)
            }
            todos |= set(puntos)
            series.append({"run": r, "color": COLORES[k], "puntos": puntos})
            if len(sel) == 1:
                for a in alertas:
                    for w in a.get("ventanas", []):
                        sombras.add(w["indice"] if isinstance(w, dict) else w)
            if metrica == "G4" and c.get("referencia") and linea is None:
                linea = {
                    "valor": c["referencia"]["proporcion_baja"],
                    "texto": f"referencia {c['referencia']['proporcion_baja']:.3f}",
                }
        if metrica == "X3":
            linea = {"valor": 0.25, "texto": "PSI 0.25 (umbral orientativo de cambio importante)"}
        indices = sorted(todos)
        hay_datos = any(p["valor"] is not None for s in series for p in s["puntos"].values())
        svg = svg_lineas(series, indices, linea=linea, sombras=sorted(sombras)) if hay_datos else ""
        return pagina(
            "Dashboard",
            T_DASHBOARD,
            corridas=corridas,
            sel=sel,
            catalogo={k: v[0] for k, v in catalogo.items()},
            metrica=metrica,
            nombre=nombre,
            unidad=unidad,
            desde=desde,
            hasta=hasta,
            series=series,
            indices=indices,
            avisos=avisos,
            hay_datos=hay_datos,
            svg=svg,
            linea=linea,
            sombras=sorted(sombras),
        )

    # --- F3 · exportación -------------------------------------------------------------------

    @app.get("/exportar/eventos.<formato>")
    def exportar(formato: str):
        if formato not in ("csv", "jsonl"):
            abort(404, "Formatos: csv o jsonl.")
        f = filtros_eventos(request.args)
        alm = abrir()
        try:
            if f["run"] and alm.corrida(f["run"]) is None:
                abort(404, f"No existe la corrida {f['run']}.")
            eventos, total = alm.eventos(
                run_id=f["run"], zona=f["zona"], status=f["status"], limite=10**9
            )
        finally:
            alm.con.close()
        nombre = "eventos" + "".join(f"_{v}" for v in f.values() if v)
        if formato == "jsonl":
            cuerpo = "".join(
                json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in eventos
            )
            tipo = "application/x-ndjson"
        else:
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            w.writerow(COLUMNAS_CSV)
            for e in eventos:
                w.writerow(
                    [
                        e["event_id"],
                        e["run_id"],
                        e["frame_id"],
                        e["timestamp_utc"],
                        e["video_pos_ms"],
                        e["status"],
                        e["zona_frame"] or "",
                        "" if e["score_max"] is None else e["score_max"],
                        e["n_candidatas"],
                        e["conteo_zonas"]["baja"],
                        e["conteo_zonas"]["duda"],
                        e["conteo_zonas"]["aceptada"],
                        e["image_ref"] or "",
                        e["model_ref"],
                        e["config_ref"],
                    ]
                )
            cuerpo, tipo = buf.getvalue(), "text/csv"
        r = Response(cuerpo, mimetype=tipo)
        r.headers["Content-Disposition"] = f'attachment; filename="{nombre}.{formato}"'
        r.headers["X-Total-Eventos"] = str(total)
        return r


COLUMNAS_CSV = (
    "event_id",
    "run_id",
    "frame_id",
    "timestamp_utc",
    "video_pos_ms",
    "status",
    "zona_frame",
    "score_max",
    "n_candidatas",
    "n_baja",
    "n_duda",
    "n_aceptada",
    "image_ref",
    "model_ref",
    "config_ref",
)
