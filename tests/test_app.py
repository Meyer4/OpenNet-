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
        line.strip() for line in js.splitlines() if "fetch('/openbot/api'" in line
    ]
    assert live_calls, "chat UI never calls /openbot/api"
    for line in live_calls:
        assert not line.startswith("//"), f"call is still commented out: {line}"


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
    assert matches[0]["name"] == "getting-started.txt"


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
