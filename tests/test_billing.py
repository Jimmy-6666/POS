import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from pos_app.services.sales import complete_sale
from tests.staff_helpers import staff_login


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "test.db")})

    def tearDown(self):
        self.folder.cleanup()

    def test_billed_sale_and_partial_payment(self):
        with self.app.app_context():
            db = get_db()
            db.execute("""INSERT INTO products(barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity)
                VALUES('BILL-1','สินค้าทดสอบ',1,1,500,1000,10)""")
            db.execute("INSERT INTO billing_customers(name,credit_limit_satang) VALUES('โรงเรียนทดสอบ',100000)")
            customer_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()
            product_uuid = db.execute("SELECT product_uuid FROM products WHERE id=1").fetchone()[0]
            sale_id, _, cart, _ = complete_sale({"items": [{"product_uuid": product_uuid, "quantity": 1}], "payment_method": "billing", "billing_customer_id": customer_id}, 1)
            billed = db.execute("SELECT * FROM billed_sales WHERE sale_id=?", (sale_id,)).fetchone()
            self.assertEqual(billed["original_satang"], cart["total_satang"])
            self.assertEqual(billed["status"], "outstanding")

        client = self.app.test_client()
        self.assertEqual(staff_login(client).status_code, 302)
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            csrf = db.execute("SELECT csrf_token FROM staff_sessions WHERE staff_id=1").fetchone()[0]
            db.commit()
        response = client.post(f"/billing/{billed['id']}/payments", data={"csrf_token": csrf, "amount": "1", "payment_method": "cash"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            updated = get_db().execute("SELECT paid_satang,status FROM billed_sales WHERE id=?", (billed["id"],)).fetchone()
            self.assertEqual(updated["paid_satang"], 100)
            self.assertIn(updated["status"], ("partial", "paid"))
        page = client.get("/billing").get_data(as_text=True)
        self.assertNotIn("กำหนดชำระ", page)
        self.assertIn("receipt-popup", page)
        self.assertIn("TOTAL รายการที่เลือก", page)
        response = client.post("/billing/payments/bulk", data={"csrf_token": csrf, "billed_id": billed["id"], "payment_method": "transfer"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            cleared = get_db().execute("SELECT original_satang,paid_satang,status FROM billed_sales WHERE id=?", (billed["id"],)).fetchone()
            self.assertEqual(cleared["original_satang"], cleared["paid_satang"])
            self.assertEqual(cleared["status"], "paid")


if __name__ == "__main__":
    unittest.main()
