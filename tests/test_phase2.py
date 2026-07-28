import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from werkzeug.security import check_password_hash

from pos_app import create_app
from pos_app.auth import iso_time, permission_required, utc_now
from pos_app.database import get_db


class Phase2Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "phase2.db"),
            "SESSION_TIMEOUT_MINUTES": 30,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.folder.cleanup()

    def login(self, pin="1234"):
        return self.client.post("/login", data={"staff_id": "1", "pin": pin}, follow_redirects=False)

    def csrf(self):
        with self.app.app_context():
            return get_db().execute(
                "SELECT csrf_token FROM staff_sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]

    def test_default_pin_is_hashed_and_roles_are_seeded(self):
        with self.app.app_context():
            db = get_db()
            staff = db.execute("SELECT pin_hash, must_change_pin FROM staff WHERE id = 1").fetchone()
            self.assertNotEqual(staff["pin_hash"], "1234")
            self.assertTrue(check_password_hash(staff["pin_hash"], "1234"))
            self.assertEqual(staff["must_change_pin"], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM roles").fetchone()[0], 3)

    def test_login_page_has_touch_numpad(self):
        html = self.client.get("/login").get_data(as_text=True)
        self.assertIn('class="login-numpad"', html)
        self.assertIn('data-pin-action="backspace"', html)
        self.assertIn('data-pin-action="clear"', html)

    def test_login_forces_pin_change_then_allows_dashboard(self):
        self.assertEqual(self.login().status_code, 302)
        self.assertTrue(self.client.get("/").headers["Location"].endswith("/change-pin"))
        response = self.client.post("/change-pin", data={
            "csrf_token": self.csrf(), "current_pin": "1234",
            "new_pin": "2468", "confirm_pin": "2468",
        })
        self.assertTrue(response.headers["Location"].endswith("/pos"))
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_invalid_login_is_logged(self):
        response = self.login("9999")
        self.assertIn("ไม่ถูกต้อง", response.get_data(as_text=True))
        with self.app.app_context():
            event = get_db().execute("SELECT event_type FROM login_events").fetchone()[0]
            self.assertEqual(event, "login_failed")

    def test_logout_requires_csrf_and_removes_server_session(self):
        self.login()
        self.assertEqual(self.client.post("/logout", data={"csrf_token": "wrong"}).status_code, 400)
        self.assertEqual(self.client.post("/logout", data={"csrf_token": self.csrf()}).status_code, 302)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM staff_sessions").fetchone()[0], 0)

    def test_staff_cookie_is_secure_only_for_https_requests(self):
        local_cookie = self.login().headers["Set-Cookie"]
        self.assertNotIn("Secure", local_cookie)
        secure_app = create_app({
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "https-phase2.db"),
            "POS_TRUST_PROXY": True,
        })
        secure_cookie = secure_app.test_client().post(
            "/login", data={"staff_id": "1", "pin": "1234"},
            headers={"X-Forwarded-Proto": "https"}, follow_redirects=False,
        ).headers["Set-Cookie"]
        self.assertIn("Secure", secure_cookie)

    def test_expired_session_is_rejected(self):
        self.login()
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff_sessions SET expires_at = ?", (iso_time(utc_now() - timedelta(minutes=1)),))
            db.commit()
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_permission_decorator_rejects_cashier(self):
        @self.app.get("/admin-test")
        @permission_required("staff.manage")
        def admin_test():
            return "ok"

        with self.app.app_context():
            db = get_db()
            cashier_role = db.execute("SELECT id FROM roles WHERE code = 'cashier'").fetchone()[0]
            db.execute("UPDATE staff SET role_id = ?, must_change_pin = 0 WHERE id = 1", (cashier_role,))
            db.commit()
        self.login()
        self.assertEqual(self.client.get("/admin-test").status_code, 403)


if __name__ == "__main__":
    unittest.main()
