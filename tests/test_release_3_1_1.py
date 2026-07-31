import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from tests.staff_helpers import staff_login


class Release311Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": str(root / "pos.db"),
                "PROJECT_ROOT": str(root),
            }
        )
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            category_id = db.execute(
                "SELECT id FROM categories WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()[0]
            unit_id = db.execute(
                "SELECT id FROM units WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()[0]
            cursor = db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,price_satang,stock_quantity)
                   VALUES ('311-GRID-ITEM','สินค้าทดสอบตำแหน่งเก้า',?,?,1200,5)""",
                (category_id, unit_id),
            )
            self.product_uuid = db.execute(
                "SELECT product_uuid FROM products WHERE id=?", (cursor.lastrowid,)
            ).fetchone()[0]
            db.commit()
        self.client = self.app.test_client()
        self.assertEqual(staff_login(self.client, 1, "1234").status_code, 302)

    def tearDown(self):
        self.folder.cleanup()

    def csrf(self):
        with self.app.app_context():
            return get_db().execute(
                """SELECT csrf_token FROM staff_sessions
                   WHERE staff_id=1 ORDER BY created_at DESC LIMIT 1"""
            ).fetchone()[0]

    def test_main_menu_position_nine_is_reserved_but_product_slot_nine_remains_valid(self):
        response = self.client.post(
            "/products/pos-buttons",
            data={
                "csrf_token": self.csrf(),
                "action": "create_group",
                "name_th": "ตำแหน่งต้องห้าม",
                "position": "9",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "ตำแหน่งเมนู 9 สงวนไว้สำหรับปุ่มตั้งราคาขาย Manual",
            response.get_data(as_text=True),
        )
        with self.app.app_context():
            self.assertEqual(
                get_db().execute(
                    "SELECT COUNT(*) FROM pos_button_groups WHERE position=9"
                ).fetchone()[0],
                0,
            )

        self.client.post(
            "/products/pos-buttons",
            data={
                "csrf_token": self.csrf(),
                "action": "create_group",
                "name_th": "เมนูปกติ",
                "position": "1",
            },
        )
        with self.app.app_context():
            group_id = get_db().execute(
                "SELECT id FROM pos_button_groups WHERE position=1"
            ).fetchone()[0]
        response = self.client.post(
            "/products/pos-buttons",
            data={
                "csrf_token": self.csrf(),
                "action": "add_item",
                "group_id": str(group_id),
                "product_uuid": self.product_uuid,
                "position": "9",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(
                get_db().execute(
                    "SELECT position FROM pos_button_items WHERE group_id=?",
                    (group_id,),
                ).fetchone()[0],
                9,
            )

    def test_cashier_controls_manual_cancel_and_styled_remove_are_wired(self):
        root = Path(self.app.root_path)
        html = self.client.get("/pos").get_data(as_text=True)
        settings = (root / "templates" / "pos_button_settings.html").read_text(
            encoding="utf-8"
        )
        js = (root / "static" / "js" / "pos.js").read_text(encoding="utf-8")
        css = (root / "static" / "css" / "v310.css").read_text(encoding="utf-8")

        self.assertIn('id="manualPriceCancel"', html)
        self.assertIn("async function cancelManualPrice()", js)
        self.assertIn("manualPriceDialog.addEventListener('cancel'", js)
        self.assertIn("$('#manualPriceCancel').addEventListener('click', cancelManualPrice)", js)
        self.assertIn("renderCart(); focusProductLookup();", js)
        self.assertIn("catalogMode === 'groups' && slot === 9", js)
        self.assertIn("data-manual-price", js)
        self.assertIn("openManualPrice(null, manualBarcode, 'manual_price_barcode')", js)
        self.assertIn('class="danger-button" type="submit">นำออก</button>', settings)
        self.assertIn(".pos-button-item-list .danger-button{", css)
        self.assertIn(".pos-manual-price-button{", css)
        self.assertIn(".manual-price-actions{", css)


if __name__ == "__main__":
    unittest.main()
