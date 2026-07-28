import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pos_app import create_app
from pos_app.database import get_db
from pos_app.services.line_login import LineLoginError


class LineAuthTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "line.db"),
            "PROJECT_ROOT": self.folder.name,
            "LINE_LIFF_ID": "1234567890-abcdef",
            "LINE_LOGIN_CHANNEL_ID": "1234567890",
            "APP_BASE_URL": "https://orders.example.test",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.folder.cleanup()

    def auth_config(self):
        response = self.client.get("/api/auth/config")
        self.assertTrue(response.get_json()["configured"])
        return response.get_json()

    def login(self, line_user_id="U0123456789abcdef0123456789abcdef"):
        config = self.auth_config()
        verified = {"line_user_id": line_user_id, "display_name": "ลูกค้า LINE", "picture_url": "https://example.test/avatar.jpg"}
        with patch("pos_app.routes.line_auth.verify_id_token", return_value=verified) as verify:
            response = self.client.post(
                "/api/auth/line", json={"idToken": "real-token-is-never-stored"},
                headers={"X-CSRF-Token": config["csrfToken"]},
            )
        verify.assert_called_once_with("real-token-is-never-stored", "1234567890")
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_verified_line_identity_creates_customer_and_pos_session(self):
        payload = self.login()
        self.assertTrue(payload["authenticated"])
        self.assertFalse(payload["customer"]["profileComplete"])
        with self.app.app_context():
            customer = get_db().execute("SELECT * FROM customers").fetchone()
            self.assertEqual(customer["line_user_id"], "U0123456789abcdef0123456789abcdef")
            self.assertEqual(customer["line_display_name"], "ลูกค้า LINE")
            self.assertEqual(customer["line_picture_url"], "https://example.test/avatar.jpg")
            self.assertTrue(customer["phone_normalized"].startswith("line:"))
        me = self.client.get("/api/auth/me").get_json()
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["customer"]["lineUserId"], "U0123456789abcdef0123456789abcdef")

    def test_rejected_token_never_creates_a_customer(self):
        config = self.auth_config()
        with patch("pos_app.routes.line_auth.verify_id_token", side_effect=LineLoginError("invalid")):
            response = self.client.post("/api/auth/line", json={"idToken": "modified-token"}, headers={"X-CSRF-Token": config["csrfToken"]})
        self.assertEqual(response.status_code, 401)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM customers").fetchone()[0], 0)

    def test_profile_requires_phone_confirmation_before_completion_and_logout(self):
        login = self.login()
        with self.app.app_context():
            get_db().execute("INSERT INTO delivery_locations(name,room_required) VALUES('รีสอร์ต',1)")
            get_db().commit()
        profile = {
            "csrf_token": login["csrfToken"], "phone": "0812345678", "delivery_location_id": "1", "room_reference": "A101",
        }
        review = self.client.post("/order/profile", data=profile)
        self.assertEqual(review.status_code, 200)
        self.assertIn("กรุณาตรวจสอบเบอร์อีกครั้ง", review.get_data(as_text=True))
        self.assertIn("แก้ไข", review.get_data(as_text=True))
        self.assertIn("ยืนยัน", review.get_data(as_text=True))
        with self.app.app_context():
            customer = get_db().execute("SELECT phone_normalized,profile_completed FROM customers").fetchone()
            self.assertTrue(customer["phone_normalized"].startswith("line:"))
            self.assertFalse(customer["profile_completed"])
        response = self.client.post("/order/profile", data={**profile, "profile_action": "confirm"})
        self.assertEqual(response.status_code, 302)
        me = self.client.get("/api/auth/me").get_json()
        self.assertTrue(me["customer"]["profileComplete"])
        self.assertEqual(self.client.post("/api/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/logout", headers={"X-CSRF-Token": login["csrfToken"]}).status_code, 200)
        self.assertFalse(self.client.get("/api/auth/me").get_json()["authenticated"])

    def test_profile_duplicate_phone_has_a_friendly_thai_error(self):
        login = self.login()
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT INTO delivery_locations(name) VALUES('จุดรับสินค้า')")
            db.execute(
                """INSERT INTO customers
                   (public_id,phone_normalized,pin_hash,is_guest,created_at,updated_at)
                   VALUES('existing-customer','0812345678','retired-pin',0,'2026-07-28','2026-07-28')"""
            )
            db.commit()
        profile = {
            "csrf_token": login["csrfToken"], "phone": "0812345678", "delivery_location_id": "1", "room_reference": "A101",
        }
        self.assertEqual(self.client.post("/order/profile", data=profile).status_code, 200)
        response = self.client.post("/order/profile", data={**profile, "profile_action": "confirm"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("หมายเลขโทรศัพท์นี้ถูกใช้กับบัญชีลูกค้าอื่นแล้ว", response.get_data(as_text=True))
        self.assertNotIn("UNIQUE constraint failed", response.get_data(as_text=True))

    def test_retired_phone_pin_routes_and_guest_order_are_rejected(self):
        self.assertEqual(self.client.get("/order/login").status_code, 410)
        self.assertEqual(self.client.get("/order/register").status_code, 410)
        self.assertEqual(self.client.post("/order/api/orders", json={}).status_code, 401)

    def test_suspended_customer_is_rejected_without_a_new_session(self):
        self.login()
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE customers SET is_active=0 WHERE id=1")
            db.commit()
        config = self.auth_config()
        verified = {
            "line_user_id": "U0123456789abcdef0123456789abcdef",
            "display_name": "LINE customer",
            "picture_url": None,
        }
        with patch("pos_app.routes.line_auth.verify_id_token", return_value=verified):
            response = self.client.post(
                "/api/auth/line", json={"idToken": "real-token-is-never-stored"},
                headers={"X-CSRF-Token": config["csrfToken"]},
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "suspended")
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM customer_login_events WHERE event_type='login_failed'").fetchone()[0], 0)

    def test_line_login_rate_limit_is_configurable(self):
        self.app.config["LINE_LOGIN_FAILURE_LIMIT"] = 2
        config = self.auth_config()
        with patch("pos_app.routes.line_auth.verify_id_token", side_effect=LineLoginError("invalid")):
            for _ in range(2):
                response = self.client.post(
                    "/api/auth/line", json={"idToken": "modified-token"},
                    headers={"X-CSRF-Token": config["csrfToken"]},
                )
                self.assertEqual(response.status_code, 401)
            response = self.client.post(
                "/api/auth/line", json={"idToken": "modified-token"},
                headers={"X-CSRF-Token": config["csrfToken"]},
            )
        self.assertEqual(response.status_code, 429)

    def test_deleted_customer_can_register_again_with_the_same_line_identity(self):
        self.login()
        with self.app.app_context():
            db = get_db()
            db.execute(
                """UPDATE customers SET is_active=0,is_deleted=1,line_user_id=NULL,
                   phone_normalized='deleted:1:test' WHERE id=1"""
            )
            db.commit()
        payload = self.login()
        self.assertTrue(payload["authenticated"])
        with self.app.app_context():
            customers = get_db().execute(
                "SELECT id,is_deleted,line_user_id FROM customers ORDER BY id"
            ).fetchall()
            self.assertEqual(len(customers), 2)
            self.assertEqual(customers[0]["is_deleted"], 1)
            self.assertEqual(customers[1]["is_deleted"], 0)
            self.assertEqual(customers[1]["line_user_id"], "U0123456789abcdef0123456789abcdef")


if __name__ == "__main__":
    unittest.main()
