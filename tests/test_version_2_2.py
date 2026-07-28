import ast
import unittest
from pathlib import Path

from pos_app.runtime_paths import DEFAULT_APP_VERSION


ROOT = Path(__file__).resolve().parent.parent


class Version24ReleaseTests(unittest.TestCase):
    def test_release_identity_is_consistent(self):
        self.assertEqual(DEFAULT_APP_VERSION, "2.4.1")
        self.assertIn("R2.4.1", (ROOT / "pos_app" / "templates" / "base.html").read_text(encoding="utf-8"))
        launcher = (ROOT / "pos_desktop.py").read_text(encoding="utf-8")
        self.assertIn("Saengngam POS 2.4.1", launcher)
        ast.parse(launcher)
        self.assertTrue((ROOT / "VERSION_2.4.1.md").is_file())
        self.assertTrue((ROOT / "NEXT_SESSION_PROMPT.md").is_file())


if __name__ == "__main__":
    unittest.main()
