"""Small in-process daily trigger for the verified backup-and-sync command."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .backup import record_remote_backup_status
# Thailand has no daylight-saving change. A fixed offset avoids requiring the
# optional tzdata package on Windows POS installations.
BANGKOK = timezone(timedelta(hours=7), name="Asia/Bangkok")


def is_valid_schedule(value: str) -> bool:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        return False
    return True


class BackupScheduler:
    def __init__(self, app, runner=subprocess.Popen):
        self.app = app
        self.runner = runner
        self.last_started_date: str | None = None
        self._thread: threading.Thread | None = None

    def _settings(self) -> tuple[bool, str]:
        connection = sqlite3.connect(self.app.config["DATABASE"], timeout=10)
        try:
            values = dict(connection.execute(
                "SELECT key,value FROM settings WHERE key IN ('backup_schedule_enabled','backup_schedule_time')"
            ).fetchall())
        finally:
            connection.close()
        enabled = values.get("backup_schedule_enabled", "1") == "1"
        schedule = values.get("backup_schedule_time", "02:00")
        return enabled, schedule

    def tick(self, now: datetime | None = None) -> bool:
        current = (now or datetime.now(timezone.utc)).astimezone(BANGKOK)
        enabled, schedule = self._settings()
        if not enabled or not is_valid_schedule(schedule):
            return False
        business_date = current.date().isoformat()
        if self.last_started_date == business_date:
            return False
        # Trigger only in the selected minute. A restart must not unexpectedly
        # run a missed backup outside the operator-selected time.
        if current.strftime("%H:%M") != schedule:
            return False
        self.last_started_date = business_date
        self.start_backup("scheduled")
        return True

    def start_backup(self, reason: str = "manual") -> None:
        paths = self.app.config["RUNTIME_PATHS"]
        paths.logs.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment["POS_RUNTIME_ROOT"] = str(paths.root)
        environment["POS_PORT"] = str(self.app.config["POS_PORT"])
        environment["POS_BACKUP_TRIGGER"] = reason
        record_remote_backup_status(paths, "started", {"trigger": reason})
        with (paths.logs / "scheduled-backup.log").open("a", encoding="utf-8") as log:
            self.runner(
                [sys.executable, "-m", "pos_app.backup_cli", "backup-and-sync"],
                cwd=self.app.config["POS_INSTALL_ROOT"], env=environment,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

    def run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:
                pass
            time.sleep(5)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self.run, name="pos-backup-scheduler", daemon=True)
            self._thread.start()


def init_app(app) -> None:
    if not app.config.get("BACKUP_SCHEDULER_ENABLED", False):
        return
    scheduler = BackupScheduler(app)
    app.extensions["backup_scheduler"] = scheduler
    scheduler.start()
