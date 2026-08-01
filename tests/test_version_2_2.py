import ast
import hashlib
import unittest
from pathlib import Path

from pos_app.runtime_paths import DEFAULT_APP_VERSION


ROOT = Path(__file__).resolve().parent.parent


class Version310ReleaseTests(unittest.TestCase):
    def test_release_identity_is_consistent(self):
        self.assertEqual(DEFAULT_APP_VERSION, "3.1.5")
        self.assertIn("R3.1.5", (ROOT / "pos_app" / "templates" / "base.html").read_text(encoding="utf-8"))
        launcher = (ROOT / "pos_desktop.py").read_text(encoding="utf-8")
        self.assertIn("Saengngam POS 3.1.5", launcher)
        ast.parse(launcher)
        production = (ROOT / "production-common.ps1").read_text(encoding="utf-8")
        self.assertIn('AppVersion = "3.1.5"', production)
        self.assertIn("$env:POS_APP_VERSION = $Context.AppVersion", production)
        self.assertIn('ServerIp = "192.168.0.200"', production)
        self.assertIn("Push-Location $Context.InstallRoot", production)
        self.assertIn("New-ScheduledTaskTrigger -AtStartup", production)
        self.assertIn("New-ScheduledTaskTrigger -AtLogOn", production)
        self.assertIn("-LogonType Interactive", production)
        self.assertIn('-User "SYSTEM" -RunLevel Highest', production)
        self.assertIn('DesktopTaskName = "SaengngamPOS-Desktop"', production)
        self.assertIn("Ensure-ProductionPrintAgentToken", production)
        start_production = (ROOT / "start-production.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$Desktop", start_production)
        self.assertIn("[switch]$AttachOnly", start_production)
        self.assertIn("& $context.DesktopPython -B $desktopScript", start_production)
        self.assertNotIn("& $context.Pythonw $desktopScript", start_production)
        desktop_task = (ROOT / "configure-production-desktop-startup.ps1").read_text(encoding="utf-8")
        self.assertIn("Register-ProductionStartup $context", desktop_task)
        self.assertIn("Register-ProductionDesktopStartup $context $DesktopUser", desktop_task)
        self.assertIn("Start-ScheduledTask -TaskName $context.TaskName", desktop_task)
        kiosk = (ROOT / "configure-production-kiosk-user.ps1").read_text(encoding="utf-8")
        self.assertIn("-NoPassword", kiosk)
        self.assertIn("Register-ProductionDesktopStartup $context $desktopUser", kiosk)
        self.assertIn("Saengngam POS.lnk", kiosk)
        self.assertIn("Set-KioskRootWriteDeny", kiosk)
        verification = (ROOT / "verify-production.ps1").read_text(encoding="utf-8")
        self.assertNotIn("$null = Get-SupportedPython", verification)
        stop_production = (ROOT / "stop-production.ps1").read_text(encoding="utf-8")
        self.assertIn('"browser-profile"', stop_production)
        self.assertIn('"print-browser-profile"', stop_production)
        self.assertIn('"^(msedge|chrome)\\.exe$"', stop_production)
        release_note = (ROOT / "VERSION_3.0.9.md").read_text(encoding="utf-8")
        self.assertIn("SaengngamPOS-Production", release_note)
        self.assertIn("SaengngamPOS-Desktop", release_note)
        self.assertIn("configure-production-kiosk-user.ps1", release_note)
        self.assertIn("runtime/pos-desktop/display_state.json", release_note)
        self.assertIn("C:\\Users\\Public\\Desktop\\Saengngam POS.lnk", release_note)
        release_310 = (ROOT / "VERSION_3.1.0.md").read_text(encoding="utf-8")
        self.assertIn("text-only", release_310)
        self.assertIn("Migration 28", release_310)
        self.assertIn("Numpad", release_310)
        self.assertTrue((ROOT / "NEXT_SESSION_PROMPT.md").is_file())

    def test_default_product_image_is_the_approved_asset(self):
        image = ROOT / "pos_app" / "static" / "img" / "noimage.png"
        self.assertEqual(
            hashlib.sha256(image.read_bytes()).hexdigest(),
            "89f12bb18e95f7c08ce8b756ebf9dd2fb1d659165bb3b4a34ede0383942ede0c",
        )


if __name__ == "__main__":
    unittest.main()
