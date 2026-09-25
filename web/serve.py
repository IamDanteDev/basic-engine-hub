"""Basic Engine Hub — standalone web menu server.

Serves the browser UI (this directory) and exposes a single API route,
GET /api/listing. The studio+user merge itself lives in listing.py (shared
with the GitHub Pages build); see listing.py for the ordering contract.

Python stdlib only (http.server + urllib). No third-party dependencies.
"""

import argparse
import json
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from listing import build_listing  # module sibling: works when running `python web/serve.py`

BASE_DIR = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    """Serves the web/ static files plus GET /api/listing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):  # noqa: N802 - http.server API name
        if self.path == "/api/listing" or self.path.startswith("/api/listing?"):
            self._serve_listing()
            return
        super().do_GET()

    def _serve_listing(self) -> None:
        try:
            payload = json.dumps(
                build_listing(), ensure_ascii=False
            ).encode("utf-8")
        except Exception as exc:  # noqa: BLE001 - never crash on upstream failures
            body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Basic Engine Hub web menu server")
    parser.add_argument("--port", type=int, default=8000,
                        help="port to listen on (default: 8000)")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open the default browser at startup")
    args = parser.parse_args()

    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"error starting server on port {args.port}: {exc}", file=sys.stderr)
        return 1

    url = f"http://localhost:{args.port}"
    print(f"Basic Engine Hub web: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())