# ruff: noqa: E501  (plantillas HTML en línea)
"""Portal de consulta de eventos y alertas (issues #20 y #21).

Lee la base SQLite en solo lectura. Rutas:
    /eventos             lista con filtros por corrida, zona y estado (paginada)
    /eventos/<id>        detalle: detecciones con zona, imagen con cajas, ventana, alertas, corrida
    /alertas             lista con momento, regla, severidad, estado, motivo y acción sugerida
    /alertas/<id>        detalle: regla, ventanas, configuración y eventos de origen con imágenes
    /corridas[/<id>]     identidad de la corrida, configuración efectiva y métricas
    /imagenes/<id>       la captura (solo archivos registrados en la base)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from flask import Flask, abort, render_template_string, request, send_file

from .almacen import Almacen

POR_PAGINA = 50

BASE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ titulo }} · Centro de monitoreo P6</title>
<style>
:root{--fondo:#f6f7f9;--texto:#1d2330;--sutil:#5d6675;--borde:#d8dde5;--panel:#fff;
--baja:#b42318;--duda:#b54708;--aceptada:#067647;--neutro:#475467;--enlace:#1849a9}
@media (prefers-color-scheme:dark){:root{--fondo:#12151b;--texto:#e6e9ef;--sutil:#9aa3b2;
--borde:#2c323d;--panel:#1a1e26;--baja:#f97066;--duda:#fdb022;--aceptada:#47cd89;--neutro:#98a2b3;
--enlace:#84adff}}
*{box-sizing:border-box}body{margin:0;font:15px/1.45 system-ui,sans-serif;background:var(--fondo);
color:var(--texto)}header{background:var(--panel);border-bottom:1px solid var(--borde);
padding:12px 16px;display:flex;gap:20px;align-items:center;flex-wrap:wrap}
header b{font-size:16px}nav a{margin-right:14px}a{color:var(--enlace)}
main{max-width:1200px;margin:0 auto;padding:16px}
.panel{background:var(--panel);border:1px solid var(--borde);border-radius:8px;padding:14px;
margin-bottom:14px;overflow-x:auto}table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--borde);vertical-align:top}
th{color:var(--sutil);font-weight:600;font-size:13px}
.z{font-weight:600;padding:1px 8px;border-radius:10px;border:1px solid currentColor;
white-space:nowrap;font-size:13px}.baja,.critica{color:var(--baja)}.duda,.advertencia{color:var(--duda)}
.aceptada{color:var(--aceptada)}.neutro,.info,.sin_detecciones,.error{color:var(--neutro)}
.vacio{color:var(--sutil);padding:24px;text-align:center}
.err{border-color:var(--baja)}.mono{font-family:ui-monospace,monospace;font-size:13px;
word-break:break-all}form{display:flex;gap:10px;flex-wrap:wrap;align-items:end}
label{font-size:13px;color:var(--sutil);display:flex;flex-direction:column;gap:2px}
select,button{font:inherit;padding:4px 8px}img.mini{height:54px;border-radius:4px}
.figura{position:relative;max-width:100%}.figura svg{position:absolute;inset:0;width:100%;height:100%}
.figura img{display:block;max-width:100%;height:auto}dl{display:grid;grid-template-columns:
max-content 1fr;gap:4px 14px;margin:0}dt{color:var(--sutil)}dd{margin:0}
pre{white-space:pre-wrap;font-size:12px;margin:0}
</style></head><body>
<header><b>Centro de monitoreo · P6</b><nav><a href="/eventos">Eventos</a><a href="/alertas">Alertas</a>
<a href="/corridas">Corridas</a></nav></header>
<main><h1 style="font-size:20px">{{ titulo }}</h1>{{ cuerpo|safe }}</main></body></html>"""


def _zona(valor: str | None, estado: str | None = None) -> str:
    texto = valor or estado or "—"
    clase = valor or estado or "neutro"
    return f'<span class="z {clase}">{texto}</span>'


