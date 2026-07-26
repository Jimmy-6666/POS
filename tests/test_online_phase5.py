import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from tests.online_helpers import register_customer


class OnlinePhase5Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "online.db"),
            "PROJECT_ROOT": self.folder.name,
            "PRINT_AGENT_TOKEN": "test-print-token",
        })
        with self.app.app_context():
            db = get_db(); db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            category = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]; unit = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute("UPDATE settings SET value='1' WHERE key='online_ordering_enabled'")
            db.execute("INSERT INTO products(barcode,name_th,category_id,unit_id,price_satang,stock_quantity,is_online_available) VALUES('111','สินค้า',?,?,1000,5,1)", (category, unit))
            db.execute("INSERT INTO delivery_locations(name,room_required) VALUES('รีสอร์ต',1)"); db.commit()
        customer = self.app.test_client(); register_customer(customer)
        with self.app.app_context(): customer_csrf = get_db().execute("SELECT csrf_token FROM customer_sessions").fetchone()[0]
        customer.post("/order/api/orders", json={"items": [{"product_id": 1, "quantity": 2}], "delivery_location_id": 1,
            "room_reference": "A1", "payment_method": "cash", "idempotency_key": "reconcile-123456"}, headers={"X-CSRF-Token": customer_csrf})
        self.staff = self.app.test_client(); self.staff.post("/login", data={"staff_id": "1", "pin": "1234"})
        with self.app.app_context(): self.csrf = get_db().execute("SELECT csrf_token FROM staff_sessions").fetchone()[0]
        self.staff.post("/online-orders/1/accept", data={"csrf_token": self.csrf, "staff_id": "1"}); self.staff.post("/online-orders/1/preparation/start", data={"csrf_token": self.csrf})
        self.staff.post("/online-orders/1/preparation", data={"csrf_token": self.csrf, "prepared_1": "2", "complete": "1"})

    def tearDown(self): self.folder.cleanup()

    def test_barcode_reconciliation_blocks_wrong_over_and_incomplete(self):
        self.staff.post("/online-orders/1/reconcile/scan", data={"csrf_token": self.csrf, "barcode": "wrong"})
        self.staff.post("/online-orders/1/reconcile/scan", data={"csrf_token": self.csrf, "barcode": "111"})
        self.staff.post("/online-orders/1/reconcile/complete", data={"csrf_token": self.csrf})
        with self.app.app_context(): self.assertEqual(get_db().execute("SELECT status FROM online_orders").fetchone()[0], "reconciling")
        self.staff.post("/online-orders/1/reconcile/scan", data={"csrf_token": self.csrf, "barcode": "111"})
        self.staff.post("/online-orders/1/reconcile/scan", data={"csrf_token": self.csrf, "barcode": "111"})
        self.staff.post("/online-orders/1/reconcile/complete", data={"csrf_token": self.csrf})
        with self.app.app_context():
            db = get_db(); self.assertEqual(db.execute("SELECT status FROM online_orders").fetchone()[0], "ready")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM order_reconciliation_events").fetchone()[0], 2)
        job = self.staff.get("/print-agent/next?token=test-print-token").get_json()["job"]
        self.assertEqual(job["document_type"], "checked_order")
        print_page = self.staff.get(f"{job['render_url']}?token=test-print-token").get_data(as_text=True)
        self.assertIn("addEventListener('load',()=>window.print())", print_page)

    def test_manual_reconciliation_assignment_and_delivery_start(self):
        self.staff.post("/online-orders/1/reconcile/manual/1", data={"csrf_token": self.csrf})
        self.staff.post("/online-orders/1/reconcile/complete", data={"csrf_token": self.csrf})
        page = self.staff.get("/online-orders/1").get_data(as_text=True)
        self.assertIn("บันทึกและออกจัดส่ง", page)
        self.assertNotIn(">มอบหมาย<", page)
        self.staff.post("/online-orders/1/delivery/start", data={"csrf_token": self.csrf, "staff_id": "1"})
        with self.app.app_context():
            db = get_db(); order = db.execute("SELECT * FROM online_orders").fetchone()
            self.assertEqual(order["status"], "delivering")
            self.assertEqual(order["assigned_staff_id"], 1)
            self.assertEqual(db.execute("SELECT method FROM order_reconciliation_events").fetchone()[0], "manual")


if __name__ == "__main__": unittest.main()
