import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyotp
from werkzeug.security import generate_password_hash

from pos_app import create_app
from pos_app.auth import create_session
from pos_app.database import get_db
from pos_app.launcher import waitress_options
from pos_app.services.admin_two_factor import encrypt_secret
from tests.staff_helpers import staff_login


ORDER_HOST = "online.raisanngam.com"
ADMIN_HOST = "admin.raisanngam.com"


class PublicHostAccessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "public-hosts.db"),
            "POS_PUBLIC_ORDER_HOST": ORDER_HOST,
            "POS_ADMIN_HOST": ADMIN_HOST,
            "POS_TRUSTED_HOSTS": f"{ORDER_HOST},{ADMIN_HOST},lan.raisanngam.local",
            "POS_LAN_ACCESS_ENABLED": True,
            "POS_LAN_NETWORKS": "192.168.0.0/24",
        })
        self.customer = self.app.test_client()
        self.admin = self.app.test_client()
        self.lan = self.app.test_client()
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            db.commit()

    def tearDown(self):
        self.folder.cleanup()

    @staticmethod
    def host(hostname):
        return {"Host": hostname}

    @staticmethod
    def remote_base_url():
        return f"https://{ADMIN_HOST}"

    def add_manager(self):
        with self.app.app_context():
            db = get_db()
            manager_role = db.execute("SELECT id FROM roles WHERE code='manager'").fetchone()[0]
            cursor = db.execute(
                "INSERT INTO staff(display_name,pin_hash,role_id,must_change_pin) VALUES(?,?,?,0)",
                ("Remote Manager", generate_password_hash("5678"), manager_role),
            )
            db.commit()
            return cursor.lastrowid

    def enable_admin_two_factor(self):
        secret = pyotp.random_base32()
        with self.app.app_context():
            db = get_db()
            db.execute(
                """INSERT INTO staff_two_factor(staff_id,secret_encrypted,is_enabled,enabled_at)
                   VALUES(?,?,1,CURRENT_TIMESTAMP)""",
                (1, encrypt_secret(secret)),
            )
            db.commit()
        return secret

    def complete_remote_admin_login(self, secret):
        start = staff_login(
            self.admin, headers=self.host(ADMIN_HOST),
            base_url=self.remote_base_url(),
        )
        self.assertEqual(start.status_code, 302)
        self.assertTrue(start.headers["Location"].endswith("/login/2fa"))
        with self.app.app_context():
            csrf = get_db().execute(
                "SELECT csrf_token FROM staff_two_factor_challenges WHERE staff_id=1"
            ).fetchone()[0]
        return self.admin.post(
            "/login/2fa", data={"csrf_token": csrf, "code": pyotp.TOTP(secret).now()},
            headers=self.host(ADMIN_HOST), base_url=self.remote_base_url(),
        )

    def test_customer_host_allows_only_customer_routes(self):
        self.assertEqual(self.customer.get("/order", headers=self.host(ORDER_HOST)).status_code, 200)
        self.assertEqual(self.customer.get("/order/policy", headers=self.host(ORDER_HOST)).status_code, 200)
        self.assertEqual(self.customer.get("/api/auth/config", headers=self.host(ORDER_HOST)).status_code, 200)
        static_response = self.customer.get("/static/css/online.css", headers=self.host(ORDER_HOST))
        self.assertEqual(static_response.status_code, 200)
        static_response.close()
        for path in ("/login", "/", "/pos", "/online-orders", "/maintenance", "/health", "/print-agent"):
            with self.subTest(path=path):
                self.assertEqual(self.customer.get(path, headers=self.host(ORDER_HOST)).status_code, 404)

    def test_untrusted_host_is_rejected_before_routing(self):
        self.assertEqual(self.customer.get("/order", headers=self.host("not-raisanngam.example")).status_code, 400)

    def test_admin_host_blocks_customer_and_unauthenticated_utility_routes(self):
        self.assertEqual(self.admin.get("/login", headers=self.host(ADMIN_HOST)).status_code, 200)
        for path in ("/order", "/api/auth/config", "/health", "/print-agent"):
            with self.subTest(path=path):
                self.assertEqual(self.admin.get(path, headers=self.host(ADMIN_HOST)).status_code, 404)

    def test_admin_host_requires_enrolled_and_verified_two_factor(self):
        manager_id = self.add_manager()
        login_page = self.admin.get("/login", headers=self.host(ADMIN_HOST)).get_data(as_text=True)
        self.assertNotIn("Remote Manager", login_page)

        manager_login = staff_login(
            self.admin, manager_id, "5678", headers=self.host(ADMIN_HOST),
            base_url=self.remote_base_url(),
        )
        self.assertEqual(manager_login.status_code, 200)
        self.assertNotIn("pos_session=", manager_login.headers.get("Set-Cookie", ""))

        unenrolled_login = staff_login(
            self.admin, headers=self.host(ADMIN_HOST), base_url=self.remote_base_url(),
        )
        self.assertEqual(unenrolled_login.status_code, 403)
        self.assertNotIn("pos_session=", unenrolled_login.headers.get("Set-Cookie", ""))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM staff_sessions WHERE staff_id=1").fetchone()[0], 0)

        secret = self.enable_admin_two_factor()
        verified_login = self.complete_remote_admin_login(secret)
        self.assertEqual(verified_login.status_code, 302)
        self.assertIn("pos_session=", verified_login.headers["Set-Cookie"])
        self.assertEqual(
            self.admin.get("/", headers=self.host(ADMIN_HOST), base_url=self.remote_base_url()).status_code,
            200,
        )

    def test_admin_host_rejects_an_existing_manager_session(self):
        manager_id = self.add_manager()
        with self.app.test_request_context("/", base_url=f"http://{ADMIN_HOST}"):
            token = create_session(manager_id)
        self.admin.set_cookie("pos_session", token, domain=ADMIN_HOST)
        self.assertEqual(self.admin.get("/", headers=self.host(ADMIN_HOST)).status_code, 403)

    def test_admin_host_revokes_an_old_or_lan_only_admin_session(self):
        with self.app.test_request_context("/", base_url=f"http://{ADMIN_HOST}"):
            token = create_session(1)
        self.admin.set_cookie("pos_session", token, domain=ADMIN_HOST)
        response = self.admin.get("/pos", headers=self.host(ADMIN_HOST))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login?next=/pos"))
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM staff_sessions WHERE staff_id=1").fetchone()[0], 0)
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM audit_logs WHERE action='remote_admin_session_revoked_missing_two_factor'"
                ).fetchone()[0],
                1,
            )

    def test_remote_admin_cannot_disable_two_factor(self):
        secret = self.enable_admin_two_factor()
        self.assertEqual(self.complete_remote_admin_login(secret).status_code, 302)
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM staff_sessions WHERE staff_id=1").fetchone()[0]
        response = self.admin.post(
            "/account/security/disable",
            data={"csrf_token": csrf, "current_pin": "1234", "code": "000000"},
            headers=self.host(ADMIN_HOST), base_url=self.remote_base_url(),
        )
        self.assertEqual(response.status_code, 403)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT is_enabled FROM staff_two_factor WHERE staff_id=1").fetchone()[0], 1)

    def test_private_lan_staff_can_login_and_reuse_their_session(self):
        remote = {"REMOTE_ADDR": "192.168.0.50"}
        response = staff_login(
            self.lan,
            headers=self.host("192.168.0.200"),
            environ_overrides=remote,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.lan.get(
                "/pos",
                headers=self.host("192.168.0.200"),
                environ_overrides=remote,
            ).status_code,
            200,
        )

    def test_outside_configured_lan_staff_is_blocked_while_customer_and_health_remain_available(self):
        remote = {"REMOTE_ADDR": "192.168.1.50"}
        self.assertEqual(
            self.lan.get(
                "/login", headers=self.host("lan.raisanngam.local"), environ_overrides=remote,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.lan.get(
                "/order", headers=self.host("lan.raisanngam.local"), environ_overrides=remote,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.lan.get(
                "/health", headers=self.host("lan.raisanngam.local"), environ_overrides=remote,
            ).status_code,
            200,
        )

    def test_staff_login_requires_a_pre_session_csrf_token(self):
        missing = self.lan.post(
            "/login",
            data={"staff_id": "1", "pin": "1234"},
            headers=self.host("lan.raisanngam.local"),
        )
        self.assertEqual(missing.status_code, 400)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM staff_sessions").fetchone()[0], 0)
        self.assertEqual(
            staff_login(self.lan, headers=self.host("lan.raisanngam.local")).status_code,
            302,
        )

    def test_outside_configured_lan_cannot_reuse_a_staff_session(self):
        with self.app.test_request_context("/", base_url="http://lan.raisanngam.local"):
            token = create_session(1)
        self.lan.set_cookie("pos_session", token, domain="lan.raisanngam.local")
        response = self.lan.get(
            "/pos",
            headers=self.host("lan.raisanngam.local"),
            environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
        )
        self.assertEqual(response.status_code, 403)

    def test_public_hosts_must_be_distinct(self):
        with self.assertRaisesRegex(RuntimeError, "must be different"):
            create_app({
                "TESTING": True,
                "DATABASE": str(Path(self.folder.name) / "same-host.db"),
                "POS_PUBLIC_ORDER_HOST": ORDER_HOST,
                "POS_ADMIN_HOST": ORDER_HOST,
            })

    def test_public_hosts_receive_secure_cookies_and_security_headers(self):
        response = self.customer.get("/api/auth/config", headers=self.host(ORDER_HOST))
        self.assertIn("Secure", response.headers["Set-Cookie"])
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", response.headers["Set-Cookie"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])
        self.assertEqual(response.headers["Cache-Control"], "no-store, private, max-age=0")
        csp = response.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self' https://static.line-scdn.net", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertNotIn("Strict-Transport-Security", self.lan.get("/login", headers=self.host("lan.raisanngam.local")).headers)

    def test_waitress_trusts_forwarded_headers_only_from_local_connector(self):
        with patch.dict("os.environ", {"POS_TRUST_PROXY": "1", "POS_TRUSTED_PROXY": "127.0.0.1"}, clear=False):
            options = waitress_options()
        self.assertEqual(options["trusted_proxy"], "127.0.0.1")
        self.assertEqual(options["trusted_proxy_headers"], "x-forwarded-for x-forwarded-host x-forwarded-proto x-forwarded-port")
        self.assertTrue(options["clear_untrusted_proxy_headers"])

    def test_invalid_trusted_proxy_is_rejected(self):
        with patch.dict("os.environ", {"POS_TRUST_PROXY": "1", "POS_TRUSTED_PROXY": "not-an-ip"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "local Cloudflare connector"):
                waitress_options()


if __name__ == "__main__":
    unittest.main()
