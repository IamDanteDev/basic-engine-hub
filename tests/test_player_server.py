"""The desktop player server must serve every asset the player page loads.

Run with: python -m unittest discover -s tests

`web/player.html` is served by the loopback server in `hub/player.py`, not by
`web/serve.py`, and that server routes a fixed list of paths instead of serving
the whole directory. So an asset the page references is not automatically
reachable: when the page switched to the shared i18n core, `/i18n.js` answered
404 in the desktop app, `I18n` stayed undefined and the player rendered its raw
key names instead of copy. This test derives the list from the page itself, so
the next asset added to the markup cannot repeat that.

The verifier found this defect, and this test is the reproduction it handed
over: it fails against the whitelist as it was (`404 for /i18n.js`).

PySide6 is stubbed rather than imported: the CI runner installs requests and
beautifulsoup4 but not PySide6, and a test that pulled the widgets in would fail
the build it is supposed to protect.
"""

import re
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _stub_pyside6():
    """Register the minimum PySide6 surface `hub.player` imports."""
    module = sys.modules

    def register(name, **attributes):
        module[name] = type(name, (), {})
        for key, value in attributes.items():
            setattr(module[name], key, value)
        return module[name]

    register("PySide6")
    register("PySide6.QtCore", QUrl=object, Signal=lambda *args, **kwargs: (lambda fn: fn))

    class _Settings:
        class WebAttribute:
            FullScreenSupportEnabled = 0

        def setAttribute(self, *args):
            pass

    register("PySide6.QtWebEngineCore", QWebEngineSettings=_Settings)

    class _View:
        def __init__(self, *args, **kwargs):
            pass

        def settings(self):
            return _Settings()

        def setUrl(self, *args):
            pass

        def page(self):
            return None

    register("PySide6.QtWebEngineWidgets", QWebEngineView=_View)


class PlayerServerAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _stub_pyside6()
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import hub.player

        cls.player = hub.player

    def test_the_server_serves_every_script_the_player_page_loads(self):
        html = (ROOT / "web" / "player.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script src="([^"]+)"', html)
        self.assertIn("i18n.js", scripts, "the player must ask the shared i18n core")

        server = self.player.LocalServer()
        server.start()
        try:
            for script in scripts:
                url = server.url.rstrip("/") + "/" + script
                status = None
                try:
                    with urllib.request.urlopen(url, timeout=5) as response:
                        status = response.status
                except urllib.error.HTTPError as error:
                    status = error.code
                self.assertEqual(
                    status,
                    200,
                    f"hub/player.py answered {status} for /{script}: the player page "
                    "loads it, so the desktop app would render raw key names",
                )
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
