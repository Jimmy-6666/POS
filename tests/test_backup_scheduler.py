import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from pos_app.runtime_paths import RuntimePaths
from pos_app.services.backup_scheduler import BANGKOK, BackupScheduler, is_valid_schedule


class BackupSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        paths = RuntimePaths.from_root(Path(self.folder.name) / "runtime")
        paths.create_directories()
        database = sqlite3.connect(paths.database)
        database.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        database.executemany("INSERT INTO settings(key,value) VALUES (?,?)", [("backup_schedule_enabled", "1"), ("backup_schedule_time", "02:00")])
        database.commit()
        database.close()
        self.calls = []
        self.app = SimpleNamespace(config={"DATABASE": str(paths.database), "RUNTIME_PATHS": paths, "POS_PORT": 8001, "POS_INSTALL_ROOT": str(Path.cwd())})
        self.scheduler = BackupScheduler(self.app, runner=lambda *args, **kwargs: self.calls.append((args, kwargs)))

    def tearDown(self):
        self.folder.cleanup()

    def test_schedule_runs_once_after_daily_time_and_validates_format(self):
        self.assertTrue(is_valid_schedule("02:00"))
        self.assertFalse(is_valid_schedule("2pm"))
        before = datetime(2026, 7, 20, 1, 59, tzinfo=BANGKOK)
        self.assertFalse(self.scheduler.tick(before))
        due = datetime(2026, 7, 20, 2, 0, tzinfo=BANGKOK)
        self.assertTrue(self.scheduler.tick(due))
        self.assertFalse(self.scheduler.tick(due))
        self.assertEqual(len(self.calls), 1)
        command = self.calls[0][0][0]
        self.assertEqual(command[-1], "backup-and-sync")
        self.assertEqual(self.calls[0][1]["env"]["POS_BACKUP_TRIGGER"], "scheduled")


if __name__ == "__main__":
    unittest.main()
