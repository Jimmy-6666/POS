import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from pos_app import create_app
from pos_app.database import get_db
from pos_app.runtime_paths import RuntimePaths
from pos_app.services.signed_updates import UpdateVerificationError, verify_staged_update
from pos_app.services.support_bundle import create_support_bundle
from tests.staff_helpers import staff_login


class SignedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.staging = Path(self.folder.name)
        self.script = self.staging / "release.ps1"
        self.script.write_text("Write-Output 'signed release'", encoding="utf-8")
        self.manifest = self.staging / "release.update.json"
        self.manifest.write_text(json.dumps({
            "format_version": 1, "release_id": "release-3", "version": "3.0.0",
            "script": self.script.name, "script_sha256": hashlib.sha256(self.script.read_bytes()).hexdigest(),
        }), encoding="utf-8")

    def tearDown(self):
        self.folder.cleanup()

    def test_manifest_hash_and_pinned_signer_must_verify(self):
        verified = verify_staged_update(
            self.staging, self.manifest.name, "AB CD",
            signature_inspector=lambda _path: ("Valid", "ABCD"),
        )
        self.assertEqual(verified.release_id, "release-3")
        with self.assertRaises(UpdateVerificationError):
            verify_staged_update(self.staging, self.manifest.name, "ABCD", signature_inspector=lambda _path: ("Valid", "OTHER"))
        self.script.write_text("tampered", encoding="utf-8")
        with self.assertRaises(UpdateVerificationError):
            verify_staged_update(self.staging, self.manifest.name, "ABCD", signature_inspector=lambda _path: ("Valid", "ABCD"))


class SupportBundleTests(unittest.TestCase):
    def test_bundle_excludes_data_and_redacts_log_values(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = RuntimePaths.from_root(Path(folder) / "runtime")
            paths.create_directories(); paths.ensure_secret_key()
            connection = sqlite3.connect(paths.database); connection.execute("CREATE TABLE sample(id INTEGER)"); connection.commit(); connection.close()
            secrets = (
                "0812345678", "abc_def-123456789012345678901234", "1234",
                "short-password", "Bearer short-authorization", "pos_session=short-cookie",
            )
            paths.logs.joinpath("server.log").write_text(
                "phone=0812345678 token=abc_def-123456789012345678901234\n"
                '{"pin":"1234","password":"short-password",'
                '"authorization":"Bearer short-authorization",'
                '"cookie":"pos_session=short-cookie"}\n',
                encoding="utf-8",
            )
            bundle = create_support_bundle(paths, SimpleNamespace(paths=paths, host="127.0.0.1", port=8000, min_free_space_mb=0, app_version="2.1", store_id="test"))
            with ZipFile(bundle) as package:
                names = package.namelist()
                self.assertIn("runtime-validation.json", names)
                self.assertNotIn("data/pos.db", names)
                text = package.read("logs/server.log").decode("utf-8")
                for secret in secrets:
                    self.assertNotIn(secret, text)
                self.assertGreaterEqual(text.count("[redacted]"), 6)


class MaintenanceRouteTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "maintenance.db")})
        self.client = self.app.test_client()
        with self.app.app_context():
            db = get_db(); db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1"); db.commit()
        staff_login(self.client)
        with self.app.app_context():
            self.csrf = get_db().execute("SELECT csrf_token FROM staff_sessions ORDER BY id DESC LIMIT 1").fetchone()[0]

    def tearDown(self):
        self.folder.cleanup()

    def test_admin_dashboard_and_audited_support_bundle(self):
        page = self.client.get("/maintenance")
        self.assertEqual(page.status_code, 200)
        self.assertIn("ดูแลระบบ", page.get_data(as_text=True))
        response = self.client.post("/maintenance/support-bundles", data={"csrf_token": self.csrf})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM audit_logs WHERE action='create_support_bundle'").fetchone()[0], 1)

    @patch("pos_app.routes.maintenance.subprocess.Popen")
    @patch("pos_app.routes.maintenance._verification")
    def test_signed_update_reauth_reads_current_admin_pin_from_database(self, verify, popen):
        verify.return_value = SimpleNamespace(
            script_path=Path(self.folder.name) / "release.ps1",
            signer_thumbprint="ABCD",
            release_id="release-3",
            version="3.0.0",
        )
        response = self.client.post(
            "/maintenance/updates/release.update.json/apply",
            data={"csrf_token": self.csrf, "admin_pin": "1234"},
        )
        self.assertEqual(response.status_code, 302)
        verify.assert_called_once_with("release.update.json")
        popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
