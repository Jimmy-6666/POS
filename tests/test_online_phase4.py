import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from tests.online_helpers import register_customer


class OnlinePhase4Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "online.db"), "PROJECT_ROOT": self.folder.name})
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            category = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute("UPDATE settings SET value='1' WHERE key='online_ordering_enabled'")
            db.execute("""INSERT INTO products(barcode,name_th,category_id,unit_id,price_satang,stock_quantity,is_online_available)
                          VALUES('111','สินค้า',?,?,2500,5,1)""", (category, unit))
            db.execute("""INSERT INTO products(barcode,name_th,category_id,unit_id,price_satang,stock_quantity,is_online_available)
                          VALUES('222','สินค้าเพิ่ม',?,?,1500,8,1)""", (category, unit))
            db.execute("INSERT INTO delivery_locations(name,room_required) VALUES('รีสอร์ต',1)")
            db.commit()
        customer = self.app.test_client()
        register_customer(customer)
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM customer_sessions").fetchone()[0]
        result = customer.post("/order/api/orders", json={"items": [{"product_id": 1, "quantity": 2}],
            "delivery_location_id": 1, "room_reference": "A1", "payment_method": "cash", "idempotency_key": "staff-test-123456"},
            headers={"X-CSRF-Token": csrf}).get_json()
        self.staff = self.app.test_client()
        self.staff.post("/login", data={"staff_id": "1", "pin": "1234"})
        with self.app.app_context():
            self.csrf = get_db().execute("SELECT csrf_token FROM staff_sessions").fetchone()[0]

    def tearDown(self):
        self.folder.cleanup()

    def test_accept_adjust_and_prepare_with_controlled_transitions(self):
        self.assertEqual(self.staff.post("/online-orders/1/accept", data={"csrf_token": self.csrf, "staff_id": "1"}).status_code, 302)
        self.staff.post("/online-orders/1/items/1", data={"csrf_token": self.csrf, "quantity": "1", "reason": "สินค้าเหลือ 1 ชิ้น"})
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT quantity FROM stock_reservations").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT total_satang FROM online_orders").fetchone()[0], 2500)
        self.staff.post("/online-orders/1/preparation/start", data={"csrf_token": self.csrf})
        self.staff.post("/online-orders/1/preparation", data={"csrf_token": self.csrf, "prepared_1": "1", "complete": "1"})
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT status FROM online_orders").fetchone()[0], "reconciling")

    def test_queue_and_summary_render(self):
        self.assertEqual(self.staff.get("/online-orders").status_code, 200)
        self.assertEqual(self.staff.get("/online-orders/api/summary").get_json()["new_count"], 1)

    def test_staff_adds_item_and_price_change_requires_customer_confirmation(self):
        self.staff.post("/online-orders/1/accept", data={"csrf_token": self.csrf, "staff_id": "1"})
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE products SET price_satang=3000 WHERE id=1")
            db.commit()
        self.staff.post("/online-orders/1/items/1", data={
            "csrf_token": self.csrf, "quantity": "1",
            "reason": "ลูกค้าขอแก้จำนวน กรุณายืนยันราคาใหม่",
        })
        response = self.staff.post("/online-orders/1/items", data={
            "csrf_token": self.csrf, "product_id": "2", "quantity": "2",
            "reason": "ลูกค้าขอเพิ่มสินค้า กรุณายืนยันราคาใหม่",
        }, follow_redirects=True)
        page = response.get_data(as_text=True)
        self.assertIn("ยอดราคาเปลี่ยนจากที่ลูกค้ายืนยัน", page)
        self.assertIn("พนักงานเพิ่มภายหลัง", page)
        with self.app.app_context():
            db = get_db()
            order = db.execute("SELECT * FROM online_orders WHERE id=1").fetchone()
            added = db.execute("SELECT * FROM online_order_items WHERE product_id=2").fetchone()
            self.assertEqual(order["subtotal_satang"], 6000)
            self.assertEqual(order["total_satang"], 6000)
            self.assertEqual(added["unit_price_satang"], 1500)
            self.assertIsNone(added["customer_confirmed_unit_price_satang"])
            self.assertEqual(db.execute(
                "SELECT amount_satang FROM online_order_payments WHERE order_id=1"
            ).fetchone()[0], 6000)
            self.assertEqual(db.execute(
                "SELECT quantity FROM stock_reservations WHERE order_id=1 AND product_id=2"
            ).fetchone()[0], 2)

    def test_cashier_cannot_verify_transfer_payment(self):
        with self.app.app_context():
            db = get_db()
            cashier_role = db.execute("SELECT id FROM roles WHERE code='cashier'").fetchone()[0]
            db.execute("UPDATE staff SET role_id=? WHERE id=1", (cashier_role,))
            db.commit()
        response = self.staff.post("/online-orders/1/payment/999", data={"csrf_token": self.csrf, "action": "confirm"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
