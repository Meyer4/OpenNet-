#!/usr/bin/env python3
"""Build a static copy of OpenNet for GitHub Pages.

The Flask app is the single source of truth: every page is rendered by the real
routes through Flask's test client, then written to disk. OpenBot keeps working
because static/openbot-search.js does the retrieval in the browser against the
documents copied into <out>/docs/.

Usage:
    python build_static.py --base /OpenNet-/ --out site
"""

import argparse
import json
import os
import shutil
import sys

SEARCHABLE = (".txt", ".md", ".markdown", ".rst", ".csv", ".json")


def build(base_url, out_dir, repo_root):
    # app.py reads these at import time, so they must be set first.
    os.environ["BASE_URL"] = base_url
    os.environ["OPENNET_STATIC"] = "1"
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    import app as opennet

    if opennet.BASE_URL != base_url:
        raise SystemExit(f"BASE_URL did not take effect: {opennet.BASE_URL}")
    if not opennet.STATIC_BUILD:
        raise SystemExit("OPENNET_STATIC did not take effect")

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    client = opennet.app.test_client()

    # Every GET route except the API, the health probe and static files.
    skip = {"/openbot/api", "/healthz"}
    routes = sorted(
        str(rule)
        for rule in opennet.app.url_map.iter_rules()
        if str(rule) not in skip
        and not str(rule).startswith("/static/")
        and "<" not in str(rule)
    )

    written = []
    for route in routes:
        response = client.get(route)
        if response.status_code != 200:
            raise SystemExit(f"{route} returned {response.status_code} during build")

        relative = route.strip("/")
        target = os.path.join(out_dir, relative, "index.html") if relative else os.path.join(out_dir, "index.html")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(response.get_data(as_text=True))
        written.append(os.path.relpath(target, out_dir))

    # Static assets.
    shutil.copytree(
        os.path.join(repo_root, "static"), os.path.join(out_dir, "static")
    )

    # Documents, plus the manifest openbot-search.js reads.
    docs_out = os.path.join(out_dir, "docs")
    os.makedirs(docs_out, exist_ok=True)
    manifest = []
    for name in sorted(os.listdir(opennet.DOCS_DIR)):
        source = os.path.join(opennet.DOCS_DIR, name)
        if not os.path.isfile(source):
            continue
        shutil.copy2(source, os.path.join(docs_out, name))
        manifest.append({
            "name": name,
            "file": name,
            "searchable": name.lower().endswith(SEARCHABLE),
        })
    with open(os.path.join(docs_out, "index.json"), "w", encoding="utf-8") as handle:
        json.dump({"documents": manifest}, handle, indent=2)

    # GitHub Pages serves 404.html for unknown paths.
    shutil.copy2(os.path.join(out_dir, "index.html"), os.path.join(out_dir, "404.html"))

    return written, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="/", help="Base URL, e.g. /OpenNet-/")
    parser.add_argument("--out", default="site", help="Output directory")
    args = parser.parse_args()

    base = args.base if args.base.endswith("/") else args.base + "/"
    repo_root = os.path.dirname(os.path.abspath(__file__))

    written, manifest = build(base, os.path.join(repo_root, args.out), repo_root)

    print(f"Built {len(written)} pages into {args.out}/ with base {base}")
    for page in written:
        print(f"  {page}")
    print(f"  docs/index.json ({len(manifest)} documents)")


if __name__ == "__main__":
    main()
