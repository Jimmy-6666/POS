import tempfile
import unittest
from pathlib import Path

from werkzeug.security import check_password_hash

from pos_app import create_app
from pos_app.database import get_db
from tests.online_helpers import form_csrf, login_customer, register_customer


class OnlinePhase1Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "online.db"), "PROJECT_ROOT": self.folder.name})
        self.client = self.app.test_client()

    def tearDown(self):
        self.folder.cleanup()

    def test_schema_defaults_all_products_online_and_seeds_permissions(self):
        with self.app.app_context():
            db = get_db()
            columns = {row["name"] for row in db.execute("PRAGMA table_info(products)")}
            self.assertIn("is_online_available", columns)
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0], "19")
            self.assertIn(
                "customer_confirmed_unit_price_satang",
                {row[1] for row in db.execute("PRAGMA table_info(online_order_items)").fetchall()},
            )
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='online_ordering_enabled'").fetchone()[0], "0")
            self.assertEqual(
                db.execute("SELECT sql FROM sqlite_master WHERE name='products'").fetchone()[0]
                .split("is_online_available", 1)[1].split(",", 1)[0].count("DEFAULT 1"),
                1,
            )
            self.assertIn("online_bank_accounts", {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            })
            self.assertGreaterEqual(db.execute("SELECT COUNT(*) FROM permissions WHERE code LIKE 'online_%'").fetchone()[0], 10)

    def test_public_registration_requires_csrf(self):
        response = self.client.post("/order/register", data={"phone": "0812345678", "pin": "2468", "pin_confirm": "2468"})
        self.assertEqual(response.status_code, 400)

    def test_registration_normalizes_phone_and_hashes_pin(self):
        response = register_customer(self.client, "+66 81-234-5678")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            customer = get_db().execute("SELECT * FROM customers").fetchone()
            self.assertEqual(customer["phone_normalized"], "0812345678")
            self.assertNotEqual(customer["pin_hash"], "2468")
            self.assertTrue(check_password_hash(customer["pin_hash"], "2468"))

    def test_duplicate_phone_is_not_created(self):
        payload = {"csrf_token": form_csrf(self.client, "/order/register"), "phone": "0812345678", "pin": "2468", "pin_confirm": "2468"}
        self.client.post("/order/register", data=payload)
        response = self.client.post("/order/register", data=payload)
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM customers").fetchone()[0], 1)

    def test_login_rate_limit_and_logout_csrf(self):
        register_customer(self.client)
        self.client.post("/order/logout", data={"csrf_token": "bad"})
        for _ in range(5):
            login_customer(self.client, pin="9999")
        self.assertEqual(login_customer(self.client).status_code, 429)

    def test_customer_contact_settings_render_as_vector_actions(self):
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE settings SET value='@shoptest' WHERE key='online_contact_line'")
            db.execute("UPDATE settings SET value='099-111-2222' WHERE key='online_contact_phone'")
            db.commit()
        page = self.client.get("/order/login").get_data(as_text=True)
        self.assertIn("หากจำ PIN ไม่ได้", page)
        self.assertIn("@shoptest", page)
        self.assertIn("099-111-2222", page)
        self.assertIn("line-logo", page)
        self.assertIn("phone-logo", page)

    def test_customer_store_name_breaks_at_spaces_in_header(self):
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE settings SET value='แสนงาม มินิมาร์ท' WHERE key='store_name'")
            db.commit()
        page = self.client.get("/order").get_data(as_text=True)
        self.assertIn(
            '<span class="customer-store-name"><span>แสนงาม</span><span>มินิมาร์ท</span></span>',
            page,
        )
        self.assertIn("online-uat.css?v=6", page)

    def test_admin_can_manage_locations_and_reset_customer_pin(self):
        register_customer(self.client)
        staff_client = self.app.test_client()
        staff_client.post("/login", data={"staff_id": "1", "pin": "1234"})
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            db.commit()
            csrf = db.execute("SELECT csrf_token FROM staff_sessions ORDER BY id DESC LIMIT 1").fetchone()[0]
        response = staff_client.post("/online-admin/locations", data={
            "csrf_token": csrf, "name": "โรงแรมทดสอบ", "is_active": "on", "is_available": "on",
            "room_required": "on", "delivery_fee": "20", "minimum_order": "100",
        })
        self.assertEqual(response.status_code, 302)
        response = staff_client.post("/online-admin/customers/1/reset-pin", data={"csrf_token": csrf, "temporary_pin": "1357"})
        self.assertEqual(response.status_code, 302)
        search_page = staff_client.get("/online-admin/customers?q=081234").get_data(as_text=True)
        self.assertIn('name="q" value="081234"', search_page)
        self.assertIn("0812345678", search_page)
        empty_page = staff_client.get("/online-admin/customers?q=ไม่พบแน่นอน").get_data(as_text=True)
        self.assertIn("ไม่พบลูกค้าที่ค้นหา", empty_page)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT delivery_fee_satang FROM delivery_locations").fetchone()[0], 2000)
            self.assertEqual(db.execute("SELECT must_change_pin FROM customers WHERE id=1").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_logs WHERE action='reset_customer_pin'").fetchone()[0], 1)

    def test_online_settings_are_sectioned_and_saved_bank_account_can_be_selected(self):
        staff_client = self.app.test_client()
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            db.commit()
        staff_client.post("/login", data={"staff_id": "1", "pin": "1234"})
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM staff_sessions ORDER BY id DESC LIMIT 1").fetchone()[0]
        page = staff_client.get("/online-admin/settings?section=payment").get_data(as_text=True)
        self.assertIn("เพิ่มบัญชีรับโอน", page)
        self.assertNotIn("เพิ่มสถานที่จัดส่ง", page)
        response = staff_client.post("/online-admin/bank-accounts", data={
            "csrf_token": csrf, "label": "บัญชีหลัก", "bank_name": "ธนาคารทดสอบ",
            "account_name": "ร้านทดสอบ", "account_number": "1234567890",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            account_id = get_db().execute("SELECT id FROM online_bank_accounts").fetchone()[0]
        response = staff_client.post("/online-admin/bank-accounts/select", data={
            "csrf_token": csrf, "account_id": str(account_id), "online_transfer_enabled": "on",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            settings = dict(get_db().execute(
                "SELECT key,value FROM settings WHERE key IN ('online_transfer_enabled','online_bank_account_id','online_bank_account_number')"
            ).fetchall())
            self.assertEqual(settings["online_transfer_enabled"], "1")
            self.assertEqual(settings["online_bank_account_id"], str(account_id))
            self.assertEqual(settings["online_bank_account_number"], "1234567890")
        response = staff_client.post("/online-admin/settings?section=schedule", data={
            "csrf_token": csrf, "online_order_expiry_minutes": "60", "online_max_order_quantity": "50",
            "online_contact_line": "@newshop", "online_contact_phone": "099-999-9999",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            settings = dict(get_db().execute(
                "SELECT key,value FROM settings WHERE key IN ('online_contact_line','online_contact_phone')"
            ).fetchall())
            self.assertEqual(settings["online_contact_line"], "@newshop")
            self.assertEqual(settings["online_contact_phone"], "099-999-9999")


if __name__ == "__main__":
    unittest.main()
