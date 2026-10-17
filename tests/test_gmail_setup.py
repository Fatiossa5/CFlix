"""Local Gmail setup helper tests. Network access is always mocked."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch, sentinel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_gmail


class GmailSetupTests(unittest.TestCase):
    def test_gmail_values_normalizes_app_password_groups_and_username(self):
        values = setup_gmail.gmail_values(" sender@example.com ", "abcd efgh\tijkl\nmnop")
        self.assertEqual(values["SMTP_USERNAME"], "sender@example.com")
        self.assertEqual(values["SMTP_FROM"], "sender@example.com")
        self.assertEqual(values["SMTP_PASSWORD"], "abcdefghijklmnop")
        self.assertEqual((values["SMTP_HOST"], values["SMTP_PORT"], values["SMTP_STARTTLS"], values["SMTP_SSL"]),
            ("smtp.gmail.com", "587", "1", "0"))

    def test_gmail_values_rejects_invalid_email_and_non_app_password(self):
        for email, password in (("invalid", "abcdefghijklmnop"), ("bad\n@example.com", "abcdefghijklmnop"),
                ("sender@example.com", "short-pass"), ("sender@example.com", ""),
                ("sender@example.com", "abcdefghijklmnopq"), ("sender@example.com", "abcdefghijklmn!@")):
            with self.subTest(email=email, password_length=len(password)):
                with self.assertRaises(ValueError):
                    setup_gmail.gmail_values(email, password)

    def test_save_preserves_unrelated_settings_and_removes_every_duplicate_key(self):
        values = setup_gmail.gmail_values("sender@example.com", "abcdefghijklmnop")
        with tempfile.TemporaryDirectory(prefix="cflix-gmail-save-") as temp:
            path = Path(temp) / ".env"
            old_lines = ["# Keep this comment", "HOST=127.0.0.1", "PORT=4567", "CUSTOM_SETTING=keep"]
            for key in values:
                old_lines.extend([f"{key}=old-one", f" export {key} =old-two"])
            path.write_text("\ufeff" + "\r\n".join(old_lines), encoding="utf-8")
            setup_gmail.save_values(values, path)
            lines = path.read_text(encoding="utf-8").splitlines()
            for unchanged in old_lines[:4]:
                self.assertIn(unchanged, lines)
            for key, value in values.items():
                matching = [line for line in lines if line.strip().removeprefix("export ").partition("=")[0].strip() == key]
                self.assertEqual(matching, [f"{key}={value}"])
            self.assertFalse((Path(temp) / ".env.tmp").exists())

    def test_failed_atomic_replace_keeps_original_and_cleans_temporary_file(self):
        values = setup_gmail.gmail_values("sender@example.com", "abcdefghijklmnop")
        with tempfile.TemporaryDirectory(prefix="cflix-gmail-atomic-") as temp:
            path = Path(temp) / ".env"
            original = "HOST=127.0.0.1\nPORT=3001\n"
            path.write_text(original, encoding="utf-8")
            with patch.object(setup_gmail.Path, "replace", side_effect=OSError("simulated file replacement failure")):
                with self.assertRaises(OSError):
                    setup_gmail.save_values(values, path)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertFalse((Path(temp) / ".env.tmp").exists())

    def test_verify_login_negotiates_tls_before_authentication_and_never_sends_mail(self):
        values = setup_gmail.gmail_values("sender@example.com", "abcdefghijklmnop")
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        with (patch.object(setup_gmail.smtplib, "SMTP", return_value=smtp) as factory,
                patch.object(setup_gmail.ssl, "create_default_context", return_value=sentinel.tls_context)):
            setup_gmail.verify_login(values)
        factory.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
        self.assertEqual(smtp.method_calls, [call.ehlo(), call.starttls(context=sentinel.tls_context),
            call.ehlo(), call.login("sender@example.com", "abcdefghijklmnop")])
        smtp.send_message.assert_not_called()
        smtp.sendmail.assert_not_called()

    def test_verify_login_propagates_authentication_failure_without_sending(self):
        values = setup_gmail.gmail_values("sender@example.com", "abcdefghijklmnop")
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.login.side_effect = setup_gmail.smtplib.SMTPAuthenticationError(535, b"test refusal")
        with (patch.object(setup_gmail.smtplib, "SMTP", return_value=smtp),
                patch.object(setup_gmail.ssl, "create_default_context", return_value=sentinel.tls_context)):
            with self.assertRaises(setup_gmail.smtplib.SMTPAuthenticationError):
                setup_gmail.verify_login(values)
        smtp.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
