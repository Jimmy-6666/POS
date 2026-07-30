import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from tests.staff_helpers import staff_login


class Release307Tests(unittest.TestCase):
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
            category_id = db.execute(
                "SELECT id FROM categories WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()[0]
            unit_id = db.execute(
                "SELECT id FROM units WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()[0]
            db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,image_path)
                   VALUES ('307-camera','สินค้าสำหรับสแกนด้วยกล้อง',?,?,500,1700,NULL)""",
                (category_id, unit_id),
            )
            db.commit()
        self.client = self.app.test_client()
        self.assertEqual(staff_login(self.client).status_code, 302)

    def tearDown(self):
        self.folder.cleanup()

    def static_source(self, relative_path):
        return (Path(self.app.static_folder) / relative_path).read_text(encoding="utf-8")

    def test_quick_edit_has_camera_scan_with_lan_photo_fallback(self):
        html = self.client.get("/products/quick-edit").get_data(as_text=True)
        self.assertIn('id="quickCameraScanButton"', html)
        self.assertIn(">สแกนด้วยกล้อง</button>", html)
        self.assertIn('id="quickBarcodePhoto"', html)
        self.assertIn('capture="environment"', html)
        self.assertIn('id="quickBarcodeVideo" playsinline hidden', html)
        self.assertIn("vendor/zxing-browser.min.js", html)
        self.assertIn("js/barcode-camera-scanner.js?v=1", html)
        self.assertIn("js/product-quick-edit.js?v=6", html)

        quick_js = self.static_source("js/product-quick-edit.js")
        self.assertIn("fallbackToPhoto: true", quick_js)
        self.assertIn("scanForm.requestSubmit()", quick_js)
        self.assertIn("if (scanSubmitted) return", quick_js)

    def test_quick_edit_owns_file_and_camera_preview(self):
        html = self.client.get(
            "/products/quick-edit",
            query_string={"barcode": "307-camera"},
        ).get_data(as_text=True)
        self.assertNotIn("js/product-form.js", html)
        self.assertIn("js/product-quick-edit.js?v=6", html)
        self.assertIn('id="productImageBrowse"', html)
        self.assertIn('id="productImageCamera"', html)
        self.assertIn('id="productImagePreview"', html)

        quick_js = self.static_source("js/product-quick-edit.js")
        self.assertIn("imageBrowse?.addEventListener('change'", quick_js)
        self.assertIn("imageCamera?.addEventListener('change'", quick_js)
        self.assertIn("reader.readAsDataURL(file)", quick_js)
        self.assertIn("reader.result.startsWith('data:image/')", quick_js)
        self.assertIn("previewGeneration !== imagePreviewGeneration", quick_js)
        self.assertNotIn("URL.createObjectURL", quick_js)
        self.assertIn("imagePreview.classList.toggle('is-visible', visible)", quick_js)
        self.assertIn("if (currentImage) currentImage.hidden = visible", quick_js)

        base_html = (
            Path(self.app.root_path) / self.app.template_folder / "base.html"
        ).read_text(encoding="utf-8")
        self.assertIn("filename='css/v307.css',v=4", base_html)
        css = self.static_source("css/v307.css")
        self.assertIn(".quick-product-editor .product-image-preview.is-visible", css)
        self.assertIn("max-width:100%", css)
        self.assertIn(".quick-product-editor .product-image-section>*", css)

        security_source = (
            Path(self.app.root_path) / "web_security.py"
        ).read_text(encoding="utf-8")
        self.assertIn("\"img-src 'self' data: https:\"", security_source)
        self.assertNotIn("blob:", security_source)

    def test_camera_scanner_is_shared_with_stock_count_and_stops_cleanly(self):
        stock_template = (
            Path(self.app.root_path) / self.app.template_folder / "stock_count_session.html"
        ).read_text(encoding="utf-8")
        self.assertIn("js/barcode-camera-scanner.js", stock_template)
        self.assertIn("filename='js/stock-count.js',v=3", stock_template)

        scanner = self.static_source("js/barcode-camera-scanner.js")
        stock_js = self.static_source("js/stock-count.js")
        self.assertIn("window.PosBarcodeCamera = {attach}", scanner)
        self.assertIn("new BarcodeDetector", scanner)
        self.assertIn("BrowserMultiFormatReader", scanner)
        self.assertIn("liveStream?.getTracks().forEach(track => track.stop())", scanner)
        self.assertIn("window.addEventListener('pagehide', stop)", scanner)
        self.assertIn("window.PosBarcodeCamera.attach", stock_js)
        self.assertNotIn("new BarcodeDetector", stock_js)

    def test_unknown_stock_count_scan_returns_focus_to_barcode(self):
        missing = self.client.get(
            "/stock-counts/product-lookup",
            query_string={"barcode": "missing-307"},
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.get_json()["error"], "ไม่พบสินค้าจากบาร์โค้ดนี้")

        stock_js = self.static_source("js/stock-count.js")
        self.assertIn("if (lookupId !== lookupSequence) return", stock_js)
        self.assertIn("quantityInput.value = ''", stock_js)
        self.assertIn("barcodeInput.value = ''", stock_js)
        self.assertIn("barcodeInput.focus({preventScroll: true})", stock_js)
        self.assertIn("ไม่พบสินค้า — พร้อมสแกนสินค้าชิ้นถัดไป", stock_js)

    def test_mobile_found_product_opens_price_numpad_with_name_visible(self):
        html = self.client.get(
            "/products/quick-edit",
            query_string={"barcode": "307-camera"},
        ).get_data(as_text=True)
        self.assertIn(
            '<strong class="quick-product-current-name" data-quick-product-current-name>'
            "สินค้าสำหรับสแกนด้วยกล้อง</strong>",
            html,
        )
        self.assertIn('class="quick-price-entry"', html)
        self.assertIn('id="quickPriceOutput"', html)
        self.assertEqual(html.count("data-price-key="), 10)
        self.assertIn("ยืนยันราคาและแก้ข้อมูลต่อ", html)
        self.assertNotIn(
            'name="barcode" autocomplete="off" required autofocus',
            html,
        )

        quick_js = self.static_source("js/product-quick-edit.js")
        self.assertIn("if (!priceAccepted) setPriceEntryOpen(true)", quick_js)
        self.assertIn("priceInput.readOnly = true", quick_js)
        self.assertIn("replaceNextDigit = true", quick_js)
        self.assertIn("currentProductNames.forEach", quick_js)

        css = self.static_source("css/v307.css")
        self.assertIn("@media(max-width:600px)", css)
        self.assertIn(".quick-price-entry:not([hidden])", css)
        self.assertIn("grid-template-columns:repeat(3,minmax(0,1fr))", css)
        self.assertIn("min-height:44px", css)


if __name__ == "__main__":
    unittest.main()
