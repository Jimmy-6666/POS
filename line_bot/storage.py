"""Durable SQLite state for conversations, webhook delivery, and POS retries."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


FLOW_TIMEOUT = timedelta(minutes=1)
SOURCE_IMAGE_RETENTION = timedelta(hours=24)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


class BotStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.database = self.root / "line_bot.db"
        self.root.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        return db

    @contextmanager
    def session(self):
        db = self.connect()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self) -> None:
        with self.session() as db:
            db.executescript(
                """CREATE TABLE IF NOT EXISTS webhook_events (
                    event_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','processing','processed','failed')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    received_at TEXT NOT NULL,
                    processing_at TEXT,
                    error_detail TEXT,
                    processed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_webhook_events_pending
                ON webhook_events(status,received_at);
                CREATE TABLE IF NOT EXISTS source_images (
                    message_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    received_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    flow_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(group_id,user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_expiry ON conversations(expires_at);
                CREATE TABLE IF NOT EXISTS pending_commands (
                    command_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    image_file TEXT,
                    status TEXT NOT NULL CHECK(status IN ('pending','attempting','retry_wait','applied','failed')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    outage_notified_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_pending_commands_due
                ON pending_commands(status,next_attempt_at);
                CREATE TABLE IF NOT EXISTS enrollment_groups (
                    group_id TEXT PRIMARY KEY,
                    observed_at TEXT NOT NULL,
                    last_observed_at TEXT NOT NULL
                );"""
            )

    def record_enrollment_group(self, group_id: str) -> None:
        """Record a group ID while enrollment is temporarily enabled.

        Enrollment never queues an event or performs a product operation.  The
        recorded value must be explicitly placed on the allowlist before the
        bot can interact with that group.
        """
        now = iso_now()
        with self.session() as db:
            db.execute(
                """INSERT INTO enrollment_groups(group_id,observed_at,last_observed_at)
                   VALUES(?,?,?) ON CONFLICT(group_id) DO UPDATE SET last_observed_at=excluded.last_observed_at""",
                (group_id, now, now),
            )

    def record_event(self, event: dict[str, Any]) -> bool:
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        fallback = f"{event.get('timestamp','')}:{event.get('type','')}:{message.get('id','')}"
        event_key = str(event.get("webhookEventId") or fallback)
        if not event_key or event_key == "::":
            return False
        with self.session() as db:
            cursor = db.execute(
                """INSERT OR IGNORE INTO webhook_events(event_key,payload_json,status,received_at)
                   VALUES(?,?,'pending',?)""",
                (event_key, json.dumps(event, ensure_ascii=False, separators=(",", ":")), iso_now()),
            )
            return bool(cursor.rowcount)

    def claim_events(self, limit: int = 20) -> list[dict[str, Any]]:
        claimed: list[dict[str, Any]] = []
        with self.session() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """SELECT event_key,payload_json FROM webhook_events
                   WHERE status='pending' OR (status='processing' AND processing_at<=datetime('now','-2 minutes'))
                   ORDER BY received_at LIMIT ?""",
                (limit,),
            ).fetchall()
            for row in rows:
                db.execute(
                    """UPDATE webhook_events SET status='processing',attempts=attempts+1,processing_at=?,error_detail=NULL
                       WHERE event_key=?""",
                    (iso_now(), row["event_key"]),
                )
                claimed.append({"event_key": row["event_key"], "event": json.loads(row["payload_json"])})
            db.commit()
        return claimed

    def finish_event(self, event_key: str, *, error: str | None = None) -> None:
        with self.session() as db:
            db.execute(
                """UPDATE webhook_events SET status=?,error_detail=?,processed_at=? WHERE event_key=?""",
                ("failed" if error else "processed", (error or "")[:1000] or None, iso_now(), event_key),
            )

    def remember_source_image(self, message_id: str, group_id: str, user_id: str) -> None:
        with self.session() as db:
            db.execute(
                """INSERT OR REPLACE INTO source_images(message_id,group_id,user_id,received_at)
                   VALUES(?,?,?,?)""",
                (message_id, group_id, user_id, iso_now()),
            )

    def source_image(self, message_id: str):
        retained_since = (utc_now() - SOURCE_IMAGE_RETENTION).isoformat(timespec="seconds")
        with self.session() as db:
            return db.execute(
                "SELECT * FROM source_images WHERE message_id=? AND received_at>?",
                (message_id, retained_since),
            ).fetchone()

    def purge_expired_source_images(self) -> int:
        """Remove LINE image references after their 24-hour retention window."""

        retained_since = (utc_now() - SOURCE_IMAGE_RETENTION).isoformat(timespec="seconds")
        with self.session() as db:
            cursor = db.execute("DELETE FROM source_images WHERE received_at<=?", (retained_since,))
            return cursor.rowcount

    def start_flow(self, group_id: str, user_id: str, flow_id: str, state: str, data: dict[str, Any]) -> None:
        expires = (utc_now() + FLOW_TIMEOUT).isoformat(timespec="seconds")
        with self.session() as db:
            db.execute(
                """INSERT INTO conversations(group_id,user_id,flow_id,state,data_json,expires_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(group_id,user_id) DO UPDATE SET flow_id=excluded.flow_id,state=excluded.state,
                     data_json=excluded.data_json,expires_at=excluded.expires_at,updated_at=excluded.updated_at""",
                (group_id, user_id, flow_id, state, json.dumps(data, ensure_ascii=False), expires, iso_now()),
            )

    def conversation(self, group_id: str, user_id: str):
        with self.session() as db:
            row = db.execute(
                "SELECT * FROM conversations WHERE group_id=? AND user_id=?", (group_id, user_id)
            ).fetchone()
            if not row:
                return None
            if row["expires_at"] <= iso_now():
                return None
            return {
                "flow_id": row["flow_id"], "state": row["state"],
                "data": json.loads(row["data_json"]), "expires_at": row["expires_at"],
            }

    def update_flow(self, group_id: str, user_id: str, *, state: str, data: dict[str, Any]) -> None:
        expires = (utc_now() + FLOW_TIMEOUT).isoformat(timespec="seconds")
        with self.session() as db:
            db.execute(
                """UPDATE conversations SET state=?,data_json=?,expires_at=?,updated_at=?
                   WHERE group_id=? AND user_id=?""",
                (state, json.dumps(data, ensure_ascii=False), expires, iso_now(), group_id, user_id),
            )

    def close_flow(self, group_id: str, user_id: str) -> None:
        with self.session() as db:
            db.execute("DELETE FROM conversations WHERE group_id=? AND user_id=?", (group_id, user_id))

    def expire_flows(self) -> list[dict[str, str]]:
        """Atomically close expired conversations so the worker can notify their owners."""

        now = iso_now()
        inactive_since = (utc_now() - FLOW_TIMEOUT).isoformat(timespec="seconds")
        with self.session() as db:
            db.execute("BEGIN IMMEDIATE")
            expired = db.execute(
                """SELECT group_id,user_id FROM conversations
                   WHERE expires_at<=? OR updated_at<=? ORDER BY expires_at""",
                (now, inactive_since),
            ).fetchall()
            db.execute(
                "DELETE FROM conversations WHERE expires_at<=? OR updated_at<=?",
                (now, inactive_since),
            )
            db.commit()
            return [dict(row) for row in expired]

    def enqueue_command(self, command_id: str, group_id: str, user_id: str, command: dict[str, Any]) -> None:
        with self.session() as db:
            db.execute(
                """INSERT INTO pending_commands
                   (command_id,group_id,user_id,command_json,status,next_attempt_at,created_at)
                   VALUES(?,?,?,?,'pending',?,?)""",
                (command_id, group_id, user_id, json.dumps(command, ensure_ascii=False), iso_now(), iso_now()),
            )

    def claim_due_commands(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.session() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """SELECT * FROM pending_commands
                   WHERE status IN ('pending','retry_wait') AND next_attempt_at<=?
                   ORDER BY created_at LIMIT ?""",
                (iso_now(), limit),
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE pending_commands SET status='attempting',attempts=attempts+1 WHERE command_id=?",
                    (row["command_id"],),
                )
            db.commit()
            return [dict(row) | {"command": json.loads(row["command_json"])} for row in rows]

    def complete_command(self, command_id: str) -> None:
        with self.session() as db:
            db.execute(
                "UPDATE pending_commands SET status='applied',completed_at=?,last_error=NULL WHERE command_id=?",
                (iso_now(), command_id),
            )

    def retry_command(self, command_id: str, error: str, retry_seconds: int) -> bool:
        next_attempt = (utc_now() + timedelta(seconds=retry_seconds)).isoformat(timespec="seconds")
        with self.session() as db:
            row = db.execute("SELECT outage_notified_at FROM pending_commands WHERE command_id=?", (command_id,)).fetchone()
            first_outage = bool(row and not row["outage_notified_at"])
            db.execute(
                """UPDATE pending_commands SET status='retry_wait',next_attempt_at=?,last_error=?,
                   outage_notified_at=COALESCE(outage_notified_at,?) WHERE command_id=?""",
                (next_attempt, error[:1000], iso_now() if first_outage else None, command_id),
            )
            return first_outage

    def fail_command(self, command_id: str, error: str) -> None:
        with self.session() as db:
            db.execute(
                "UPDATE pending_commands SET status='failed',completed_at=?,last_error=? WHERE command_id=?",
                (iso_now(), error[:1000], command_id),
            )
