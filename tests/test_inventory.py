import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "pos.db")})
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            category = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute("""INSERT INTO products
                (barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity)
                VALUES ('10001','สินค้ารับเข้า',?,?,1000,2500,10)""", (category, unit))
            db.commit()
        self.client = self.app.test_client()
        self.client.post("/login", data={"staff_id": 1, "pin": "1234"})
        with self.app.app_context():
            self.csrf = get_db().execute("SELECT csrf_token FROM staff_sessions").fetchone()[0]

    def tearDown(self):
        self.folder.cleanup()

    def test_receiving_uses_lot_cost_and_does_not_change_sale_price(self):
        response = self.client.post("/inventory/receive", data={
            "csrf_token": self.csrf, "product_id": 1, "quantity": "10", "unit_cost": "20.00",
            "supplier_name": "ผู้จำหน่ายทดสอบ",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            db = get_db()
            product = db.execute("SELECT stock_quantity,cost_satang,price_satang FROM products WHERE id=1").fetchone()
            self.assertEqual(product["stock_quantity"], 20)
            self.assertEqual(product["cost_satang"], 1500)
            self.assertEqual(product["price_satang"], 2500)
            self.assertEqual(db.execute("SELECT movement_type FROM stock_movements").fetchone()[0], "receive_stock")


if __name__ == "__main__":
    unittest.main()
