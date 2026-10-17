"""Durable feedback delivery tests. SMTP is always mocked; no real mail is sent."""
from contextlib import closing, redirect_stdout
import http.cookiejar
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import retry_feedback
import server


class FeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="cflix-feedback-test-")
        cls.original_data_dir = server.DATA_DIR
        server.DATA_DIR = Path(cls.temp.name)
        server.init_db()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.worker = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close(); cls.worker.join(timeout=5)
        server.DATA_DIR = cls.original_data_dir
        server.SESSIONS.clear(); server.ATTEMPTS.clear()
        cls.temp.cleanup()

    def setUp(self):
        recipient = patch.object(server, "FEEDBACK_RECIPIENT", "feedback@example.test")
        recipient.start()
        self.addCleanup(recipient.stop)
        self.environment = patch.dict(os.environ,
            {key: value for key, value in os.environ.items() if not key.startswith("SMTP_")}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        # Catch accidental delivery even if a test forgets to configure its own mock.
        self.network_guard = patch.object(server.smtplib, "SMTP", side_effect=AssertionError("Real SMTP forbidden in tests"))
        self.ssl_guard = patch.object(server.smtplib, "SMTP_SSL", side_effect=AssertionError("Real SMTP forbidden in tests"))
        self.network_guard.start(); self.ssl_guard.start()
        self.addCleanup(self.network_guard.stop); self.addCleanup(self.ssl_guard.stop)
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        status, user = self.request("/api/register", {"name": "Test Üye", "email": f"{uuid.uuid4().hex}@example.com", "password": "test-password-123"})
        self.assertEqual(status, 200)
        self.user_id = user["user"]["id"]
        with closing(server.connect()) as db:
            db.execute("DELETE FROM feedback_outbox")
            db.commit()

    def request(self, path, data=None, anonymous=False):
        req = urllib.request.Request(self.base+path, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type": "application/json"})
        try:
            response = (urllib.request.build_opener() if anonymous else self.client).open(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def submit(self, **changes):
        return self.request("/api/feedback", {"kind": "suggestion", "subject": "Yeni içerik", "message": "Daha fazla belgesel eklenmesini öneriyorum.", **changes})

    def row(self, feedback_id):
        with closing(server.connect()) as db:
            return dict(db.execute("SELECT * FROM feedback_outbox WHERE id=?", (feedback_id,)).fetchone())

    def configure(self, **changes):
        os.environ.update({"SMTP_HOST": "smtp.example.test", "SMTP_PORT": "587", "SMTP_FROM": "sender@example.test",
            "SMTP_USERNAME": "private-user", "SMTP_PASSWORD": "private-password", "SMTP_STARTTLS": "1", **changes})

    def seed_feedback(self, status="queued", attempts=0, last_attempt=None):
        feedback_id = uuid.uuid4().hex
        with closing(server.connect()) as db:
            db.execute("INSERT INTO feedback_outbox (id,user_id,kind,subject,message,sender_name,sender_email,status,created_at,attempts,last_attempt) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (feedback_id, self.user_id, "suggestion", "Test", "Yeterli uzunlukta mesaj", "Test Üye", "member@example.com", status, "2026-01-01", attempts, last_attempt))
            db.commit()
        return feedback_id

    def test_health_is_public_versioned_and_contains_no_private_configuration(self):
        self.configure()
        status, payload = self.request("/api/health", anonymous=True)
        self.assertEqual(status, 200)
        self.assertEqual(payload["app"], "CFlix")
        self.assertRegex(payload["version"], r"^\d{4}\.\d{2}\.\d{2}\.\d+$")
        self.assertTrue({"feedback", "password", "gmail-smtp"}.issubset(payload["features"]))
        self.assertEqual(set(payload), {"app", "version", "features"})

    def test_feedback_requires_membership_and_validates_metadata(self):
        self.assertEqual(self.request("/api/feedback", {"kind": "suggestion", "message": "Yeterli uzunlukta bir mesaj"}, anonymous=True)[0], 401)
        for changes in ({"kind": "other"}, {"message": "short"}, {"message": "x"*4001},
                {"message": None}, {"subject": "x"*121}, {"subject": "bad\nheader"}, {"subject": []}):
            with self.subTest(changes=changes):
                self.assertEqual(self.submit(**changes)[0], 400)
        with closing(server.connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM feedback_outbox WHERE user_id=?", (self.user_id,)).fetchone()[0], 0)

    def test_missing_smtp_queues_persistently_without_claiming_delivery(self):
        status, payload = self.submit(kind="complaint")
        self.assertEqual(status, 202)
        self.assertEqual(payload["status"], "queued")
        self.assertIn("henüz yapılandırılmadı", payload["message"])
        self.assertEqual(payload["code"], "smtp_not_configured")
        self.assertNotIn(server.FEEDBACK_RECIPIENT, json.dumps(payload))
        row = self.row(payload["id"])
        self.assertEqual((row["status"], row["kind"], row["attempts"]), ("queued", "complaint", 0))
        server.init_db()
        self.assertEqual(self.row(payload["id"])["message"], row["message"])

    def test_feedback_rate_limit_does_not_create_extra_outbox_rows(self):
        for _ in range(5):
            self.assertEqual(self.submit()[0], 202)
        status, payload = self.submit()
        self.assertEqual(status, 429)
        self.assertEqual(payload["code"], "feedback_rate_limited")
        with closing(server.connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM feedback_outbox WHERE user_id=?", (self.user_id,)).fetchone()[0], 5)

    def test_starttls_delivery_authenticates_and_returns_sent(self):
        self.configure()
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.__enter__.return_value = smtp
        with patch.object(server.smtplib, "SMTP", return_value=smtp) as factory:
            status, payload = self.submit()
        self.assertEqual((status, payload["status"]), (201, "sent"))
        factory.assert_called_once_with("smtp.example.test", 587, timeout=10)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("private-user", "private-password")
        calls = [call[0] for call in smtp.method_calls]
        self.assertLess(calls.index("starttls"), calls.index("login"))
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], server.FEEDBACK_RECIPIENT)
        self.assertIn("belgesel", message.get_content())
        self.assertEqual(self.row(payload["id"])["status"], "sent")
        for secret in (server.FEEDBACK_RECIPIENT, "private-user", "private-password"):
            self.assertNotIn(secret, json.dumps(payload))

    def test_delivery_error_stays_queued_and_hides_exception_details(self):
        self.configure()
        with patch.object(server.smtplib, "SMTP", side_effect=OSError("private-password " + server.FEEDBACK_RECIPIENT)):
            status, payload = self.submit()
        self.assertEqual((status, payload["status"]), (202, "queued"))
        row = self.row(payload["id"])
        self.assertEqual((row["attempts"], row["error_code"]), (1, "smtp_unreachable"))
        self.assertNotIn("private-password", json.dumps(payload))
        self.assertNotIn(server.FEEDBACK_RECIPIENT, json.dumps(payload))

    def test_gmail_authentication_failure_is_actionable_without_exposing_credentials(self):
        self.configure(SMTP_HOST="smtp.gmail.com", SMTP_USERNAME="sender@example.test", SMTP_PASSWORD="abcd efgh ijkl mnop")
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.login.side_effect = server.smtplib.SMTPAuthenticationError(535, b"sensitive provider detail")
        with patch.object(server.smtplib, "SMTP", return_value=smtp):
            status, payload = self.submit()
        self.assertEqual((status, payload["code"]), (202, "smtp_auth_failed"))
        smtp.login.assert_called_once_with("sender@example.test", "abcdefghijklmnop")
        self.assertEqual(self.row(payload["id"])["error_code"], "smtp_auth_failed")
        self.assertNotIn("sensitive provider detail", json.dumps(payload))
        self.assertNotIn("abcdefghijklmnop", json.dumps(payload))

    def test_smtp_delivery_refusal_uses_generic_safe_code(self):
        self.configure()
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.send_message.side_effect = server.smtplib.SMTPDataError(554, b"sensitive rejection")
        with patch.object(server.smtplib, "SMTP", return_value=smtp):
            status, payload = self.submit()
        self.assertEqual((status, payload["code"]), (202, "smtp_delivery_failed"))
        self.assertNotIn("sensitive rejection", json.dumps(payload))

    def test_mail_status_requires_admin_and_reports_only_safe_aggregates(self):
        self.assertEqual(self.request("/api/admin/mail-status", anonymous=True)[0], 401)
        self.assertEqual(self.request("/api/admin/mail-status")[0], 403)
        feedback_id = self.submit()[1]["id"]
        with closing(server.connect()) as db:
            db.execute("UPDATE users SET role='admin' WHERE id=?", (self.user_id,))
            db.commit()
        status, payload = self.request("/api/admin/mail-status")
        self.assertEqual(status, 200)
        self.assertEqual(set(payload), {"configured", "provider", "queued", "sent", "lastErrorCode", "safeMessage"})
        self.assertEqual((payload["configured"], payload["queued"], payload["sent"], payload["lastErrorCode"]), (False, 1, 0, "smtp_not_configured"))
        self.configure(SMTP_HOST="smtp.gmail.com")
        with closing(server.connect()) as db:
            db.execute("UPDATE feedback_outbox SET attempts=1,last_attempt=?,error_code='smtp_auth_failed' WHERE id=?", (time.time(), feedback_id))
            db.commit()
        payload = self.request("/api/admin/mail-status")[1]
        self.assertEqual(payload["provider"], "gmail")
        self.assertTrue(payload["configured"])
        self.assertEqual(payload["lastErrorCode"], "smtp_auth_failed")
        self.assertIn("uygulama şifresini", payload["safeMessage"])
        for secret in (server.FEEDBACK_RECIPIENT, "private-user", "private-password", "sender@example.test"):
            self.assertNotIn(secret, json.dumps(payload))

    def test_ssl_retry_sends_queued_item_once(self):
        feedback_id = self.submit()[1]["id"]
        self.configure(SMTP_SSL="1", SMTP_PORT="465")
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.__enter__.return_value = smtp
        with patch.object(server.smtplib, "SMTP_SSL", return_value=smtp) as factory:
            self.assertEqual(server.deliver_feedback(feedback_id), "sent")
            self.assertEqual(server.deliver_feedback(feedback_id), "sent")
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(smtp.send_message.call_count, 1)
        smtp.starttls.assert_not_called()
        self.assertEqual(self.row(feedback_id)["attempts"], 1)

    def test_retry_cli_without_smtp_leaves_outbox_unchanged(self):
        feedback_id = self.submit()[1]["id"]
        with patch.object(sys, "argv", ["retry_feedback.py"]), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                retry_feedback.main()
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(self.row(feedback_id)["status"], "queued")

    def test_background_batch_honors_backoff_and_active_leases(self):
        self.configure()
        now = time.time()
        due = self.seed_feedback(attempts=1, last_attempt=now-100)
        recent = self.seed_feedback(attempts=1, last_attempt=now-30)
        repeated = self.seed_feedback(attempts=4, last_attempt=now-300)
        active = self.seed_feedback(status="sending", attempts=1, last_attempt=now-200)
        stale = self.seed_feedback(status="sending", attempts=1, last_attempt=now-400)
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.__enter__.return_value = smtp
        with patch.object(server.smtplib, "SMTP", return_value=smtp):
            self.assertEqual(server.retry_feedback_batch(threading.Event()), 2)
        self.assertEqual(smtp.send_message.call_count, 2)
        self.assertEqual(self.row(due)["status"], "sent")
        self.assertEqual(self.row(stale)["status"], "sent")
        self.assertEqual(self.row(recent)["attempts"], 1)
        self.assertEqual(self.row(repeated)["attempts"], 4)
        self.assertEqual(self.row(active)["status"], "sending")

    def test_background_batch_is_capped_at_five_and_stops_on_shutdown(self):
        self.configure()
        ids = [self.seed_feedback() for _ in range(6)]
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.__enter__.return_value = smtp
        with patch.object(server.smtplib, "SMTP", return_value=smtp):
            self.assertEqual(server.retry_feedback_batch(threading.Event(), limit=100), 5)
        self.assertEqual(sum(self.row(item)["status"] == "sent" for item in ids), 5)
        stop = threading.Event()
        stop.set()
        self.assertEqual(server.retry_feedback_batch(stop), 0)

    def test_worker_requires_smtp_and_waits_interruptibly_between_batches(self):
        with patch.object(server.threading, "Thread") as thread_factory:
            self.assertIsNone(server.start_feedback_worker(threading.Event()))
            thread_factory.assert_not_called()
        stop = MagicMock()
        stop.is_set.return_value = False
        stop.wait.return_value = True
        with patch.object(server, "retry_feedback_batch") as batch:
            server.feedback_worker(stop)
        batch.assert_called_once_with(stop)
        stop.wait.assert_called_once_with(60)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        recipient = patch.object(server, "FEEDBACK_RECIPIENT", "feedback@example.test")
        recipient.start()
        self.addCleanup(recipient.stop)

    def test_missing_or_invalid_recipient_disables_delivery(self):
        for value in ("", "invalid", "bad\n@example.test"):
            with patch.object(server, "FEEDBACK_RECIPIENT", value):
                self.assertIsNone(server.smtp_config())

    def test_gmail_defaults_and_app_password_spacing(self):
        with patch.dict(os.environ, {"SMTP_PROVIDER": "gmail", "SMTP_USERNAME": "sender@example.test", "SMTP_PASSWORD": "abcd efgh ijkl mnop"}, clear=True):
            config = server.smtp_config()
            self.assertEqual((config["host"], config["port"], config["provider"]), ("smtp.gmail.com", 587, "gmail"))
            self.assertTrue(config["starttls"])
            self.assertFalse(config["use_ssl"])
            self.assertEqual(config["password"], "abcdefghijklmnop")
            self.assertEqual(config["sender"], "sender@example.test")

    def test_generic_smtp_password_whitespace_is_preserved(self):
        with patch.dict(os.environ, {"SMTP_HOST": "smtp.example.test", "SMTP_FROM": "sender@example.test", "SMTP_USERNAME": "user", "SMTP_PASSWORD": "has spaces"}, clear=True):
            config = server.smtp_config()
            self.assertEqual(config["password"], "has spaces")
            self.assertEqual(config["provider"], "smtp")

    def test_local_env_loader_preserves_process_configuration_and_literal_password(self):
        with tempfile.TemporaryDirectory(prefix="cflix-env-test-") as temp:
            path = Path(temp) / ".env"
            path.write_text('# comment\nSMTP_HOST=file-host\nSMTP_PASSWORD="literal#value"\nINVALID KEY=ignored\n', encoding="utf-8")
            with patch.dict(os.environ, {"SMTP_HOST": "process-host"}, clear=True):
                server.load_local_env(path)
                self.assertEqual(os.environ["SMTP_HOST"], "process-host")
                self.assertEqual(os.environ["SMTP_PASSWORD"], "literal#value")
                self.assertNotIn("INVALID KEY", os.environ)

    def test_lan_urls_exclude_wildcard_and_loopback_duplicates(self):
        with patch.object(server.socket, "gethostbyname_ex", return_value=("pc", [], ["127.0.0.1", "192.168.1.5", "192.168.1.5"])):
            self.assertEqual(server.local_urls("0.0.0.0", 3000), ["http://localhost:3000", "http://192.168.1.5:3000"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
