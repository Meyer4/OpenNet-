"""OpenNet - a small multi-app shell (Flask).

Runs locally with ``python app.py`` or in production with
``gunicorn app:app``.  Every route advertised by the home screen is
implemented; see ``tests/test_app.py`` for the contract.
"""

import difflib
import os
import re
from functools import lru_cache

import jinja2
from flask import Flask, jsonify, render_template, render_template_string, request
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "opennet-dev-secret")

# Base URL the site is served from. Flask serves from "/", GitHub Pages serves a
# project site from "/<repo>/". Always ends with a slash.
BASE_URL = os.environ.get("BASE_URL", "/")
if not BASE_URL.endswith("/"):
    BASE_URL += "/"

# A static build writes each page to <route>/index.html, so links need a
# trailing slash for the directory index to resolve.
STATIC_BUILD = os.environ.get("OPENNET_STATIC", "0") == "1"


def site_url(path):
    """Build a link that works from BASE_URL on both Flask and GitHub Pages.

    A static build writes pages to <route>/index.html, so page links need a
    trailing slash - but real files (anything with an extension) must not get
    one, or the asset request 404s.
    """
    if path == "/":
        return BASE_URL
    clean = path.strip("/")
    last = clean.rsplit("/", 1)[-1]
    if STATIC_BUILD and "." not in last:
        clean += "/"
    return BASE_URL + clean

# Where OpenBot looks for documents.  Defaults to the ``docs`` folder that
# ships with the repo so the assistant works out of the box on any host.
DOCS_DIR = os.environ.get("OPENBOT_DOCS_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "docs"
)

# Platforms shown on the home screen and on /explore.
platforms = [
    {"name": "OpenBot", "route": "/openbot", "icon": "🤖",
     "blurb": "Chat assistant that answers from your documents."},
    {"name": "E-Book", "route": "/ebook", "icon": "📖",
     "blurb": "Read and manage your e-books."},
    {"name": "AppBox", "route": "/appbox", "icon": "📦",
     "blurb": "Your toolbox of small utilities."},
    {"name": "MyFace", "route": "/myface", "icon": "🙂",
     "blurb": "Your profile and avatar."},
    {"name": "MyVids", "route": "/myvids", "icon": "🎬",
     "blurb": "Watch and organise your videos."},
    {"name": "Piggy Bank", "route": "/piggybank", "icon": "🐷",
     "blurb": "Track savings and spending."},
    {"name": "SnapStyle", "route": "/snapstyle", "icon": "📸",
     "blurb": "Photos, filters and galleries."},
]


