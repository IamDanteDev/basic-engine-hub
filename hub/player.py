"""Local HTTP server and QWebEngineView wrapper for the Scaffolding player.

The web view cannot ``fetch()`` local files from a ``file://`` page (CORS), so
the app serves ``web/`` and ``projects/`` over a loopback HTTP server on a
random port.
"""

import json
import mimetypes
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from hub import i18n
from hub.cache import PROJECTS

BASE = Path(__file__).resolve().parent.parent
WEB = BASE / "web"
VENDOR_ALLOWED = {"scaffolding-with-music.js"}


class _PlayerHandler(SimpleHTTPRequestHandler):
    """Handles the few routed GET paths; never logs to stdout/stderr."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/":
            self._serve_file(WEB / "player.html")
        elif path.startswith("/vendor/"):
            name = path[len("/vendor/"):]
            if name in VENDOR_ALLOWED:
                self._serve_file(WEB / "vendor" / name)
            else:
                self.send_error(403, "Forbidden")
        elif path.startswith("/projects/"):
            self._serve_project(path[len("/projects/"):])
        else:
            self.send_error(404, "Not Found")

    def _serve_project(self, name: str) -> None:
        root = PROJECTS.resolve()
        target = (PROJECTS / name).resolve()
        if not target.is_relative_to(root):
            self.send_error(403, "Forbidden")
            return
        self._serve_file(target)

    def _serve_file(self, path: Path) -> None:
        path = Path(path)
        if not path.is_file():
            self.send_error(404, "Not Found")
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


class LocalServer:
    """Minimal loopback HTTP server for the player page and cached projects."""

    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0
        self.url = ""

    def start(self) -> None:
        if self._server is not None:
            return
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _PlayerHandler)
        self.port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/"
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="basic-engine-hub-http",
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        server, self._server = self._server, None
        server.shutdown()
        server.server_close()

    def __enter__(self) -> "LocalServer":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


class Player(QWebEngineView):
    """Web view showing web/player.html served by :class:`LocalServer`."""

    load_failed = Signal(str)
    fullscreen_requested = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Qt WebEngine disables the HTML Fullscreen API by default; without
        # this, requestFullscreen() rejects with "Fullscreen is not supported".
        self.settings().setAttribute(
            QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True
        )
        self._server = LocalServer()
        self._server.start()
        self.loadFinished.connect(self._on_load_finished)
        self.page().fullScreenRequested.connect(self._on_fullscreen_requested)
        # The query string only carries the UI language: the loopback handler
        # reads urlsplit(self.path).path, so "?lang=..." never reaches routing.
        self.setUrl(QUrl(self._server.url + "?lang=" + i18n.current()))

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            self.load_failed.emit(i18n.tr("player_load_failed"))

    def set_language(self, lang) -> None:
        """Switch the loaded player page's language at runtime."""
        self.page().runJavaScript(f"window.setPlayerLanguage({json.dumps(lang)})")

    def load_project(self, project_id) -> None:
        code = f"window.loadScratchProject({json.dumps(str(project_id))})"
        self.page().runJavaScript(code)

    def list_variables(self, callback) -> None:
        """Invoke callback([{id,name,target,value,isCloud}, ...]) with the current project's variables.

        The page returns a native JS array, but PySide6 6.11 runJavaScript callbacks
        only deliver scalars (compound values collapse to ''), so the value is
        round-tripped through JSON.
        """

        def _parse(result) -> None:
            try:
                rows = json.loads(result) if isinstance(result, str) and result else []
            except (TypeError, ValueError):
                rows = []
            callback(rows)

        self.page().runJavaScript("JSON.stringify(window.listVariables())", _parse)

    def switch_project(self, old_pid, old_saved_ids, new_pid, new_saved_ids) -> None:
        """Snapshot checked vars of old project, stop it, load new project, restore its saved vars."""
        code = (
            f"window.switchProject("
            f"{json.dumps(str(old_pid)) if old_pid is not None else 'null'}, "
            f"{json.dumps(list(old_saved_ids or []))}, "
            f"{json.dumps(str(new_pid))}, "
            f"{json.dumps(list(new_saved_ids or []))})"
        )
        self.page().runJavaScript(code)

    def set_variable_value(self, variable_id, value, callback=None) -> None:
        """Set a variable/list value on the loaded project.

        Local-only: cloud variables are not propagated to any server.
        """
        code = (
            f"window.setVariableValue({json.dumps(variable_id)}, "
            f"{json.dumps(value)})"
        )
        # PySide6 6.11 binds a literal None as ``worldId`` and rejects the call,
        # so only pass the result callback when one is actually provided.
        if callback is None:
            self.page().runJavaScript(code)
        else:
            self.page().runJavaScript(code, callback)

    def green_flag(self) -> None:
        self.page().runJavaScript("window.greenFlag()")

    def stop_all(self) -> None:
        self.page().runJavaScript("window.stopAll()")

    def pause_game(self) -> None:
        self.page().runJavaScript("window.pausePlayer()")

    def resume_game(self) -> None:
        self.page().runJavaScript("window.resumePlayer()")

    def get_clone_count(self, callback) -> None:
        self.page().runJavaScript("JSON.stringify(window.getCloneCount() || 0)", callback)

    def _on_fullscreen_requested(self, request) -> None:
        request.accept()
        self.fullscreen_requested.emit(request.toggleOn())

    def toggle_clones_panel(self) -> None:
        self.page().runJavaScript("window.toggleClonesPanel()")

    def enter_fullscreen(self) -> None:
        self.page().runJavaScript("window.enterFullscreen()")

    def shutdown(self) -> None:
        self._server.stop()