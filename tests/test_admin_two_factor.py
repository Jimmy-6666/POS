import re
import tempfile
import unittest
from pathlib import Path

import pyotp

from pos_app import create_app
from pos_app.database import get_db
from pos_app.services.admin_two_factor import decrypt_secret
from werkzeug.security import generate_password_hash


class AdminTwoFactorTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "two-factor.db")})
        self.client = self.app.test_client()
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            manager_role = db.execute("SELECT id FROM roles WHERE code='manager'").fetchone()[0]
            admin_role = db.execute("SELECT id FROM roles WHERE code='admin'").fetchone()[0]
            db.execute(
                "INSERT INTO staff(display_name,pin_hash,role_id,must_change_pin) VALUES(?,?,?,0)",
                ("Manager", generate_password_hash("2222"), manager_role),
            )
            db.execute(
                "INSERT INTO staff(display_name,pin_hash,role_id,must_change_pin) VALUES(?,?,?,0)",
                ("Second admin", generate_password_hash("3333"), admin_role),
            )
            db.commit()

    def tearDown(self):
        self.folder.cleanup()

    def csrf(self):
        with self.app.app_context():
            return get_db().execute("SELECT csrf_token FROM staff_sessions WHERE staff_id=1").fetchone()[0]

    def enable_two_factor(self):
        self.assertEqual(self.client.post("/login", data={"staff_id": 1, "pin": "1234"}).status_code, 302)
        setup = self.client.get("/account/security/setup")
        self.assertEqual(setup.status_code, 200)
        self.assertIn(b"data:image/svg+xml;base64,", setup.data)
        with self.app.app_context():
            db = get_db()
            encrypted = db.execute(
                "SELECT pending_secret_encrypted FROM staff_two_factor WHERE staff_id=1"
            ).fetchone()[0]
            secret = decrypt_secret(encrypted)
            self.assertNotIn(secret, encrypted)
        response = self.client.post(
            "/account/security/enable",
            data={"csrf_token": self.csrf(), "code": pyotp.TOTP(secret).now()},
        )
        self.assertEqual(response.status_code, 200)
        codes = re.findall(r"<code>([A-Z0-9]{4}-[A-Z0-9]{4})</code>", response.get_data(as_text=True))
        self.assertEqual(len(codes), 10)
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff_two_factor SET last_totp_counter=NULL WHERE staff_id=1")
            db.commit()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        return secret, codes

    def test_non_admin_login_and_security_route_are_unchanged(self):
        response = self.client.post("/login", data={"staff_id": 2, "pin": "2222"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM staff_sessions WHERE staff_id=2").fetchone()[0], 1)
        self.assertEqual(self.client.get("/account/security").status_code, 403)

    def test_admin_session_waits_for_totp_and_replay_is_rejected(self):
        secret, codes = self.enable_two_factor()
        first = self.client.post("/login", data={"staff_id": 1, "pin": "1234"})
        self.assertTrue(first.headers["Location"].endswith("/login/2fa"))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM staff_sessions WHERE staff_id=1").fetchone()[0], 0)
            csrf = get_db().execute("SELECT csrf_token FROM staff_two_factor_challenges WHERE staff_id=1").fetchone()[0]
        code = pyotp.TOTP(secret).now()
        verified = self.client.post("/login/2fa", data={"csrf_token": csrf, "code": code})
        self.assertEqual(verified.status_code, 302)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM staff_sessions WHERE staff_id=1").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_logs WHERE action='admin_login_success'").fetchone()[0], 1)
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.client.post("/login", data={"staff_id": 1, "pin": "1234"})
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM staff_two_factor_challenges WHERE staff_id=1").fetchone()[0]
        rejected = self.client.post("/login/2fa", data={"csrf_token": csrf, "code": code})
        self.assertEqual(rejected.status_code, 200)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM staff_sessions WHERE staff_id=1").fetchone()[0], 0)

    def test_recovery_code_is_single_use_and_rate_limit_never_logs_code(self):
        _, codes = self.enable_two_factor()
        recovery = codes[0]
        self.client.post("/login", data={"staff_id": 1, "pin": "1234"})
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM staff_two_factor_challenges WHERE staff_id=1").fetchone()[0]
        self.assertEqual(self.client.post("/login/2fa", data={"csrf_token": csrf, "code": recovery}).status_code, 302)
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.client.post("/login", data={"staff_id": 1, "pin": "1234"})
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM staff_two_factor_challenges WHERE staff_id=1").fetchone()[0]
        self.assertEqual(self.client.post("/login/2fa", data={"csrf_token": csrf, "code": recovery}).status_code, 200)
        for _ in range(4):
            self.client.post("/login/2fa", data={"csrf_token": csrf, "code": "000000"})
        limited = self.client.post("/login/2fa", data={"csrf_token": csrf, "code": "000000"})
        self.assertEqual(limited.status_code, 429)
        with self.app.app_context():
            values = [row[0] or "" for row in get_db().execute(
                "SELECT new_value FROM audit_logs WHERE action='admin_two_factor_failed'"
            ).fetchall()]
            self.assertFalse(any(recovery in value or "000000" in value for value in values))

    def test_disable_requires_pin_and_second_factor(self):
        secret, codes = self.enable_two_factor()
        self.assertEqual(self.client.post("/login", data={"staff_id": 1, "pin": "1234"}).status_code, 302)
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM staff_two_factor_challenges WHERE staff_id=1").fetchone()[0]
        self.client.post("/login/2fa", data={"csrf_token": csrf, "code": pyotp.TOTP(secret).now()})
        response = self.client.post(
            "/account/security/disable",
            data={"csrf_token": self.csrf(), "current_pin": "1234", "code": "000000"},
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT is_enabled FROM staff_two_factor WHERE staff_id=1").fetchone()[0], 1)
        disabled = self.client.post(
            "/account/security/disable",
            data={"csrf_token": self.csrf(), "current_pin": "1234", "code": codes[0]},
        )
        self.assertEqual(disabled.status_code, 302)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT is_enabled FROM staff_two_factor WHERE staff_id=1").fetchone()[0], 0)
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.assertTrue(self.client.post("/login", data={"staff_id": 1, "pin": "1234"}).headers["Location"].endswith("/pos"))


if __name__ == "__main__":
    unittest.main()
