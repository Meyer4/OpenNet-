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

**Render (easiest - one click, free tier).** Push to GitHub, then in Render
choose *New +* → *Blueprint* and point it at this repository. The included
[`render.yaml`](render.yaml) sets the build command, start command and
`/healthz` health check. You get a public `https://<app>.onrender.com` URL.

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

`.github/workflows/aws.yml` is an opt-in, manual ECR image build. It skips
cleanly until real AWS values and secrets are configured - see the comments at
the top of that file.

## Layout

```
app.py                 Flask app: routes, search, error handling
templates/openbot.html OpenBot chat markup
static/openbot.css     OpenBot styles
static/openbot.js      OpenBot behaviour, including the API call
docs/                  OpenBot's default knowledge folder
tests/test_app.py      Route and API regression tests
```

## Licence

MIT - see [LICENSE](LICENSE).
