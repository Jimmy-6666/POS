import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from pos_app.services.online_orders import OnlineOrderError, complete_online_order_sale
from tests.online_helpers import register_customer
from tests.staff_helpers import staff_login


class OnlinePhase6Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "online.db"), "PROJECT_ROOT": self.folder.name})
        with self.app.app_context():
            db = get_db(); db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            category = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]; unit = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute("UPDATE settings SET value='1' WHERE key='online_ordering_enabled'")
            db.execute("INSERT INTO products(barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity,is_online_available) VALUES('111','สินค้า',?,?,600,1000,5,1)", (category, unit))
            db.execute("INSERT INTO delivery_locations(name,delivery_fee_satang,room_required) VALUES('รีสอร์ต',500,1)"); db.commit()
        customer = self.app.test_client(); register_customer(customer)
        with self.app.app_context():
            db=get_db(); customer_csrf = db.execute("SELECT csrf_token FROM customer_sessions").fetchone()[0]; self.product_uuid=db.execute("SELECT product_uuid FROM products WHERE id=1").fetchone()[0]
        customer.post("/order/api/orders", json={"items": [{"product_uuid": self.product_uuid, "quantity": 2}], "delivery_location_id": 1,
            "room_reference": "A1", "payment_method": "cash", "idempotency_key": "complete-123456"}, headers={"X-CSRF-Token": customer_csrf})
        self.staff = self.app.test_client(); staff_login(self.staff)
        with self.app.app_context(): self.csrf = get_db().execute("SELECT csrf_token FROM staff_sessions").fetchone()[0]
        self.staff.post("/online-orders/1/accept", data={"csrf_token": self.csrf, "staff_id": "1"}); self.staff.post("/online-orders/1/preparation/start", data={"csrf_token": self.csrf})
        self.staff.post("/online-orders/1/preparation", data={"csrf_token": self.csrf, "prepared_1": "2", "complete": "1"})
        self.staff.post("/online-orders/1/reconcile/manual/1", data={"csrf_token": self.csrf, "reason": "ทดสอบ"})
        self.staff.post("/online-orders/1/reconcile/complete", data={"csrf_token": self.csrf})
        self.staff.post("/online-orders/1/assign", data={"csrf_token": self.csrf, "staff_id": "1"})
        self.staff.post("/online-orders/1/delivery/start", data={"csrf_token": self.csrf})

    def tearDown(self): self.folder.cleanup()

    def test_completion_creates_one_sale_and_deducts_stock_once(self):
        response = self.staff.post("/online-orders/1/delivery/complete", data={
            "csrf_token": self.csrf, "cash_received": "30", "delivery_result": "delivered",
            "payment_method": "cash", "payment_method_confirmed": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/online-orders/1"))
        with self.app.app_context():
            db = get_db(); order = db.execute("SELECT * FROM online_orders").fetchone()
            self.assertEqual(order["status"], "completed"); self.assertIsNotNone(order["sale_id"])
            self.assertEqual(db.execute("SELECT stock_quantity FROM products").fetchone()[0], 3)
            sale = db.execute("SELECT * FROM sales").fetchone()
            self.assertEqual(sale["total_satang"], 2500); self.assertEqual(sale["delivery_fee_satang"], 500)
            self.assertEqual(db.execute("SELECT status FROM stock_reservations").fetchone()[0], "converted")
        second = self.staff.post("/online-orders/1/delivery/complete", data={
            "csrf_token": self.csrf, "cash_received": "30", "delivery_result": "delivered",
            "payment_method": "cash", "payment_method_confirmed": "1"})
        self.assertEqual(second.status_code, 302)
        with self.app.app_context():
            db = get_db(); self.assertEqual(db.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT stock_quantity FROM products").fetchone()[0], 3)

    def test_cash_shortfall_rolls_back_everything(self):
        response = self.staff.post("/online-orders/1/delivery/complete", data={
            "csrf_token": self.csrf, "cash_received": "10", "delivery_result": "delivered",
            "payment_method": "cash", "payment_method_confirmed": "1"}, follow_redirects=True)
        self.assertIn("น้อยกว่า", response.get_data(as_text=True))
        with self.app.app_context():
            db = get_db(); self.assertEqual(db.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT status FROM online_orders").fetchone()[0], "delivering")
            self.assertEqual(db.execute("SELECT stock_quantity FROM products").fetchone()[0], 5)

    def test_delivery_can_confirm_changed_payment_method(self):
        response = self.staff.post("/online-orders/1/delivery/complete", data={
            "csrf_token": self.csrf, "delivery_result": "delivered",
            "payment_method": "transfer", "payment_method_confirmed": "1",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            db = get_db()
            order = db.execute("SELECT * FROM online_orders").fetchone()
            sale = db.execute("SELECT * FROM sales").fetchone()
            payment = db.execute("SELECT * FROM online_order_payments ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(order["payment_method_code"], "transfer")
            self.assertEqual(sale["payment_method_code"], "transfer")
            self.assertEqual(payment["method_code"], "transfer")
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action='online_payment_override'"
            ).fetchone()[0], 1)

    def test_delivery_requires_payment_confirmation(self):
        page = self.staff.get("/online-orders/1").get_data(as_text=True)
        self.assertIn('name="payment_method"', page)
        self.assertIn('name="payment_method_confirmed"', page)
        self.assertIn("staff-glass-item", page)
        response = self.staff.post("/online-orders/1/delivery/complete", data={
            "csrf_token": self.csrf, "cash_received": "30", "delivery_result": "delivered",
            "payment_method": "cash",
        }, follow_redirects=True)
        self.assertIn("กรุณายืนยันว่าตรวจสอบช่องทางการชำระเงิน", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT status FROM online_orders").fetchone()[0], "delivering")


if __name__ == "__main__": unittest.main()
