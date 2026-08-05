import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class Release318Tests(unittest.TestCase):
    def test_release_identity_is_consistent(self):
        runtime_paths = (ROOT / "pos_app" / "runtime_paths.py").read_text(encoding="utf-8")
        base = (ROOT / "pos_app" / "templates" / "base.html").read_text(encoding="utf-8")
        settings = (ROOT / "pos_app" / "templates" / "pos_button_settings.html").read_text(encoding="utf-8")

        self.assertIn('DEFAULT_APP_VERSION = "3.1.8"', runtime_paths)
        self.assertIn("R3.1.8", base)
        self.assertIn("Release 3.1.8", settings)

    def test_system_gdi_receipt_logo_and_native_pos80_form_are_retained(self):
        source = (ROOT / "pos_app" / "services" / "print_jobs.py").read_text(encoding="utf-8")

        self.assertIn('new PaperSize("80(72)mm x 297mm", 283, 1169)', source)
        self.assertIn("DrawReceiptLogo", source)
        self.assertIn("Image.FromFile(logoPath)", source)
        self.assertNotIn("$logo = [byte[]]", source)


if __name__ == "__main__":
    unittest.main()