T_EVENTOS = """
<div class="panel"><form method="get">
<label>Corrida<select name="run"><option value="">todas</option>
{% for c in corridas %}<option value="{{c.run_id}}" {{'selected' if c.run_id==f.run}}>{{c.run_id}}
</option>{% endfor %}</select></label>
<label>Zona del frame<select name="zona"><option value="">todas</option>
{% for z in ['baja','duda','aceptada'] %}<option {{'selected' if z==f.zona}}>{{z}}</option>{% endfor %}
</select></label>
<label>Estado<select name="status"><option value="">todos</option>
{% for s in ['ok','sin_detecciones','error'] %}<option {{'selected' if s==f.status}}>{{s}}</option>
{% endfor %}</select></label><button>Filtrar</button></form></div>
<div class="panel">
{% if not eventos %}<div class="vacio">No hay eventos con estos filtros.
{% if not corridas %} La base no tiene corridas: corre <code>python -m monitor importar …</code>.{% endif %}
</div>{% else %}
<p>{{ total }} eventos · página {{ pagina }} de {{ paginas }}</p>
<table><tr><th>Evento</th><th>Corrida</th><th>t video</th><th>Estado</th><th>Zona</th>
<th>Score máx.</th><th>Candidatas baja/duda/acept.</th><th>Imagen</th></tr>
{% for e in eventos %}<tr>
<td><a class="mono" href="/eventos/{{e.event_id}}">{{e.frame_id}}</a></td>
<td class="mono">{{e.run_id}}</td><td>{{ '%.1f'|format(e.video_pos_ms/1000) }} s</td>
<td>{{e.status}}</td><td>{{ zona(e.zona_frame, e.status)|safe }}</td>
<td>{{ '%.3f'|format(e.score_max) if e.score_max is not none else '—' }}</td>
<td>{{e.conteo_zonas.baja}} / {{e.conteo_zonas.duda}} / {{e.conteo_zonas.aceptada}}</td>
<td>{% if e.image_ref %}<a href="/eventos/{{e.event_id}}"><img class="mini" loading="lazy"
src="/imagenes/img-{{e.event_id}}" alt="captura de {{e.frame_id}}"></a>{% else %}—{% endif %}</td>
</tr>{% endfor %}</table>
<p>{% if pagina>1 %}<a href="?{{qs}}&pagina={{pagina-1}}">← anterior</a>{% endif %}
{% if pagina<paginas %} <a href="?{{qs}}&pagina={{pagina+1}}">siguiente →</a>{% endif %}</p>
{% endif %}</div>"""

