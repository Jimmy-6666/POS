import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from pos_app.routes.online import safe_customer_next_url
from pos_app.services.sales import complete_sale, void_sale
from tests.online_helpers import register_customer


class OnlinePhase2Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "online.db"), "PROJECT_ROOT": self.folder.name})
        with self.app.app_context():
            db = get_db()
            category = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute("UPDATE settings SET value='1' WHERE key='online_ordering_enabled'")
            db.execute("UPDATE settings SET value='0' WHERE key='online_allow_negative_stock'")
            db.execute("""INSERT INTO products(barcode,name_th,category_id,unit_id,price_satang,stock_quantity,is_online_available)
                          VALUES('111','ออนไลน์',?,?,2500,5,1),('222','ซ่อน',?,?,1000,5,0),('333','ปิด',?,?,1000,5,1)""",
                       (category, unit, category, unit, category, unit))
            db.execute("UPDATE products SET is_active=0 WHERE barcode='333'")
            db.execute("""INSERT INTO products(barcode,name_th,category_id,unit_id,price_satang,stock_quantity,is_online_available)
                          VALUES('000','สินค้าราคา UAT',?,?,0,5,1)""", (category, unit))
            db.execute("INSERT INTO delivery_locations(name,room_required) VALUES('จุดทดสอบ',0)")
            db.commit()
            self.product_uuid = db.execute("SELECT product_uuid FROM products WHERE barcode='111'").fetchone()[0]
        self.client = self.app.test_client()

    def tearDown(self):
        self.folder.cleanup()

    def test_catalog_hides_inactive_and_non_online_products(self):
        html = self.client.get("/order").get_data(as_text=True)
        self.assertIn("ออนไลน์", html)
        self.assertNotIn("<h2>ซ่อน</h2>", html)
        self.assertNotIn("<h2>ปิด</h2>", html)
        self.assertIn("สินค้าราคา UAT", html)

    def test_catalog_defaults_to_best_sellers_and_uses_default_product_image(self):
        html = self.client.get("/order").get_data(as_text=True)
        self.assertIn(">สินค้าขายดี</a>", html)
        self.assertNotIn(">ทั้งหมด</a>", html)
        self.assertIn('aria-current="page">สินค้าขายดี</a>', html)
        self.assertIn('placeholder="ค้นหาสินค้าทุกหมวด"', html)
        self.assertIn("/static/img/noimage.png", html)
        self.assertTrue(
            (Path(__file__).resolve().parents[1] / "pos_app" / "static" / "img" / "noimage.png").is_file()
        )

    def test_best_sellers_use_net_quantity_after_voids(self):
        with self.app.app_context():
            db = get_db()
            zero_uuid = db.execute("SELECT product_uuid FROM products WHERE barcode='000'").fetchone()[0]
            db.execute("UPDATE products SET price_satang=100 WHERE product_uuid=?", (zero_uuid,))
            db.commit()
            sale_id = complete_sale({
                "items": [{"product_uuid": self.product_uuid, "quantity": 4}],
                "payment_method": "cash", "amount_received_satang": 10000,
            }, 1)[0]
            complete_sale({
                "items": [{"product_uuid": zero_uuid, "quantity": 2}],
                "payment_method": "cash", "amount_received_satang": 200,
            }, 1)
            sale_item_id = db.execute(
                "SELECT id FROM sale_items WHERE sale_id=?", (sale_id,)
            ).fetchone()[0]
            void_sale(sale_id, {
                "void_type": "partial", "reason": "ทดสอบอันดับขายสุทธิ",
                "items": [{"sale_item_id": sale_item_id, "quantity": 3}],
            }, 1)

        names = [row["name_th"] for row in self.client.get("/order/api/products").get_json()]
        self.assertEqual(names[:2], ["สินค้าราคา UAT", "ออนไลน์"])

    def test_search_is_global_even_when_a_category_is_in_the_url(self):
        with self.app.app_context():
            db = get_db()
            original_category = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            other_category = db.execute(
                "INSERT INTO categories(name_th,sort_order) VALUES('หมวดค้นหา',99)"
            ).lastrowid
            db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,price_satang,stock_quantity,is_online_available)
                   VALUES('444','ค้นหาข้ามหมวด',?,?,1000,5,1)""",
                (other_category, unit),
            )
            db.commit()

        filtered = self.client.get(f"/order/api/products?category_id={other_category}").get_json()
        self.assertEqual([row["name_th"] for row in filtered], ["ค้นหาข้ามหมวด"])
        global_results = self.client.get(
            f"/order/api/products?category_id={original_category}&q=ข้ามหมวด"
        ).get_json()
        self.assertEqual([row["name_th"] for row in global_results], ["ค้นหาข้ามหมวด"])

    def test_cart_uses_server_price_and_validates_stock(self):
        response = self.client.post("/order/api/cart/validate", json={"items": [{"product_uuid": self.product_uuid, "quantity": 2, "price_satang": 1}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["subtotal_satang"], 5000)
        response = self.client.post("/order/api/cart/validate", json={"items": [{"product_uuid": self.product_uuid, "quantity": 6}]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("ไม่เพียงพอ", response.get_json()["error"])

    def test_customer_catalog_and_cart_api_hide_barcode_and_exact_stock(self):
        catalog = self.client.get("/order").get_data(as_text=True)
        self.assertNotIn('"barcode": "111"', catalog)
        self.assertNotIn('"available_quantity"', catalog)
        products = self.client.get("/order/api/products").get_json()
        product = next(row for row in products if row["product_uuid"] == self.product_uuid)
        self.assertNotIn("barcode", product)
        self.assertNotIn("available_quantity", product)
        self.assertEqual(product["max_quantity"], 50.0)
        cart = self.client.post(
            "/order/api/cart/validate", json={"items": [{"product_uuid": self.product_uuid, "quantity": 1}]}
        ).get_json()["items"][0]
        self.assertNotIn("barcode", cart)
        self.assertNotIn("available_quantity", cart)
        self.assertEqual(cart["max_quantity"], 50.0)

    def test_customer_stock_error_does_not_reveal_exact_quantity(self):
        response = self.client.post(
            "/order/api/cart/validate", json={"items": [{"product_uuid": self.product_uuid, "quantity": 6}]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("5", response.get_json()["error"])

    def test_customer_next_redirect_rejects_external_urls(self):
        self.assertEqual(safe_customer_next_url("/order/checkout?step=1"), "/order/checkout?step=1")
        self.assertIsNone(safe_customer_next_url("https://attacker.example/"))
        self.assertIsNone(safe_customer_next_url("//attacker.example/"))

    def test_customer_javascript_reuses_session_and_avoids_untrusted_html(self):
        static_root = Path(__file__).resolve().parents[1] / "pos_app" / "static" / "js"
        line_auth = (static_root / "online-line-auth.js").read_text(encoding="utf-8")
        checkout = (static_root / "online-checkout.js").read_text(encoding="utf-8")
        self.assertIn('api("/api/auth/me")', line_auth)
        self.assertIn("safeOrderPath", line_auth)
        self.assertNotIn("innerHTML", checkout)

    def test_checkout_requires_line_session_and_has_no_guest_pin_fields(self):
        page = self.client.get("/order/checkout")
        self.assertEqual(page.status_code, 302)
        register_customer(self.client)
        html = self.client.get("/order/checkout").get_data(as_text=True)
        self.assertIn("ข้อมูลจัดส่งและการชำระเงิน", html)
        self.assertIn("เลือกข้อมูลจัดส่งเดิม", html)
        self.assertNotIn('id="paymentStep"', html)
        self.assertNotIn("guestPhone", html)
        self.assertNotIn("ตั้ง PIN เพื่อใช้สั่งครั้งถัดไป", html)

    def test_cart_is_a_dedicated_page_not_a_catalog_dialog(self):
        catalog = self.client.get("/order").get_data(as_text=True)
        self.assertIn('href="/order/cart"', catalog)
        self.assertNotIn('id="cartDialog"', catalog)
        cart = self.client.get("/order/cart")
        self.assertEqual(cart.status_code, 200)
        self.assertIn("ตะกร้าของฉัน", cart.get_data(as_text=True))
        self.assertIn("สั่งสินค้าเพิ่ม", cart.get_data(as_text=True))

    def test_guest_order_submission_is_rejected(self):
        response = self.client.post("/order/api/orders", json={"items": [{"product_uuid": self.product_uuid, "quantity": 1}]})
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
