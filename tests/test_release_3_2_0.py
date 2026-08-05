import unittest
from pathlib import Path

from pos_app.runtime_paths import DEFAULT_APP_VERSION


ROOT = Path(__file__).resolve().parent.parent


class Release320Tests(unittest.TestCase):
    def test_cumulative_release_identity_is_consistent(self):
        self.assertEqual(DEFAULT_APP_VERSION, "3.2.0")
        self.assertIn(
            "R3.2.0",
            (ROOT / "pos_app" / "templates" / "base.html").read_text(encoding="utf-8"),
        )
        self.assertIn(
            'AppVersion = "3.2.0"',
            (ROOT / "production-common.ps1").read_text(encoding="utf-8"),
        )
        self.assertIn(
            'set "POS_APP_VERSION=3.2.0"',
            (ROOT / "start-uat.bat").read_text(encoding="utf-8"),
        )

    def test_pos_318_and_line_bot_319_behaviors_are_both_present(self):
        print_jobs = (ROOT / "pos_app" / "services" / "print_jobs.py").read_text(encoding="utf-8")
        workflow = (ROOT / "line_bot" / "workflow.py").read_text(encoding="utf-8")
        storage = (ROOT / "line_bot" / "storage.py").read_text(encoding="utf-8")
        migrations = (ROOT / "pos_app" / "migrations.py").read_text(encoding="utf-8")

        self.assertIn('new PaperSize("80(72)mm x 297mm", 283, 1169)', print_jobs)
        self.assertIn("DrawReceiptLogo", print_jobs)
        self.assertIn("process_due_notifications", workflow)
        self.assertIn("pending_notifications", storage)
        self.assertIn('Migration(31, "add LINE Bot command and image-cleanup records"', migrations)

    def test_release_documents_have_no_merge_markers(self):
        for relative in ("CHANGELOG.md", "DECISIONS.md", "FEATURE_STATUS.md"):
            content = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("<<<<<<<", content, relative)
            self.assertNotIn("=======", content, relative)
            self.assertNotIn(">>>>>>>", content, relative)


if __name__ == "__main__":
    unittest.main()
