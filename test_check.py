"""Tests for check.py"""

import sys
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from check import check, main  # noqa: E402


# ---------------------------------------------------------------------------
# Tiny local HTTP server used by integration tests
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):  # silence request logs during tests
        pass

    def do_GET(self):
        if self.path == "/ok":
            self.send_response(200)
        elif self.path == "/not-found":
            self.send_response(404)
        elif self.path == "/error":
            self.send_response(500)
        else:
            self.send_response(200)
        self.end_headers()


def _start_server() -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.base = _start_server()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_ok(self):
        code, msg = check(f"{self.base}/ok")
        self.assertEqual(code, 200)
        self.assertIn("200", msg)

    def test_not_found(self):
        code, msg = check(f"{self.base}/not-found")
        self.assertEqual(code, 404)
        self.assertIn("404", msg)

    def test_server_error(self):
        code, msg = check(f"{self.base}/error")
        self.assertEqual(code, 500)
        self.assertIn("500", msg)

    def test_invalid_uri(self):
        code, msg = check("not-a-valid-uri")
        self.assertIsNone(code)
        self.assertIn("Invalid URI", msg)

    def test_unreachable_host(self):
        code, msg = check("http://192.0.2.1/")  # TEST-NET, always unreachable
        self.assertIsNone(code)
        self.assertIn("Error", msg)


class TestMain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.base = _start_server()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_no_args_returns_2(self):
        self.assertEqual(main([]), 2)

    def test_ok_uri_returns_0(self):
        self.assertEqual(main([f"{self.base}/ok"]), 0)

    def test_bad_uri_returns_1(self):
        self.assertEqual(main([f"{self.base}/not-found"]), 1)

    def test_multiple_uris_mixed(self):
        # One OK, one 404 → exit code 1
        result = main([f"{self.base}/ok", f"{self.base}/not-found"])
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
