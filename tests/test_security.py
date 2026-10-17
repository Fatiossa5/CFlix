"""Deployment regressions: real HTTP, isolated database, no external services."""
from contextlib import closing
import http.client
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

import server
import test_server as helpers


class SecurityTests(unittest.TestCase):
    new_client = staticmethod(helpers.ApplicationTests.new_client)
    request = helpers.ApplicationTests.request
    register = helpers.ApplicationTests.register
    setUp = helpers.ApplicationTests.setUp

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="fatihflix-security-")
        cls.original_data_dir = server.DATA_DIR
        server.DATA_DIR = Path(cls.temp.name)
        server.init_db()
        cls.httpd = server.LimitedHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.worker = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    tearDownClass = classmethod(helpers.ApplicationTests.tearDownClass.__func__)

    def test_csrf_origin_fetch_metadata_and_simple_form_requests(self):
        data = {"name": "Test", "email": self.email, "password": self.password}
        for headers, expected in (({"Origin": "null"}, 403),
                                  ({"Sec-Fetch-Site": "cross-site"}, 403),
                                  ({"Content-Type": "text/plain"}, 415),
                                  ({"Content-Type": "application/x-www-form-urlencoded"}, 415)):
            self.assertEqual(self.request("/api/register", data, headers=headers)[0], expected)
        with patch.dict(os.environ, {"PUBLIC_ORIGIN": "https://site.example.test"}):
            self.assertEqual(self.request("/api/register", data,
                headers={"Origin": self.base})[0], 403)
            self.assertEqual(self.request("/api/register", data,
                headers={"Origin": "https://site.example.test"})[0], 200)

    def test_security_headers_and_secure_login_logout_cookies(self):
        with patch.dict(os.environ, {"COOKIE_SECURE": "1"}):
            _, headers = self.register()
            self.assertIn("; Secure", headers["Set-Cookie"])
            # HTTP clients correctly withhold Secure cookies: supply it explicitly.
            cookie = headers["Set-Cookie"].split(";", 1)[0]
            status, _, headers = self.request("/api/logout", {}, headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertIn("; Secure", headers["Set-Cookie"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("script-src 'self';", headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_proxy_ip_is_accepted_only_from_explicit_trusted_peer(self):
        for trusted, expected in (("", "127.0.0.1"), ("127.0.0.1/32", "192.0.2.9")):
            with patch.dict(os.environ, {"TRUSTED_PROXY_CIDRS": trusted}):
                with server.LOCK:
                    server.ATTEMPTS.clear()
                self.request("/api/login", {"email": self.email, "password": self.password},
                    headers={"X-Real-IP": "192.0.2.9", "X-Forwarded-For": "192.0.2.99"})
                self.assertIn(expected, server.ATTEMPTS)
                self.assertNotIn("192.0.2.99", server.ATTEMPTS)

    def test_request_framing_rejects_duplicate_length_and_transfer_encoding(self):
        for transfer in (False, True):
            connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=3)
            try:
                connection.putrequest("POST", "/api/login")
                connection.putheader("Content-Type", "application/json")
                connection.putheader("Content-Length", "2")
                connection.putheader("Transfer-Encoding", "chunked") if transfer else connection.putheader("Content-Length", "2")
                connection.endheaders(b"{}")
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
            finally:
                connection.close()

    def test_sql_input_is_data(self):
        status, _, _ = self.request("/api/login", {"email": "'OR'1'='1@example.test", "password": self.password})
        self.assertEqual(status, 401)
        with closing(server.connect()) as db:
            self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE name='users'").fetchone())

    def test_health_detects_database_failure_without_exposing_details(self):
        with patch.object(server, "connect", side_effect=server.sqlite3.OperationalError("private-path")):
            status, body, _ = self.request("/api/health")
        self.assertEqual(status, 503)
        self.assertNotIn("private-path", json.dumps(body))


class ConnectionLimitTests(unittest.TestCase):
    def test_capacity_releases_after_disconnection(self):
        with patch.dict(os.environ, {"MAX_CONNECTIONS": "1"}):
            httpd = server.LimitedHTTPServer(("127.0.0.1", 0), server.Handler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        # Reserve the sole worker deterministically; overload cannot create threads.
        self.assertTrue(httpd.slots.acquire(blocking=False))
        try:
            with socket.create_connection(httpd.server_address, timeout=2) as sock:
                sock.settimeout(2)
                self.assertEqual(sock.recv(1), b"")
        finally:
            httpd.slots.release()
        try:
            connection = http.client.HTTPConnection(*httpd.server_address, timeout=2)
            connection.request("GET", "/api/health")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            json.loads(response.read())
            connection.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=3)
