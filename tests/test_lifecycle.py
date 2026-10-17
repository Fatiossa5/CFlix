"""Restart the real Python process with disposable data; never contact SMTP."""
import http.client
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest


class LifecycleTests(unittest.TestCase):
    def test_process_restart_preserves_data_and_invalidates_sessions(self):
        with tempfile.TemporaryDirectory(prefix="fatihflix-lifecycle-") as directory:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            environment = dict(os.environ)
            # Override every local mail setting before server imports .env.
            for key in ("SMTP_PROVIDER", "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME",
                        "SMTP_PASSWORD", "SMTP_FROM", "FEEDBACK_RECIPIENT"):
                environment[key] = ""
            environment.update(DATA_DIR=directory, HOST="127.0.0.1", PORT=str(port),
                               COOKIE_SECURE="0", PUBLIC_ORIGIN="", TRUSTED_PROXY_CIDRS="")
            process = None
            cookie = ""

            def request(path, payload=None, raw=None, headers=None):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                body = json.dumps(payload).encode() if payload is not None else raw
                try:
                    connection.request("POST" if body is not None else "GET", path, body=body,
                        headers={"Cookie": cookie, "Content-Type": "application/json", **(headers or {})})
                    response = connection.getresponse()
                    return response.status, response.read(), response.getheader("Set-Cookie")
                finally:
                    connection.close()

            def start():
                running = subprocess.Popen([sys.executable, "server.py"], env=environment,
                    cwd=Path(__file__).resolve().parents[1], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + 10
                try:
                    while time.monotonic() < deadline:
                        if running.poll() is not None:
                            self.fail("Disposable server did not start")
                        try:
                            if request("/api/health")[0] == 200:
                                return running
                        except OSError:
                            pass
                        time.sleep(.05)
                    self.fail("Disposable server startup timed out")
                except BaseException:
                    running.terminate()
                    running.wait(timeout=5)
                    raise

            try:
                process = start()
                credentials = {"email": "restart@example.test", "password": "restart-test-password"}
                status, _, session = request("/api/register", {"name": "Restart Test", **credentials})
                self.assertEqual(status, 200)
                cookie = session.split(";", 1)[0]
                with closing(sqlite3.connect(Path(directory) / "fatihflix.db")) as db:
                    db.execute("UPDATE users SET role='admin' WHERE email=?", (credentials["email"],))
                    db.commit()
                video = b"\x00\x00\x00\x18ftypisom" + b"test-video" * 20
                status, body, _ = request("/api/admin/uploads?kind=video", raw=video,
                    headers={"Content-Type": "video/mp4"})
                self.assertEqual(status, 201)
                asset = json.loads(body)["asset"]
                self.assertEqual(request("/api/favorites", {"id": "aurora"})[0], 200)
                self.assertEqual(request("/api/progress", {"id": "aurora", "position": 25, "duration": 100})[0], 200)
                self.assertEqual(request("/api/feedback", {"kind": "suggestion", "message": "Test restart queue message"})[0], 202)
                process.terminate()
                process.wait(timeout=5)
                process = start()
                self.assertEqual(request("/api/me")[0], 401)
                self.assertEqual(request(asset["url"])[0], 401)
                status, body, session = request("/api/login", credentials)
                self.assertEqual(status, 200)
                cookie = session.split(";", 1)[0]
                user = json.loads(body)["user"]
                self.assertEqual(user["role"], "admin")
                self.assertIn("aurora", user["favorites"])
                self.assertEqual(user["history"]["aurora"]["position"], 25)
                status, body, _ = request(asset["url"], headers={"Range": "bytes=4-11"})
                self.assertEqual((status, body), (206, video[4:12]))
                status, body, _ = request("/api/admin/mail-status")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["queued"], 1)
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
