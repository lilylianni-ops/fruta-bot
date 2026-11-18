import os, hmac, html
from urllib.parse import urlparse
from flask import Flask, request, redirect, Response
from store import *
import core, story

app = Flask(__name__)
LABEL = {"waiting_clips": "Esperando clips", "assembling": "Armando", "waiting_approval": "Por aprobar",
         "approved": "En cola de subida", "uploaded": "Subido", "rejected": "Descartado", "error": "Error"}


@app.before_request
def guard():
    pw = os.getenv("PANEL_PASSWORD")
    if pw:
        a = request.authorization
        if not (a and hmac.compare_digest(a.password or "", pw)):
            return Response("Acceso restringido", 401, {"WWW-Authenticate": 'Basic realm="panel"'})
    if request.method == "POST":
        o = request.headers.get("Origin")
        if o and urlparse(o).netloc != request.host:
            return Response("Origen no permitido", 403)


@app.post("/do/<action>")
def do(action):
    n = request.form.get("n", type=int)
    if action == "generate":
        core.generate()
    elif action == "pause":
        s = state(); s["paused"] = not s["paused"]; save_state(s)
    elif action == "approve" and n:
        core.approve(n)
    elif action == "reject" and n:
        core.reject(n)
    elif action == "trends":
        story.refresh_trends()
    return redirect("/")


def btn(action, label, n=None):
    f = f'<input type="hidden" name="n" value="{n}">' if n else ""
    return f'<form method="post" action="/do/{action}">{f}<button>{label}</button></form>'


@app.get("/")
def home():
    s, c, eps = state(), cfg(), ep_list()
    up = s["uploads"].get(today(), 0)
    rows = ""
    for e in reversed(eps):
        st = e["status"]
        act = ""
        if st == "waiting_approval":
            act = btn("approve", "Aprobar", e["n"]) + btn("reject", "Descartar", e["n"])
        elif st == "error":
            act = btn("approve", "Reintentar", e["n"])
        extra = ""
        if st == "waiting_clips":
            ps = "\n\n".join(f"CLIP {i}\n{p}" for i, p in enumerate(e["clips"], 1))
            extra = (f'<details><summary>Prompts de los clips</summary><p class="hint">Suelta los clips en '
                     f'data/episodes/ep{e["n"]:03d}/clips/</p><textarea readonly rows="8">{html.escape(ps)}</textarea></details>')
        if st == "uploaded":
            extra = f'<p class="hint"><a href="https://youtu.be/{html.escape(e.get("youtube_id", ""))}">Ver en YouTube</a></p>'
        if st == "error":
            extra = f'<p class="hint err">{html.escape(e.get("error", ""))}</p>'
        rows += (f'<li class="ep"><div class="top"><b>{e["n"]}. {html.escape(e["title"])}</b>'
                 f'<span class="tag {st}">{LABEL.get(st, st)}</span></div>'
                 f'<p class="hint">{html.escape(e["summary"])}</p>{extra}<div class="acts">{act}</div></li>')
    if not rows:
        rows = '<li class="ep"><p class="hint">Todavía no hay episodios. Toca «Generar episodio».</p></li>'
    page = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="60">
<title>{html.escape(c.get('channel_name',''))}</title><style>
:root{{--bg:#f6f7f4;--ink:#17211f;--mut:#5d6b67;--line:#dde2dc;--card:#fff;--mango:#f2a01e;--ok:#1f8a5b;--bad:#c0392b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121816;--ink:#eef2ef;--mut:#9aa8a3;--line:#2a3531;--card:#1a2320}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:720px;margin:0 auto;padding:20px 16px 60px}}
h1{{font-size:24px;margin:0}}h2{{font-size:17px;margin:28px 0 8px}}
.bar{{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}}
.pill{{padding:4px 12px;border-radius:99px;font-size:13px;background:var(--mango);color:#2b1c00}}
.pill.on{{background:var(--ok);color:#fff}}
.nums{{display:flex;gap:24px;margin:16px 0;flex-wrap:wrap}}.nums div{{min-width:90px}}
.nums b{{display:block;font-size:26px}}.nums span,.hint{{color:var(--mut);font-size:14px;margin:4px 0}}
ul{{list-style:none;padding:0;margin:0}}.ep{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:10px}}
.top{{display:flex;justify-content:space-between;gap:8px;align-items:baseline}}
.tag{{font-size:12px;padding:2px 8px;border-radius:6px;border:1px solid var(--line);white-space:nowrap}}
.tag.uploaded{{color:var(--ok);border-color:var(--ok)}}.tag.error{{color:var(--bad);border-color:var(--bad)}}.tag.waiting_approval{{color:#a06800;border-color:var(--mango)}}
.err{{color:var(--bad)}}.acts{{display:flex;gap:8px;flex-wrap:wrap}}.acts form{{margin:6px 0 0}}
button{{font:inherit;font-size:14px;padding:8px 14px;min-height:40px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}}
button:hover{{border-color:var(--mango)}}button:focus-visible,summary:focus-visible{{outline:2px solid var(--mango);outline-offset:2px}}
.tools{{display:flex;gap:8px;flex-wrap:wrap}}.tools form{{margin:0}}
textarea{{width:100%;font:13px/1.4 ui-monospace,monospace;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px}}
details{{margin-top:8px}}summary{{cursor:pointer;font-size:14px}}pre{{white-space:pre-wrap;font:inherit;color:var(--mut);font-size:14px}}
</style></head><body><main>
<div class="bar"><h1>{html.escape(c.get('channel_name',''))}</h1><span class="pill {'' if s['paused'] else 'on'}">{'En pausa' if s['paused'] else 'Activo'}</span></div>
<div class="nums"><div><b>{len(eps)}</b><span>episodios</span></div>
<div><b>{up}/{c.get('daily_upload_cap')}</b><span>subidos hoy</span></div>
<div><b>{sum(1 for e in eps if e['status']=='waiting_clips')}</b><span>esperando clips</span></div>
<div><b>{c.get('upload_privacy')}</b><span>privacidad al subir</span></div></div>
<div class="tools">{btn('generate','Generar episodio')}{btn('trends','Actualizar tendencias')}{btn('pause','Pausar o seguir')}</div>
<h2>Episodios</h2><ul>{rows}</ul>
<h2>Tendencias de hoy</h2><details><summary>Ver resumen</summary><pre>{html.escape(story.trends_text())}</pre></details>
</main></body></html>"""
    return page


if __name__ == "__main__":
    app.run(host=os.getenv("PANEL_HOST", "127.0.0.1"), port=int(os.getenv("PANEL_PORT", "5000")))
