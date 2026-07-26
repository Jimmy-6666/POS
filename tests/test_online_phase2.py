import tempfile
import unittest
import re
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from tests.online_helpers import register_customer


class OnlinePhase2Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "online.db"), "PROJECT_ROOT": self.folder.name})
        with self.app.app_context():
            db = get_db()
            category = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute("UPDATE settings SET value='1' WHERE key='online_ordering_enabled'")
            db.execute("""INSERT INTO products(barcode,name_th,category_id,unit_id,price_satang,stock_quantity,is_online_available)
                          VALUES('111','ออนไลน์',?,?,2500,5,1),('222','ซ่อน',?,?,1000,5,0),('333','ปิด',?,?,1000,5,1)""",
                       (category, unit, category, unit, category, unit))
            db.execute("UPDATE products SET is_active=0 WHERE barcode='333'")
            db.execute("""INSERT INTO products(barcode,name_th,category_id,unit_id,price_satang,stock_quantity,is_online_available)
                          VALUES('000','สินค้าราคา UAT',?,?,0,5,1)""", (category, unit))
            db.execute("INSERT INTO delivery_locations(name,room_required) VALUES('จุดทดสอบ',0)")
            db.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        self.folder.cleanup()

    def test_catalog_hides_inactive_and_non_online_products(self):
        html = self.client.get("/order").get_data(as_text=True)
        self.assertIn("ออนไลน์", html)
        self.assertNotIn("<h2>ซ่อน</h2>", html)
        self.assertNotIn("<h2>ปิด</h2>", html)
        self.assertIn("สินค้าราคา UAT", html)

    def test_cart_uses_server_price_and_validates_stock(self):
        response = self.client.post("/order/api/cart/validate", json={"items": [{"product_id": 1, "quantity": 2, "price_satang": 1}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["subtotal_satang"], 5000)
        response = self.client.post("/order/api/cart/validate", json={"items": [{"product_id": 1, "quantity": 6}]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("ไม่เพียงพอ", response.get_json()["error"])

    def test_checkout_allows_guest_details(self):
        page = self.client.get("/order/checkout")
        self.assertEqual(page.status_code, 200)
        self.assertIn("เบอร์มือถือ", page.get_data(as_text=True))
        self.assertIn("ตั้ง PIN เพื่อใช้สั่งครั้งถัดไป", page.get_data(as_text=True))
        self.assertNotIn("ตั้ง PIN เพื่อใช้สั่งครั้งถัดไปไหม", page.get_data(as_text=True))
        self.assertIn("รายละเอียดการจัดส่ง", page.get_data(as_text=True))
        self.assertIn("ถัดไป: วิธีชำระเงิน", page.get_data(as_text=True))
        self.assertIn("ถัดไป: ตรวจสอบออเดอร์", page.get_data(as_text=True))

    def test_cart_is_a_dedicated_page_not_a_catalog_dialog(self):
        catalog = self.client.get("/order").get_data(as_text=True)
        self.assertIn('href="/order/cart"', catalog)
        self.assertNotIn('id="cartDialog"', catalog)
        cart = self.client.get("/order/cart")
        self.assertEqual(cart.status_code, 200)
        self.assertIn("ตะกร้าของฉัน", cart.get_data(as_text=True))
        self.assertIn("สั่งสินค้าเพิ่ม", cart.get_data(as_text=True))

    def test_checkout_can_lookup_and_login_existing_account_inline(self):
        account_client = self.app.test_client()
        register_customer(account_client, phone="0812345678", pin="2468")
        checkout = self.client.get("/order/checkout").get_data(as_text=True)
        csrf = re.search(r'id="customerCsrf" value="([^"]+)"', checkout).group(1)
        lookup = self.client.post(
            "/order/api/account/lookup", json={"phone": "0812345678"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertTrue(lookup.get_json()["account_exists"])
        login = self.client.post(
            "/order/api/account/login", json={"phone": "0812345678", "pin": "2468"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.get_json()["csrf_token"])

    def test_guest_can_submit_without_registration(self):
        html = self.client.get("/order/checkout").get_data(as_text=True)
        csrf = re.search(r'id="customerCsrf" value="([^"]+)"', html).group(1)
        response = self.client.post("/order/api/orders", headers={"X-CSRF-Token": csrf}, json={
            "items": [{"product_id": 1, "quantity": 1}], "delivery_location_id": 1,
            "room_reference": "", "payment_method": "cash", "cash_expected_satang": 3000,
            "idempotency_key": "guest-order-test-123", "phone": "0811112222", "display_name": "ลูกค้า Guest",
        })
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT is_guest FROM customers").fetchone()[0], 1)
            order = db.execute("SELECT contact_phone,contact_name FROM online_orders").fetchone()
            self.assertEqual(order["contact_phone"], "0811112222")
            self.assertEqual(order["contact_name"], "ลูกค้า Guest")


if __name__ == "__main__":
    unittest.main()
