"""Regression tests for the OpenNet Flask app.

These cover the specific defects that made the app undeployable:
missing routes advertised by the home screen, a 500 from the chat API,
and a chat page that never called that API.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as opennet


@pytest.fixture()
def client():
    opennet.app.config["TESTING"] = True
    with opennet.app.test_client() as test_client:
        yield test_client


# --- routes ---------------------------------------------------------------
ADVERTISED = [p["route"] for p in opennet.platforms]


@pytest.mark.parametrize("path", ADVERTISED)
def test_every_advertised_app_route_resolves(client, path):
    """The home screen links to these; none of them may 404."""
    response = client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"


@pytest.mark.parametrize("path", ["/", "/explore", "/settings", "/healthz"])
def test_shell_routes_resolve(client, path):
    response = client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"


def test_nav_links_are_not_dead(client):
    """The bottom nav on every page links Home / Explore / Settings."""
    home = client.get("/").get_data(as_text=True)
    for target in ('href="/"', 'href="/explore"', 'href="/settings"'):
        assert target in home


def test_healthz_reports_ok(client):
    payload = client.get("/healthz").get_json()
    assert payload["status"] == "ok"
    assert payload["apps"] == len(opennet.platforms)


def test_home_search_filters_apps(client):
    page = client.get("/?search=piggy").get_data(as_text=True)
    assert "Piggy Bank" in page
    assert "SnapStyle" not in page


def test_home_search_reports_no_match(client):
    page = client.get("/?search=zzzzz").get_data(as_text=True)
    assert "No apps match" in page


def test_home_search_preserves_query_in_the_box(client):
    page = client.get("/?search=myvids").get_data(as_text=True)
    assert "value='myvids'" in page, "the search box should keep what you typed"


def test_home_search_escapes_the_query(client):
    """The query is reflected into the page, so it must be HTML-escaped."""
    page = client.get("/?search=<script>alert(1)</script>").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_unknown_route_returns_404_page_not_500(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert b"Not found" in response.data


# --- OpenBot UI -----------------------------------------------------------
def test_openbot_ui_loads_its_script(client):
    html = client.get("/openbot").get_data(as_text=True)
    assert "/static/openbot.js" in html
    assert "/static/openbot.css" in html


def test_openbot_ui_calls_the_real_api(client):
    """Regression: the fetch to /openbot/api used to be commented out."""
    js = client.get("/static/openbot.js").get_data(as_text=True)
    live_calls = [
        line.strip()
        for line in js.splitlines()
        if "fetch(" in line and "openbot/api" in line
    ]
    assert live_calls, "chat UI never calls /openbot/api"
    for line in live_calls:
        assert not line.startswith("//"), f"call is still commented out: {line}"


def test_openbot_page_tells_the_script_where_the_api_is(client):
    html = client.get("/openbot").get_data(as_text=True)
    assert 'apiUrl: "/openbot/api"' in html
    assert "staticBuild: false" in html
    assert "/static/openbot-search.js" in html


def test_openbot_ui_has_a_way_home(client):
    html = client.get("/openbot").get_data(as_text=True)
    assert 'href="/"' in html


# --- OpenBot API ----------------------------------------------------------
def test_openbot_api_answers_from_documents(client):
    """Regression: this endpoint used to raise ModuleNotFoundError and 500."""
    response = client.post(
        "/openbot/api", json={"question": "which apps are installed in OpenNet?"}
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["answer"]
    assert payload["source"], "answer should cite the document it came from"
    assert payload["matches"]


def test_openbot_api_finds_the_openbot_guide(client):
    response = client.post(
        "/openbot/api",
        json={"question": "how does openbot cache parsed documents?"},
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["source"] == "openbot-guide.md"


def test_openbot_api_matches_a_document_by_title(client):
    response = client.post(
        "/openbot/api", json={"question": "getting-started.txt"}
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["source"] == "getting-started.txt"


def test_openbot_api_says_so_when_nothing_matches(client):
    response = client.post(
        "/openbot/api",
        json={"question": "xyzzy plugh frobnicate quasiturbulence"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["matches"] == []
    assert payload["source"] is None


@pytest.mark.parametrize(
    "body, content_type",
    [
        ("not json at all", "application/json"),
        (json.dumps(["a", "list"]), "application/json"),
        (b"", "application/json"),
    ],
    ids=["malformed", "wrong-shape", "empty"],
)
def test_openbot_api_rejects_bad_input_with_400_not_500(client, body, content_type):
    """Regression: malformed input used to raise an unhandled 500."""
    response = client.post("/openbot/api", data=body, content_type=content_type)
    assert response.status_code == 400
    assert response.get_json()["error"]


def test_openbot_api_rejects_empty_question(client):
    response = client.post("/openbot/api", json={"question": "   "})
    assert response.status_code == 400
    assert "question" in response.get_json()["error"]


def test_openbot_api_rejects_get(client):
    response = client.get("/openbot/api")
    assert response.status_code == 405


# --- document retrieval ---------------------------------------------------
def test_docs_folder_ships_with_the_repo():
    assert os.path.isdir(opennet.DOCS_DIR), f"missing docs folder: {opennet.DOCS_DIR}"
    assert opennet.load_documents(), "no documents were loaded"


def test_search_ranks_relevant_document_first():
    matches = opennet.search_documents("how do I deploy opennet with gunicorn")
    assert matches
    # Both documents cover deploying with gunicorn; neither may be beaten by a
    # document that only matches the word "opennet".
    assert matches[0]["name"] in {"deploying.txt", "getting-started.txt"}
    assert matches[0]["score"] > 0.5


def test_stopwords_do_not_drive_the_ranking():
    """Regression: "how do I deploy" tied three documents on the word "how"."""
    assert "how" in opennet.STOPWORDS
    assert opennet._tokens("how do I deploy opennet with gunicorn") == {
        "deploy", "gunicorn", "opennet"
    }
    top = opennet.search_documents("how do I deploy opennet?")[0]
    assert top["name"] == "deploying.txt"
    assert top["score"] == 1.0


def test_search_returns_nothing_for_an_empty_query():
    assert opennet.search_documents("   ") == []


def test_document_cache_picks_up_new_files(tmp_path, monkeypatch):
    """Regression guard: the parsed-text cache must invalidate on change."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "first.txt").write_text("the capital of florin is guilder city")

    monkeypatch.setattr(opennet, "DOCS_DIR", str(docs))
    assert [d["name"] for d in opennet.load_documents()] == ["first.txt"]

    (docs / "second.txt").write_text("a second document appeared")
    names = [d["name"] for d in opennet.load_documents()]
    assert names == ["first.txt", "second.txt"], "cache did not notice the new file"


