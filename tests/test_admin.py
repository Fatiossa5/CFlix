"""Yeniden adlandırma sırasında eski kullanıcı verileri korunur."""
from contextlib import closing, redirect_stdout, redirect_stderr
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import create_admin
import server


class AdminMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cflix-migration-test-")
        self.original_data_dir = server.DATA_DIR
        server.DATA_DIR = Path(self.temp.name)

    def tearDown(self):
        server.DATA_DIR = self.original_data_dir
        self.temp.cleanup()

    def test_legacy_database_keeps_user_identity_password_and_activity(self):
        # Initial schema had no role column and uses the same database filename.
        with closing(sqlite3.connect(server.DATA_DIR / "fatihflix.db")) as db:
            db.execute("CREATE TABLE users (id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL)")
            db.execute("INSERT INTO users VALUES ('old-id','Eski İsim','old@example.com','salt','existing-hash')")
            db.commit()
        server.init_db()
        with closing(server.connect()) as db:
            db.execute("INSERT INTO favorites VALUES ('old-id','aurora')")
            db.execute("INSERT INTO history VALUES ('old-id','aurora',42,120,'2026-01-01',0)")
            db.commit()
        server.init_db()
        with closing(server.connect()) as db:
            user = db.execute("SELECT * FROM users WHERE id='old-id'").fetchone()
            self.assertEqual((user["name"], user["email"], user["password"], user["role"]),
                ("Eski İsim", "old@example.com", "existing-hash", "user"))
            public = server.public_user(db, user)
            self.assertEqual(public["favorites"], ["aurora"])
            self.assertEqual(public["history"]["aurora"]["position"], 42)
            self.assertTrue(all("qualities" in movie for movie in server.get_catalog(db)))

    def test_new_admin_default_preserves_legacy_admin_and_existing_accounts(self):
        server.init_db()
        with closing(server.connect()) as db:
            db.execute("INSERT INTO users VALUES ('legacy-admin','Eski Yönetici','admin@fatihflix.local','old-salt','old-hash','admin')")
            db.commit()
        with patch.object(sys, "argv", ["create_admin.py"]), redirect_stdout(io.StringIO()):
            create_admin.main()
        with closing(server.connect()) as db:
            old = dict(db.execute("SELECT * FROM users WHERE id='legacy-admin'").fetchone())
            new = dict(db.execute("SELECT * FROM users WHERE email='admin@cflix.local'").fetchone())
        self.assertEqual(old["email"], "admin@fatihflix.local")
        self.assertEqual(old["password"], "old-hash")
        self.assertEqual(old["role"], "admin")
        self.assertEqual(new["role"], "admin")
        with patch.object(sys, "argv", ["create_admin.py"]), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exit_error:
                create_admin.main()
        self.assertEqual(exit_error.exception.code, 1)
        with closing(server.connect()) as db:
            self.assertEqual(dict(db.execute("SELECT * FROM users WHERE email='admin@cflix.local'").fetchone()), new)


if __name__ == "__main__":
    unittest.main(verbosity=2)
