import unittest
from pathlib import Path

from pos_app.runtime_paths import DEFAULT_APP_VERSION


ROOT = Path(__file__).resolve().parent.parent


class Release315Tests(unittest.TestCase):
    def test_release_identity_and_backup_repair_tools_are_wired(self):
        self.assertEqual(DEFAULT_APP_VERSION, "3.1.5")
        base = (ROOT / "pos_app" / "templates" / "base.html").read_text(encoding="utf-8")
        production_common = (ROOT / "production-common.ps1").read_text(encoding="utf-8")
        repair = (ROOT / "repair-production.ps1").read_text(encoding="utf-8")
        verify = (ROOT / "verify-production.ps1").read_text(encoding="utf-8")
        connection_test = (ROOT / "test-production-backup-connection.ps1").read_text(encoding="utf-8")
        stop_production = (ROOT / "stop-production.ps1").read_text(encoding="utf-8")
        release_note = (ROOT / "VERSION_3.1.5.md").read_text(encoding="utf-8")

        self.assertIn("R3.1.5", base)
        self.assertIn('AppVersion = "3.1.5"', production_common)
        self.assertIn("Repair-ProductionVpsBackupSecrets", repair)
        self.assertIn("Test-ProductionVpsBackupSecrets", verify)
        self.assertIn("pos_app.backup_cli test-connection", connection_test)
        self.assertIn("Get-NetTCPConnection -LocalPort $context.Port", stop_production)
        self.assertIn("$desktopScript", stop_production)
        self.assertNotIn('CommandLine -match "(pos_app\\.launcher|pos_desktop\\.py)"', stop_production)
        self.assertIn("SYSTEM", release_note)
        self.assertIn("released to Production and UAT", release_note)

    def test_remote_retry_keeps_the_last_sftp_error(self):
        remote_backup = (ROOT / "pos_app" / "services" / "remote_backup.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Remote operation failed after {attempts} attempt(s): {detail}", remote_backup)
        self.assertIn('detail = " ".join(', remote_backup)


if __name__ == "__main__":
    unittest.main()
