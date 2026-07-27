import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from pos_app.runtime_paths import RuntimePaths
from pos_app.services.maintenance_jobs import enqueue_job, get_job, run_job
from pos_app.services.support import SupportError, create_support_bundle, verify_remote_request
from pos_app.services.update_agent import UpdateError, load_manifest, validate_compatibility, verify_manifest, verify_release_package


class Sprint3ServiceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.paths = RuntimePaths.from_root(Path(self.folder.name) / "runtime")
        self.paths.create_directories()
        self.paths.ensure_secret_key()
        connection = sqlite3.connect(self.paths.database)
        connection.executescript("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL); INSERT INTO settings VALUES('schema_version','19');")
        connection.commit()
        connection.close()
        self.config = SimpleNamespace(app_version="2.1", store_id="store-test", production=False)
        self.key = b"release-test-key"

    def tearDown(self):
        self.folder.cleanup()

    def _manifest(self, version="2.2.0", package_sha="0" * 64, files=None):
        data = {
            "manifest_version": 1, "application_version": version, "release_timestamp": "2026-07-27T00:00:00Z",
            "minimum_supported_current_version": "2.1.0", "minimum_supported_schema_version": 19,
            "target_schema_version": 19, "restart_required": True, "release_notes": "test",
            "package_url": "file://release.zip", "package_sha256": package_sha,
            "files": files or [{"path": "pos_app/example.txt", "size": 5, "sha256": hashlib.sha256(b"hello").hexdigest()}],
        }
        data["signature_hmac_sha256"] = hmac.new(self.key, json.dumps({k: v for k, v in data.items()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        return data

    def test_release_manifest_signature_and_compatibility(self):
        manifest = self._manifest()
        verified = verify_manifest(manifest, self.key)
        self.assertEqual(verified.application_version, "2.2.0")
        validate_compatibility(verified, "2.1.0", 19)
        with self.assertRaises(UpdateError):
            validate_compatibility(verified, "2.2.0", 19)
        tampered = dict(manifest)
        tampered["release_notes"] = "tampered"
        with self.assertRaises(UpdateError):
            verify_manifest(tampered, self.key)

    def test_release_package_path_and_checksum_validation(self):
        package = Path(self.folder.name) / "release.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("pos_app/example.txt", "hello")
        manifest = self._manifest(package_sha=hashlib.sha256(package.read_bytes()).hexdigest())
        self.assertEqual(verify_release_package(package, verify_manifest(manifest, self.key))["file_count"], 1)
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr("runtime/data/pos.db", "blocked")
        with self.assertRaises(UpdateError):
            verify_release_package(package, verify_manifest(manifest, self.key))

    def test_durable_job_allow_list_and_execution(self):
        job = enqueue_job(self.paths, "controlled_restart", requested_by=1)
        self.assertEqual(get_job(self.paths, job["id"])["status"], "queued")
        result = run_job(self.paths, self.config, job["id"])
        self.assertEqual(result["status"], "succeeded")
        with self.assertRaises(ValueError):
            enqueue_job(self.paths, "arbitrary_shell")

    def test_support_bundle_redacts_secrets_and_phone_numbers(self):
        (self.paths.logs / "update.jsonl").write_text('{"token":"secret","phone":"0812345678"}\n', encoding="utf-8")
        bundle = create_support_bundle(self.paths, self.config)
        with zipfile.ZipFile(bundle) as archive:
            content = "\n".join(archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".json") or name.endswith(".jsonl"))
        self.assertNotIn("0812345678", content)
        self.assertNotIn("secret", content)
        self.assertNotIn("pos.db", "\n".join(zipfile.ZipFile(bundle).namelist()))

    def test_remote_request_is_signed_expiring_and_replay_resistant(self):
        now = datetime(2026, 7, 27, tzinfo=timezone.utc)
        request = {"request_id": "req-1", "store_id": "store-test", "action": "backup", "issued_at": now.isoformat(), "expires_at": (now + timedelta(minutes=10)).isoformat(), "nonce": "nonce-1"}
        request["signature"] = hmac.new(self.key, json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        replay = self.paths.support / "remote-replay"
        self.assertEqual(verify_remote_request(request, trusted_key=self.key, store_id="store-test", now=now, replay_dir=replay)["action"], "backup")
        with self.assertRaises(SupportError):
            verify_remote_request(request, trusted_key=self.key, store_id="store-test", now=now, replay_dir=replay)

    def test_maintenance_dashboard_is_admin_only_and_csrf_protected(self):
        from pos_app import create_app
        from pos_app.database import get_db

        app = create_app({"TESTING": True, "DATABASE": str(Path(self.folder.name) / "web.db")})
        client = app.test_client()
        with app.app_context():
            db = get_db()
            db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1")
            db.commit()
        client.post("/login", data={"staff_id": "1", "pin": "1234"})
        response = client.get("/maintenance")
        self.assertEqual(response.status_code, 200)
        self.assertIn("การบำรุงรักษาระบบ", response.get_data(as_text=True))
        self.assertEqual(client.post("/maintenance/backup", data={}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
