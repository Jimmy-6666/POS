import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from pos_app import create_app
from pos_app.database import get_db
from pos_app.runtime_paths import RuntimePaths
from pos_app.services.signed_updates import UpdateVerificationError, verify_staged_update
from pos_app.services.support_bundle import create_support_bundle


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
            paths.logs.joinpath("server.log").write_text("phone=0812345678 token=abc_def-123456789012345678901234\n", encoding="utf-8")
            bundle = create_support_bundle(paths, SimpleNamespace(paths=paths, host="127.0.0.1", port=8000, min_free_space_mb=0, app_version="2.1", store_id="test"))
            with ZipFile(bundle) as package:
                names = package.namelist()
                self.assertIn("runtime-validation.json", names)
                self.assertNotIn("data/pos.db", names)
                text = package.read("logs/server.log").decode("utf-8")
                self.assertNotIn("0812345678", text)
                self.assertNotIn("abc_def-123456789012345678901234", text)


class MaintenanceRouteTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "maintenance.db")})
        self.client = self.app.test_client()
        with self.app.app_context():
            db = get_db(); db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1"); db.commit()
        self.client.post("/login", data={"staff_id": "1", "pin": "1234"})
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


if __name__ == "__main__":
    unittest.main()
