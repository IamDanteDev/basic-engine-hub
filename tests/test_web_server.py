import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

from web.serve import Handler


class WebServerTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_download_api_streams_project_bytes(self):
        with patch("web.serve.scratch_api.download_project_bytes", return_value=b"sb3 project") as download:
            with urlopen(f"{self.base_url}/api/download/42") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"sb3 project")
            download.assert_called_once_with(42)

    def test_invalid_project_id_is_rejected(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(f"{self.base_url}/api/download/../../settings")
        self.assertEqual(error.exception.code, 404)

    def test_health_route_answers_the_probes(self):
        # Something polls the port for a health check while the server runs, and
        # without this route every probe lands in the log as a 404.
        with urlopen(f"{self.base_url}/health") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "application/json")
            self.assertEqual(json.loads(response.read()), {"status": "ok"})

    def test_detail_api_returns_json(self):
        detail = {"id": 42, "title": "Test", "stats": {"views": 7}}
        with patch("web.serve.scratch_api.fetch_project_detail", return_value=detail):
            with urlopen(f"{self.base_url}/api/project/42") as response:
                self.assertEqual(response.headers.get_content_type(), "application/json")
                self.assertEqual(json.loads(response.read()), detail)

    def test_assets_route_serves_the_shared_art(self):
        # The pages reference the repository Assets/ as ../Assets/..., which is
        # /Assets/... once this server owns web/ as the document root. The title
        # filenames are not ASCII, so one case arrives percent-encoded.
        for path in (
            "/Assets/Placeholders/thumbnail.png",
            "/Assets/Placeholders/profile.png",
            "/Assets/Lengs/Titles/espa%C3%B1ol.png",
        ):
            with self.subTest(path=path):
                with urlopen(f"{self.base_url}{path}") as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get_content_type(), "image/png")
                    self.assertEqual(response.read()[:8], b"\x89PNG\r\n\x1a\n")

    def test_assets_route_refuses_to_leave_its_directory(self):
        # urllib strips literal dot segments before sending, so the attempted
        # escapes are percent-encoded and decoded server-side. /etc/passwd exists
        # on the runner, which is what makes the containment check the thing under
        # test rather than file existence.
        for path in (
            "/Assets/..%2F..%2Fetc%2Fpasswd",
            "/Assets/%2e%2e%2fhub%2fi18n.py",
            "/Assets/nope.png",
            "/Assets/",
        ):
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as error:
                    urlopen(f"{self.base_url}{path}")
                self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()