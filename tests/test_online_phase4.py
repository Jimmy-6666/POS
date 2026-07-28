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
            self.first_product_uuid = db.execute("SELECT product_uuid FROM products WHERE id=1").fetchone()[0]
            self.second_product_uuid = db.execute("SELECT product_uuid FROM products WHERE id=2").fetchone()[0]
        customer = self.app.test_client()
        register_customer(customer)
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM customer_sessions").fetchone()[0]
        result = customer.post("/order/api/orders", json={"items": [{"product_uuid": self.first_product_uuid, "quantity": 2}],
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
        page = self.staff.get("/online-orders").get_data(as_text=True)
        self.assertIn("รอร้านตรวจสอบ", page)
        self.assertIn("ยังไม่ชำระ", page)
        self.assertNotIn(">submitted<", page)
        self.assertNotIn(">unpaid<", page)
        self.assertEqual(self.staff.get("/online-orders/api/summary").get_json()["new_count"], 1)

    def test_pos_submitted_alert_uses_local_looping_audio_not_sidebar_badge(self):
        staff_page = self.staff.get("/online-orders").get_data(as_text=True)
        pos_page = self.staff.get("/pos").get_data(as_text=True)
        script = (Path(__file__).resolve().parents[1] / "pos_app" / "static" / "js" / "online-order-alerts.js").read_text(encoding="utf-8")
        sidebar_script = (Path(__file__).resolve().parents[1] / "pos_app" / "static" / "js" / "sidebar.js").read_text(encoding="utf-8")
        css = (Path(__file__).resolve().parents[1] / "pos_app" / "static" / "css" / "v2.css").read_text(encoding="utf-8")
        audio = Path(__file__).resolve().parents[1] / "pos_app" / "static" / "audio" / "order_sound.mp3"
        self.assertIn('id="onlineOrdersPageBadge"', staff_page)
        self.assertIn('id="posOnlineOrderBadge"', pos_page)
        self.assertIn('id="onlineOrderShortcut"', pos_page)
        self.assertTrue(audio.is_file())
        self.assertIn('new Audio("/static/audio/order_sound.mp3")', script)
        self.assertIn("audio.loop = true", script)
        self.assertIn('new Set(["pos.index", "online_staff.index"])', script)
        self.assertIn('if (!alertPages.has(document.body.dataset.endpoint)) return;', script)
        self.assertIn('window.location.reload()', script)
        self.assertIn('onlineOrderAlertNavigationGesture', script)
        self.assertIn("onlineOrderAlertNavigationGesture", sidebar_script)
        self.assertIn("path === '/pos' || path === '/online-orders'", sidebar_script)
        self.assertIn("setInterval(poll, 15000)", script)
        self.assertIn("width:32px", css)
        self.assertIn("border-radius:50%", css)
        self.assertIn("animation:online-order-pulse .85s", css)
        self.assertIn(".online-orders-title", css)
        self.assertEqual(self.staff.get("/online-orders/api/summary").get_json()["new_count"], 1)
        self.staff.post("/online-orders/1/accept", data={"csrf_token": self.csrf, "staff_id": "1"})
        self.assertEqual(self.staff.get("/online-orders/api/summary").get_json()["new_count"], 0)

    def test_staff_cancel_uses_confirmation_ui_and_releases_reservation(self):
        with self.app.app_context():
            cashier_role_id = get_db().execute("SELECT id FROM roles WHERE code='cashier'").fetchone()[0]
            get_db().execute("UPDATE staff SET role_id=? WHERE id=1", (cashier_role_id,))
            get_db().commit()
        page = self.staff.get("/online-orders/1").get_data(as_text=True)
        self.assertIn('id="cancelOrderDialog"', page)
        self.assertIn("ยืนยันยกเลิกออเดอร์", page)
        self.assertIn('class="actions order-heading-actions"', page)
        self.assertIn('class="primary-button danger-small cancel-order-button"', page)
        self.assertLess(page.index("ยกเลิกออเดอร์"), page.index("กลับหน้ารายการ"))
        self.assertLess(page.index('class="actions order-heading-actions"'), page.index('class="staff-order-side"'))
        css = (Path(__file__).resolve().parents[1] / "pos_app" / "static" / "css" / "online-staff.css").read_text(encoding="utf-8")
        self.assertIn(".order-heading-actions .cancel-order-button", css)
        self.assertIn("background:#fee2e2", css)
        response = self.staff.post(
            "/online-orders/1/cancel", data={"csrf_token": self.csrf, "reason": "ลูกค้าขอยกเลิก"}
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT status FROM online_orders WHERE id=1").fetchone()[0], "staff_cancelled")
            self.assertEqual(db.execute("SELECT status FROM stock_reservations WHERE order_id=1").fetchone()[0], "released")
            history = db.execute(
                "SELECT new_status,actor_staff_id,reason FROM online_order_status_history WHERE order_id=1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual((history["new_status"], history["actor_staff_id"], history["reason"]), ("staff_cancelled", 1, "ลูกค้าขอยกเลิก"))
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action='online_order_staff_cancelled'"
            ).fetchone()[0], 1)

    def test_cashier_cannot_cancel_after_delivery_has_started(self):
        with self.app.app_context():
            db = get_db()
            cashier_role_id = db.execute("SELECT id FROM roles WHERE code='cashier'").fetchone()[0]
            db.execute("UPDATE staff SET role_id=? WHERE id=1", (cashier_role_id,))
            db.execute("UPDATE online_orders SET status='delivering' WHERE id=1")
            db.commit()
        page = self.staff.get("/online-orders/1").get_data(as_text=True)
        self.assertNotIn('id="cancelOrderDialog"', page)
        response = self.staff.post(
            "/online-orders/1/cancel", data={"csrf_token": self.csrf, "reason": "ยกเลิกช้าเกินไป"}, follow_redirects=True
        )
        self.assertIn("ยกเลิกได้ก่อนออกจัดส่งเท่านั้น", response.get_data(as_text=True))
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT status FROM online_orders WHERE id=1").fetchone()[0], "delivering")
            self.assertEqual(db.execute("SELECT status FROM stock_reservations WHERE order_id=1").fetchone()[0], "active")
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action='online_order_staff_cancelled'"
            ).fetchone()[0], 0)

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
            "csrf_token": self.csrf, "product_uuid": self.second_product_uuid, "quantity": "2",
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

    def test_transfer_slip_verification_endpoint_is_removed(self):
        with self.app.app_context():
            db = get_db()
            cashier_role = db.execute("SELECT id FROM roles WHERE code='cashier'").fetchone()[0]
            db.execute("UPDATE staff SET role_id=? WHERE id=1", (cashier_role,))
            db.commit()
        response = self.staff.post("/online-orders/1/payment/999", data={"csrf_token": self.csrf, "action": "confirm"})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
