import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from pos_app import backup_cli
from pos_app.runtime_paths import RuntimePaths
from pos_app.services.backup import BackupBusyError, BackupError, create_local_backup, restore_backup_to_runtime, verify_backup
from pos_app.services.file_sync import sync_files
from pos_app.services.remote_backup import RemoteBackupConfig, SftpTransport


class FakeTransport:
    def __init__(self):
        self.uploads = []
        self.quarantines = []

    def upload_file(self, local, remote):
        self.uploads.append((Path(local), remote))

    def upload_versioned_file(self, local, remote, archive):
        self.uploads.append((Path(local), remote))
        self.quarantines.append((remote, archive))

    def quarantine_file(self, remote, quarantine):
        self.quarantines.append((remote, quarantine))


class Sprint2MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.paths = RuntimePaths.from_root(Path(self.folder.name) / "runtime")
        self.paths.create_directories()
        self.paths.ensure_secret_key()
        connection = sqlite3.connect(self.paths.database)
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL REFERENCES parent(id));
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO parent VALUES (1, 'ok');
            INSERT INTO child VALUES (1, 1);
            INSERT INTO settings VALUES ('schema_version', '19');
            """
        )
        connection.commit()
        connection.close()
        self.paths.product_images.joinpath("coffee.png").write_bytes(b"image-v1")
        self.config = SimpleNamespace(app_version="2.1", store_id="store-test", config_file=None)

    def tearDown(self):
        self.folder.cleanup()

    def test_online_backup_manifest_checksums_and_sqlite_integrity(self):
        artifact = create_local_backup(self.paths, self.config)
        verified = verify_backup(artifact.path)
        self.assertEqual(verified["status"], "complete")
        self.assertEqual(verified["schema_version"], "19")
        with ZipFile(artifact.path) as package:
            names = set(package.namelist())
            self.assertIn("database/pos.db", names)
            self.assertNotIn("uploads/products/coffee.png", names)
            self.assertNotIn("data/pos.db-wal", names)
            self.assertTrue(verified["product_images_separate_sync"])
            recovery_config = json.loads(package.read("config/recovery-config.json"))
            self.assertNotIn("secret_key", recovery_config)

    def test_incomplete_backup_is_not_restorable(self):
        archive = self.paths.backups / "backup-incomplete.zip"
        with ZipFile(archive, "w") as package:
            package.writestr("database/pos.db", b"not-a-database")
            package.writestr("manifest.json", json.dumps({"status": "incomplete", "format_version": 1}))
            package.writestr("checksums.sha256", "")
        with self.assertRaises(BackupError):
            verify_backup(archive)

    def test_backup_lock_and_local_retention_keep_a_known_good_archive(self):
        lock = self.paths.backups / ".backup.lock"
        lock.write_text("busy", encoding="ascii")
        with self.assertRaises(BackupBusyError):
            create_local_backup(self.paths, self.config)
        lock.unlink()
        base = datetime(2026, 7, 20, tzinfo=timezone.utc)
        for offset in range(3):
            create_local_backup(self.paths, self.config, retention=2, now=base + timedelta(days=offset))
        archives = list(self.paths.backups.glob("backup-*.zip"))
        self.assertEqual(len(archives), 2)
        self.assertTrue(all(verify_backup(path)["status"] == "complete" for path in archives))

    def test_incremental_sync_archives_replaced_and_deleted_images(self):
        transport = FakeTransport()
        first = sync_files(self.paths, transport, now=datetime(2026, 7, 20, tzinfo=timezone.utc), deletion_grace_days=2, backup_id="backup-one")
        self.assertEqual(first.uploaded, 1)
        second = sync_files(self.paths, transport, now=datetime(2026, 7, 20, 1, tzinfo=timezone.utc), deletion_grace_days=2, backup_id="backup-one")
        self.assertEqual(second.unchanged, 1)
        self.paths.product_images.joinpath("coffee.png").write_bytes(b"image-v2")
        third = sync_files(self.paths, transport, now=datetime(2026, 7, 20, 2, tzinfo=timezone.utc), deletion_grace_days=2, backup_id="backup-two")
        self.assertEqual(third.uploaded, 1)
        self.assertIn("file-backups/20260720T020000Z/uploads/products/coffee.png", transport.quarantines[-1][1])
        self.paths.product_images.joinpath("coffee.png").unlink()
        deleted = sync_files(self.paths, transport, now=datetime(2026, 7, 20, 3, tzinfo=timezone.utc), deletion_grace_days=2, backup_id="backup-three")
        self.assertEqual(deleted.pending_deletions, 0)
        self.assertEqual(deleted.quarantined, 1)
        self.assertEqual(len(transport.quarantines), 2)
        self.assertIn("file-backups/20260720T030000Z/uploads/products/coffee.png", transport.quarantines[-1][1])

    def test_recovery_restores_to_separate_runtime_without_overwrite(self):
        artifact = create_local_backup(self.paths, self.config)
        target = Path(self.folder.name) / "replacement-runtime"
        restored = restore_backup_to_runtime(artifact.path, target)
        self.assertTrue((restored / "data" / "pos.db").is_file())
        self.assertFalse((restored / "uploads" / "products" / "coffee.png").exists())
        with self.assertRaises(BackupError):
            restore_backup_to_runtime(artifact.path, target)

    def test_sftp_upload_uses_temp_name_then_atomic_rename(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs["input"]))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        key = Path(self.folder.name) / "backup.key"
        known_hosts = Path(self.folder.name) / "known_hosts"
        key.write_text("private-key-not-in-production", encoding="ascii")
        known_hosts.write_text("host-key", encoding="ascii")
        transport = SftpTransport(RemoteBackupConfig("backup.example", "posbackup", key, known_hosts, "store-test"), runner=runner)
        transport.upload_file(self.paths.product_images / "coffee.png", "file-snapshots/uploads/products/coffee.png")
        batch = calls[-1][1]
        self.assertIn(".part", batch)
        self.assertIn("rename", batch)
        self.assertIn("file-snapshots/uploads/products/coffee.png", batch)
        self.assertIn("UserKnownHostsFile=" + str(known_hosts), calls[-1][0])
        transport.upload_versioned_file(self.paths.product_images / "coffee.png", "file-snapshots/uploads/products/coffee.png", "file-backups/test/uploads/products/coffee.png")
        version_batches = [batch for _, batch in calls if "file-backups/test/uploads/products/coffee.png" in batch]
        self.assertTrue(any("-rename" in batch for batch in version_batches))
        transport.upload_files([(self.paths.product_images / "coffee.png", "file-snapshots/uploads/products/coffee.png")])
        self.assertIn("put", calls[-1][1])

    def test_vps_failure_reports_degraded_status_after_verified_local_backup(self):
        artifact = create_local_backup(self.paths, self.config)
        output = StringIO()
        config = SimpleNamespace(paths=self.paths, app_version="2.1", store_id="store-test", config_file=None)
        with patch.object(backup_cli, "_config", return_value=config), \
             patch.object(backup_cli, "create_local_backup", return_value=artifact), \
             patch.object(backup_cli, "_remote", side_effect=BackupError("VPS unavailable")), \
             redirect_stdout(output):
            self.assertEqual(backup_cli.main(["backup-and-sync"]), 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "local_complete_remote_failed")
        self.assertEqual(result["backup"], str(artifact.path))
        self.assertTrue(verify_backup(artifact.path))


if __name__ == "__main__":
    unittest.main()