T_EVENTO = """
<div class="panel"><dl>
<dt>event_id</dt><dd class="mono">{{e.event_id}}</dd>
<dt>Corrida</dt><dd><a class="mono" href="/corridas/{{e.run_id}}">{{e.run_id}}</a></dd>
<dt>Frame</dt><dd class="mono">{{e.frame_id}} · {{ '%.3f'|format(e.video_pos_ms/1000) }} s del video</dd>
<dt>Fecha (UTC)</dt><dd>{{e.timestamp_utc}}</dd>
<dt>Fuente</dt><dd>{{e.source_id}} (segmento {{e.segmento}})</dd>
<dt>Tarea</dt><dd>{{e.task}}</dd>
<dt>Modelo</dt><dd class="mono">{{e.model_ref}}</dd>
<dt>Configuración</dt><dd class="mono"><a href="/corridas/{{e.run_id}}#config">{{e.config_ref}}</a>
 · umbrales {{ umbrales.inferior }} / {{ umbrales.superior }}</dd>
<dt>Estado</dt><dd>{{e.status}}{% if e.error %}: {{e.error.code}} — {{e.error.message}}{% endif %}</dd>
<dt>Zona del frame</dt><dd>{{ zona(e.zona_frame, e.status)|safe }} (candidata de mayor score:
{{ '%.3f'|format(e.score_max) if e.score_max is not none else '—' }})</dd>
<dt>Tiempos (ms)</dt><dd>inferencia {{e.tiempos_ms.inferencia}} · cola {{e.tiempos_ms.cola}}</dd>
<dt>Ventana</dt><dd>{% if ventana %}{{ventana.indice}} [{{ventana.inicio_ms/1000}} s, {{ventana.fin_ms/1000}} s):
proporción baja {{ '%.3f'|format(ventana.proporcion_baja) if ventana.proporcion_baja is not none else '—' }}
({{ventana.n_baja}}/{{ventana.n_candidatas}}), {{ventana.estado}}{% else %}—{% endif %}</dd>
<dt>Alertas</dt><dd>{% for a in alertas %}<a href="/alertas/{{a.alert_id}}">{{a.rule_id}}</a>
<span class="z {{a.severidad}}">{{a.severidad}}</span> {% else %}ninguna{% endfor %}</dd>
<dt>Captura</dt><dd>{% if captura %}<span class="mono">{{captura.ruta}}</span> · motivos
{{ captura.motivos|join(', ') }} · SHA-256 <span class="mono">{{captura.sha256[:16]}}…</span>
{% else %}no se capturó (política de captura){% endif %}</dd></dl></div>
{% if captura %}<div class="panel"><div class="figura">
<img src="/imagenes/{{captura.image_id}}" alt="frame {{e.frame_id}}">
<svg viewBox="0 0 {{e.image_width}} {{e.image_height}}" preserveAspectRatio="none">
{% for d in e.detecciones %}<rect x="{{d.bbox[0]}}" y="{{d.bbox[1]}}" width="{{d.bbox[2]-d.bbox[0]}}"
height="{{d.bbox[3]-d.bbox[1]}}" fill="none" stroke-width="3" class="{{d.zona}}" stroke="currentColor"/>
{% endfor %}</svg></div></div>{% endif %}
<div class="panel"><h2 style="font-size:16px">Detecciones ({{e.n_candidatas}})</h2>
{% if not e.detecciones %}<div class="vacio">Sin detecciones en este frame ({{e.status}}).</div>{% else %}
<table><tr><th>#</th><th>Clase</th><th>Score</th><th>Zona</th><th>Caja xyxy (px)</th></tr>
{% for d in e.detecciones|sort(attribute='score', reverse=True) %}<tr><td>{{loop.index}}</td>
<td>{{d.class_name}} ({{d.class_id}})</td><td>{{'%.3f'|format(d.score)}}</td><td>{{zona(d.zona)|safe}}</td>
<td class="mono">{{ d.bbox|join(', ') }}</td></tr>{% endfor %}</table>{% endif %}</div>"""

T_ALERTAS = """
<div class="panel"><form method="get">
<label>Corrida<select name="run"><option value="">todas</option>
{% for c in corridas %}<option value="{{c.run_id}}" {{'selected' if c.run_id==f.run}}>{{c.run_id}}
</option>{% endfor %}</select></label>
<label>Severidad<select name="severidad"><option value="">todas</option>
{% for s in ['info','advertencia','critica'] %}<option {{'selected' if s==f.severidad}}>{{s}}</option>
{% endfor %}</select></label><button>Filtrar</button></form></div>
<div class="panel">{% if not alertas %}<div class="vacio">No hay alertas con estos filtros.
Que no haya alertas no significa operación sana: revisa las ventanas insuficientes de cada corrida.
</div>{% else %}
<table><tr><th>Momento (UTC)</th><th>Regla</th><th>Severidad</th><th>Estado</th><th>Motivo</th>
<th>Acción sugerida</th><th>Eventos</th></tr>
{% for a in alertas %}<tr><td><a href="/alertas/{{a.alert_id}}">{{a.timestamp_utc}}</a></td>
<td class="mono">{{a.rule_id}}</td><td><span class="z {{a.severidad}}">{{a.severidad}}</span></td>
<td>{{a.estado}}</td><td>{{a.motivo}}</td><td>{{a.accion_sugerida}}</td>
<td>{{a.event_ids|length}}</td></tr>{% endfor %}</table>{% endif %}</div>"""

