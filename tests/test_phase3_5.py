import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from pos_app.services.money import baht_to_satang, change_breakdown
from pos_app.services.sales import SaleError, calculate_cart, complete_sale, void_sale


class Phase3To5Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "pos.db"),
            "PRINT_AGENT_TOKEN": "test-print-token",
        })
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            category = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute(
                """INSERT INTO products
                   (barcode,sku,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity,minimum_stock)
                   VALUES ('885000000001','SKU-1','สินค้าทดสอบ',?,?,700,1000,10,2)""",
                (category, unit),
            )
            db.commit()
            self.product_uuid = db.execute("SELECT product_uuid FROM products WHERE id=1").fetchone()[0]
        self.client = self.app.test_client()
        self.client.post("/login", data={"staff_id": "1", "pin": "1234"})
        with self.app.app_context():
            self.csrf = get_db().execute("SELECT csrf_token FROM staff_sessions").fetchone()[0]

    def tearDown(self):
        self.folder.cleanup()

    def payload(self, **updates):
        data = {
            "items": [{"product_uuid": self.product_uuid, "quantity": 2, "discount_satang": 100}],
            "bill_discount_satang": 100,
            "payment_method": "cash",
            "amount_received_satang": 3000,
        }
        data.update(updates)
        return data

    def test_money_and_change_breakdown(self):
        self.assertEqual(baht_to_satang("12.345"), 1235)
        self.assertEqual(change_breakdown(24700), [
            {"value": 100, "count": 2, "kind": "ธนบัตร"},
            {"value": 20, "count": 2, "kind": "ธนบัตร"},
            {"value": 5, "count": 1, "kind": "เหรียญ"},
            {"value": 2, "count": 1, "kind": "เหรียญ"},
        ])

    def test_discount_calculation_uses_database_price(self):
        with self.app.app_context():
            quote = calculate_cart(self.payload()["items"], 100)
            self.assertEqual(quote["subtotal_satang"], 2000)
            self.assertEqual(quote["total_satang"], 1800)
            self.assertEqual(quote["gross_profit_satang"], 400)

    def test_completed_sale_reduces_stock_and_records_ledger_atomically(self):
        with self.app.app_context():
            sale_id, receipt, cart, change = complete_sale(self.payload(), 1)
            db = get_db()
            self.assertEqual(receipt[-4:], "0001")
            self.assertEqual(cart["total_satang"], 1800)
            self.assertEqual(change, 1200)
            self.assertEqual(db.execute("SELECT stock_quantity FROM products WHERE id=1").fetchone()[0], 8)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sale_items WHERE sale_id=?", (sale_id,)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT changed_quantity FROM stock_movements").fetchone()[0], -2)

    def test_sale_allows_negative_stock_for_short_over_reconciliation(self):
        with self.app.app_context():
            get_db().execute("UPDATE settings SET value='0' WHERE key='allow_negative_stock'")
            get_db().commit()
            with self.assertRaisesRegex(SaleError, "สต็อกไม่เพียงพอ"):
                complete_sale(self.payload(items=[{"product_uuid": self.product_uuid, "quantity": 99}], amount_received_satang=100000), 1)
            get_db().execute("UPDATE settings SET value='1' WHERE key='allow_negative_stock'")
            get_db().commit()
            sale_id, _, _, _ = complete_sale(self.payload(items=[{"product_uuid": self.product_uuid, "quantity": 99}], amount_received_satang=100000), 1)
            db = get_db()
            self.assertGreater(sale_id, 0)
            self.assertEqual(db.execute("SELECT stock_quantity FROM products WHERE id=1").fetchone()[0], -89)

    def test_scan_requires_confirmation(self):
        with self.app.app_context():
            with self.assertRaisesRegex(SaleError, "ยืนยัน"):
                complete_sale(self.payload(payment_method="scan", amount_received_satang=0), 1)

    def test_pos_api_and_pages_render(self):
        self.assertEqual(self.client.get("/products").status_code, 200)
        low_page = self.client.get("/products?view=low").get_data(as_text=True)
        self.assertIn("สินค้าใกล้หมด", low_page)
        pos_page = self.client.get("/pos")
        self.assertEqual(pos_page.status_code, 200)
        self.assertIn(b'id="productLookup"', pos_page.data)
        self.assertIn(b'id="mobileCartBar"', pos_page.data)
        self.assertIn(b'js/pos.js?v=27', pos_page.data)
        self.assertIn("จัดการออเดอร์ออนไลน์".encode(), pos_page.data)
        self.assertIn(b'css/v2.css', pos_page.data)
        self.assertIn("ตั้งราคาขาย".encode(), self.client.get("/products").data)
        self.assertIn("ตั้งราคาขาย".encode(), self.client.get("/products/new").data)
        dashboard = self.client.get("/")
        self.assertIn("ภาพรวมวันนี้".encode(), dashboard.data)
        self.assertIn("งานด่วน".encode(), dashboard.data)
        products = self.client.get("/api/pos/products?barcode=885000000001").get_json()
        self.assertEqual(products[0]["name_th"], "สินค้าทดสอบ")
        response = self.client.post(
            "/api/pos/complete", json=self.payload(), headers={"X-CSRF-Token": self.csrf}
        )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["print_queued"])
        receipt_page = self.client.get(result["receipt_url"]).get_data(as_text=True)
        self.assertNotIn("addEventListener('load',()=>window.print())", receipt_page)

        self.assertEqual(self.client.get("/print-agent/next").status_code, 404)
        job = self.client.get("/print-agent/next?token=test-print-token").get_json()["job"]
        self.assertEqual(job["document_type"], "sale_receipt")
        print_page = self.client.get(f"{job['render_url']}?token=test-print-token").get_data(as_text=True)
        self.assertIn("addEventListener('load',()=>window.print())", print_page)
        self.assertTrue(
            self.client.post(f"/print-agent/ack/{job['id']}?token=test-print-token").get_json()["ok"]
        )

    def test_partial_and_full_void_restore_stock_and_keep_audit_history(self):
        with self.app.app_context():
            sale_id, _, _, _ = complete_sale(self.payload(), 1)
            item_id = get_db().execute("SELECT id FROM sale_items WHERE sale_id=?", (sale_id,)).fetchone()[0]
            void_sale(sale_id, {"void_type": "partial", "reason": "ลูกค้าคืนสินค้า", "items": [{"sale_item_id": item_id, "quantity": 1}]}, 1)
            db = get_db()
            self.assertEqual(db.execute("SELECT stock_quantity FROM products WHERE id=1").fetchone()[0], 9)
            self.assertEqual(db.execute("SELECT voided_quantity FROM sale_items WHERE id=?", (item_id,)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT status FROM sales WHERE id=?", (sale_id,)).fetchone()[0], "completed")
            void_sale(sale_id, {"void_type": "full", "reason": "ยกเลิกทั้งบิล"}, 1)
            self.assertEqual(db.execute("SELECT stock_quantity FROM products WHERE id=1").fetchone()[0], 10)
            self.assertEqual(db.execute("SELECT status FROM sales WHERE id=?", (sale_id,)).fetchone()[0], "voided")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sale_voids WHERE sale_id=?", (sale_id,)).fetchone()[0], 2)

    def test_void_page_is_available_to_admin(self):
        with self.app.app_context():
            sale_id, _, _, _ = complete_sale(self.payload(), 1)
        self.assertEqual(self.client.get(f"/sales/{sale_id}/void").status_code, 200)


if __name__ == "__main__":
    unittest.main()
