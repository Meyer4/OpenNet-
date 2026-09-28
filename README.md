# OpenNet

A small multi-app shell written in Python with Flask. Seven mini applications sit
behind one home screen and share navigation, styling and deployment.

| App | Route | What it does |
| --- | --- | --- |
| OpenBot | `/openbot` | Chat assistant that answers from your documents |
| E-Book | `/ebook` | Read and manage e-books |
| AppBox | `/appbox` | Toolbox of small utilities |
| MyFace | `/myface` | Profile and avatar |
| MyVids | `/myvids` | Watch and organise videos |
| Piggy Bank | `/piggybank` | Track savings and spending |
| SnapStyle | `/snapstyle` | Photos, filters and galleries |

Everything except OpenBot is a wired-up placeholder: the route resolves and the
page renders, ready for an implementation.

## Run it locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open <http://localhost:5000>.

Production-style, with Gunicorn:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

## Tests

```bash
pytest
```

The suite covers every route the home screen advertises, the OpenBot API contract
and the document search, so a missing route or a broken endpoint fails the build
rather than showing up in production.

## OpenBot

OpenBot answers by searching documents instead of guessing. It reads `.txt`,
`.md`, `.markdown`, `.rst`, `.csv`, `.json` and `.pdf` files from its knowledge
folder, splits them into overlapping chunks, and returns the chunk that best
covers your question, citing the file it came from. If nothing matches it says so
plainly.

The folder defaults to [`docs/`](docs) and can be moved:

```bash
OPENBOT_DOCS_DIR=/path/to/documents python app.py
```

Parsed text is cached in memory and the cache invalidates automatically when a
file is added, edited or removed.

The chat page calls a JSON endpoint you can also use directly:

```bash
curl -X POST http://localhost:5000/openbot/api \
     -H "Content-Type: application/json" \
     -d '{"question": "what is OpenNet?"}'
```

Malformed or empty requests return `400` with an `error` field, never a `500`.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `5000` | Port to listen on |
| `SECRET_KEY` | dev value | Flask secret key - set this in production |
| `OPENBOT_DOCS_DIR` | `./docs` | Folder OpenBot searches |
| `FLASK_DEBUG` | `0` | Set to `1` for the local debug reloader |

`GET /healthz` returns JSON status for platform health checks.

## Deploying

### GitHub Pages (static, free, permanent)

[`build_static.py`](build_static.py) renders every page through the real Flask
routes and writes a plain HTML site, so the Flask app stays the single source of
truth. Push to `main` and
[`pages.yml`](.github/workflows/pages.yml) builds and publishes it to
`https://<user>.github.io/<repo>/`.

Enable it once in the repository: *Settings* → *Pages* → *Source* → **GitHub
Actions**.

Build it yourself:

```bash
python build_static.py --base /OpenNet-/ --out site
```

`--base` must be the path the site is served from, including both slashes. Pass
`/` if you publish from a custom domain or a user site.

**What changes on a static host.** There is no server, so OpenBot's search runs
in the browser (`static/openbot-search.js`) against the documents copied into
`site/docs/`. The ranking is the same algorithm as the Python one and is verified
to agree by `tests/js/parity_check.mjs`. Two differences follow from having no
server:

- the knowledge folder is fixed at build time, rather than set by
  `OPENBOT_DOCS_DIR` at runtime;
- PDFs are copied but not searched, since parsing them needs a server. Text
  formats are searched normally.

The chat page detects which host it is on: it calls `/openbot/api` when there is
one and falls back to the in-browser search otherwise, so the same code works on
both.

### Running the server

**Render (one click, free tier).** In Render choose *New +* → *Blueprint* and
point it at this repository. The included [`render.yaml`](render.yaml) sets the
build command, start command and `/healthz` health check. You get a public
`https://<app>.onrender.com` URL.

**Docker.** [`Dockerfile`](Dockerfile) builds a slim image that runs as a
non-root user with a health check:

```bash
docker build -t opennet .
docker run -p 8080:8080 opennet
```

**Anywhere else.** Any host that runs a Python web app works - Railway, Fly.io,
Heroku, an ECS task. The [`Procfile`](Procfile) provides the start command and
the app reads `PORT` from the environment, which is what these platforms supply.

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and
pull request: it installs the pinned dependencies, runs the test suite on Python
3.9/3.11/3.12, then boots the real server under Gunicorn and checks that `/`,
`/openbot`, `/piggybank` and `/healthz` all return `200`.

The suite includes a cross-language check: `tests/js/parity_check.mjs` runs the
browser retrieval in Node and asserts it ranks documents exactly as `app.py`
does, so the static site cannot silently drift from the server.

[`pages.yml`](.github/workflows/pages.yml) runs on `main`, re-runs the tests,
builds the static site and verifies that every internal link and asset in it
resolves to a real file before publishing.

`.github/workflows/aws.yml` is an opt-in, manual ECR image build. It skips
cleanly until real AWS values and secrets are configured - see the comments at
the top of that file.

## Layout

```
app.py                  Flask app: routes, search, error handling
build_static.py         Renders the GitHub Pages build from the Flask routes
templates/openbot.html  OpenBot chat markup
static/openbot.css      OpenBot styles
static/openbot.js       OpenBot behaviour, including the API call and fallback
static/openbot-search.js  In-browser retrieval used by the static build
docs/                   OpenBot's knowledge folder
tests/test_app.py       Route, API and static-build regression tests
tests/js/parity_check.mjs  Proves the browser search matches app.py
```

## Licence

MIT - see [LICENSE](LICENSE).
