import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from tests.online_helpers import register_customer


class OnlinePhase3Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "online.db"), "PROJECT_ROOT": self.folder.name})
        with self.app.app_context():
            db = get_db()
            category = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute("UPDATE settings SET value='1' WHERE key='online_ordering_enabled'")
            db.execute("UPDATE settings SET value='0' WHERE key='online_allow_negative_stock'")
            db.execute("UPDATE settings SET value='1' WHERE key='online_transfer_enabled'")
            db.execute("""INSERT INTO products(barcode,name_th,category_id,unit_id,price_satang,stock_quantity,is_online_available)
                          VALUES('111','สินค้าออนไลน์',?,?,2500,5,1)""", (category, unit))
            db.execute("""INSERT INTO delivery_locations(name,delivery_fee_satang,minimum_order_satang,room_required)
                          VALUES('รีสอร์ต',1000,0,1)""")
            db.commit()
            self.product_uuid = db.execute("SELECT product_uuid FROM products WHERE id=1").fetchone()[0]
        self.client = self.app.test_client()
        register_customer(self.client)
        with self.app.app_context():
            self.csrf = get_db().execute("SELECT csrf_token FROM customer_sessions").fetchone()[0]

    def tearDown(self):
        self.folder.cleanup()

    def payload(self, **changes):
        data = {"items": [{"product_uuid": self.product_uuid, "quantity": 2}], "delivery_location_id": 1,
                "room_reference": "A101", "payment_method": "cash", "idempotency_key": "order-key-123456"}
        data.update(changes)
        return data

    def submit(self, **changes):
        return self.client.post("/order/api/orders", json=self.payload(**changes), headers={"X-CSRF-Token": self.csrf})

    def test_order_creation_reserves_stock_and_uses_server_totals(self):
        response = self.submit(total_satang=1)
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            db = get_db()
            order = db.execute("SELECT * FROM online_orders").fetchone()
            self.assertEqual(order["subtotal_satang"], 5000)
            self.assertEqual(order["total_satang"], 6000)
            self.assertEqual(db.execute("SELECT quantity FROM stock_reservations").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT stock_quantity FROM products WHERE id=1").fetchone()[0], 5)

    def test_duplicate_submit_returns_same_order(self):
        first = self.submit().get_json()
        second = self.submit().get_json()
        self.assertEqual(first["public_id"], second["public_id"])
        self.assertTrue(second["duplicate"])
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM online_orders").fetchone()[0], 1)

    def test_competing_order_and_customer_cancel_release(self):
        public_id = self.submit(items=[{"product_uuid": self.product_uuid, "quantity": 5}]).get_json()["public_id"]
        other = self.app.test_client()
        register_customer(other, "0899999999")
        with self.app.app_context():
            other_csrf = get_db().execute("SELECT csrf_token FROM customer_sessions ORDER BY id DESC LIMIT 1").fetchone()[0]
        blocked = other.post("/order/api/orders", json=self.payload(idempotency_key="other-order-12345", room_reference="B2"),
                             headers={"X-CSRF-Token": other_csrf})
        self.assertEqual(blocked.status_code, 400)
        cancel = self.client.post(f"/order/orders/{public_id}/cancel", data={"csrf_token": self.csrf, "reason": "เปลี่ยนใจ"})
        self.assertEqual(cancel.status_code, 302)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT status FROM stock_reservations").fetchone()[0], "released")

    def test_order_ownership_and_slip_endpoint_removed(self):
        public_id = self.submit(payment_method="transfer").get_json()["public_id"]
        self.assertEqual(self.client.post(f"/order/orders/{public_id}/slips").status_code, 404)
        other = self.app.test_client()
        register_customer(other, "0899999999")
        self.assertEqual(other.get(f"/order/orders/{public_id}").status_code, 404)

    def test_negative_stock_setting_controls_online_reservations(self):
        blocked = self.submit(items=[{"product_uuid": self.product_uuid, "quantity": 6}])
        self.assertEqual(blocked.status_code, 400)
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE settings SET value='0' WHERE key='allow_negative_stock'")
            db.execute("UPDATE settings SET value='1' WHERE key='online_allow_negative_stock'")
            db.commit()
        allowed = self.submit(items=[{"product_uuid": self.product_uuid, "quantity": 6}], idempotency_key="negative-stock-order-123")
        self.assertEqual(allowed.status_code, 200)

    def test_online_negative_stock_returns_a_repeatable_customer_quantity_limit(self):
        self.submit(items=[{"product_uuid": self.product_uuid, "quantity": 5}])
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE settings SET value='1' WHERE key='online_allow_negative_stock'")
            db.commit()
        response = self.client.post("/order/api/cart/validate", json={"items": [{"product_uuid": self.product_uuid, "quantity": 1}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["items"][0]["max_quantity"], 50.0)
        self.assertNotIn("available_quantity", response.get_json()["items"][0])

    def test_customer_order_hides_bank_details_and_uses_contact_icons(self):
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE settings SET value='123-SECRET-456' WHERE key='online_bank_account_number'")
            db.commit()
        public_id = self.submit(payment_method="transfer").get_json()["public_id"]
        page = self.client.get(f"/order/orders/{public_id}").get_data(as_text=True)
        self.assertIn("โอนเงินเมื่อส่งสินค้า", page)
        self.assertNotIn("123-SECRET-456", page)
        self.assertNotIn("คัดลอกเลขบัญชี", page)
        self.assertIn("line-logo", page)
        self.assertIn("phone-logo", page)

    def test_customer_order_detail_uses_fixed_three_line_items_and_hides_payment_status(self):
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE products SET name_th=? WHERE id=1", ("สินค้าชื่อยาวมากสำหรับทดสอบการตัดข้อความในหน้ารายละเอียดออเดอร์ลูกค้า",))
            db.commit()
        public_id = self.submit().get_json()["public_id"]
        page = self.client.get(f"/order/orders/{public_id}").get_data(as_text=True)
        self.assertIn('class="customer-order-progress"', page)
        self.assertIn('class="customer-order-item-name"', page)
        self.assertIn('class="customer-order-item-quantity">× 2', page)
        self.assertIn('class="customer-order-item-price">50.00 บาท', page)
        self.assertNotIn("การชำระเงิน:", page)
        self.assertNotIn('id="lineLogout"', page)
        self.assertIn("รอร้าน", page)
        css = (Path(__file__).resolve().parents[1] / "pos_app" / "static" / "css" / "online-orders.css").read_text(encoding="utf-8")
        self.assertIn("-webkit-line-clamp:2", css)
        self.assertIn("grid-template-rows:2.7em 1.5em", css)

    def test_customer_order_refresh_and_cancelled_progress(self):
        public_id = self.submit().get_json()["public_id"]
        page = self.client.get(f"/order/orders/{public_id}").get_data(as_text=True)
        self.assertIn('class="order-status-refresh"', page)
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE online_orders SET status='staff_cancelled' WHERE public_id=?", (public_id,))
            db.commit()
        cancelled = self.client.get(f"/order/orders/{public_id}").get_data(as_text=True)
        self.assertIn('class="customer-order-status cancelled"', cancelled)
        self.assertIn('class="customer-order-progress no-progress"', cancelled)
        self.assertIn("ยกเลิก", cancelled)
        self.assertNotIn('class="order-status-refresh"', cancelled)

    def test_catalog_hides_availability_and_respects_online_negative_stock(self):
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE products SET stock_quantity=0 WHERE id=1")
            db.commit()
        unavailable = self.client.get("/order").get_data(as_text=True)
        self.assertNotIn("พร้อมขาย", unavailable)
        self.assertIn('class="add-product" disabled>สินค้าหมด</button>', unavailable)
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE settings SET value='1' WHERE key='online_allow_negative_stock'")
            db.commit()
        negative_allowed = self.client.get("/order").get_data(as_text=True)
        self.assertNotIn("สินค้าหมด</button>", negative_allowed)
        self.assertIn('class="add-product" >เพิ่มลงตะกร้า</button>', negative_allowed)

    def test_repeat_uses_current_price(self):
        public_id = self.submit().get_json()["public_id"]
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE products SET price_satang=3000 WHERE id=1")
            db.commit()
        result = self.client.get(f"/order/orders/{public_id}/repeat").get_json()
        self.assertEqual(result["items"][0]["price_satang"], 3000)
        self.assertTrue(result["notices"])


if __name__ == "__main__":
    unittest.main()
