import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from uuid import UUID
from pathlib import Path

from pos_app import create_app
from pos_app.migrations import _add_product_uuid, Migration, MigrationError, apply_migrations, ensure_history_table
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
        self.assertEqual(release.print_agent_token, release.configuration / "print-agent-token")

    def test_local_configuration_and_environment_precedence(self):
        root = Path(self.folder.name) / "configured"
        config_dir = root / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "production.json").write_text(
            json.dumps({"port": 8123, "bind_host": "127.0.0.1", "min_free_space_mb": 0, "update_signer_thumbprint": "ABCD"}),
            encoding="utf-8",
        )
        config = load_runtime_config(root, {"POS_RUNTIME_ROOT": str(root)})
        self.assertEqual(config.port, 8123)
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.update_signer_thumbprint, "ABCD")
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

    def test_runtime_validation_rejects_invalid_backup_schedule(self):
        root = Path(self.folder.name) / "invalid-schedule"
        paths = RuntimePaths.from_root(root)
        paths.create_directories()
        paths.ensure_secret_key()
        connection = sqlite3.connect(paths.database)
        connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO settings(key,value) VALUES (?,?)",
            [("backup_schedule_enabled", "1"), ("backup_schedule_time", "25:00")],
        )
        connection.commit()
        connection.close()
        config = RuntimeConfig(paths, "127.0.0.1", 8000, 0, "store-1", "3.0.0", True, None)
        report = validate_runtime(config)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["backup_schedule"]["ok"])

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
            self.assertEqual(first, [
                (19, "legacy-ad-hoc-migrations", 1),
                (20, "enable configured negative stock", 1),
                (21, "add LINE customer identity", 1),
                (22, "add customer lifecycle fields", 1),
                (23, "add immutable product UUIDs", 1),
                (24, "add admin TOTP two-factor authentication", 1),
                (25, "add reconciliation void total", 1),
                (26, "record second-factor verified staff sessions", 1),
                (27, "add sale-item manual-price references", 1),
                (28, "add configurable POS button layout", 1),
                (29, "add per-product manual-price flag", 1),
                (30, "grant manager settings and billing access", 1),
                (31, "add LINE Bot command and image-cleanup records", 1),
            ])
            connection.close()
            create_app({"TESTING": True, "DATABASE": str(database)})
            connection = sqlite3.connect(database)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 13)
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

    def test_product_uuid_migration_backfills_held_bills_and_locks_identity(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """CREATE TABLE products (id INTEGER PRIMARY KEY, name_th TEXT NOT NULL);
               CREATE TABLE held_bills (id INTEGER PRIMARY KEY, cart_json TEXT NOT NULL, updated_at TEXT);"""
        )
        connection.execute("INSERT INTO products(id,name_th) VALUES(1,'first'),(2,'second')")
        connection.execute(
            "INSERT INTO held_bills(id,cart_json) VALUES(1,?)",
            (json.dumps({"items": [{"product_id": 1, "quantity": 2}]}),),
        )

        _add_product_uuid(connection)

        products = connection.execute("SELECT id,product_uuid FROM products ORDER BY id").fetchall()
        self.assertEqual(len({row["product_uuid"] for row in products}), 2)
        for row in products:
            self.assertEqual(str(UUID(row["product_uuid"])), row["product_uuid"])
        held_cart = json.loads(connection.execute("SELECT cart_json FROM held_bills WHERE id=1").fetchone()[0])
        self.assertEqual(held_cart["items"][0]["product_uuid"], products[0]["product_uuid"])
        self.assertNotIn("product_id", held_cart["items"][0])
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("UPDATE products SET product_uuid=? WHERE id=1", (products[1]["product_uuid"],))
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO products(id,name_th) VALUES(3,'third')")
        connection.close()

    def test_power_shell_scripts_parse_when_available(self):
        powershell = shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("Windows PowerShell is unavailable.")
        root = Path(__file__).resolve().parent.parent
        command = (
            "$files=Get-ChildItem -LiteralPath . -Filter '*-production.ps1';"
            "$files+=Get-Item production-common.ps1;"
            "$files+=Get-Item configure-production-network.ps1;"
            "foreach($file in $files){$t=$null;$e=$null;"
            "[System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$t,[ref]$e)|Out-Null;"
            "if($e.Count -gt 0){exit 1}}"
        )
        result = subprocess.run([powershell, "-NoProfile", "-Command", command], cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_attach_only_desktop_skips_server_only_line_bot_secret(self):
        powershell = shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("Windows PowerShell is unavailable.")
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder) / "desktop-runtime"
            config = runtime / "config"
            config.mkdir(parents=True)
            (config / "line-bot-integration.env").write_text(
                "invalid desktop-only sentinel\n",
                encoding="utf-8",
            )
            command = (
                ". (Join-Path $env:TEST_INSTALL_ROOT 'production-common.ps1');"
                "$context=Get-ProductionContext $env:TEST_INSTALL_ROOT $env:TEST_RUNTIME_ROOT 8000;"
                "Set-ProductionEnvironment $context -DesktopAttachOnly;"
                "if($env:POS_RUNTIME_ROOT -ne $context.RuntimeRoot){exit 3};"
                "$serverRejected=$false;"
                "try{Set-ProductionEnvironment $context}catch{$serverRejected=$true};"
                "if(-not $serverRejected){exit 4}"
            )
            environment = os.environ.copy()
            environment["TEST_INSTALL_ROOT"] = str(root)
            environment["TEST_RUNTIME_ROOT"] = str(runtime)
            result = subprocess.run(
                [powershell, "-NoProfile", "-Command", command],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
