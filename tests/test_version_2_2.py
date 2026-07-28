import ast
import unittest
from pathlib import Path

from pos_app.runtime_paths import DEFAULT_APP_VERSION


ROOT = Path(__file__).resolve().parent.parent


class Version30ReleaseTests(unittest.TestCase):
    def test_release_identity_is_consistent(self):
        self.assertEqual(DEFAULT_APP_VERSION, "3.0.0")
        self.assertIn("R3.0.0", (ROOT / "pos_app" / "templates" / "base.html").read_text(encoding="utf-8"))
        launcher = (ROOT / "pos_desktop.py").read_text(encoding="utf-8")
        self.assertIn("Saengngam POS 3.0.0", launcher)
        ast.parse(launcher)
        production = (ROOT / "production-common.ps1").read_text(encoding="utf-8")
        self.assertIn('AppVersion = "3.0.0"', production)
        self.assertIn("$env:POS_APP_VERSION = $Context.AppVersion", production)
        self.assertTrue((ROOT / "VERSION_3.0.0.md").is_file())
        self.assertTrue((ROOT / "NEXT_SESSION_PROMPT.md").is_file())


if __name__ == "__main__":
    unittest.main()
