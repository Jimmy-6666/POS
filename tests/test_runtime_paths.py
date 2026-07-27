import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from pos_app import create_app
from pos_app.migrations import Migration, MigrationError, apply_migrations, ensure_history_table
from pos_app.runtime_paths import (
    RuntimeConfig,
    RuntimePathError,
    RuntimePaths,
    load_runtime_config,
    validate_runtime,
)


class RuntimePathTests(unittest.TestCase):
    def test_defaults_and_environment_override(self):
        project_root = Path(self.folder.name) / "source"
        legacy = RuntimePaths.from_environment(project_root, {})
        self.assertEqual(legacy.root, project_root.resolve())
        uat = RuntimePaths.from_environment(project_root, {"POS_RUNTIME_ROOT": str(Path(self.folder.name) / "uat_runtime")})
        self.assertEqual(uat.root.name, "uat_runtime")
        release = RuntimePaths.from_environment(project_root, {"POS_RUNTIME_ROOT": str(Path(self.folder.name) / "runtime")})
        self.assertEqual(release.browser_profile.name, "browser-profile")

    def test_local_configuration_and_environment_precedence(self):
        root = Path(self.folder.name) / "configured"
        config_dir = root / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "production.json").write_text(
            json.dumps({"port": 8123, "bind_host": "127.0.0.1", "min_free_space_mb": 0}),
            encoding="utf-8",
        )
        config = load_runtime_config(root, {"POS_RUNTIME_ROOT": str(root)})
        self.assertEqual(config.port, 8123)
        self.assertEqual(config.host, "127.0.0.1")
        overridden = load_runtime_config(root, {"POS_RUNTIME_ROOT": str(root), "POS_PORT": "8124"})
        self.assertEqual(overridden.port, 8124)

    def test_paths_support_spaces_and_non_ascii_and_stay_contained(self):
        root = Path(self.folder.name) / "ร้าน ทดสอบ POS"
        paths = RuntimePaths.from_root(root)
        paths.assert_safe()
        self.assertEqual(paths.resolve_relative("uploads/products/item.png"), paths.product_images / "item.png")
        with self.assertRaises(RuntimePathError):
            paths.resolve_relative("../outside.txt")
        with self.assertRaises(RuntimePathError):
            paths.with_database(root.parent / "outside.db")

    def test_runtime_validation_is_machine_readable_and_preserves_secret(self):
        paths = RuntimePaths.from_root(Path(self.folder.name) / "production")
        paths.create_directories()
        paths.secret_key.write_text("existing-secret", encoding="ascii")
        connection = sqlite3.connect(paths.database)
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
        connection.commit()
        connection.close()
        paths.ensure_secret_key()
        self.assertEqual(paths.secret_key.read_text(encoding="ascii"), "existing-secret")
        config = RuntimeConfig(paths, "0.0.0.0", 8000, 0, "store-1", "2.1", True, paths.configuration / "production.json")
        report = validate_runtime(config)
        self.assertTrue(report["ok"], report)
        self.assertIn("database_integrity", report["checks"])
        self.assertEqual(report["repairable"], [])
        self.assertNotIn("existing-secret", json.dumps(report))

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.folder.cleanup()


class MigrationHistoryTests(unittest.TestCase):
    def test_application_initializes_legacy_bridge_once(self):
        folder = tempfile.TemporaryDirectory()
        try:
            database = Path(folder.name) / "pos.db"
            create_app({"TESTING": True, "DATABASE": str(database)})
            connection = sqlite3.connect(database)
            first = connection.execute("SELECT version,name,success FROM schema_migrations").fetchall()
            self.assertEqual(first, [(19, "legacy-ad-hoc-migrations", 1)])
            connection.close()
            create_app({"TESTING": True, "DATABASE": str(database)})
            connection = sqlite3.connect(database)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 1)
            connection.close()
        finally:
            folder.cleanup()

    def test_new_migration_is_applied_once(self):
        connection = sqlite3.connect(":memory:")
        calls = []
        ensure_history_table(connection)
        migration = Migration(20, "test migration", lambda db: (calls.append(1), db.execute("CREATE TABLE marker (id INTEGER)")))
        apply_migrations(connection, [migration], "test")
        apply_migrations(connection, [migration], "test")
        self.assertEqual(len(calls), 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 1)
        connection.close()

    def test_failed_migration_is_recorded_and_blocks_retry(self):
        connection = sqlite3.connect(":memory:")
        ensure_history_table(connection)
        migration = Migration(20, "failed migration", lambda _db: (_ for _ in ()).throw(RuntimeError("boom")))
        with self.assertRaises(MigrationError):
            apply_migrations(connection, [migration], "test")
        self.assertEqual(connection.execute("SELECT success FROM schema_migrations WHERE version=20").fetchone()[0], 0)
        with self.assertRaises(MigrationError):
            apply_migrations(connection, [migration], "test")
        connection.close()

    def test_power_shell_scripts_parse_when_available(self):
        powershell = shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("Windows PowerShell is unavailable.")
        root = Path(__file__).resolve().parent.parent
        command = (
            "$files=Get-ChildItem -LiteralPath . -Filter '*-production.ps1';"
            "$files+=Get-Item production-common.ps1;"
            "foreach($file in $files){$t=$null;$e=$null;"
            "[System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$t,[ref]$e)|Out-Null;"
            "if($e.Count -gt 0){exit 1}}"
        )
        result = subprocess.run([powershell, "-NoProfile", "-Command", command], cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
