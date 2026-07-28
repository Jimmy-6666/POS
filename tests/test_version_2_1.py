import json
import os
import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from tests.staff_helpers import staff_login


class Version21DisplayTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.state_file = Path(self.folder.name) / "display_state.json"
        self.previous_state_file = os.environ.get("POS_DISPLAY_STATE_FILE")
        os.environ["POS_DISPLAY_STATE_FILE"] = str(self.state_file)
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "pos.db")})
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            db.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        if self.previous_state_file is None:
            os.environ.pop("POS_DISPLAY_STATE_FILE", None)
        else:
            os.environ["POS_DISPLAY_STATE_FILE"] = self.previous_state_file
        self.folder.cleanup()

    def test_login_and_logout_signal_window_mode(self):
        response = staff_login(self.client)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(json.loads(self.state_file.read_text(encoding="utf-8"))["mode"], "fullscreen")
        with self.app.app_context():
            csrf = get_db().execute("SELECT csrf_token FROM staff_sessions").fetchone()[0]
        response = self.client.post("/logout", data={"csrf_token": csrf})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(json.loads(self.state_file.read_text(encoding="utf-8"))["mode"], "normal")

    def test_register_has_no_discount_controls_and_shows_item_count(self):
        staff_login(self.client)
        page = self.client.get("/pos").get_data(as_text=True)
        self.assertNotIn("ส่วนลด", page)
        self.assertIn('id="paymentItemCount"', page)
        self.assertIn('data-method="billing"', page)
        self.assertNotIn('id="billingDueDate"', page)
        self.assertNotIn('data-silent-print', page)
        self.assertIn('id="manualReceiptLink"', page)

    def test_launcher_limits_kiosk_printing_to_receipt_agent(self):
        source = (Path(__file__).parent.parent / "pos_desktop.py").read_text(encoding="utf-8")
        main_args = source.split("def main_browser_args", 1)[1].split("def print_browser_args", 1)[0]
        print_args = source.split("def print_browser_args", 1)[1].split("class PosDesktop", 1)[0]
        self.assertNotIn("--kiosk-printing", main_args)
        self.assertIn("--kiosk-printing", print_args)
        self.assertIn("POS_PRINT_AGENT_TOKEN", source)
        staff_login(self.client)
        manual_sheet = self.client.get("/stock-counts/manual-sheet").get_data(as_text=True)
        self.assertIn('onclick="window.print()"', manual_sheet)

if __name__ == "__main__":
    unittest.main()
