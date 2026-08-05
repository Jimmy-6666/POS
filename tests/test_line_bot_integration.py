import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from pos_app.migrations import MIGRATIONS


class LineBotIntegrationTests(unittest.TestCase):
    secret = "test-line-bot-shared-secret-which-is-long-enough"

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(root / "pos.db"),
            "PROJECT_ROOT": str(root),
            "POS_LINE_BOT_ENABLED": True,
            "POS_LINE_BOT_SHARED_SECRET": self.secret,
        })
        with self.app.app_context():
            db = get_db()
            category_id = db.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()[0]
            unit_id = db.execute("SELECT id FROM units ORDER BY id LIMIT 1").fetchone()[0]
            product = db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,requires_manual_price)
                   VALUES ('LINE-EXISTING','สินค้าเดิม',?,?,1000,2000,1)""",
                (category_id, unit_id),
            )
            self.product_id = product.lastrowid
            db.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        self.folder.cleanup()

    def signed_json(self, path, payload):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self.signed_raw(path, raw, "application/json")

    def signed_raw(self, path, raw, content_type):
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.secret.encode("utf-8"), timestamp.encode("ascii") + b"." + raw,
            hashlib.sha256,
        ).hexdigest()
        return self.client.post(
            path,
            data=raw,
            content_type=content_type,
            headers={
                "X-POS-LineBot-Timestamp": timestamp,
                "X-POS-LineBot-Signature": signature,
            },
        )

    def lookup(self, barcode):
        return self.signed_json("/_internal/line-bot/lookup", {"barcode": barcode})

    def command(self, command):
        return self.signed_json("/_internal/line-bot/commands", command)

    def source(self):
        return {"group_id": "C-group-1", "line_user_id": "U-manager-1"}

    def test_lookup_and_idempotent_price_change_preserve_manual_price_flag(self):
        looked_up = self.lookup("LINE-EXISTING")
        self.assertEqual(looked_up.status_code, 200)
        product = looked_up.get_json()["product"]
        command = {
            "command_id": "price-change-command-0001",
            "operation": "update_prices",
            "barcode": "LINE-EXISTING",
            "product_uuid": product["product_uuid"],
            "expected_revision": product["revision"],
            "cost_satang": 2550,
            "sale_baht": 30,
            "source": self.source(),
        }
        first = self.command(command)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.get_json().get("replayed"))
        second = self.command(command)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.get_json()["replayed"])
        with self.app.app_context():
            db = get_db()
            row = db.execute(
                "SELECT cost_satang,price_satang,requires_manual_price FROM products WHERE id=?",
                (self.product_id,),
            ).fetchone()
            self.assertEqual(tuple(row), (2550, 3000, 1))
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM audit_logs WHERE action='line_bot_change_prices'").fetchone()[0],
                1,
            )

    def test_stale_revision_is_recorded_as_conflict_without_overwrite(self):
        product = self.lookup("LINE-EXISTING").get_json()["product"]
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE products SET price_satang=2200 WHERE id=?", (self.product_id,))
            db.commit()
        response = self.command({
            "command_id": "stale-price-command-0001",
            "operation": "update_prices",
            "barcode": "LINE-EXISTING",
            "product_uuid": product["product_uuid"],
            "expected_revision": product["revision"],
            "cost_satang": 1000,
            "sale_baht": 20,
            "source": self.source(),
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "product_conflict")
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT price_satang FROM products WHERE id=?", (self.product_id,)).fetchone()[0], 2200)
            self.assertEqual(db.execute("SELECT status FROM line_bot_commands").fetchone()[0], "conflict")

    def test_unknown_barcode_creates_offline_product_with_approved_defaults(self):
        response = self.command({
            "command_id": "create-product-command-0001",
            "operation": "create_or_complete",
            "barcode": "LINE-NEW-001",
            "name_th": "สินค้าเพิ่มจากไลน์",
            "cost_satang": 0,
            "sale_baht": 15,
            "source": self.source(),
        })
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            row = get_db().execute(
                """SELECT p.is_active,p.is_online_available,c.name_th,u.name_th
                   FROM products p JOIN categories c ON c.id=p.category_id JOIN units u ON u.id=p.unit_id
                   WHERE p.barcode='LINE-NEW-001'"""
            ).fetchone()
            self.assertEqual(tuple(row), (1, 0, "อื่น ๆ", "ชิ้น"))

    def test_image_operations_are_not_available_from_the_line_bot_boundary(self):
        product = self.lookup("LINE-EXISTING").get_json()["product"]
        response = self.command({
            "command_id": "image-change-command-0001",
            "operation": "update_image",
            "barcode": "LINE-EXISTING",
            "product_uuid": product["product_uuid"],
            "expected_revision": product["revision"],
            "source": self.source(),
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "invalid_command")
        self.assertEqual(self.signed_json("/_internal/line-bot/cleanup", {}).status_code, 404)

    def test_migration_31_is_idempotent(self):
        import sqlite3

        db = sqlite3.connect(":memory:")
        try:
            db.execute("CREATE TABLE products(id INTEGER PRIMARY KEY)")
            migration = next(item for item in MIGRATIONS if item.version == 31)
            migration.apply(db)
            migration.apply(db)
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"line_bot_commands", "line_bot_image_cleanup"}.issubset(tables))
        finally:
            db.close()