def test_read_pdf_tolerates_a_broken_file(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a pdf")
    assert opennet._read_pdf(str(broken)) == ""


# --- app object -----------------------------------------------------------
def _app_source():
    with open(os.path.abspath(opennet.__file__), encoding="utf-8") as handle:
        return handle.read()


def test_app_has_an_entry_point():
    """Regression: the original file had no way to start the server."""
    source = _app_source()
    assert "__main__" in source
    assert "app.run(" in source


def test_app_binds_all_interfaces():
    assert 'host="0.0.0.0"' in _app_source(), (
        "must bind 0.0.0.0 to be reachable inside a container"
    )


def test_no_dead_placeholder_imports():
    """The original imported sqlite3, secure_filename, send_file and more, unused."""
    for unused in ("sqlite3", "secure_filename", "mimetypes", "unquote"):
        assert not hasattr(opennet, unused), f"{unused} is imported but never used"


# --- base URL handling (Flask root vs GitHub Pages subpath) ----------------
def test_site_url_on_flask_root():
    assert opennet.site_url("/") == "/"
    assert opennet.site_url("/openbot") == "/openbot"
    assert opennet.site_url("static/openbot.css") == "/static/openbot.css"


def test_site_url_on_a_static_subpath(monkeypatch):
    monkeypatch.setattr(opennet, "BASE_URL", "/OpenNet-/")
    monkeypatch.setattr(opennet, "STATIC_BUILD", True)
    assert opennet.site_url("/") == "/OpenNet-/"
    assert opennet.site_url("/openbot") == "/OpenNet-/openbot/"
    assert opennet.site_url("/explore") == "/OpenNet-/explore/"


def test_site_url_never_adds_a_slash_to_a_file(monkeypatch):
    """Regression: assets got a trailing slash and would 404 on Pages."""
    monkeypatch.setattr(opennet, "BASE_URL", "/OpenNet-/")
    monkeypatch.setattr(opennet, "STATIC_BUILD", True)
    assert opennet.site_url("static/openbot.css") == "/OpenNet-/static/openbot.css"
    assert opennet.site_url("static/openbot.js") == "/OpenNet-/static/openbot.js"
    assert opennet.site_url("docs/") == "/OpenNet-/docs/"


def test_flask_pages_use_root_relative_links(client):
    """On Flask the app must keep working from the root, unchanged."""
    html = client.get("/").get_data(as_text=True)
    assert "href='/openbot'" in html
    assert "/openbot/" not in html


# --- browser/Python retrieval parity (GitHub Pages build) ------------------
PARITY_QUERIES = [
    "which apps are installed in OpenNet?",
    "how do I run opennet in production with gunicorn?",
    "how do I deploy opennet?",
    "how do I publish to github pages?",
    "how does openbot cache parsed documents?",
    "getting-started.txt",
    "what file types does openbot support?",
    "xyzzy plugh frobnicate",
]


def _node_available():
    import shutil

    return shutil.which("node") is not None


@pytest.mark.skipif(not _node_available(), reason="node is not installed")
def test_browser_search_matches_python_search(tmp_path):
    """GitHub Pages has no API, so openbot-search.js must rank identically."""
    import subprocess

    expected = []
    for question in PARITY_QUERIES:
        matches = opennet.search_documents(question, top_k=3)
        expected.append({
            "question": question,
            "expected_names": [m["name"] for m in matches],
            "expected_top_score": matches[0]["score"] if matches else 0.0,
            "expected_tokens": sorted(opennet._tokens(question)),
        })

    payload = tmp_path / "expected.json"
    payload.write_text(json.dumps(expected), encoding="utf-8")

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(repo_root, "tests", "js", "parity_check.mjs")

    result = subprocess.run(
        ["node", script, str(payload), opennet.DOCS_DIR],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert result.returncode == 0, (
        "browser search disagreed with app.py:\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert "agree with app.py" in result.stdout


def test_static_build_emits_every_page(tmp_path, monkeypatch):
    """The GitHub Pages build must cover every page the shell links to."""
    import importlib

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    builder = importlib.import_module("build_static")

    # Build in this process, then restore the module-level config.
    monkeypatch.setenv("BASE_URL", "/OpenNet-/")
    monkeypatch.setenv("OPENNET_STATIC", "1")
    importlib.reload(opennet)
    try:
        written, manifest = builder.build("/OpenNet-/", str(tmp_path), repo_root)
    finally:
        monkeypatch.delenv("BASE_URL", raising=False)
        monkeypatch.delenv("OPENNET_STATIC", raising=False)
        importlib.reload(opennet)

    for route in [p["route"].strip("/") for p in opennet.platforms] + ["explore", "settings"]:
        assert os.path.isfile(os.path.join(tmp_path, route, "index.html")), route
    assert "index.html" in written
    assert [d["name"] for d in manifest]
    assert (tmp_path / "docs" / "index.json").is_file()
    assert (tmp_path / "static" / "openbot-search.js").is_file()
    assert (tmp_path / "404.html").is_file()

    home = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "href='/OpenNet-/openbot/'" in home
    # Assets must not pick up a trailing slash.
    assert "/static/openbot.css/" not in home


def test_search_returns_each_document_at_most_once():
    """A document can match by title and by content - only the best should show."""
    matches = opennet.search_documents("getting-started.txt", top_k=5)
    names = [m["name"] for m in matches]
    assert len(names) == len(set(names)), f"duplicate documents: {names}"
    assert names[0] == "getting-started.txt"


def test_search_scores_are_ordered_descending():
    matches = opennet.search_documents("opennet documents flask python", top_k=5)
    scores = [m["score"] for m in matches]
    assert scores == sorted(scores, reverse=True), scores


def _build_site(tmp_path, monkeypatch):
    """Build the static site into tmp_path, then restore module config."""
    import importlib

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    builder = importlib.import_module("build_static")
    monkeypatch.setenv("BASE_URL", "/OpenNet-/")
    monkeypatch.setenv("OPENNET_STATIC", "1")
    importlib.reload(opennet)
    try:
        builder.build("/OpenNet-/", str(tmp_path), repo_root)
    finally:
        monkeypatch.delenv("BASE_URL", raising=False)
        monkeypatch.delenv("OPENNET_STATIC", raising=False)
        importlib.reload(opennet)


def test_static_build_has_no_broken_links(tmp_path, monkeypatch):
    """Every internal link in the Pages build must resolve to a real file.

    Guards against the class of bug where a subpath deployment silently 404s on
    its own assets. The link count is asserted so the check cannot pass
    vacuously by matching nothing.
    """
    import pathlib
    import re

    _build_site(tmp_path, monkeypatch)

    base = "/OpenNet-/"
    # Shell templates use single quotes, the OpenBot template double.
    pattern = re.compile(r"""(?:href|src)=["']([^"']+)["']""")

    checked = 0
    broken = []
    root = pathlib.Path(tmp_path)
    for page in sorted(root.rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        for url in pattern.findall(text):
            if url.startswith(("http://", "https://", "#", "mailto:")):
                continue
            checked += 1
            if not url.startswith(base):
                broken.append(f"{page.name}: {url} escapes the base path")
                continue
            target = root / url[len(base):].rstrip("/")
            if "." not in url.rstrip("/").split("/")[-1]:
                target = target / "index.html"
            if not target.exists():
                broken.append(f"{page.name}: {url} -> missing {target}")

    assert checked >= 50, f"only {checked} links inspected - the pattern is not matching"
    assert not broken, "broken links in the static build:\n" + "\n".join(broken)
