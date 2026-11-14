"""Painel web para usar o bot pelo celular.  Uso:  python -m fbbot painel"""

from __future__ import annotations

import hmac
import os
import secrets
import tempfile
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, redirect, render_template_string, request, session, url_for

from .config import Config
from .graph import GraphClient, GraphError

BASE = """<!doctype html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#1877f2">
<title>Meu Bot</title>
<style>
:root{--bg:#f0f2f5;--card:#fff;--txt:#1c1e21;--muted:#65676b;--brand:#1877f2;--ok:#e7f6ec;--err:#fdecea;--line:#dddfe2}
@media (prefers-color-scheme:dark){:root{--bg:#18191a;--card:#242526;--txt:#e4e6eb;--muted:#b0b3b8;--line:#3a3b3c;--ok:#1e3a28;--err:#4a1f1f}}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--txt)}
header{background:var(--brand);color:#fff;padding:14px 16px;font-weight:700;font-size:18px;display:flex;justify-content:space-between;align-items:center}
header a{color:#fff;font-weight:400;font-size:14px}
main{max-width:560px;margin:0 auto;padding:16px}
.card{background:var(--card);border-radius:12px;padding:16px;margin-bottom:16px;box-shadow:0 1px 2px rgba(0,0,0,.15)}
h2{font-size:17px;margin:0 0 12px}
label{display:block;font-size:14px;color:var(--muted);margin:12px 0 4px}
input,textarea,select,button{width:100%;font:inherit;font-size:16px;padding:12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--txt)}
textarea{min-height:90px;resize:vertical}
button{background:var(--brand);color:#fff;border:0;font-weight:700;margin-top:16px}
button:disabled{opacity:.6}
.msg{padding:12px;border-radius:8px;margin-bottom:16px;word-break:break-word}.ok{background:var(--ok)}.err{background:var(--err)}
.reel{padding:10px 0;border-top:1px solid var(--line);font-size:14px}.reel:first-of-type{border-top:0}
.small{font-size:13px;color:var(--muted)}a{color:var(--brand)}
</style></head><body>
<header>📱 Meu Bot{% if session.get('ok') %}<a href="{{ url_for('logout') }}">Sair</a>{% endif %}</header>
<main>{% for kind, text in msgs %}<div class="msg {{ kind }}">{{ text|safe }}</div>{% endfor %}{{ body|safe }}</main>
<script>
document.querySelectorAll('form[data-busy]').forEach(f=>f.addEventListener('submit',()=>{
  const b=f.querySelector('button');b.disabled=true;b.textContent=f.dataset.busy;}));
</script></body></html>"""

LOGIN = """<div class="card"><h2>Entrar</h2><form method="post">
<label>Senha do painel</label><input type="password" name="senha" autofocus required>
<button>Entrar</button></form></div>"""

HOME = """
<div class="card"><h2>🎬 Novo Reel</h2>
<form method="post" action="{{ url_for('reel') }}" enctype="multipart/form-data" data-busy="Enviando… não feche a tela">
{% if pages|length > 1 %}<label>Página</label><select name="page">
{% for p in pages %}<option value="{{ p.id }}" {% if p.id == page.id %}selected{% endif %}>{{ p.name }}</option>{% endfor %}
</select>{% else %}<input type="hidden" name="page" value="{{ page.id }}"><p class="small">Página: <b>{{ page.name }}</b></p>{% endif %}
<label>Vídeo (vertical, 3 a 90 s)</label><input type="file" name="video" accept="video/*" required>
<label>Legenda</label><textarea name="descricao" placeholder="Escreva a legenda… #hashtags"></textarea>
<label>Agendar (opcional)</label><input type="datetime-local" name="agendar">
<button>Publicar Reel</button></form></div>

<div class="card"><h2>✍️ Post de texto</h2>
<form method="post" action="{{ url_for('post') }}" data-busy="Publicando…">
<input type="hidden" name="page" value="{{ page.id }}">
<textarea name="mensagem" required placeholder="No que você está pensando?"></textarea>
<label>Link (opcional)</label><input type="url" name="link" placeholder="https://">
<button>Publicar post</button></form></div>

<div class="card"><h2>📋 Últimos Reels de {{ page.name }}</h2>
{% for r in reels %}<div class="reel">{{ (r.description or '(sem legenda)')[:120] }}<br>
<span class="small">{{ r.created_time[:16].replace('T',' ') if r.created_time }}</span>
{% if r.permalink_url %} · <a href="{{ r.permalink_url if r.permalink_url.startswith('http') else 'https://www.facebook.com' ~ r.permalink_url }}" target="_blank">abrir</a>{% endif %}
· <a href="{{ url_for('status', page=page.id, video_id=r.id) }}">status</a></div>
{% else %}<p class="small">Nenhum Reel ainda.</p>{% endfor %}</div>
"""