T_ALERTA = """
<div class="panel"><dl>
<dt>alert_id</dt><dd class="mono">{{a.alert_id}}</dd>
<dt>Momento (UTC)</dt><dd>{{a.timestamp_utc}}</dd>
<dt>Regla</dt><dd class="mono">{{a.rule_id}} ({{a.regla.tipo}})</dd>
<dt>Condición</dt><dd>{{a.regla.descripcion}}</dd>
<dt>Parámetros</dt><dd>umbral inferior {{a.regla.umbral_inferior}} · mínimo {{a.regla.minimo_candidatas}}
candidatas por ventana · {{a.regla.ventanas_consecutivas}} ventana(s) seguida(s)
{% if a.regla.umbral is not none %} · umbral {{a.regla.umbral}}{% endif %}
{% if a.regla.tolerancia is not none %} · tolerancia {{a.regla.tolerancia}} sobre la referencia
{{a.regla.referencia_proporcion_baja}}{% endif %}</dd>
<dt>Severidad</dt><dd><span class="z {{a.severidad}}">{{a.severidad}}</span></dd>
<dt>Estado</dt><dd>{{a.estado}}{% if a.cerrada_en %} (cerrada {{a.cerrada_en}} por la ventana
{{a.cerrada_por_ventana}}){% endif %}</dd>
<dt>Motivo</dt><dd>{{a.motivo}}</dd>
<dt>Acción sugerida</dt><dd>{{a.accion_sugerida}}</dd>
<dt>Corrida</dt><dd><a class="mono" href="/corridas/{{a.run_id}}">{{a.run_id}}</a></dd>
<dt>Configuración</dt><dd class="mono"><a href="/corridas/{{a.run_id}}#config">{{a.config_ref}}</a></dd>
<dt>Modelo</dt><dd class="mono">{{a.model_ref}}</dd></dl></div>
<div class="panel"><h2 style="font-size:16px">Ventanas que la originaron</h2>
<table><tr><th>Ventana</th><th>Intervalo (s)</th><th>Candidatas</th><th>Baja</th><th>Proporción</th></tr>
{% for v in a.ventanas %}<tr><td>{{v.indice}}</td><td>[{{v.inicio_ms/1000}}, {{v.fin_ms/1000}})</td>
<td>{{v.n_candidatas}}</td><td>{{v.n_baja}}</td><td>{{'%.3f'|format(v.proporcion_baja)}}</td></tr>
{% endfor %}</table></div>
<div class="panel"><h2 style="font-size:16px">Eventos de origen ({{eventos|length}})</h2>
{% if not eventos %}<div class="vacio">Los eventos de esta alerta no están en la base.</div>{% else %}
<table><tr><th>Evento</th><th>t video</th><th>Zona</th><th>Baja/duda/acept.</th><th>Imagen</th></tr>
{% for e in eventos %}<tr><td><a class="mono" href="/eventos/{{e.event_id}}">{{e.frame_id}}</a></td>
<td>{{'%.1f'|format(e.video_pos_ms/1000)}} s</td><td>{{zona(e.zona_frame, e.status)|safe}}</td>
<td>{{e.conteo_zonas.baja}} / {{e.conteo_zonas.duda}} / {{e.conteo_zonas.aceptada}}</td>
<td>{% if e.image_ref %}<img class="mini" loading="lazy" src="/imagenes/img-{{e.event_id}}"
alt="captura">{% else %}—{% endif %}</td></tr>{% endfor %}</table>{% endif %}</div>"""

T_CORRIDAS = """<div class="panel">{% if not corridas %}<div class="vacio">No hay corridas en la base.
Corre <code>python -m monitor importar &lt;carpetas&gt;</code>.</div>{% else %}
<table><tr><th>Corrida</th><th>Segmento</th><th>Inicio (UTC)</th><th>Commit</th><th>Eventos</th>
<th>Alertas</th></tr>{% for c in corridas %}<tr><td><a class="mono" href="/corridas/{{c.run_id}}">
{{c.run_id}}</a></td><td>{{c.segmento}}</td><td>{{c.inicio_utc}}</td>
<td class="mono">{{(c.git.commit or '')[:10]}}</td><td>{{c.conteos.eventos if c.conteos}}</td>
<td>{{c.conteos.alertas if c.conteos}}</td></tr>{% endfor %}</table>{% endif %}</div>"""

