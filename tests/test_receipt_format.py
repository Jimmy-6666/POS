import base64
import gzip
import hashlib
import re
import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from pos_app.services.print_jobs import _sale_receipt_payload, _windows_gdi_command
from tests.staff_helpers import staff_login


ROOT = Path(__file__).resolve().parent.parent
DRAWER_BLOCK_SHA256 = "f5b6a4ee5c4797a22ecade0754111fb1b209fe7798afdee9d5b46a972de1eee0"


class ReceiptFormatTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.database = Path(self.folder.name) / "receipt-format.db"
        self.app = create_app({"TESTING": True, "DATABASE": str(self.database)})
        self.client = self.app.test_client()
        with self.app.app_context():
            db = get_db()
            db.executemany(
                """INSERT INTO settings(key,value) VALUES(?,?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (
                    ("store_name", "ร้านทดสอบ"),
                    ("store_phone", "02-123-4567"),
                    ("store_address", "ที่อยู่ที่ต้องไม่พิมพ์"),
                    ("tax_id", "TAX-NOT-PRINTED"),
                ),
            )
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            category_id = db.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()[0]
            unit_id = db.execute("SELECT id FROM units ORDER BY id LIMIT 1").fetchone()[0]
            product_id = db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity)
                   VALUES ('RECEIPT-80','สินค้าทดสอบชื่อยาว',?,?,5000,12500,20)""",
                (category_id, unit_id),
            ).lastrowid
            self.sale_id = db.execute(
                """INSERT INTO sales
                   (receipt_number,cashier_id,subtotal_satang,item_discount_satang,
                    bill_discount_satang,delivery_fee_satang,total_satang,total_cost_satang,
                    gross_profit_satang,payment_method_code,amount_received_satang,
                    change_satang,customer_note,created_at)
                   VALUES ('POS-20260802-0001',1,25000,0,0,1000,26000,10000,16000,
                           'cash',30000,4000,'หมายเหตุที่ต้องไม่พิมพ์','2026-08-02T03:04:05+00:00')"""
            ).lastrowid
            db.execute(
                """INSERT INTO sale_items
                   (sale_id,product_id,product_name,quantity,unit_price_satang,
                    discount_satang,cost_satang,line_total_satang,manual_price_reference)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    self.sale_id,
                    product_id,
                    "สินค้าทดสอบชื่อยาว",
                    2,
                    12500,
                    0,
                    5000,
                    25000,
                    "MP-00000001",
                ),
            )
            db.commit()

    def tearDown(self):
        self.folder.cleanup()

    def test_browser_receipt_matches_approved_80_mm_content(self):
        staff_login(self.client)
        html = self.client.get(f"/sales/{self.sale_id}/receipt").get_data(as_text=True)

        self.assertIn("ร้านทดสอบ", html)
        self.assertIn("โทร. 02-123-4567", html)
        self.assertIn("เลขที่:</span> POS-20260802-0001", html)
        self.assertIn("อ้างอิงราคา: MP-00000001", html)
        self.assertIn("receipt-logo.png", html)
        self.assertIn("02/08/2026 10:04", html)
        self.assertNotIn("delivery-row", html)
        self.assertNotIn("ที่อยู่ที่ต้องไม่พิมพ์", html)
        self.assertNotIn("TAX-NOT-PRINTED", html)
        self.assertNotIn("หมายเหตุที่ต้องไม่พิมพ์", html)

        css = (ROOT / "pos_app" / "static" / "css" / "receipt.css").read_text(encoding="utf-8")
        self.assertIn("width:80mm", css)
        self.assertIn("width:72mm", css)
        self.assertIn("width:51mm", css)
        self.assertIn("width:21mm", css)
        self.assertIn("size:80mm 297mm", css)
        self.assertIn("padding:4mm", css)

    def test_direct_windows_payload_uses_same_receipt_fields_only(self):
        with self.app.app_context():
            payload = _sale_receipt_payload(self.sale_id, "POSPrinter POS-80")

        self.assertEqual(payload["layout"], "sale_receipt_80mm")
        self.assertEqual(payload["store_phone"], "02-123-4567")
        self.assertEqual(payload["receipt_number"], "POS-20260802-0001")
        self.assertEqual(payload["receipt_datetime"], "02/08/2026 10:04:05")
        self.assertEqual(
            hashlib.sha256(Path(payload["logo_path"]).read_bytes()).hexdigest(),
            "ef7641365048ebb73d64e6282fc1a7d218080bb5c01f56bab3c8c703bd52b648",
        )
        self.assertEqual(payload["delivery_fee"], "")
        self.assertEqual(payload["total"], "260.00")
        self.assertEqual(payload["amount_received"], "300.00")
        self.assertEqual(payload["change"], "40.00")
        self.assertEqual(payload["items"][0]["manual_price_reference"], "MP-00000001")
        self.assertEqual(payload["items"][0]["detail"], "2 × 125.00 บาท")
        serialized = repr(payload)
        self.assertNotIn("ที่อยู่ที่ต้องไม่พิมพ์", serialized)
        self.assertNotIn("TAX-NOT-PRINTED", serialized)
        self.assertNotIn("หมายเหตุที่ต้องไม่พิมพ์", serialized)

    def test_cash_drawer_pulse_and_order_are_unchanged(self):
        with self.app.app_context():
            payload = _sale_receipt_payload(self.sale_id, "POSPrinter POS-80")
        command = _windows_gdi_command(payload)
        bootstrap = base64.b64decode(command[-1]).decode("utf-16le")
        compressed = re.search(r"\$compressed = \[Convert\]::FromBase64String\('([^']+)'\)", bootstrap)
        self.assertIsNotNone(compressed)
        script = gzip.decompress(base64.b64decode(compressed.group(1))).decode("utf-16le")
        drawer_block = """try {
    # Keep the original single drawer pulse before the receipt job.
    $drawer = [byte[]](0x1B,0x40,0x1B,0x70,0,25,250)
    [SaengngamReceiptPrinter]::SendRaw([string]$payload.printer_name, $drawer)
} catch {
    # Optional RAW drawer support must never suppress the receipt.
}"""

        self.assertEqual(hashlib.sha256(drawer_block.encode("utf-8")).hexdigest(), DRAWER_BLOCK_SHA256)
        self.assertEqual(script.count("$drawer = [byte[]](0x1B,0x40,0x1B,0x70,0,25,250)"), 1)
        self.assertLess(script.index("$drawer ="), script.index("::Print($payloadJson)"))
        self.assertIn("DrawReceiptLogo", script)
        self.assertIn("payload.logo_path", script)
        self.assertNotIn("$logo = [byte[]]", script)
        self.assertIn('new PaperSize("80(72)mm x 297mm", 283, 1169)', script)
        self.assertIn("available.Width == 283 && available.Height == 1169", script)
        self.assertIn("document.DefaultPageSettings.Landscape = false", script)
        self.assertIn("new Margins(0, 0, 16, 16)", script)


if __name__ == "__main__":
    unittest.main()
