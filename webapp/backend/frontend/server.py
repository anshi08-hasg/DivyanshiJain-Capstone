"""Standalone static file server for the frontend, used only when the
frontend is deployed as its own Railway service, separate from the Flask
backend in webapp/backend/app.py.

The frontend's JS was written assuming same-origin serving (relative
fetch("/api/...") calls), which only works when one Flask app serves both
the pages and the API together (the default, single-service setup - see
FIGMA_CONNECT.md section 8). Running the frontend as a separate service
means those relative URLs would hit this service's own origin, which has no
API behind it. This server fixes that by injecting the real backend's URL
into a small /config.js file, which index.html/figjam.html load before their
own app.js/figjam.js, so those scripts can build absolute API URLs instead.
"""

import os
from flask import Flask, Response

app = Flask(__name__, static_folder=".", static_url_path="")


def _normalize_backend_url(raw: str) -> str:
    """A bare host (no scheme) like 'my-app.up.railway.app' is not an
    absolute URL - a browser resolves it as a relative path instead of a
    cross-origin target, which silently sends API calls to the frontend's
    own (API-less) origin. Confirmed live: this exact mistake produced
    'Unexpected token <, "<!doctype "... is not valid JSON', because the
    request hit this frontend's own 404 HTML page instead of the backend.
    Defaults a missing scheme to https:// rather than failing outright."""
    value = raw.strip().rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value


BACKEND_URL = _normalize_backend_url(os.environ.get("BACKEND_URL", ""))


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/figjam")
def figjam_page():
    return app.send_static_file("figjam.html")


@app.get("/config.js")
def config_js():
    body = (
        f"window.API_BASE_URL = {BACKEND_URL!r};\n"
        "window.apiUrl = function (path) { return (window.API_BASE_URL || \"\") + path; };\n"
    )
    return Response(body, mimetype="application/javascript")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "").strip() or 5000)
    app.run(host="0.0.0.0", port=port)