T_CORRIDA = """<div class="panel"><dl>
<dt>run_id</dt><dd class="mono">{{c.run_id}}</dd><dt>Segmento</dt><dd>{{c.segmento}}</dd>
<dt>Inicio / fin</dt><dd>{{c.inicio_utc}} → {{c.fin_utc}}</dd>
<dt>Commit</dt><dd class="mono">{{c.git.commit}} ({{c.git.rama}}{{', con cambios sin commit' if
c.git.cambios_sin_commit}})</dd>
<dt>Comando</dt><dd class="mono">{{c.comando|join(' ')}}</dd>
<dt>Entorno</dt><dd>{{c.entorno.so}} · Python {{c.entorno.python}} · {{c.entorno.dispositivo}}</dd>
<dt>Modelo</dt><dd class="mono">{{c.model_ref_esperado}}</dd>
<dt>Fuente</dt><dd>{{c.fuente.modo}} · {{c.fuente.manifiesto.url if c.fuente.manifiesto}}
({{c.fuente.manifiesto.licencia if c.fuente.manifiesto}}, {{c.fuente.manifiesto.canal if
c.fuente.manifiesto}})</dd>
<dt>Referencia</dt><dd>{{c.referencia.run_id ~ ' · proporción baja ' ~ '%.4f'|format(
c.referencia.proporcion_baja) if c.referencia else 'ninguna (esta es la corrida de referencia)'}}</dd>
<dt>Conteos</dt><dd class="mono">{{c.conteos|tojson}}</dd></dl>
<p><a href="/eventos?run={{c.run_id}}">Ver eventos</a> · <a href="/alertas?run={{c.run_id}}">Ver alertas</a></p>
</div>
<div class="panel"><h2 style="font-size:16px">Ventanas</h2><table><tr><th>#</th><th>Intervalo (s)</th>
<th>Frames</th><th>Candidatas</th><th>Proporción baja</th><th>Estado</th><th>Reglas</th>
<th>Alertas activas</th></tr>{% for v in ventanas %}<tr><td>{{v.indice}}</td>
<td>[{{v.inicio_ms/1000}}, {{v.fin_ms/1000}})</td><td>{{v.n_frames}}</td><td>{{v.n_candidatas}}</td>
<td>{{'%.3f'|format(v.proporcion_baja) if v.proporcion_baja is not none else '—'}}</td>
<td>{{v.estado}}</td><td>{% for k, r in v.reglas.items() %}{{k}}: {{r.resultado}}<br>{% endfor %}</td>
<td>{{v.alertas_activas}}</td></tr>{% else %}<tr><td colspan="8" class="vacio">Sin ventanas.</td></tr>
{% endfor %}</table></div>
{% if metricas %}<div class="panel"><h2 style="font-size:16px">Métricas base</h2><table>
<tr><th>Grupo</th><th>Métrica</th><th>Valor (corrida)</th><th>Unidad</th><th>n</th></tr>
{% for g, m in metricas.metricas.items() %}<tr><td>{{g}}</td><td>{{m.nombre}}</td>
<td>{{m.corrida.valor if m.corrida.valor is not none else '— (sin datos)'}}</td><td>{{m.unidad}}</td>
<td>{{m.corrida.n}}</td></tr>{% endfor %}</table></div>{% endif %}
<div class="panel" id="config"><h2 style="font-size:16px">Configuración efectiva
<span class="mono">{{c.config_ref}}</span></h2><pre>{{ c.config_efectiva|tojson(indent=1) }}</pre></div>"""


