"""Basic Engine Hub — standalone web menu server.

Serves the browser UI (this directory) and exposes a single API route,
GET /api/listing, project detail/comments routes, and a byte-stream download
route. The studio+user merge itself lives in listing.py (shared with Pages).

HTTP serving uses the Python standard library; Scratch requests reuse
hub.scratch_api.
"""

import argparse
import json
import mimetypes
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
for import_path in (str(BASE_DIR), str(PROJECT_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from hub import scratch_api
from listing import build_listing  # module sibling: works when running `python web/serve.py`


class Handler(SimpleHTTPRequestHandler):
    """Serves the web/ static files plus GET /api/listing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):  # noqa: N802 - http.server API name
        path = urlsplit(self.path).path
        if path == "/sw.js":
            self._serve_root_script()
            return
        if path == "/api/listing":
            self._serve_listing()
            return
        for route, action in (
            ("/api/project/", self._serve_project_detail),
            ("/api/comments/", self._serve_comments),
            ("/api/download/", self._download_project),
        ):
            if path.startswith(route):
                self._serve_project_action(path[len(route):], action)
                return
        super().do_GET()

    def _serve_root_script(self) -> None:
        script = PROJECT_ROOT / "sw.js"
        if not script.is_file():
            self.send_error(404, "Not Found")
            return
        payload = script.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(script.name)[0] or "text/javascript")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_project_action(self, project_id: str, action) -> None:
        if not project_id.isdigit():
            self.send_error(404, "Not Found")
            return
        try:
            result = action(int(project_id))
        except Exception as exc:  # noqa: BLE001 - upstream failures are API responses
            self._send_json({"error": str(exc)}, status=502)
            return
        if isinstance(result, bytes):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(result)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(result)
            return
        self._send_json(result)

    @staticmethod
    def _serve_project_detail(project_id: int) -> dict:
        return scratch_api.fetch_project_detail(project_id)

    @staticmethod
    def _serve_comments(project_id: int) -> list[dict]:
        return scratch_api.fetch_project_comments(project_id)

    @staticmethod
    def _download_project(project_id: int) -> bytes:
        return scratch_api.download_project_bytes(project_id)

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

    def _send_json(self, value, status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
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