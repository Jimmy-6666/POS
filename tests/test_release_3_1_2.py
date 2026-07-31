import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from pos_app import create_app
from pos_app.database import get_db
from pos_app.migrations import MIGRATIONS
from tests.staff_helpers import staff_login


class Release312Tests(unittest.TestCase):
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
            cashier_role = db.execute(
                "SELECT id FROM roles WHERE code='cashier'"
            ).fetchone()[0]
            cashier = db.execute(
                """INSERT INTO staff
                   (display_name,pin_hash,role_id,must_change_pin,is_active)
                   VALUES ('Cashier 3.1.2',?,?,0,1)""",
                (generate_password_hash("1111"), cashier_role),
            )
            self.cashier_id = cashier.lastrowid
            manager_role = db.execute(
                "SELECT id FROM roles WHERE code='manager'"
            ).fetchone()[0]
            manager = db.execute(
                """INSERT INTO staff
                   (display_name,pin_hash,role_id,must_change_pin,is_active)
                   VALUES ('Manager 3.1.2',?,?,0,1)""",
                (generate_password_hash("4321"), manager_role),
            )
            self.manager_id = manager.lastrowid
            self.category_id = db.execute(
                "SELECT id FROM categories WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()[0]
            self.unit_id = db.execute(
                "SELECT id FROM units WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()[0]
            cursor = db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,
                    stock_quantity,requires_manual_price,is_online_available)
                   VALUES ('312-FRESH-PORK','หมูสดราคาประจำวัน',?,?,12000,19900,10,1,0)""",
                (self.category_id, self.unit_id),
            )
            self.product_id = cursor.lastrowid
            self.product_uuid = db.execute(
                "SELECT product_uuid FROM products WHERE id=?", (self.product_id,)
            ).fetchone()[0]
            db.commit()
        self.admin = self.app.test_client()
        self.assertEqual(staff_login(self.admin, 1, "1234").status_code, 302)
        self.cashier = self.app.test_client()
        self.assertEqual(
            staff_login(self.cashier, self.cashier_id, "1111").status_code, 302
        )
        self.manager = self.app.test_client()
        self.assertEqual(
            staff_login(self.manager, self.manager_id, "4321").status_code, 302
        )

    def tearDown(self):
        self.folder.cleanup()

    def csrf(self, staff_id):
        with self.app.app_context():
            return get_db().execute(
                """SELECT csrf_token FROM staff_sessions
                   WHERE staff_id=? ORDER BY created_at DESC LIMIT 1""",
                (staff_id,),
            ).fetchone()[0]

    def product_form_data(self, barcode, *, online=False, manual=False):
        data = {
            "csrf_token": self.csrf(1),
            "barcode": barcode,
            "name_th": "สินค้าสร้างใหม่",
            "category_id": str(self.category_id),
            "unit_id": str(self.unit_id),
            "cost": "10",
            "price": "20",
            "stock_quantity": "0",
            "minimum_stock": "0",
            "is_active": "on",
        }
        if online:
            data["is_online_available"] = "on"
            data["online_sort_order"] = "99"
            data["online_max_quantity"] = "5"
        if manual:
            data["requires_manual_price"] = "on"
        return data

    def enter_manual_price(self, price_baht):
        return self.cashier.post(
            "/api/pos/manual-price",
            json={"barcode": "312-FRESH-PORK", "price_baht": price_baht},
            headers={"X-CSRF-Token": self.csrf(self.cashier_id)},
        )

    def test_migration_29_is_idempotent_and_preserves_existing_products(self):
        db = sqlite3.connect(":memory:")
        try:
            db.execute(
                """CREATE TABLE products (
                    id INTEGER PRIMARY KEY,
                    barcode TEXT NOT NULL,
                    name_th TEXT NOT NULL
                )"""
            )
            db.execute(
                "INSERT INTO products(barcode,name_th) VALUES ('OLD','สินค้าเดิม')"
            )
            migration = next(item for item in MIGRATIONS if item.version == 29)
            migration.apply(db)
            migration.apply(db)
            columns = {row[1] for row in db.execute("PRAGMA table_info(products)")}
            self.assertIn("requires_manual_price", columns)
            self.assertEqual(
                db.execute(
                    "SELECT requires_manual_price FROM products WHERE barcode='OLD'"
                ).fetchone()[0],
                0,
            )
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """INSERT INTO products
                       (barcode,name_th,requires_manual_price)
                       VALUES ('BAD','ค่าไม่ถูกต้อง',2)"""
                )
        finally:
            db.close()

    def test_migration_30_grants_manager_settings_without_granting_cashier(self):
        db = sqlite3.connect(":memory:")
        try:
            db.executescript(
                """CREATE TABLE roles (
                       id INTEGER PRIMARY KEY,
                       code TEXT NOT NULL UNIQUE
                   );
                   CREATE TABLE permissions (
                       id INTEGER PRIMARY KEY,
                       code TEXT NOT NULL UNIQUE,
                       name_th TEXT NOT NULL
                   );
                   CREATE TABLE role_permissions (
                       role_id INTEGER NOT NULL,
                       permission_id INTEGER NOT NULL,
                       PRIMARY KEY(role_id,permission_id)
                   );
                   INSERT INTO roles(id,code) VALUES
                       (1,'admin'),(2,'manager'),(3,'cashier');"""
            )
            migration = next(item for item in MIGRATIONS if item.version == 30)
            migration.apply(db)
            migration.apply(db)
            granted = db.execute(
                """SELECT r.code FROM role_permissions rp
                   JOIN roles r ON r.id=rp.role_id
                   JOIN permissions p ON p.id=rp.permission_id
                   WHERE p.code='settings.manage' ORDER BY r.code"""
            ).fetchall()
            self.assertEqual(granted, [("manager",)])
        finally:
            db.close()

    def test_manager_can_use_settings_and_clear_billing_cashier_cannot(self):
        with self.app.app_context():
            db = get_db()
            product = db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,price_satang,stock_quantity)
                   VALUES ('312-BILLING','Billing permission test',?,?,1000,10)""",
                (self.category_id, self.unit_id),
            )
            product_uuid = db.execute(
                "SELECT product_uuid FROM products WHERE id=?",
                (product.lastrowid,),
            ).fetchone()[0]
            customer = db.execute(
                """INSERT INTO billing_customers(name,credit_limit_satang)
                   VALUES ('Release 3.1.2 billing customer',100000)"""
            )
            customer_id = customer.lastrowid
            db.commit()
            from pos_app.services.sales import complete_sale

            sale_id, _, _, _ = complete_sale(
                {
                    "items": [{"product_uuid": product_uuid, "quantity": 1}],
                    "payment_method": "billing",
                    "billing_customer_id": customer_id,
                },
                1,
            )
            billed_id = db.execute(
                "SELECT id FROM billed_sales WHERE sale_id=?", (sale_id,)
            ).fetchone()[0]

        self.assertEqual(self.cashier.get("/settings").status_code, 403)
        self.assertEqual(self.cashier.get("/billing").status_code, 403)
        denied = self.cashier.post(
            f"/billing/{billed_id}/payments",
            data={
                "csrf_token": self.csrf(self.cashier_id),
                "amount": "1",
                "payment_method": "cash",
            },
        )
        self.assertEqual(denied.status_code, 403)

        settings_page = self.manager.get("/settings")
        self.assertEqual(settings_page.status_code, 200)
        manager_html = settings_page.get_data(as_text=True)
        self.assertIn('href="/settings"', manager_html)
        self.assertIn('href="/billing"', manager_html)
        for admin_only_path in (
            "/staff",
            "/audit-logs",
            "/backups",
            "/maintenance",
            "/products/xlsx/export",
        ):
            self.assertEqual(
                self.manager.get(admin_only_path).status_code,
                403,
                admin_only_path,
            )
        saved = self.manager.post(
            "/settings",
            data={
                "csrf_token": self.csrf(self.manager_id),
                "store_name": "Manager configured store",
                "store_address": "",
                "store_phone": "",
                "tax_id": "",
                "receipt_prefix": "POS",
                "allow_negative_stock": "on",
            },
        )
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(self.manager.get("/billing").status_code, 200)

        partial = self.manager.post(
            f"/billing/{billed_id}/payments",
            data={
                "csrf_token": self.csrf(self.manager_id),
                "amount": "1",
                "payment_method": "cash",
            },
        )
        self.assertEqual(partial.status_code, 302)
        cleared = self.manager.post(
            "/billing/payments/bulk",
            data={
                "csrf_token": self.csrf(self.manager_id),
                "billed_id": str(billed_id),
                "payment_method": "transfer",
            },
        )
        self.assertEqual(cleared.status_code, 302)
        with self.app.app_context():
            db = get_db()
            bill = db.execute(
                """SELECT original_satang,paid_satang,status
                   FROM billed_sales WHERE id=?""",
                (billed_id,),
            ).fetchone()
            self.assertEqual(bill["paid_satang"], bill["original_satang"])
            self.assertEqual(bill["status"], "paid")
            actions = db.execute(
                """SELECT action,staff_id FROM audit_logs
                   WHERE entity_type='billed_sale' AND entity_id=?
                   ORDER BY id""",
                (str(billed_id),),
            ).fetchall()
            self.assertEqual(
                [(row["action"], row["staff_id"]) for row in actions],
                [
                    ("receive_billing_payment", self.manager_id),
                    ("receive_bulk_billing_payment", self.manager_id),
                ],
            )

    def test_new_product_is_active_offline_and_create_form_has_no_online_control(self):
        page = self.admin.get("/products/new").get_data(as_text=True)
        content = page.split('<main id="mainContent"', 1)[1].split("</main>", 1)[0]
        self.assertIn('name="is_active"', content)
        self.assertIn('name="requires_manual_price"', content)
        self.assertNotIn('name="is_online_available"', content)
        self.assertNotIn('name="online_sort_order"', content)
        self.assertNotIn('name="online_max_quantity"', content)

        response = self.admin.post(
            "/products/new",
            data=self.product_form_data(
                "312-NEW-OFFLINE", online=True, manual=True
            ),
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            product = get_db().execute(
                """SELECT product_uuid,is_active,is_online_available,
                          online_sort_order,online_max_quantity,requires_manual_price
                   FROM products WHERE barcode='312-NEW-OFFLINE'"""
            ).fetchone()
            self.assertEqual(product["is_active"], 1)
            self.assertEqual(product["is_online_available"], 0)
            self.assertEqual(product["online_sort_order"], 0)
            self.assertIsNone(product["online_max_quantity"])
            self.assertEqual(product["requires_manual_price"], 1)
            created_uuid = product["product_uuid"]

        edit_page = self.admin.get(
            f"/products/{created_uuid}/edit"
        ).get_data(as_text=True)
        self.assertIn('name="is_online_available"', edit_page)
        self.assertIn('name="online_sort_order"', edit_page)

    def test_flagged_product_requires_price_and_receipt_keeps_real_name(self):
        product_api = self.cashier.get(
            "/api/pos/products?barcode=312-FRESH-PORK"
        ).get_json()[0]
        self.assertEqual(product_api["requires_manual_price"], 1)

        bypass = self.cashier.post(
            "/api/pos/quote",
            json={
                "items": [{"product_uuid": self.product_uuid, "quantity": 1}],
                "bill_discount_satang": 0,
            },
            headers={"X-CSRF-Token": self.csrf(self.cashier_id)},
        )
        self.assertEqual(bypass.status_code, 400)
        self.assertIn("กรุณาระบุราคาขาย", bypass.get_json()["error"])

        entered = self.enter_manual_price("235")
        self.assertEqual(entered.status_code, 200)
        manual = entered.get_json()
        self.assertEqual(manual["manual_price_reason"], "product_manual_price")
        self.assertEqual(manual["manual_price_satang"], 23500)
        self.assertEqual(manual["product"]["name_th"], "หมูสดราคาประจำวัน")
        reference = manual["manual_price_reference"]

        item = {
            "product_uuid": self.product_uuid,
            "quantity": 1,
            "discount_satang": 0,
            "manual_price_satang": 23500,
            "manual_price_reference": reference,
        }
        quote = self.cashier.post(
            "/api/pos/quote",
            json={"items": [item], "bill_discount_satang": 0},
            headers={"X-CSRF-Token": self.csrf(self.cashier_id)},
        )
        self.assertEqual(quote.status_code, 200)
        self.assertEqual(quote.get_json()["total_satang"], 23500)

        completed = self.cashier.post(
            "/api/pos/complete",
            json={
                "items": [item],
                "bill_discount_satang": 0,
                "payment_method": "cash",
                "amount_received_satang": 23500,
            },
            headers={"X-CSRF-Token": self.csrf(self.cashier_id)},
        )
        self.assertEqual(completed.status_code, 200)
        result = completed.get_json()
        receipt = self.cashier.get(result["receipt_url"]).get_data(as_text=True)
        self.assertIn("หมูสดราคาประจำวัน", receipt)
        self.assertNotIn(f"รายการระบุราคา {reference}", receipt)

        with self.app.app_context():
            db = get_db()
            sale_item = db.execute(
                """SELECT product_name,unit_price_satang,manual_price_reference
                   FROM sale_items WHERE sale_id=?""",
                (result["sale_id"],),
            ).fetchone()
            self.assertEqual(sale_item["product_name"], "หมูสดราคาประจำวัน")
            self.assertEqual(sale_item["unit_price_satang"], 23500)
            self.assertEqual(sale_item["manual_price_reference"], reference)
            entry = db.execute(
                "SELECT new_value FROM audit_logs WHERE id=?",
                (int(reference.removeprefix("MP-")),),
            ).fetchone()
            detail = json.loads(entry["new_value"])
            self.assertEqual(detail["product_name"], "หมูสดราคาประจำวัน")
            self.assertEqual(detail["reason"], "product_manual_price")

    def test_pos_javascript_opens_named_product_manual_price_prompt(self):
        js = (
            Path(self.app.static_folder) / "js" / "pos.js"
        ).read_text(encoding="utf-8")
        self.assertIn("Boolean(product.requires_manual_price)", js)
        self.assertIn("'product_manual_price'", js)
        self.assertIn(
            "['manual_price_barcode', 'product_manual_price'].includes(reason)",
            js,
        )


if __name__ == "__main__":
    unittest.main()
