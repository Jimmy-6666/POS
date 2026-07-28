import sqlite3
import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from pos_app.services.sales import SaleError, calculate_cart


class ProductIdentityTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "pos.db")})
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            category_id = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit_id = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute(
                """INSERT INTO products
                   (barcode,sku,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity,is_online_available)
                   VALUES('00123','SKU-00123','UUID product',?,?,100,250,4,1)""",
                (category_id, unit_id),
            )
            db.execute("UPDATE settings SET value='1' WHERE key='online_ordering_enabled'")
            db.commit()
            self.product_uuid = db.execute("SELECT product_uuid FROM products WHERE id=1").fetchone()[0]
        self.client = self.app.test_client()
        self.client.post("/login", data={"staff_id": 1, "pin": "1234"})

    def tearDown(self):
        self.folder.cleanup()

    def test_uuid_is_immutable_and_sku_barcode_do_not_control_identity(self):
        with self.app.app_context():
            db = get_db()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE products SET product_uuid='00000000-0000-4000-8000-000000000000' WHERE id=1")
            db.rollback()
            db.execute("UPDATE products SET barcode='00999',sku='NEW-SKU' WHERE id=1")
            db.commit()
            quote = calculate_cart([{"product_uuid": self.product_uuid, "quantity": 2}])
            self.assertEqual(quote["subtotal_satang"], 500)

    def test_external_product_boundaries_accept_uuid_not_numeric_ids(self):
        with self.app.app_context():
            self.assertEqual(
                calculate_cart([{"product_uuid": self.product_uuid, "quantity": 1}])["items"][0]["product"]["product_uuid"],
                self.product_uuid,
            )
            with self.assertRaises(SaleError):
                calculate_cart([{"product_id": 1, "quantity": 1}])

        pos_product = self.client.get("/api/pos/products?barcode=00123").get_json()[0]
        self.assertEqual(pos_product["product_uuid"], self.product_uuid)
        self.assertNotIn("id", pos_product)

        online_cart = self.client.post(
            "/order/api/cart/validate", json={"items": [{"product_uuid": self.product_uuid, "quantity": 1}]}
        ).get_json()
        self.assertEqual(online_cart["items"][0]["product_uuid"], self.product_uuid)
        self.assertNotIn("product_id", online_cart["items"][0])
        rejected = self.client.post(
            "/order/api/cart/validate", json={"items": [{"product_id": 1, "quantity": 1}]}
        )
        self.assertEqual(rejected.status_code, 400)


if __name__ == "__main__":
    unittest.main()