# --------------------------------------------------------------------------
# Shared shell (styles + chrome) for every non-OpenBot page
# --------------------------------------------------------------------------
SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}OpenNet{% endblock %}</title>
<style>
  :root { --bg:#111; --panel:#222; --fg:#fff; --muted:#9aa; --accent:#57cc99; }
  html[data-theme="light"] { --bg:#f4f6f8; --panel:#fff; --fg:#1b1f24; --muted:#5b6672; --accent:#2f9e6e; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         background:var(--bg); color:var(--fg); text-align:center; min-height:100vh; }
  a { color:inherit; }
  main { max-width: 720px; margin: 0 auto; padding: 24px 16px 110px; }
  h1, h2 { font-weight: 600; }
  .sub { color: var(--muted); font-size: .95rem; margin: 6px 0 0; }
  .app-list { display:flex; flex-wrap:wrap; justify-content:center; gap:15px; margin-top:24px; }
  .app { background:var(--panel); padding:14px 10px; border-radius:12px; width:120px;
         border:1px solid rgba(127,127,127,.25); transition: transform .15s ease; }
  .app:hover { transform: translateY(-3px); }
  .app a { color:var(--fg); text-decoration:none; display:block; }
  .app .icon { font-size: 28px; display:block; margin-bottom:6px; }
  .app .name { font-size: 14px; }
  form.search { display:flex; gap:8px; justify-content:center; margin-top:16px; }
  form.search input { padding:10px 14px; border-radius:8px; border:1px solid rgba(127,127,127,.4);
                      background:var(--panel); color:var(--fg); width:min(70%, 340px); }
  form.search button { padding:10px 18px; border-radius:8px; border:none;
                       background:var(--accent); color:#06281a; font-weight:600; cursor:pointer; }
  .empty { color: var(--muted); margin-top: 28px; }
  .bottom-nav { position:fixed; bottom:0; left:0; width:100%; display:flex;
                background:var(--panel); padding:12px 0; border-top:1px solid rgba(127,127,127,.3); }
  .nav-item { flex:1; font-size:14px; }
  .nav-item a { color:var(--fg); text-decoration:none; opacity:.65; }
  .nav-item a.active { opacity:1; font-weight:600; color:var(--accent); }
  .card { background:var(--panel); border:1px solid rgba(127,127,127,.25);
          border-radius:12px; padding:18px; text-align:left; margin:14px 0; }
  .card h3 { margin:0 0 6px; font-size:1.05rem; }
  .card p { margin:0; color:var(--muted); font-size:.92rem; }
  .badge { display:inline-block; font-size:11px; padding:2px 8px; border-radius:999px;
           background:rgba(87,204,153,.18); color:var(--accent); margin-left:8px; }
  .back { display:inline-block; margin-bottom:18px; color:var(--accent); text-decoration:none; }
</style>
</head>
<body>
<main>
{% block body %}{% endblock %}
</main>
<div class="bottom-nav">
  <div class="nav-item"><a href="{{ u('/') }}" class="{{ 'active' if active == 'home' }}">Home</a></div>
  <div class="nav-item"><a href="{{ u('/explore') }}" class="{{ 'active' if active == 'explore' }}">Explore</a></div>
  <div class="nav-item"><a href="{{ u('/settings') }}" class="{{ 'active' if active == 'settings' }}">Settings</a></div>
</div>
<script>
  // Theme preference is stored locally and applied before paint on every page.
  try {
    var t = localStorage.getItem('opennet-theme');
    if (t) document.documentElement.setAttribute('data-theme', t);
  } catch (e) {}
</script>
</body>
</html>
"""

HOME_TEMPLATE = (
    "{% extends 'shell' %}"
    "{% block title %}OpenNet{% endblock %}"
    "{% block body %}"
    "<h1>OpenNet</h1>"
    "<p class='sub'>Seven apps, one shell.</p>"
    "<form class='search' action='{{ u('/') }}' method='get'>"
    "  <input name='search' value='{{ query }}' placeholder='Search apps' aria-label='Search apps'>"
    "  <button type='submit'>Go</button>"
    "</form>"
    "<div class='app-list' id='app-list'>"
    "{% for p in matched %}"
    "  <div class='app' data-name='{{ p.name|lower }}'><a href='{{ u(p.route) }}'>"
    "    <span class='icon' aria-hidden='true'>{{ p.icon }}</span>"
    "    <span class='name'>{{ p.name }}</span>"
    "  </a></div>"
    "{% endfor %}"
    "</div>"
    "<p class='empty' id='no-match'{% if matched %} hidden{% endif %}>"
    "No apps match &ldquo;<span id='no-match-q'>{{ query }}</span>&rdquo;.</p>"
    "{% if static_build %}"
    # A static site cannot filter server-side, so the query is applied here.
    "<script>"
    "(function(){var q=new URLSearchParams(location.search).get('search')||'';"
    "var n=q.trim().toLowerCase();"
    "var shown=0;"
    "document.querySelectorAll('#app-list .app').forEach(function(el){"
    "  var hit=!n||el.dataset.name.indexOf(n)>-1;"
    "  el.style.display=hit?'':'none';if(hit){shown++;}});"
    "var msg=document.getElementById('no-match');"
    "document.getElementById('no-match-q').textContent=q;"
    "if(msg){msg.hidden=shown>0;}"
    "})();"
    "</script>"
    "{% endif %}"
    "{% endblock %}"
)

EXPLORE_TEMPLATE = (
    "{% extends 'shell' %}"
    "{% block title %}Explore &middot; OpenNet{% endblock %}"
    "{% block body %}"
    "<h1>Explore</h1>"
    "<p class='sub'>Everything installed on this device.</p>"
    "{% for p in platforms %}"
    "<a href='{{ u(p.route) }}' style='text-decoration:none'>"
    "  <div class='card'><h3>{{ p.icon }} {{ p.name }}"
    "    <span class='badge'>{{ p.route }}</span></h3>"
    "    <p>{{ p.blurb }}</p></div>"
    "</a>"
    "{% endfor %}"
    "{% endblock %}"
)

SETTINGS_TEMPLATE = (
    "{% extends 'shell' %}"
    "{% block title %}Settings &middot; OpenNet{% endblock %}"
    "{% block body %}"
    "<h1>Settings</h1>"
    "<div class='card'><h3>Appearance</h3>"
    "  <p>Choose how the shell looks. The choice is saved in this browser.</p>"
    "  <p style='margin-top:12px'>"
    "    <button id='theme-dark' type='button' class='theme-btn'>Dark</button> "
    "    <button id='theme-light' type='button' class='theme-btn'>Light</button>"
    "  </p>"
    "</div>"
    "<div class='card'><h3>OpenBot documents</h3>"
    "  <p>OpenBot answers from the folder: <code>{{ docs_dir }}</code></p>"
    "  <p>Change it by setting the <code>OPENBOT_DOCS_DIR</code> environment variable.</p>"
    "</div>"
    "<div class='card'><h3>About</h3>"
    "  <p>OpenNet {{ version }} &middot; {{ platform_count }} apps installed.</p>"
    "</div>"
    "<script>"
    "document.querySelectorAll('.theme-btn').forEach(function(b){b.style.cssText="
    "'padding:8px 16px;border-radius:8px;border:1px solid rgba(127,127,127,.4);"
    "background:var(--panel);color:var(--fg);cursor:pointer'});"
    "function setTheme(t){document.documentElement.setAttribute('data-theme',t);"
    "try{localStorage.setItem('opennet-theme',t)}catch(e){}}"
    "document.getElementById('theme-dark').onclick=function(){setTheme('dark')};"
    "document.getElementById('theme-light').onclick=function(){setTheme('light')};"
    "</script>"
    "{% endblock %}"
)

APP_TEMPLATE = (
    "{% extends 'shell' %}"
    "{% block title %}{{ name }} &middot; OpenNet{% endblock %}"
    "{% block body %}"
    "<a class='back' href='{{ u('/') }}'>&larr; Home</a>"
    "<h1>{{ icon }} {{ name }}</h1>"
    "<p class='sub'>{{ blurb }}</p>"
    "<div class='card'><h3>Coming soon</h3>"
    "  <p>This app is a placeholder. The route is wired up and reachable from "
    "the home screen &mdash; drop your implementation into <code>{{ route }}</code> "
    "in <code>app.py</code>.</p></div>"
    "{% endblock %}"
)

# Register SHELL as a base template that inline templates can "extend".
app.jinja_env.loader = jinja2.ChoiceLoader([
    jinja2.DictLoader({"shell": SHELL}),
    app.jinja_env.loader,
])

app.jinja_env.globals["u"] = site_url
app.jinja_env.globals["static_build"] = STATIC_BUILD
app.jinja_env.globals["base_url"] = BASE_URL

VERSION = "1.0.0"


# --------------------------------------------------------------------------
# OpenBot document retrieval
# --------------------------------------------------------------------------
def _read_pdf(path):
    """Extract text from a PDF, tolerating a missing PDF library."""
    try:
        from pypdf import PdfReader  # modern name
    except ImportError:  # pragma: no cover - depends on environment
        try:
            from PyPDF2 import PdfReader  # legacy name
        except ImportError:
            return ""
    try:
        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # noqa: BLE001 - a corrupt PDF must not 500 the API,
        # and the underlying error type differs between pypdf and PyPDF2.
        return ""


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    except OSError:
        return ""


def _docs_signature():
    """Cheap signature of the docs folder so the text cache invalidates on change."""
    if not os.path.isdir(DOCS_DIR):
        return ("missing", ())
    entries = []
    for root, _dirs, files in os.walk(DOCS_DIR):
        for name in files:
            full = os.path.join(root, name)
            try:
                entries.append((full, os.path.getmtime(full), os.path.getsize(full)))
            except OSError:
                continue
    return (DOCS_DIR, tuple(sorted(entries)))


@lru_cache(maxsize=1)
def _load_documents(signature):
    """Return a list of {name, path, text} for every readable document.

    ``signature`` is part of the cache key, so the parsed text is reused until
    the folder actually changes.
    """
    del signature  # only used as a cache key
    docs = []
    if not os.path.isdir(DOCS_DIR):
        return docs
    for root, _dirs, files in os.walk(DOCS_DIR):
        for name in sorted(files):
            full = os.path.join(root, name)
            lowered = name.lower()
            if lowered.endswith(".pdf"):
                text = _read_pdf(full)
            elif lowered.endswith((".txt", ".md", ".markdown", ".rst", ".csv", ".json")):
                text = _read_text(full)
            else:
                continue
            docs.append({"name": name, "path": full, "text": text or ""})
    return docs


def load_documents():
    return _load_documents(_docs_signature())


def _chunks(text, size=700, overlap=120):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    step = max(size - overlap, 1)
    return [text[i:i + size].strip() for i in range(0, len(text), step) if text[i:i + size].strip()]


_WORD = re.compile(r"[a-z0-9']+")


def _tokens(text):
    return set(_WORD.findall(text.lower()))


def _score_chunk(chunk_tokens, query_tokens):
    if not query_tokens:
        return 0.0
    hits = chunk_tokens & query_tokens
    if not hits:
        return 0.0
    # Coverage of the query matters more than raw hit count.
    return len(hits) / len(query_tokens)


def search_documents(query, top_k=3):
    """Rank document chunks against the query. Returns a list of matches."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    results = []
    for doc in load_documents():
        name_ratio = difflib.SequenceMatcher(
            None, doc["name"].lower(), query.lower()
        ).ratio()
        if name_ratio > 0.55:
            results.append({
                "name": doc["name"],
                "score": round(name_ratio, 3),
                "snippet": "The document title matches your question.",
                "kind": "title",
            })

        best = (0.0, "")
        for chunk in _chunks(doc["text"]):
            score = _score_chunk(_tokens(chunk), query_tokens)
            if score > best[0]:
                best = (score, chunk)
        if best[0] > 0:
            snippet = best[1]
            if len(snippet) > 340:
                snippet = snippet[:340].rsplit(" ", 1)[0] + "..."
            results.append({
                "name": doc["name"],
                "score": round(best[0], 3),
                "snippet": snippet,
                "kind": "content",
            })

    results.sort(key=lambda item: item["score"], reverse=True)

    # A document can match by title and by content; keep only its best entry.
    best_by_name = {}
    for item in results:
        if item["name"] not in best_by_name:
            best_by_name[item["name"]] = item

    return list(best_by_name.values())[:top_k]


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def home():
    query = (request.args.get("search") or "").strip()
    needle = query.lower()
    matched = [p for p in platforms if needle in p["name"].lower()] if needle else platforms
    return render_template_string(
        HOME_TEMPLATE, matched=matched, query=query, active="home"
    )


@app.route("/explore")
def explore():
    return render_template_string(
        EXPLORE_TEMPLATE, platforms=platforms, active="explore"
    )


@app.route("/settings")
def settings():
    return render_template_string(
        SETTINGS_TEMPLATE,
        docs_dir=DOCS_DIR,
        version=VERSION,
        platform_count=len(platforms),
        active="settings",
    )


@app.route("/healthz")
def healthz():
    """Liveness probe used by hosting platforms."""
    return jsonify({"status": "ok", "version": VERSION, "apps": len(platforms)})


# --- OpenBot ---------------------------------------------------------------
@app.route("/openbot")
def openbot_ui():
    return render_template("openbot.html")


@app.route("/openbot/api", methods=["POST"])
def openbot_api():
    """Answer a question from the documents in DOCS_DIR.

    Bad input is a 400 with an explanation - never a 500.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": 'Expected a JSON body like {"question": "..."}'}), 400

    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Please include a non-empty 'question'."}), 400

    matches = search_documents(question)
    if not matches:
        return jsonify({
            "answer": "I couldn't find anything about that in your documents.",
            "source": None,
            "matches": [],
        })

    top = matches[0]
    if top["kind"] == "title":
        answer = "There is a document called \u201c{}\u201d that looks relevant.".format(top["name"])
    else:
        answer = top["snippet"]

    return jsonify({"answer": answer, "source": top["name"], "matches": matches})


# --- Placeholder apps ------------------------------------------------------
PLACEHOLDER_APPS = {
    "/ebook": ("E-Book", "\U0001f4d6", "Read and manage your e-books."),
    "/appbox": ("AppBox", "\U0001f4e6", "Your toolbox of small utilities."),
    "/myface": ("MyFace", "\U0001f642", "Your profile and avatar."),
    "/myvids": ("MyVids", "\U0001f3ac", "Watch and organise your videos."),
    "/piggybank": ("Piggy Bank", "\U0001f437", "Track savings and spending."),
    "/snapstyle": ("SnapStyle", "\U0001f4f8", "Photos, filters and galleries."),
}


def _make_app_page(route, name, icon, blurb):
    def view():
        return render_template_string(
            APP_TEMPLATE, name=name, icon=icon, blurb=blurb, route=route, active="home"
        )
    view.__name__ = "app_" + route.strip("/").replace("-", "_")
    view.__doc__ = f"Placeholder page for {name}."
    return view


for _route, (_name, _icon, _blurb) in PLACEHOLDER_APPS.items():
    app.add_url_rule(_route, view_func=_make_app_page(_route, _name, _icon, _blurb))


# --------------------------------------------------------------------------
# Error handling - JSON for the API, a real page everywhere else
# --------------------------------------------------------------------------
def _error_page(code, description):
    if request.path.startswith("/openbot/api"):
        return jsonify({"error": description}), code
    return render_template_string(
        APP_TEMPLATE, name=f"Error {code}", icon="\u26a0\ufe0f",
        blurb=description, route=request.path, active="home"
    ), code


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/openbot/api"):
        return jsonify({"error": "Not found"}), 404
    return render_template_string(
        APP_TEMPLATE, name="Not found", icon="\U0001f9ed",
        blurb="That page does not exist.", route=request.path, active="home"
    ), 404


@app.errorhandler(HTTPException)
def http_error(error):
    return _error_page(error.code, error.description)


@app.errorhandler(Exception)
def unhandled(error):  # pragma: no cover - safety net
    app.logger.exception("Unhandled error on %s", request.path)
    return _error_page(500, "The server hit an unexpected error.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
