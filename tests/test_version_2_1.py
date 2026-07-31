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
        self.assertIn("--disable-sync", main_args)
        self.assertIn("--disable-signin-promo", main_args)
        self.assertIn("--disable-sync", print_args)
        self.assertIn('"signin"', source)
        self.assertIn('"allowed_on_next_startup"', source)
        self.assertIn("POS_PRINT_AGENT_TOKEN", source)
        self.assertIn("POS_DESKTOP_ATTACH_ONLY", source)
        self.assertIn("RUNTIME_PATHS.print_agent_token", source)
        self.assertIn("Production server is not ready", source)
        staff_login(self.client)
        manual_sheet = self.client.get("/stock-counts/manual-sheet").get_data(as_text=True)
        self.assertIn('onclick="window.print()"', manual_sheet)

    def test_pos_desktop_uses_shared_python_outside_admin_profile(self):
        root = Path(__file__).parent.parent
        production = (root / "production-common.ps1").read_text(encoding="utf-8")
        start = (root / "start-production.ps1").read_text(encoding="utf-8")
        kiosk = (root / "configure-production-kiosk-user.ps1").read_text(encoding="utf-8")
        verify = (root / "verify-production.ps1").read_text(encoding="utf-8")

        self.assertIn('"desktop-python"', production)
        self.assertIn("function Test-ProductionDesktopPython", production)
        self.assertIn("function Ensure-ProductionDesktopPython", production)
        self.assertIn("import pos_desktop", production)
        self.assertIn('"pos-desktop\\display_state.json"', production)
        self.assertIn("& $context.DesktopPython -B $desktopScript", start)
        self.assertNotIn("& $context.Pythonw $desktopScript", start)
        self.assertIn("desktop-startup-error.log", start)
        self.assertIn("System.Windows.Forms.MessageBox", start)
        self.assertIn("Ensure-ProductionDesktopPython $context", kiosk)
        self.assertIn('icacls.exe $Path /deny', kiosk)
        self.assertIn("Test-ProductionDesktopPython $context", verify)
        launcher = (root / "pos_desktop.py").read_text(encoding="utf-8")
        self.assertNotIn("from pos_app.runtime_paths import", launcher)
        self.assertIn("spec_from_file_location", launcher)
        self.assertIn('module_name = "_saengngam_runtime_paths"', launcher)
        self.assertIn('error_log = PROFILE_ROOT / "desktop-error.log"', launcher)
        self.assertIn('os.environ.get("POS_DISPLAY_STATE_FILE"', launcher)

if __name__ == "__main__":
    unittest.main()
