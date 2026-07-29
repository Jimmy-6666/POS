import ast
import hashlib
import unittest
from pathlib import Path

from pos_app.runtime_paths import DEFAULT_APP_VERSION


ROOT = Path(__file__).resolve().parent.parent


class Version305ReleaseTests(unittest.TestCase):
    def test_release_identity_is_consistent(self):
        self.assertEqual(DEFAULT_APP_VERSION, "3.0.5")
        self.assertIn("R3.0.5", (ROOT / "pos_app" / "templates" / "base.html").read_text(encoding="utf-8"))
        launcher = (ROOT / "pos_desktop.py").read_text(encoding="utf-8")
        self.assertIn("Saengngam POS 3.0.5", launcher)
        ast.parse(launcher)
        production = (ROOT / "production-common.ps1").read_text(encoding="utf-8")
        self.assertIn('AppVersion = "3.0.5"', production)
        self.assertIn("$env:POS_APP_VERSION = $Context.AppVersion", production)
        self.assertIn('ServerIp = "192.168.0.200"', production)
        self.assertTrue((ROOT / "VERSION_3.0.5.md").is_file())
        self.assertTrue((ROOT / "NEXT_SESSION_PROMPT.md").is_file())

    def test_default_product_image_is_the_approved_asset(self):
        image = ROOT / "pos_app" / "static" / "img" / "noimage.png"
        self.assertEqual(
            hashlib.sha256(image.read_bytes()).hexdigest(),
            "89f12bb18e95f7c08ce8b756ebf9dd2fb1d659165bb3b4a34ede0383942ede0c",
        )


if __name__ == "__main__":
    unittest.main()
