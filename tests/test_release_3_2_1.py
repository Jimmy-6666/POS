import unittest
from pathlib import Path

from pos_app.runtime_paths import DEFAULT_APP_VERSION


ROOT = Path(__file__).resolve().parent.parent


class Release321Tests(unittest.TestCase):
    def test_release_is_line_bot_only_and_pos_identity_stays_320(self):
        self.assertEqual(DEFAULT_APP_VERSION, "3.2.0")
        release = (ROOT / "VERSION_3.2.1.md").read_text(encoding="utf-8")
        self.assertIn("changes only the LINE Bot workflow", release)
        self.assertIn("visible Windows POS identity remains 3.2.0", release)

    def test_manual_commands_are_documented(self):
        setup = (ROOT / "docs" / "LINE_BOT_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("/check 1100000", setup)
        self.assertIn("/bot 1100000|Singha Beer|80", setup)
        self.assertIn("never overwritten", setup)


if __name__ == "__main__":
    unittest.main()
