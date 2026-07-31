import csv
import hashlib
import io
import re
import sqlite3
import tempfile
import unittest
import wave
from pathlib import Path

from werkzeug.security import generate_password_hash

from pos_app import create_app
from pos_app.database import get_db
from pos_app.migrations import MIGRATIONS
from tests.staff_helpers import staff_login


class Release308Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": str(root / "pos.db"),
                "PROJECT_ROOT": str(root),
                "PRINT_AGENT_TOKEN": "release-308-print-token",
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
                   VALUES ('แคชเชียร์ทดสอบ',?,?,0,1)""",
                (generate_password_hash("1111"), cashier_role),
            )
            self.cashier_id = cashier.lastrowid
            category_id = db.execute(
                "SELECT id FROM categories WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()[0]
            unit_id = db.execute(
                "SELECT id FROM units WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()[0]
            db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity)
                   VALUES ('308-ZERO','สินค้าราคาเป็นศูนย์',?,?,500,0,10)""",
                (category_id, unit_id),
            )
            db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity)
                   VALUES ('308-PRICED','สินค้ามีราคาแล้ว',?,?,500,1500,10)""",
                (category_id, unit_id),
            )
            db.execute(
                "UPDATE settings SET value='1' WHERE key='allow_negative_stock'"
            )
            db.commit()
        self.cashier = self.app.test_client()
        self.assertEqual(
            staff_login(self.cashier, self.cashier_id, "1111").status_code, 302
        )
        self.admin = self.app.test_client()
        self.assertEqual(staff_login(self.admin, 1, "1234").status_code, 302)

    def tearDown(self):
        self.folder.cleanup()

    def csrf(self, staff_id):
        with self.app.app_context():
            return get_db().execute(
                """SELECT csrf_token FROM staff_sessions
                   WHERE staff_id=? ORDER BY created_at DESC LIMIT 1""",
                (staff_id,),
            ).fetchone()[0]

    def product(self, barcode):
        with self.app.app_context():
            return get_db().execute(
                "SELECT * FROM products WHERE barcode=?", (barcode,)
            ).fetchone()

    def enter_manual_price(self, barcode, price_baht):
        return self.cashier.post(
            "/api/pos/manual-price",
            json={"barcode": barcode, "price_baht": price_baht},
            headers={"X-CSRF-Token": self.csrf(self.cashier_id)},
        )

    def test_zero_price_requires_reference_and_receipt_tracks_running_number(self):
        product = self.product("308-ZERO")
        missing_price = self.cashier.post(
            "/api/pos/quote",
            json={
                "items": [{"product_uuid": product["product_uuid"], "quantity": 1}],
                "bill_discount_satang": 0,
            },
            headers={"X-CSRF-Token": self.csrf(self.cashier_id)},
        )
        self.assertEqual(missing_price.status_code, 400)
        self.assertIn("กรุณาระบุราคาขาย", missing_price.get_json()["error"])

        entered = self.enter_manual_price("308-ZERO", "25")
        self.assertEqual(entered.status_code, 200)
        manual = entered.get_json()
        reference = manual["manual_price_reference"]
        self.assertRegex(reference, r"^MP-\d{8}$")
        self.assertEqual(manual["manual_price_satang"], 2500)
        self.assertEqual(manual["manual_price_reason"], "zero_catalog_price")

        item = {
            "product_uuid": product["product_uuid"],
            "quantity": 1,
            "discount_satang": 0,
            "manual_price_satang": 2500,
            "manual_price_reference": reference,
        }
        quote = self.cashier.post(
            "/api/pos/quote",
            json={"items": [item], "bill_discount_satang": 0},
            headers={"X-CSRF-Token": self.csrf(self.cashier_id)},
        )
        self.assertEqual(quote.status_code, 200)
        self.assertEqual(quote.get_json()["total_satang"], 2500)

        completed = self.cashier.post(
            "/api/pos/complete",
            json={
                "items": [item],
                "bill_discount_satang": 0,
                "payment_method": "cash",
                "amount_received_satang": 2500,
            },
            headers={"X-CSRF-Token": self.csrf(self.cashier_id)},
        )
        self.assertEqual(completed.status_code, 200)
        result = completed.get_json()
        receipt = self.cashier.get(result["receipt_url"]).get_data(as_text=True)
        self.assertIn(f"รายการระบุราคา {reference}", receipt)

        with self.app.app_context():
            db = get_db()
            sale_item = db.execute(
                """SELECT product_name,manual_price_reference,unit_price_satang
                   FROM sale_items WHERE sale_id=?""",
                (result["sale_id"],),
            ).fetchone()
            self.assertEqual(sale_item["manual_price_reference"], reference)
            self.assertEqual(sale_item["product_name"], f"รายการระบุราคา {reference}")
            self.assertEqual(sale_item["unit_price_satang"], 2500)
            audit_id = int(reference.removeprefix("MP-"))
            entered_audit = db.execute(
                "SELECT action,staff_id FROM audit_logs WHERE id=?", (audit_id,)
            ).fetchone()
            self.assertEqual(entered_audit["action"], "enter_pos_manual_price")
            self.assertEqual(entered_audit["staff_id"], self.cashier_id)
            self.assertEqual(
                db.execute(
                    """SELECT COUNT(*) FROM audit_logs
                       WHERE action='sell_with_manual_price' AND entity_id=?""",
                    (str(db.execute(
                        "SELECT id FROM sale_items WHERE sale_id=?", (result["sale_id"],)
                    ).fetchone()[0]),),
                ).fetchone()[0],
                1,
            )

        reused = self.cashier.post(
            "/api/pos/complete",
            json={
                "items": [item],
                "bill_discount_satang": 0,
                "payment_method": "cash",
                "amount_received_satang": 2500,
            },
            headers={"X-CSRF-Token": self.csrf(self.cashier_id)},
        )
        self.assertEqual(reused.status_code, 400)
        self.assertIn("ถูกใช้แล้ว", reused.get_json()["error"])

    def test_missing_and_manualprice_barcodes_create_offline_placeholders(self):
        missing = self.enter_manual_price("8859999999308", 30)
        self.assertEqual(missing.status_code, 200)
        missing_result = missing.get_json()
        self.assertEqual(missing_result["manual_price_reason"], "missing_product")
        missing_product = self.product("8859999999308")
        self.assertEqual(missing_product["price_satang"], 0)
        self.assertEqual(missing_product["is_active"], 1)
        self.assertEqual(missing_product["is_online_available"], 0)

        special = self.enter_manual_price("manualprice", 40)
        self.assertEqual(special.status_code, 200)
        special_result = special.get_json()
        self.assertEqual(special_result["product"]["barcode"], "MANUALPRICE")
        self.assertEqual(
            special_result["manual_price_reason"], "manual_price_barcode"
        )
        self.assertEqual(self.product("MANUALPRICE")["is_online_available"], 0)

        priced = self.enter_manual_price("308-PRICED", 1)
        self.assertEqual(priced.status_code, 200)
        self.assertTrue(priced.get_json()["uses_catalog_price"])
        self.assertEqual(priced.get_json()["product"]["price_satang"], 1500)
        self.assertNotIn("manual_price_reference", priced.get_json())

    def test_pos_dialog_scanner_lock_focus_audio_and_assets_are_wired(self):
        html = self.cashier.get("/pos").get_data(as_text=True)
        self.assertIn('id="manualPriceDialog"', html)
        self.assertIn('id="manualPriceInput"', html)
        self.assertIn("missing-product-price-required.wav", html)
        self.assertIn("manual-price-required.wav", html)
        self.assertIn("missing-product-price-required.wav?v=2", html)
        self.assertIn("manual-price-required.wav?v=2", html)
        self.assertIn("js/pos.js?v=35", html)
        self.assertEqual(html.count("data-manual-price-key="), 10)
        self.assertIn('id="manualPriceNumpad"', html)
        self.assertIn('data-manual-price-action="clear"', html)
        self.assertIn('data-manual-price-action="backspace"', html)

        js = (Path(self.app.static_folder) / "js" / "pos.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("'#manualPriceDialog'", js)
        self.assertIn("value.toUpperCase() === manualBarcode", js)
        self.assertIn("manualPriceDialog.addEventListener('cancel'", js)
        self.assertIn("blockScannerInsideManualPrice", js)
        self.assertIn("button.dataset.manualPriceKey", js)
        self.assertIn("button.dataset.manualPriceAction === 'backspace'", js)
        self.assertIn("button.dataset.manualPriceAction === 'clear'", js)
        self.assertIn(".slice(0, 7)", js)
        self.assertIn("กรุณาระบุราคาให้เสร็จก่อนสแกนสินค้าชิ้นถัดไป", js)
        self.assertIn("$('#productLookup').focus({ preventScroll: true })", js)
        self.assertIn("playManualPriceAlert(reason === 'manual_price_barcode')", js)

        approved_audio = {
            "missing-product-price-required.wav": (
                "c8bc78b6378c1f516c2666cd3f5c2bc00a60af66ad4cef31181cfd266f6311de",
                (3.5, 3.8),
            ),
            "manual-price-required.wav": (
                "33487453648b7b28161c695b2343125a2cc23b73223b9e6d11cb5c92e87dddf6",
                (1.8, 2.1),
            ),
        }
        for filename, (expected_hash, duration_range) in approved_audio.items():
            content = (Path(self.app.static_folder) / "audio" / filename).read_bytes()
            self.assertGreater(len(content), 10_000)
            self.assertEqual(content[:4], b"RIFF")
            self.assertEqual(content[8:12], b"WAVE")
            self.assertEqual(hashlib.sha256(content).hexdigest(), expected_hash)
            with wave.open(
                str(Path(self.app.static_folder) / "audio" / filename), "rb"
            ) as audio:
                duration = audio.getnframes() / audio.getframerate()
            self.assertGreater(duration, duration_range[0])
            self.assertLess(duration, duration_range[1])

    def test_audit_action_filter_and_csrf_protected_csv_export(self):
        with self.app.app_context():
            db = get_db()
            db.execute(
                """INSERT INTO audit_logs
                   (staff_id,action,entity_type,entity_id,new_value,created_at)
                   VALUES (1,'alpha_event','test','1','alpha detail',CURRENT_TIMESTAMP)"""
            )
            db.execute(
                """INSERT INTO audit_logs
                   (staff_id,action,entity_type,entity_id,new_value,created_at)
                   VALUES (1,'beta_event','test','2','beta detail',CURRENT_TIMESTAMP)"""
            )
            db.commit()

        filtered = self.admin.get("/audit-logs?action=alpha_event").get_data(
            as_text=True
        )
        body = filtered.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        self.assertIn("alpha_event", body)
        self.assertNotIn("beta_event", body)
        self.assertIn("Export CSV", filtered)

        invalid = self.admin.post(
            "/audit-logs/export",
            data={"csrf_token": "wrong", "action": "alpha_event"},
        )
        self.assertEqual(invalid.status_code, 400)
        exported = self.admin.post(
            "/audit-logs/export",
            data={
                "csrf_token": self.csrf(1),
                "action": "alpha_event",
            },
        )
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.mimetype, "text/csv")
        rows = list(
            csv.DictReader(
                io.StringIO(exported.get_data().decode("utf-8-sig"))
            )
        )
        self.assertEqual({row["action"] for row in rows}, {"alpha_event"})
        self.assertIn("audit-logs-alpha_event-", exported.headers["Content-Disposition"])
        with self.app.app_context():
            audit = get_db().execute(
                """SELECT new_value FROM audit_logs
                   WHERE action='export_audit_logs' ORDER BY id DESC LIMIT 1"""
            ).fetchone()
            self.assertIn('"action_filter": "alpha_event"', audit["new_value"])
            self.assertIn('"row_count": 1', audit["new_value"])

    def test_manual_price_reference_migration_is_idempotent_and_unique(self):
        db = sqlite3.connect(":memory:")
        try:
            db.execute("CREATE TABLE sale_items (id INTEGER PRIMARY KEY)")
            migration = next(item for item in MIGRATIONS if item.version == 27)
            migration.apply(db)
            migration.apply(db)
            columns = {
                row[1] for row in db.execute("PRAGMA table_info(sale_items)")
            }
            self.assertIn("manual_price_reference", columns)
            db.execute(
                "INSERT INTO sale_items(manual_price_reference) VALUES ('MP-00000001')"
            )
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO sale_items(manual_price_reference) VALUES ('MP-00000001')"
                )
        finally:
            db.close()

    def test_version_26_database_starts_before_manual_price_column_exists(self):
        database = Path(self.folder.name) / "pre-308.db"
        create_app({"TESTING": True, "DATABASE": str(database)})
        db = sqlite3.connect(database)
        try:
            db.execute(
                "DROP INDEX IF EXISTS idx_sale_items_manual_price_reference"
            )
            db.execute(
                "ALTER TABLE sale_items DROP COLUMN manual_price_reference"
            )
            db.execute("DELETE FROM schema_migrations WHERE version=27")
            db.commit()
        finally:
            db.close()

        create_app({"TESTING": True, "DATABASE": str(database)})
        db = sqlite3.connect(database)
        try:
            columns = {
                row[1] for row in db.execute("PRAGMA table_info(sale_items)")
            }
            self.assertIn("manual_price_reference", columns)
            self.assertEqual(
                db.execute(
                    "SELECT success FROM schema_migrations WHERE version=27"
                ).fetchone()[0],
                1,
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
