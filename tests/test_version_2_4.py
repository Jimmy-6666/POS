import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash

from pos_app import create_app
from pos_app.database import get_db
from pos_app.routes.products import price_rows
from pos_app.services.sales import complete_sale, void_sale


class Version24Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        (root / "uploads" / "products").mkdir(parents=True)
        self.app = create_app({"TESTING": True, "DATABASE": str(root / "pos.db"), "PROJECT_ROOT": str(root)})
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            category_id = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit_id = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute(
                """INSERT INTO products(barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity)
                   VALUES('v24-1','สินค้า V2.4',?,?,500,1000,10)""",
                (category_id, unit_id),
            )
            self.product_id = db.execute("SELECT id FROM products WHERE barcode='v24-1'").fetchone()[0]
            self.product_uuid = db.execute("SELECT product_uuid FROM products WHERE id=?", (self.product_id,)).fetchone()[0]
            manager_role = db.execute("SELECT id FROM roles WHERE code='manager'").fetchone()[0]
            cashier_role = db.execute("SELECT id FROM roles WHERE code='cashier'").fetchone()[0]
            db.execute("INSERT INTO staff(display_name,pin_hash,role_id,must_change_pin) VALUES(?,?,?,0)", ("Manager V2.4", generate_password_hash("4321"), manager_role))
            self.manager_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("INSERT INTO staff(display_name,pin_hash,role_id,must_change_pin) VALUES(?,?,?,0)", ("Cashier V2.4", generate_password_hash("2468"), cashier_role))
            self.cashier_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()

    def tearDown(self):
        self.folder.cleanup()

    def client_for(self, staff_id, pin):
        client = self.app.test_client()
        self.assertEqual(client.post("/login", data={"staff_id": staff_id, "pin": pin}).status_code, 302)
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM staff_sessions WHERE staff_id=? ORDER BY id DESC LIMIT 1", (staff_id,)).fetchone()[0]
        return client, csrf

    def product_form_data(self, csrf, barcode):
        with self.app.app_context():
            db = get_db()
            category_id = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit_id = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
        return {
            "csrf_token": csrf, "barcode": barcode, "name_th": "สินค้ารูปภาพ", "category_id": str(category_id),
            "unit_id": str(unit_id), "cost": "5", "stock_quantity": "0", "minimum_stock": "0",
            "is_active": "on", "is_online_available": "on",
        }

    def sale_for_cashier(self, quantity=2):
        with self.app.app_context():
            return complete_sale({
                "items": [{"product_uuid": self.product_uuid, "quantity": quantity}],
                "payment_method": "cash", "amount_received_satang": quantity * 1000,
            }, self.cashier_id)[0]

    def void_payload(self, csrf, sale_id, pin="4321", authorizer_id=None, quantity="1"):
        with self.app.app_context():
            item_id = get_db().execute("SELECT id FROM sale_items WHERE sale_id=?", (sale_id,)).fetchone()[0]
        data = {
            "csrf_token": csrf, "void_type": "partial", "reason": "ทดสอบ Void", f"quantity_{item_id}": quantity,
            "authorizer_pin": pin,
        }
        if authorizer_id is not None:
            data["authorizer_id"] = str(authorizer_id)
        return data

    def test_desktop_upload_and_mobile_camera_capture_use_same_product_image_save(self):
        admin, csrf = self.client_for(1, "1234")
        desktop = self.product_form_data(csrf, "v24-desktop")
        desktop["image"] = (io.BytesIO(b"desktop image"), "desktop.jpg")
        self.assertEqual(admin.post("/products/new", data=desktop, content_type="multipart/form-data").status_code, 302)
        camera = self.product_form_data(csrf, "v24-camera")
        camera["camera_image"] = (io.BytesIO(b"camera image"), "camera.jpg")
        self.assertEqual(admin.post("/products/new", data=camera, content_type="multipart/form-data").status_code, 302)
        form_html = admin.get("/products/new").get_data(as_text=True)
        self.assertIn('name="camera_image"', form_html)
        self.assertIn('capture="environment"', form_html)
        self.assertIn('id="productImagePreview"', form_html)
        with self.app.app_context():
            images = get_db().execute("SELECT image_path FROM products WHERE barcode IN ('v24-desktop','v24-camera') ORDER BY barcode").fetchall()
            self.assertEqual(len(images), 2)
            self.assertTrue(all(row["image_path"].endswith(".jpg") for row in images))

    def test_product_image_rejects_unsupported_file(self):
        admin, csrf = self.client_for(1, "1234")
        data = self.product_form_data(csrf, "v24-invalid-image")
        data["camera_image"] = (io.BytesIO(b"not image"), "bad.txt")
        response = admin.post("/products/new", data=data, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            self.assertIsNone(get_db().execute("SELECT id FROM products WHERE barcode='v24-invalid-image'").fetchone())

    def test_cashier_manager_authorization_audits_cashier_and_manager(self):
        sale_id = self.sale_for_cashier()
        cashier, csrf = self.client_for(self.cashier_id, "2468")
        response = cashier.post(f"/sales/{sale_id}/void", data=self.void_payload(csrf, sale_id, authorizer_id=self.manager_id))
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            db = get_db()
            void = db.execute("SELECT * FROM sale_voids WHERE sale_id=?", (sale_id,)).fetchone()
            item = db.execute("SELECT * FROM sale_void_items WHERE void_id=?", (void["id"],)).fetchone()
            audit = db.execute("SELECT new_value FROM audit_logs WHERE action='void_sale' ORDER BY id DESC LIMIT 1").fetchone()[0]
            payload = json.loads(audit)
            self.assertEqual(void["voided_by"], self.manager_id)
            self.assertEqual(db.execute("SELECT cashier_id FROM sales WHERE id=?", (sale_id,)).fetchone()[0], self.cashier_id)
            self.assertEqual(item["refund_satang"], 1000)
            self.assertEqual(payload["cashier_id"], self.cashier_id)
            self.assertEqual(payload["authorizing_manager_id"], self.manager_id)
            self.assertEqual(payload["items"][0]["unit_price_satang"], 1000)

    def test_cashier_incorrect_or_inactive_manager_cannot_void(self):
        sale_id = self.sale_for_cashier()
        cashier, csrf = self.client_for(self.cashier_id, "2468")
        bad_pin = cashier.post(f"/sales/{sale_id}/void", data=self.void_payload(csrf, sale_id, pin="0000", authorizer_id=self.manager_id))
        self.assertEqual(bad_pin.status_code, 400)
        self.assertIn("PIN", bad_pin.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM sale_voids WHERE sale_id=?", (sale_id,)).fetchone()[0], 0)
            get_db().execute("UPDATE staff SET is_active=0 WHERE id=?", (self.manager_id,))
            get_db().commit()
        inactive = cashier.post(f"/sales/{sale_id}/void", data=self.void_payload(csrf, sale_id, authorizer_id=self.manager_id))
        self.assertEqual(inactive.status_code, 400)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM sale_voids WHERE sale_id=?", (sale_id,)).fetchone()[0], 0)

    def test_logged_in_manager_uses_only_own_pin_and_cancel_does_not_void(self):
        sale_id = self.sale_for_cashier()
        manager, csrf = self.client_for(self.manager_id, "4321")
        page = manager.get(f"/sales/{sale_id}/void").get_data(as_text=True)
        self.assertNotIn('name="authorizer_id"', page)
        self.assertIn('id="cancelVoidAuthorization"', page)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM sale_voids WHERE sale_id=?", (sale_id,)).fetchone()[0], 0)
        wrong = manager.post(f"/sales/{sale_id}/void", data=self.void_payload(csrf, sale_id, pin="0000"))
        self.assertEqual(wrong.status_code, 400)
        accepted = manager.post(f"/sales/{sale_id}/void", data=self.void_payload(csrf, sale_id, pin="4321"))
        self.assertEqual(accepted.status_code, 302)

    def test_void_page_uses_touch_quantity_buttons_and_login_style_pin_numpad(self):
        sale_id = self.sale_for_cashier()
        manager, _ = self.client_for(self.manager_id, "4321")
        page = manager.get(f"/sales/{sale_id}/void").get_data(as_text=True)
        self.assertIn('data-void-quantity-control', page)
        self.assertIn('data-void-action="minus"', page)
        self.assertIn('data-void-action="plus"', page)
        self.assertIn('id="voidAuthorizerPin"', page)
        self.assertIn('class="login-numpad void-pin-numpad"', page)
        self.assertNotIn('class="void-quantity"', page)
        self.assertIn('เหตุผลการ Void (ไม่บังคับ)', page)
        self.assertNotIn('name="reason" rows="3" required', page)
        css = (Path(__file__).resolve().parents[1] / "pos_app" / "static" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn('.void-pin-numpad{margin-top:12px}', css)

    def test_void_reason_is_optional_and_is_stored_as_empty_when_omitted(self):
        sale_id = self.sale_for_cashier()
        manager, csrf = self.client_for(self.manager_id, "4321")
        payload = self.void_payload(csrf, sale_id, pin="4321")
        payload.pop("reason")
        response = manager.post(f"/sales/{sale_id}/void", data=payload)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            reason = get_db().execute("SELECT reason FROM sale_voids WHERE sale_id=?", (sale_id,)).fetchone()[0]
            self.assertEqual(reason, "")

    def test_reconciliation_void_totals_cover_partial_full_and_empty_windows(self):
        admin, csrf = self.client_for(1, "1234")
        today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()
        empty = admin.get(f"/reconciliations?business_date={today}&cashier_id={self.cashier_id}").get_data(as_text=True)
        self.assertIn("ยอดยกเลิกรวม", empty)
        self.assertIn("0.00", empty)
        partial_sale = self.sale_for_cashier(2)
        with self.app.app_context():
            item_id = get_db().execute("SELECT id FROM sale_items WHERE sale_id=?", (partial_sale,)).fetchone()[0]
            void_sale(partial_sale, {"void_type": "partial", "reason": "บางส่วน", "items": [{"sale_item_id": item_id, "quantity": 1}]}, self.manager_id)
        response = admin.post("/reconciliations", data={"csrf_token": csrf, "business_date": today, "cashier_id": self.cashier_id, "opening_float": "0", "actual_cash": "0"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT void_total_satang FROM reconciliations ORDER BY id DESC LIMIT 1").fetchone()[0], 1000)
        full_sale = self.sale_for_cashier(1)
        with self.app.app_context():
            void_sale(full_sale, {"void_type": "full", "reason": "ทั้งบิล"}, self.manager_id)
        page = admin.get(f"/reconciliations?business_date={today}&cashier_id={self.cashier_id}").get_data(as_text=True)
        self.assertIn("10.00", page)

    def test_latest_cost_has_fallback_and_uses_one_query(self):
        with self.app.app_context():
            db = get_db()
            now = datetime.now(timezone.utc)
            for offset, cost in ((2, 700), (1, 900)):
                receipt = db.execute(
                    "INSERT INTO stock_receipts(staff_id,total_cost_satang,created_at) VALUES(?,?,?)",
                    (1, cost, (now - timedelta(days=offset)).isoformat(timespec="seconds")),
                ).lastrowid
                db.execute("INSERT INTO stock_receipt_items(receipt_id,product_id,quantity,unit_cost_satang,total_cost_satang) VALUES(?,?,?,?,?)", (receipt, self.product_id, 1, cost, cost))
            db.commit()
            statements = []
            db.set_trace_callback(statements.append)
            rows = price_rows(db, None, "")
            db.set_trace_callback(None)
            product = next(row for row in rows if row["product_uuid"] == self.product_uuid)
            self.assertEqual(product["latest_cost_satang"], 900)
            self.assertEqual(product["cost_satang"], 500)
            self.assertEqual(len([statement for statement in statements if statement.lstrip().upper().startswith("WITH")]), 1)
        admin, _ = self.client_for(1, "1234")
        html = admin.get("/products/prices").get_data(as_text=True)
        self.assertIn("ราคาทุนล่าสุด", html)
        self.assertIn("ต้นทุนเฉลี่ยปัจจุบัน", html)
        self.assertIn("5.00", html)
        self.assertIn("9.00", html)
        self.assertIn("-", html)

    def test_pos_scanner_uses_physical_key_codes_and_returns_focus_to_lookup(self):
        source = (Path(__file__).resolve().parents[1] / "pos_app" / "static" / "js" / "pos.js").read_text(encoding="utf-8")
        self.assertIn("Keyboard-wedge barcode readers", source)
        self.assertIn("scannerCharacter(event.code)", source)
        self.assertIn("lookup.focus({ preventScroll: true })", source)
        self.assertIn("document.addEventListener('keydown', receiveScannerKey, true)", source)

    def test_product_menu_actions_reuse_the_reference_glass_button_class(self):
        admin, _ = self.client_for(1, "1234")
        html = admin.get("/products").get_data(as_text=True)
        self.assertIn('href="/products/prices" class="secondary-button"', html)
        self.assertIn('href="/products/references" class="secondary-button"', html)
        self.assertIn('href="/products/new" class="secondary-button"', html)


if __name__ == "__main__":
    unittest.main()