def crear_app(db: Path) -> Flask:
    app = Flask(__name__)
    db = Path(db)

    def pagina(titulo: str, plantilla: str, codigo: int = 200, **ctx: Any):
        cuerpo = render_template_string(plantilla, zona=_zona, **ctx)
        return render_template_string(BASE, titulo=titulo, cuerpo=cuerpo), codigo

    def abrir() -> Almacen:
        return Almacen(db, solo_lectura=True)

    @app.errorhandler(FileNotFoundError)
    @app.errorhandler(sqlite3.Error)
    def sin_base(exc):
        msg = (
            f"<div class='panel err'><p>No se pudo leer la base <code>{db}</code> ({type(exc).__name__}).</p>"
            "<p>Créala con <code>python -m monitor importar &lt;carpetas de corridas&gt;</code> o "
            "corre un escenario con <code>python -m monitor correr …</code>.</p></div>"
        )
        return pagina("Base no disponible", msg, 503)

    @app.errorhandler(404)
    def no_encontrado(exc):
        return pagina(
            "No encontrado",
            "<div class='panel err'><p>{{ m }}</p>"
            "<p><a href='/eventos'>Volver a eventos</a></p></div>",
            404,
            m=getattr(exc, "description", "No existe."),
        )

    @app.get("/")
    def inicio():
        return eventos()

    @app.get("/eventos")
    def eventos():
        f = {k: request.args.get(k, "") for k in ("run", "zona", "status")}
        try:
            num = max(1, int(request.args.get("pagina", "1")))
        except ValueError:
            num = 1
        alm = abrir()
        try:
            lista, total = alm.eventos(
                run_id=f["run"] or None,
                zona=f["zona"] or None,
                status=f["status"] or None,
                limite=POR_PAGINA,
                desplazamiento=(num - 1) * POR_PAGINA,
            )
            corridas = alm.corridas()
        finally:
            alm.con.close()
        qs = "&".join(f"{k}={v}" for k, v in f.items() if v)
        return pagina(
            "Eventos",
            T_EVENTOS,
            eventos=lista,
            total=total,
            pagina=num,
            paginas=max(1, -(-total // POR_PAGINA)),
            corridas=corridas,
            f=f,
            qs=qs,
        )

    @app.get("/eventos/<event_id>")
    def evento(event_id: str):
        alm = abrir()
        try:
            e = alm.evento(event_id)
            if e is None:
                abort(404, f"No existe el evento {event_id}.")
            captura = alm.captura_de_evento(event_id)
            alertas = alm.alertas_de_evento(event_id)
            ventana = alm.ventana_de_evento(e)
            run = alm.corrida(e["run_id"]) or {}
        finally:
            alm.con.close()
        umbrales = run.get("config_efectiva", {}).get("umbrales", {})
        return pagina(
            f"Evento {e['frame_id']}",
            T_EVENTO,
            e=e,
            captura=captura,
            alertas=alertas,
            ventana=ventana,
            umbrales=umbrales,
        )

    @app.get("/alertas")
    def alertas():
        f = {k: request.args.get(k, "") for k in ("run", "severidad")}
        alm = abrir()
        try:
            lista = alm.alertas(run_id=f["run"] or None, severidad=f["severidad"] or None)
            corridas = alm.corridas()
        finally:
            alm.con.close()
        return pagina("Alertas", T_ALERTAS, alertas=lista, corridas=corridas, f=f)

    @app.get("/alertas/<alert_id>")
    def alerta(alert_id: str):
        alm = abrir()
        try:
            a = alm.alerta(alert_id)
            if a is None:
                abort(404, f"No existe la alerta {alert_id}.")
            evs = [e for e in (alm.evento(i) for i in a["event_ids"]) if e]
        finally:
            alm.con.close()
        return pagina(f"Alerta {a['rule_id']}", T_ALERTA, a=a, eventos=evs)

    @app.get("/corridas")
    def corridas():
        alm = abrir()
        try:
            lista = alm.corridas()
        finally:
            alm.con.close()
        return pagina("Corridas", T_CORRIDAS, corridas=lista)

    @app.get("/corridas/<run_id>")
    def corrida(run_id: str):
        alm = abrir()
        try:
            c = alm.corrida(run_id)
            if c is None:
                abort(404, f"No existe la corrida {run_id}.")
            ventanas = alm.ventanas(run_id)
        finally:
            alm.con.close()
        ruta_m = Path(c["_dir"]) / "metricas.json"
        metricas = json.loads(ruta_m.read_text(encoding="utf-8")) if ruta_m.is_file() else None
        return pagina(f"Corrida {run_id}", T_CORRIDA, c=c, ventanas=ventanas, metricas=metricas)

    @app.get("/imagenes/<image_id>")
    def imagen(image_id: str):
        alm = abrir()
        try:
            cap = alm.captura(image_id)
            run = alm.corrida(cap["run_id"]) if cap else None
        finally:
            alm.con.close()
        if cap is None or run is None:
            abort(404, f"No existe la captura {image_id}.")
        base = Path(run["_dir"]).resolve()
        archivo = (base / cap["ruta"]).resolve()
        if not archivo.is_relative_to(base) or not archivo.is_file():
            abort(
                404, f"La captura {image_id} está registrada pero falta su archivo {cap['ruta']}."
            )
        return send_file(archivo, mimetype="image/jpeg", max_age=3600)

    return app
