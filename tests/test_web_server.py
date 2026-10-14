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

    def test_detail_api_returns_json(self):
        detail = {"id": 42, "title": "Test", "stats": {"views": 7}}
        with patch("web.serve.scratch_api.fetch_project_detail", return_value=detail):
            with urlopen(f"{self.base_url}/api/project/42") as response:
                self.assertEqual(response.headers.get_content_type(), "application/json")
                self.assertEqual(json.loads(response.read()), detail)


if __name__ == "__main__":
    unittest.main()