def create_app(cfg: Config | None = None, client: GraphClient | None = None) -> Flask:
    cfg = cfg or Config.from_env()
    app = Flask(__name__)
    app.secret_key = os.getenv("PANEL_SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB
    password = os.getenv("PANEL_PASSWORD", "")
    api = client or GraphClient(cfg.user_token, cfg.api_version)

    def render(body: str, msgs=(), **ctx):
        return render_template_string(BASE, body=render_template_string(body, **ctx), msgs=msgs)

    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if password and not session.get("ok"):
                return redirect(url_for("login"))
            return fn(*a, **kw)
        return wrapper

    def get_page(page_id: str | None):
        pages = api.list_pages()
        if not pages:
            raise GraphError("Nenhuma página encontrada para este token.")
        wanted = page_id or cfg.default_page_id
        page = next((p for p in pages if p.id == wanted), pages[0])
        return pages, page

    def home(msgs=(), page_id=None):
        try:
            pages, page = get_page(page_id)
            reels = api.list_reels(page)
        except GraphError as e:
            return render("", msgs=[*msgs, ("err", f"Erro: {e}")])
        return render(HOME, msgs=msgs, pages=pages, page=page, reels=reels)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if hmac.compare_digest(request.form.get("senha", ""), password):
                session["ok"] = True
                session.permanent = True
                return redirect(url_for("index"))
            return render(LOGIN, msgs=[("err", "Senha incorreta")])
        return render(LOGIN)

    @app.route("/sair")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def index():
        return home(page_id=request.args.get("page"))

    @app.post("/reel")
    @login_required
    def reel():
        f = request.files.get("video")
        page_id = request.form.get("page")
        if not f or not f.filename:
            return home([("err", "Escolha um vídeo.")], page_id)
        when = request.form.get("agendar") or None
        sched = int(datetime.strptime(when, "%Y-%m-%dT%H:%M").timestamp()) if when else None
        suffix = Path(f.filename).suffix or ".mp4"
        fd, tmp = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            f.save(tmp)
            _, page = get_page(page_id)
            res = api.publish_reel(page, tmp, description=request.form.get("descricao", ""),
                                   scheduled_time=sched, wait=False)
        except GraphError as e:
            return home([("err", f"Não foi possível publicar: {e}")], page_id)
        finally:
            Path(tmp).unlink(missing_ok=True)
        link = url_for("status", page=page.id, video_id=res["video_id"])
        txt = "agendado ✅" if sched else "enviado ✅ O Facebook está processando o vídeo."
        return home([("ok", f'Reel {txt} <a href="{link}">Ver status</a>')], page.id)

    @app.post("/post")
    @login_required
    def post():
        page_id = request.form.get("page")
        try:
            _, page = get_page(page_id)
            api.post_text(page, request.form["mensagem"], request.form.get("link") or None)
        except GraphError as e:
            return home([("err", f"Erro: {e}")], page_id)
        return home([("ok", "Post publicado ✅")], page.id)

    @app.route("/status/<page>/<video_id>")
    @login_required
    def status(page, video_id):
        try:
            _, pg = get_page(page)
            info = api.reel_status(pg, video_id)
        except GraphError as e:
            return home([("err", f"Erro: {e}")], page)
        st = info.get("status", {})
        vs = st.get("video_status", "?")
        phases = " · ".join(f"{k.replace('_phase', '')}: {v.get('status')}"
                            for k, v in st.items() if isinstance(v, dict) and "status" in v)
        kind = "err" if vs == "error" else "ok"
        return home([(kind, f"Status do Reel {video_id}: <b>{vs}</b><br><span class='small'>{phases}</span>")], page)

    return app


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    if host != "127.0.0.1" and not os.getenv("PANEL_PASSWORD"):
        raise SystemExit("Defina PANEL_PASSWORD no .env antes de abrir o painel para a rede.")
    create_app().run(host=host, port=port)
