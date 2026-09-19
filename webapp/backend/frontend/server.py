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

BACKEND_URL = os.environ.get("BACKEND_URL", "").strip().rstrip("/")


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
