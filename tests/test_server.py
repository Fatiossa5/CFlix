"""Gerçek HTTP istekleri ve geçici SQLite veritabanıyla uygulama testleri."""
import http.cookiejar
from contextlib import closing
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="fatihflix-test-")
        cls.original_data_dir = server.DATA_DIR
        server.DATA_DIR = Path(cls.temp.name)
        server.init_db()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.worker = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.worker.join(timeout=5)
        server.DATA_DIR = cls.original_data_dir
        server.SESSIONS.clear()
        server.ATTEMPTS.clear()
        cls.temp.cleanup()

    def setUp(self):
        self.client, self.cookies = self.new_client()
        self.email = f"{uuid.uuid4().hex}@example.com"
        self.password = "Guvenli-parola-123"

    @staticmethod
    def new_client():
        jar = http.cookiejar.CookieJar()
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar

    def request(self, path, data=None, client=None, headers=None):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            response = (client or self.client).open(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            payload = json.loads(response.read())
            return response.status, payload, response.headers

    def register(self, client=None, email=None):
        status, payload, headers = self.request("/api/register", {
            "name": "Deneme Üye", "email": email or self.email, "password": self.password,
        }, client=client)
        self.assertEqual(status, 200, payload)
        return payload["user"], headers

    def test_authentication_session_and_logout(self):
        self.assertEqual(self.request("/api/me")[0], 401)
        user, headers = self.register()
        self.assertEqual(user["name"], "Deneme Üye")
        self.assertNotIn("password", user)
        self.assertNotIn("salt", user)
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertEqual(self.request("/api/me")[1]["user"]["id"], user["id"])
        self.assertEqual(self.request("/api/logout", {})[0], 200)
        self.assertEqual(self.request("/api/me")[0], 401)
        self.assertEqual(self.request("/api/login", {
            "email": self.email.upper(), "password": self.password,
        })[0], 200)

    def test_duplicate_registration_and_wrong_password(self):
        self.register()
        self.assertEqual(self.request("/api/register", {
            "name": "Başka Üye", "email": self.email, "password": self.password,
        })[0], 409)
        self.assertEqual(self.request("/api/login", {
            "email": self.email, "password": "yanlis-parola",
        })[0], 401)
        self.assertEqual(self.request("/api/login", {
            "email": "bulunmayan@example.com", "password": self.password,
        })[0], 401)

    def test_favorites_and_history_survive_new_session(self):
        user, _ = self.register()
        self.assertEqual(self.request("/api/favorites", {"id": "aurora"})[0], 200)
        self.assertEqual(self.request("/api/progress", {
            "id": "aurora", "position": 34.5, "duration": 100,
        })[0], 200)
        other, _ = self.new_client()
        self.assertEqual(self.request("/api/login", {
            "email": self.email, "password": self.password,
        }, client=other)[0], 200)
        result = self.request("/api/me", client=other)[1]["user"]
        self.assertEqual(result["favorites"], ["aurora"])
        self.assertEqual(result["history"]["aurora"]["position"], 34.5)
        self.assertFalse(result["history"]["aurora"]["completed"])
        with closing(server.connect()) as db:
            self.assertEqual(db.execute("SELECT position FROM history WHERE user_id=?", (user["id"],)).fetchone()[0], 34.5)
        self.assertEqual(self.request("/api/favorites", {"id": "aurora"})[1]["user"]["favorites"], [])

    def test_accounts_have_separate_favorites_and_history(self):
        first, _ = self.register()
        self.request("/api/favorites", {"id": "aurora"})
        self.request("/api/progress", {"id": "aurora", "position": 25, "duration": 100})
        other, _ = self.new_client()
        second, _ = self.register(other, f"{uuid.uuid4().hex}@example.com")
        self.assertNotEqual(first["id"], second["id"])
        result = self.request("/api/me", client=other)[1]["user"]
        self.assertEqual(result["favorites"], [])
        self.assertEqual(result["history"], {})
        self.assertEqual(self.request("/api/me")[1]["user"]["favorites"], ["aurora"])

    def test_recommendations_prioritize_favorite_and_watched_genres(self):
        self.register()
        self.request("/api/favorites", {"id": "aurora"})
        recommended = self.request("/api/me")[1]["recommendations"]
        self.assertEqual(recommended[:2], ["aurora", "yildiz-tozu"])
        self.assertEqual(set(recommended), server.IDS)
        watched = server.recommend({"favorites": [], "history": {"golge": {"position": 60}}})
        self.assertEqual(watched[:2], ["golge", "sessiz-orman"])

    def test_progress_validation_and_completion(self):
        self.register()
        invalid = [
            {"id": "aurora", "position": -1, "duration": 100},
            {"id": "aurora", "position": 101, "duration": 100},
            {"id": "aurora", "position": 0, "duration": 0},
            {"id": "aurora", "position": float("nan"), "duration": 100},
            {"id": "aurora", "position": 1, "duration": float("inf")},
            {"id": "bilinmiyor", "position": 1, "duration": 100},
            {"id": "aurora", "position": True, "duration": 100},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.request("/api/progress", payload)[0], 400)
        self.assertEqual(self.request("/api/me")[1]["user"]["history"], {})
        self.assertEqual(self.request("/api/progress", {"id": "aurora", "position": 95, "duration": 100})[0], 200)
        self.assertTrue(self.request("/api/me")[1]["user"]["history"]["aurora"]["completed"])

    def test_source_and_filesystem_protection(self):
        self.assertEqual(self.request("/api/register", {
            "name": "Deneme", "email": self.email, "password": self.password,
        }, headers={"Origin": "https://untrusted.example"})[0], 403)
        self.assertEqual(self.request("/%2e%2e/server.py")[0], 403)
        self.assertEqual(self.request("/api/favorites", {"id": "aurora"})[0], 401)
        self.assertEqual(self.request("/api/progress", {"id": "aurora", "position": 1, "duration": 100})[0], 401)

    def test_password_change_preserves_current_session_and_invalidates_others(self):
        user, _ = self.register()
        self.request("/api/favorites", {"id": "aurora"})
        other, _ = self.new_client()
        self.assertEqual(self.request("/api/login", {"email": self.email, "password": self.password}, client=other)[0], 200)
        new_password = "Yeni-guvenli-parola-456"
        status, payload, _ = self.request("/api/password", {
            "currentPassword": self.password, "newPassword": new_password,
        })
        self.assertEqual(status, 200, payload)
        current = self.request("/api/me")[1]["user"]
        self.assertEqual(current["id"], user["id"])
        self.assertEqual(current["email"], self.email)
        self.assertEqual(current["name"], "Deneme Üye")
        self.assertEqual(current["favorites"], ["aurora"])
        self.assertEqual(self.request("/api/me", client=other)[0], 401)
        self.assertEqual(self.request("/api/login", {"email": self.email, "password": self.password}, client=other)[0], 401)
        self.assertEqual(self.request("/api/login", {"email": self.email, "password": new_password}, client=other)[0], 200)
        with closing(server.connect()) as db:
            stored = db.execute("SELECT password FROM users WHERE id=?", (user["id"],)).fetchone()[0]
            self.assertNotEqual(stored, new_password)

    def test_password_change_validation_and_wrong_current_password(self):
        self.assertEqual(self.request("/api/password", {"currentPassword": self.password, "newPassword": "new-password"})[0], 401)
        self.register()
        for new in ("short", "x"*129, None, ["not", "text"], self.password):
            with self.subTest(new=new):
                self.assertEqual(self.request("/api/password", {"currentPassword": self.password, "newPassword": new})[0], 400)
        self.assertEqual(self.request("/api/password", {"currentPassword": "wrong-password", "newPassword": "Valid-new-password"})[0], 401)
        self.assertEqual(self.request("/api/me")[0], 200)

    def test_password_change_rate_limit(self):
        self.register()
        for _ in range(10):
            self.assertEqual(self.request("/api/password", {"currentPassword": "wrong-password", "newPassword": "Valid-new-password"})[0], 401)
        self.assertEqual(self.request("/api/password", {"currentPassword": self.password, "newPassword": "Valid-new-password"})[0], 429)
        self.assertEqual(self.request("/api/me")[0], 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
