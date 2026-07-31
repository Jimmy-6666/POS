import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from pos_app import create_app
from pos_app.database import get_db
from pos_app.migrations import MIGRATIONS
from tests.staff_helpers import staff_login


class Release310Tests(unittest.TestCase):
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
            product = db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,price_satang,stock_quantity)
                   VALUES ('310-MANUAL','น้ำแข็งถุง',?,?,1000,20)""",
                (category_id, unit_id),
            )
            self.product_id = product.lastrowid
            self.product_uuid = db.execute(
                "SELECT product_uuid FROM products WHERE id=?", (self.product_id,)
            ).fetchone()[0]
            cashier_role = db.execute(
                "SELECT id FROM roles WHERE code='cashier'"
            ).fetchone()[0]
            cashier = db.execute(
                """INSERT INTO staff
                   (display_name,pin_hash,role_id,must_change_pin,is_active)
                   VALUES ('Cashier 3.1.0',?,?,0,1)""",
                (generate_password_hash("1111"), cashier_role),
            )
            self.cashier_id = cashier.lastrowid
            db.commit()
        self.admin = self.app.test_client()
        self.assertEqual(staff_login(self.admin, 1, "1234").status_code, 302)
        self.cashier = self.app.test_client()
        self.assertEqual(
            staff_login(self.cashier, self.cashier_id, "1111").status_code, 302
        )

    def tearDown(self):
        self.folder.cleanup()

    def csrf(self, staff_id=1):
        with self.app.app_context():
            return get_db().execute(
                """SELECT csrf_token FROM staff_sessions
                   WHERE staff_id=? ORDER BY created_at DESC LIMIT 1""",
                (staff_id,),
            ).fetchone()[0]

    def create_group_and_item(self):
        response = self.admin.post(
            "/products/pos-buttons",
            data={
                "csrf_token": self.csrf(),
                "action": "create_group",
                "name_th": "สินค้าหน้าร้าน",
                "position": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            group_id = get_db().execute(
                "SELECT id FROM pos_button_groups WHERE position=1"
            ).fetchone()[0]
        response = self.admin.post(
            "/products/pos-buttons",
            data={
                "csrf_token": self.csrf(),
                "action": "add_item",
                "group_id": str(group_id),
                "product_uuid": self.product_uuid,
                "position": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        return group_id

    def test_configurable_text_only_grid_and_public_pos_api(self):
        group_id = self.create_group_and_item()
        groups = self.cashier.get("/api/pos/button-groups")
        self.assertEqual(groups.status_code, 200)
        self.assertEqual(
            groups.get_json(),
            [{"id": group_id, "name_th": "สินค้าหน้าร้าน", "position": 1}],
        )
        products = self.cashier.get(
            f"/api/pos/button-groups/{group_id}/products"
        ).get_json()
        self.assertEqual(products["group"]["name_th"], "สินค้าหน้าร้าน")
        self.assertEqual(products["products"][0]["product_uuid"], self.product_uuid)
        self.assertEqual(products["products"][0]["position"], 1)

        html = self.cashier.get("/pos").get_data(as_text=True)
        self.assertIn('class="pos-button-grid"', html)
        self.assertIn('id="catalogPreviousButton"', html)
        self.assertIn('id="catalogNextButton"', html)
        self.assertNotIn('id="categoryBoxes"', html)
        self.assertNotIn("category-chip", html)

        js = (Path(self.app.static_folder) / "js" / "pos.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("const catalogPageSize = 9", js)
        self.assertIn("data-button-group", js)
        self.assertIn("pos-product-text-button", js)
        self.assertIn("<strong><span>${escapeHtml(row.name_th)}</span></strong>", js)
        self.assertIn("/api/pos/button-groups", js)
        self.assertNotIn("catalogEyebrow", js)
        self.assertNotIn("<small>เมนู ${slot}</small>", js)
        self.assertNotIn("แตะเพื่อเลือกสินค้า", js)
        self.assertNotIn("<small>${escapeHtml(row.barcode", js)
        self.assertNotIn("<img", js)
        self.assertNotIn("noimage", js)
        self.assertIn("$('#productLookup').value = '';\n      await loadButtonGroups();", js)
        css = (Path(self.app.static_folder) / "css" / "v310.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".pos-product-text-button strong span{", css)
        self.assertIn("align-items:center;", css)
        self.assertIn("-webkit-line-clamp:2;", css)

    def test_manager_configuration_is_audited_and_cashier_is_forbidden(self):
        group_id = self.create_group_and_item()
        page = self.admin.get(
            f"/products/pos-buttons?group_id={group_id}&q=น้ำแข็ง"
        ).get_data(as_text=True)
        self.assertIn("ตั้งค่าปุ่มขายสินค้า", page)
        self.assertIn("น้ำแข็งถุง", page)
        self.assertIn("ตำแหน่ง 9 สงวนไว้สำหรับตั้งราคาขาย Manual", page)
        self.assertEqual(self.cashier.get("/products/pos-buttons").status_code, 403)
        with self.app.app_context():
            actions = {
                row[0]
                for row in get_db().execute(
                    """SELECT action FROM audit_logs
                       WHERE action IN ('create_pos_button_group','add_pos_button_item')"""
                )
            }
        self.assertEqual(
            actions, {"create_pos_button_group", "add_pos_button_item"}
        )

    def test_every_role_enters_pos_and_fresh_login_resets_sidebar(self):
        client = self.app.test_client()
        login_page = client.get("/login")
        token = re.search(
            r'name="login_csrf_token" value="([^"]+)"',
            login_page.get_data(as_text=True),
        ).group(1)
        response = client.post(
            "/login",
            data={
                "staff_id": str(self.cashier_id),
                "pin": "1111",
                "next": "/products",
                "login_csrf_token": token,
            },
        )
        self.assertTrue(response.headers["Location"].endswith("/pos"))
        pos_page = client.get(response.headers["Location"])
        self.assertIn('data-reset-sidebar="1"', pos_page.get_data(as_text=True))

        sidebar = (Path(self.app.static_folder) / "js" / "sidebar.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("resetAfterLogin", sidebar)
        self.assertIn("sidebar-collapsed-v2", sidebar)

    def test_reconciliation_has_shared_touch_numpad_without_pin(self):
        html = self.cashier.get("/reconciliations").get_data(as_text=True)
        self.assertEqual(html.count("data-reconciliation-money"), 4)
        self.assertEqual(html.count("data-reconciliation-key="), 11)
        self.assertIn('data-reconciliation-action="backspace"', html)
        self.assertIn('data-reconciliation-action="clear"', html)
        self.assertIn('data-reconciliation-action="next"', html)
        self.assertNotIn('name="close_pin"', html)
        js = (
            Path(self.app.static_folder) / "js" / "reconciliation-numpad.js"
        ).read_text(encoding="utf-8")
        self.assertIn("activeInput", js)
        self.assertIn("nextInput", js)

    def test_migration_28_is_idempotent_and_protects_positions(self):
        db = sqlite3.connect(":memory:")
        try:
            migration = next(item for item in MIGRATIONS if item.version == 28)
            migration.apply(db)
            migration.apply(db)
            db.execute(
                "INSERT INTO pos_button_groups(name_th,position) VALUES ('หนึ่ง',1)"
            )
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO pos_button_groups(name_th,position) VALUES ('ซ้ำ',1)"
                )
        finally:
            db.close()

    def test_release_builder_targets_current_version(self):
        script = (Path(self.app.root_path).parent / "build-release.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('[string]$Version = "3.1.1"', script)
        self.assertIn('"VERSION_3.1.1.md"', script)
        self.assertNotIn('"VERSION_3.0.8.md"', script)


if __name__ == "__main__":
    unittest.main()
