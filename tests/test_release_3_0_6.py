import io
import json
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from pos_app import create_app
from pos_app.database import get_db
from tests.staff_helpers import staff_login


class Release306Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        (root / "uploads" / "products").mkdir(parents=True)
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(root / "pos.db"),
            "PROJECT_ROOT": str(root),
        })
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            self.category_id = db.execute(
                "SELECT id FROM categories WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()[0]
            self.unit_id = db.execute(
                "SELECT id FROM units WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()[0]
            db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,image_path)
                   VALUES ('quick-blank','สินค้ายังไม่มีรูป',?,?,500,1000,NULL)""",
                (self.category_id, self.unit_id),
            )
            db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,image_path)
                   VALUES ('quick-imaged','สินค้ามีรูปแล้ว',?,?,500,1200,'already.jpg')""",
                (self.category_id, self.unit_id),
            )
            db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,image_path)
                   VALUES ('quick-next','สินค้าชิ้นถัดไป',?,?,500,700,NULL)""",
                (self.category_id, self.unit_id),
            )
            self.blank_uuid = db.execute(
                "SELECT product_uuid FROM products WHERE barcode='quick-blank'"
            ).fetchone()[0]
            self.imaged_uuid = db.execute(
                "SELECT product_uuid FROM products WHERE barcode='quick-imaged'"
            ).fetchone()[0]
            manager_role = db.execute("SELECT id FROM roles WHERE code='manager'").fetchone()[0]
            manager = db.execute(
                "INSERT INTO staff(display_name,pin_hash,role_id,must_change_pin) VALUES(?,?,?,0)",
                ("Manager 3.0.6", generate_password_hash("4321"), manager_role),
            )
            self.manager_id = manager.lastrowid
            cashier_role = db.execute("SELECT id FROM roles WHERE code='cashier'").fetchone()[0]
            cursor = db.execute(
                "INSERT INTO staff(display_name,pin_hash,role_id,must_change_pin) VALUES(?,?,?,0)",
                ("Cashier 3.0.6", generate_password_hash("2468"), cashier_role),
            )
            self.cashier_id = cursor.lastrowid
            db.commit()

    def tearDown(self):
        self.folder.cleanup()

    def client_for(self, staff_id=1, pin="1234"):
        client = self.app.test_client()
        self.assertEqual(staff_login(client, staff_id, pin).status_code, 302)
        with self.app.app_context():
            csrf = get_db().execute(
                "SELECT csrf_token FROM staff_sessions WHERE staff_id=? ORDER BY id DESC LIMIT 1",
                (staff_id,),
            ).fetchone()[0]
        return client, csrf

    def quick_payload(self, csrf, *, product_uuid=None, barcode="quick-blank"):
        return {
            "csrf_token": csrf,
            "product_uuid": product_uuid or self.blank_uuid,
            "barcode": barcode,
            "price": "20",
            "name_th": "ชื่อสินค้าที่แก้แบบด่วน",
            "category_id": str(self.category_id),
            "unit_id": str(self.unit_id),
        }

    def assert_not_found_dialog(self, html):
        self.assertIn('id="quickProductNotFound"', html)
        self.assertIn("ไม่พบสินค้า", html)
        self.assertIn('type="submit" autofocus>ยืนยัน</button>', html)
        self.assertNotIn('data-quick-product-form', html)

    def test_quick_edit_scan_page_and_found_product_fields(self):
        admin, _ = self.client_for()
        scan = admin.get("/products/quick-edit").get_data(as_text=True)
        self.assertIn('id="quickProductBarcode"', scan)
        self.assertIn('name="barcode" autocomplete="off" required autofocus', scan)
        self.assertNotIn('data-quick-product-form', scan)

        found = admin.get(
            "/products/quick-edit",
            query_string={"barcode": "quick-blank"},
        ).get_data(as_text=True)
        self.assertIn("พบบาร์โค้ด quick-blank", found)
        self.assertIn('name="image" type="file"', found)
        self.assertIn('name="camera_image" type="file"', found)
        self.assertIn('capture="environment"', found)
        self.assertIn('id="productImagePreview"', found)
        self.assertIn('name="price"', found)
        self.assertIn('inputmode="numeric" min="0" step="1"', found)
        self.assertIn('value="10"', found)
        self.assertIn('name="name_th" rows="3"', found)
        self.assertIn('name="category_id"', found)
        self.assertIn('name="unit_id"', found)
        self.assertIn('id="quickProductSave"', found)
        self.assertIn('id="quickProductEditorDialog"', found)
        self.assertIn('data-quick-product-dialog', found)
        self.assertIn('aria-labelledby="quickProductEditorTitle"', found)
        self.assertIn('aria-label="ปิดและกลับไปสแกนสินค้าชิ้นอื่น"', found)
        self.assertIn("product-form.js?v=3", found)
        self.assertIn("product-quick-edit.js?v=2", found)

        quick_edit_js = (
            Path(self.app.static_folder) / "js" / "product-quick-edit.js"
        ).read_text(encoding="utf-8")
        self.assertIn("window.matchMedia('(max-width: 600px)')", quick_edit_js)
        self.assertIn("editorDialog.showModal()", quick_edit_js)
        self.assertIn("quick-product-modal-open", quick_edit_js)

    def test_unknown_and_already_imaged_barcodes_have_the_same_not_found_result(self):
        admin, _ = self.client_for()
        unknown = admin.get(
            "/products/quick-edit",
            query_string={"barcode": "missing-product"},
        ).get_data(as_text=True)
        imaged = admin.get(
            "/products/quick-edit",
            query_string={"barcode": "quick-imaged"},
        ).get_data(as_text=True)
        self.assert_not_found_dialog(unknown)
        self.assert_not_found_dialog(imaged)
        self.assertNotIn("สินค้ามีรูปแล้ว", imaged)

    def test_quick_edit_saves_image_and_fields_then_returns_to_scanner(self):
        admin, csrf = self.client_for()
        payload = self.quick_payload(csrf)
        payload["camera_image"] = (io.BytesIO(b"quick image"), "quick.jpg")
        response = admin.post(
            "/products/quick-edit",
            data=payload,
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/products/quick-edit"))
        with self.app.app_context():
            db = get_db()
            product = db.execute(
                """SELECT name_th,category_id,unit_id,price_satang,image_path
                   FROM products WHERE product_uuid=?""",
                (self.blank_uuid,),
            ).fetchone()
            self.assertEqual(product["name_th"], "ชื่อสินค้าที่แก้แบบด่วน")
            self.assertEqual(product["category_id"], self.category_id)
            self.assertEqual(product["unit_id"], self.unit_id)
            self.assertEqual(product["price_satang"], 2000)
            self.assertTrue(product["image_path"].endswith(".jpg"))
            audit = db.execute(
                "SELECT old_value,new_value FROM audit_logs WHERE action='quick_edit_product' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(json.loads(audit["new_value"])["image_path"], product["image_path"])
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM audit_logs WHERE action='change_price' AND entity_id=?",
                    (self.blank_uuid,),
                ).fetchone()[0],
                1,
            )
        repeat = admin.get(
            "/products/quick-edit",
            query_string={"barcode": "quick-blank"},
        ).get_data(as_text=True)
        self.assert_not_found_dialog(repeat)

    def test_last_integer_baht_price_is_remembered_per_logged_in_staff(self):
        admin, csrf = self.client_for()
        response = admin.post("/products/quick-edit", data=self.quick_payload(csrf))
        self.assertEqual(response.status_code, 302)
        admin_next = admin.get(
            "/products/quick-edit",
            query_string={"barcode": "quick-next"},
        ).get_data(as_text=True)
        self.assertIn('name="price" type="number" inputmode="numeric" min="0" step="1" required value="20"', admin_next)

        manager, _ = self.client_for(self.manager_id, "4321")
        manager_next = manager.get(
            "/products/quick-edit",
            query_string={"barcode": "quick-next"},
        ).get_data(as_text=True)
        self.assertIn('name="price" type="number" inputmode="numeric" min="0" step="1" required value="7"', manager_next)

    def test_quick_edit_rejects_satang_input(self):
        admin, csrf = self.client_for()
        payload = self.quick_payload(csrf)
        payload["price"] = "20.50"
        response = admin.post("/products/quick-edit", data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("ราคาขายต้องเป็นจำนวนเต็มบาท", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(
                get_db().execute(
                    "SELECT price_satang FROM products WHERE product_uuid=?",
                    (self.blank_uuid,),
                ).fetchone()[0],
                1000,
            )

    def test_direct_post_cannot_edit_a_product_that_already_has_an_image(self):
        admin, csrf = self.client_for()
        payload = self.quick_payload(
            csrf,
            product_uuid=self.imaged_uuid,
            barcode="quick-imaged",
        )
        response = admin.post("/products/quick-edit", data=payload)
        self.assertEqual(response.status_code, 200)
        self.assert_not_found_dialog(response.get_data(as_text=True))
        with self.app.app_context():
            product = get_db().execute(
                "SELECT name_th,price_satang,image_path FROM products WHERE product_uuid=?",
                (self.imaged_uuid,),
            ).fetchone()
            self.assertEqual(product["name_th"], "สินค้ามีรูปแล้ว")
            self.assertEqual(product["price_satang"], 1200)
            self.assertEqual(product["image_path"], "already.jpg")

    def test_quick_edit_requires_csrf_and_product_permission(self):
        admin, _ = self.client_for()
        self.assertEqual(
            admin.post("/products/quick-edit", data={"csrf_token": "wrong"}).status_code,
            400,
        )
        cashier, _ = self.client_for(self.cashier_id, "2468")
        self.assertEqual(cashier.get("/products/quick-edit").status_code, 403)

    def test_sidebar_groups_and_quick_edit_menu_defaults(self):
        admin, _ = self.client_for()
        html = admin.get("/products/quick-edit").get_data(as_text=True)
        self.assertEqual(html.count('data-default-expanded="true"'), 2)
        self.assertIn('data-nav-section="online-orders" data-default-expanded="true"', html)
        self.assertIn('data-nav-section="pos-sales" data-default-expanded="true"', html)
        self.assertIn('data-nav-section="products-inventory" data-default-expanded="false"', html)
        product_group = html.split('data-nav-section="products-inventory"', 1)[1].split("</section>", 1)[0]
        self.assertGreater(product_group.rfind('href="/products/quick-edit"'), product_group.rfind("ประวัติสต็อก"))
        self.assertIn("แก้ไขสินค้าด่วน", product_group)
        self.assertIn('aria-expanded="false"', product_group)
        self.assertEqual(
            html.count('class="nav-group-arrow" aria-hidden="true">^</span>'),
            6,
        )
        self.assertNotIn('class="nav-group-arrow" aria-hidden="true">v</span>', html)
        self.assertIn("css/v306.css?v=3", html)
        self.assertIn("js/sidebar.js?v=4", html)
        sidebar_js = (Path(self.app.static_folder) / "js" / "sidebar.js").read_text(encoding="utf-8")
        self.assertIn("sidebar-sections-v306", sidebar_js)
        self.assertIn("arrow.textContent = '^'", sidebar_js)
        self.assertNotIn(" : 'v'", sidebar_js)
        css = (Path(self.app.static_folder) / "css" / "v306.css").read_text(encoding="utf-8")
        self.assertIn(".nav-section.is-collapsed .nav-group-items", css)
        self.assertIn(".nav-section.is-collapsed .nav-group-arrow", css)
        self.assertIn("transform:rotate(180deg)", css)
        self.assertIn("@media(max-width:600px)", css)
        self.assertIn(".quick-product-editor-dialog[open]", css)
        self.assertIn("height:100dvh", css)
        self.assertIn('grid-template-areas:', css)
        self.assertIn('"price unit"', css)
        self.assertIn("@media(max-width:600px) and (max-height:620px)", css)


if __name__ == "__main__":
    unittest.main()
