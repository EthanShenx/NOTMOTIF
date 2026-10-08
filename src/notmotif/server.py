"""A small local web app for NOTMOTIF, built on the standard library."""

from __future__ import annotations

import dataclasses
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

from . import __version__
from .colors import SCHEME_DESCRIPTIONS, SCHEMES, color_for
from .core import FORMATS, MotifStyle, generate

_MIME = {
    "png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf",
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
}


def _index_html() -> bytes:
    return resources.files("notmotif").joinpath("web/index.html").read_bytes()


def _defaults() -> dict:
    out = {}
    for f in dataclasses.fields(MotifStyle):
        if f.default is not dataclasses.MISSING:
            out[f.name] = f.default
    out["colors"] = {}
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = f"notmotif/{__version__}"

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data) -> None:
        self._send(status, json.dumps(data).encode(), "application/json")

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        try:
            if url.path in ("/", "/index.html"):
                self._send(200, _index_html(), "text/html; charset=utf-8")
            elif url.path == "/api/meta":
                self._json(200, {
                    "version": __version__,
                    "defaults": _defaults(),
                    "schemes": {k: SCHEME_DESCRIPTIONS[k] for k in SCHEMES},
                    "formats": list(FORMATS),
                })
            elif url.path == "/api/palette":
                style = MotifStyle.from_mapping(q)
                word = q.get("word", "")
                if style.uppercase:
                    word = word.upper()
                chars = sorted({c for c in word if not c.isspace()}, key=word.index)
                self._json(200, {c: color_for(c, style.color_scheme, style.colors, style.mono_color)
                                 for c in chars})
            elif url.path == "/api/render":
                fmt = q.pop("format", "png").lower()
                word = q.pop("word", "")
                download = q.pop("download", "") in ("1", "true")
                motif = generate(word, MotifStyle.from_mapping(q))
                body = motif.to_bytes(fmt)
                extra = {}
                if download:
                    name = "".join(c if c.isalnum() else "_" for c in word.strip()) or "motif"
                    extra["Content-Disposition"] = f'attachment; filename="{name}.{fmt}"'
                self._send(200, body, _MIME.get(fmt, "application/octet-stream"), extra)
            else:
                self._json(404, {"error": "not found"})
        except ValueError as e:
            self._json(400, {"error": str(e)})
        except Exception as e:  # surface unexpected errors in the UI instead of hanging
            self._json(500, {"error": f"{type(e).__name__}: {e}"})


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Start the web app and block until Ctrl+C."""
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{httpd.server_port}/"
    print(f"NOTMOTIF is running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
