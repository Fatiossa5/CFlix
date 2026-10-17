"""Yerel Gmail formunun HTTP akışı; SMTP ve dosya yazımı taklit edilir."""
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_gmail_window as window


class GmailWindowTests(unittest.TestCase):
    def setUp(self):
        recipient = patch.object(window.server, "FEEDBACK_RECIPIENT", "feedback@example.test")
        recipient.start()
        self.addCleanup(recipient.stop)
        self.httpd = window.make_server()
        self.worker = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.worker.start()
        self.origin = f"http://127.0.0.1:{self.httpd.server_port}"
        self.base = self.origin+self.httpd.setup_path

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.worker.join(timeout=3)

    def request(self, action="", data=None, headers=None):
        req = urllib.request.Request(self.base+action,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json", "Origin": self.origin, **(headers or {})})
        try:
            response = urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read().decode(), response.headers

    def test_real_html_contains_both_fields_without_waiting_for_console_input(self):
        with patch.object(window, "verify_login") as smtp:
            status, text, headers = self.request()
        self.assertEqual(status, 200)
        self.assertIn('Gönderici Gmail adresi', text)
        self.assertIn('id="email" name="email" type="email"', text)
        self.assertIn('id="password" name="password" type="password"', text)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn(window.server.FEEDBACK_RECIPIENT, text)
        smtp.assert_not_called()
        self.assertEqual(self.httpd.server_address[0], '127.0.0.1')

    def test_configure_accepts_visible_form_values_and_unlocks_send(self):
        with patch.object(window, 'configure_account') as configure:
            status, text, _ = self.request('configure', {'email':'sender@example.com','password':'abcdefghijklmnop'})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(text)['ok'])
        configure.assert_called_once_with('sender@example.com','abcdefghijklmnop')
        self.assertTrue(self.httpd.configured)
        with patch.object(window, 'send_pending', return_value=(1,0)) as send:
            status, text, _ = self.request('send', {})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text), {'sent':1,'pending':0})
        send.assert_called_once()

    def test_send_is_blocked_until_setup_was_verified(self):
        with patch.object(window, 'send_pending') as send:
            status, _, _ = self.request('send', {})
        self.assertEqual(status, 400)
        send.assert_not_called()

    def test_authentication_failure_shows_safe_message_and_keeps_send_locked(self):
        with patch.object(window,'configure_account',side_effect=window.smtplib.SMTPAuthenticationError(535,b'private diagnostic')):
            status, text, _ = self.request('configure', {'email':'sender@example.com','password':'abcdefghijklmnop'})
        self.assertEqual(status, 400)
        self.assertIn('Uygulama Şifresini', json.loads(text)['error'])
        self.assertNotIn('private diagnostic', text)
        self.assertNotIn('abcdefghijklmnop', text)
        self.assertFalse(self.httpd.configured)

    def test_random_path_and_host_are_required(self):
        self.assertEqual(self.request('missing')[0], 404)
        self.assertEqual(self.request(headers={'Host':'untrusted.example'})[0],404)
        req = urllib.request.Request(self.base+'configure', data=b'', headers={'Origin':'https://untrusted.example'})
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(req,timeout=3)
        self.assertEqual(context.exception.code,403)
        context.exception.close()

    def test_busy_setup_does_not_start_a_second_operation(self):
        self.httpd.action_lock.acquire()
        try:
            with patch.object(window,'configure_account') as configure:
                status, _, _ = self.request('configure', {'email':'sender@example.com','password':'abcdefghijklmnop'})
            self.assertEqual(status,409)
            configure.assert_not_called()
        finally:
            self.httpd.action_lock.release()


if __name__ == '__main__':
    unittest.main()
