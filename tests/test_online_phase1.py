import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from tests.online_helpers import register_customer
from tests.staff_helpers import staff_login


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
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='online_allow_negative_stock'").fetchone()[0], "1")
            self.assertEqual(
                db.execute("SELECT sql FROM sqlite_master WHERE name='products'").fetchone()[0]
                .split("is_online_available", 1)[1].split(",", 1)[0].count("DEFAULT 1"),
                1,
            )
            self.assertIn("online_bank_accounts", {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            })
            customer_columns = {row[1] for row in db.execute("PRAGMA table_info(customers)")}
            self.assertTrue({"line_user_id", "line_display_name", "line_picture_url", "profile_completed"} <= customer_columns)
            self.assertGreaterEqual(db.execute("SELECT COUNT(*) FROM permissions WHERE code LIKE 'online_%'").fetchone()[0], 9)
            self.assertNotIn("online_orders.verify_payment", {
                row[0] for row in db.execute("SELECT code FROM permissions")
            })

    def test_phone_pin_customer_routes_are_retired(self):
        self.assertEqual(self.client.get("/order/register").status_code, 410)
        self.assertEqual(self.client.get("/order/login").status_code, 410)
        self.assertEqual(self.client.post("/order/api/account/lookup", json={}).status_code, 410)
        self.assertEqual(self.client.post("/order/api/account/login", json={}).status_code, 410)

    def test_privacy_policy_is_public_without_line_authentication(self):
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE settings SET value='@shoptest' WHERE key='online_contact_line'")
            db.execute("UPDATE settings SET value='099-111-2222' WHERE key='online_contact_phone'")
            db.commit()
        response = self.client.get("/order/policy")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("เงื่อนไขการใช้งานและนโยบายความเป็นส่วนตัว (PDPA)", page)
        self.assertIn("บรรจุภัณฑ์ ฉลาก และรูปลักษณ์ของสินค้าอาจแตกต่างจากภาพที่แสดง", page)
        self.assertIn("ผู้ผลิตหรือผู้จัดจำหน่ายอาจปรับเปลี่ยนรูปแบบบรรจุภัณฑ์", page)
        self.assertIn("ปริมาณและหน่วยของสินค้าจะเป็นไปตามรายละเอียดที่ระบุ", page)
        self.assertIn("สามารถติดต่อร้านค้าได้โดยตรงผ่านช่องทางด้านล่างนี้", page)
        self.assertIn('href="tel:0991112222"', page)
        self.assertIn("099-111-2222", page)
        self.assertIn("@shoptest", page)
        self.assertIn("ปรับปรุงล่าสุด: กรกฎาคม 2569", page)
        self.assertNotIn("online-line-auth.js", page)

    def test_customer_header_does_not_show_policy_button(self):
        page = self.client.get("/order").get_data(as_text=True)
        self.assertNotIn('class="consent-policy-button"', page)
        self.assertNotIn('aria-label="อ่านเงื่อนไขการใช้งานและนโยบาย PDPA"', page)
        self.assertIn("online.css?v=6", page)
        self.assertIn("online-policy-dialog.js?v=1", page)

    def test_catalog_loads_line_auth_without_exposing_contact_configuration(self):
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE settings SET value='@shoptest' WHERE key='online_contact_line'")
            db.execute("UPDATE settings SET value='099-111-2222' WHERE key='online_contact_phone'")
            db.commit()
        page = self.client.get("/order").get_data(as_text=True)
        self.assertIn("online-line-auth.js", page)
        self.assertIn("online-line-auth.js", page)
        self.assertNotIn("@shoptest", page)
        self.assertNotIn("099-111-2222", page)

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

    def test_admin_can_manage_locations_and_delete_customer_with_admin_pin(self):
        register_customer(self.client)
        staff_client = self.app.test_client()
        staff_login(staff_client)
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
        response = staff_client.post("/online-admin/customers/1/delete", data={"csrf_token": csrf, "admin_pin": "1234"})
        self.assertEqual(response.status_code, 302)
        search_page = staff_client.get("/online-admin/customers").get_data(as_text=True)
        self.assertIn('name="q" value=""', search_page)
        empty_page = staff_client.get("/online-admin/customers?q=ไม่พบแน่นอน").get_data(as_text=True)
        self.assertIn("ไม่พบลูกค้าที่ค้นหา", empty_page)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT delivery_fee_satang FROM delivery_locations").fetchone()[0], 2000)
            deleted = db.execute("SELECT is_deleted,line_user_id,phone_normalized FROM customers WHERE id=1").fetchone()
            self.assertEqual(deleted["is_deleted"], 1)
            self.assertIsNone(deleted["line_user_id"])
            self.assertTrue(deleted["phone_normalized"].startswith("deleted:1:"))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_logs WHERE action='delete_online_customer'").fetchone()[0], 1)

    def test_online_settings_exclude_retired_transfer_account_management(self):
        staff_client = self.app.test_client()
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            db.commit()
        staff_login(staff_client)
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM staff_sessions ORDER BY id DESC LIMIT 1").fetchone()[0]
        page = staff_client.get("/online-admin/settings?section=payment").get_data(as_text=True)
        self.assertIn('name="online_allow_negative_stock"', staff_client.get("/online-admin/settings").get_data(as_text=True))
        self.assertNotIn('name="online_transfer_enabled"', page)
        self.assertNotIn("/online-admin/bank-accounts", page)
        self.assertEqual(
            staff_client.post("/online-admin/bank-accounts", data={"csrf_token": csrf}).status_code,
            404,
        )

if __name__ == "__main__":
    unittest.main()
