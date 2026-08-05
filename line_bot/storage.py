"""Durable SQLite state for conversations, webhook delivery, and POS retries."""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


FLOW_TIMEOUT = timedelta(minutes=1)
SOURCE_IMAGE_RETENTION = timedelta(hours=24)
VISION_COLLECTION_WINDOW = timedelta(seconds=15)
VISION_JOB_RETENTION = timedelta(hours=24)
MICROUSD_PER_USD = 1_000_000
# Thailand has no daylight-saving time.  A fixed UTC+7 offset avoids relying
# on optional OS/tzdata packages in the Windows POS and the VPS.
BANGKOK_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Bangkok")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def gemini_budget_month() -> str:
    """Calendar month for the Thai retail operation, independent of VPS UTC."""

    return datetime.now(BANGKOK_TIMEZONE).strftime("%Y-%m")


def _microusd_to_usd(value: int) -> str:
    return format(Decimal(int(value)) / Decimal(MICROUSD_PER_USD), ".6f")


def _safe_error_detail(error: str) -> str:
    """Keep durable diagnostics useful without retaining obvious secret values."""

    text = " ".join(str(error or "").split())[:1000]
    return re.sub(
        r"(?i)\b(api[ _-]?key|authorization|bearer|token|secret|password)\b\s*[:=]?\s*\S+",
        r"\1=<redacted>",
        text,
    )


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
                CREATE TABLE IF NOT EXISTS pending_notifications (
                    notification_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    retry_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK(status IN ('pending','attempting','delivered','failed')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    delivered_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_pending_notifications_due
                ON pending_notifications(status,next_attempt_at);
                CREATE TABLE IF NOT EXISTS vision_jobs (
                    job_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    image_set_id TEXT NOT NULL,
                    image_message_ids_json TEXT NOT NULL,
                    reply_token TEXT,
                    status TEXT NOT NULL CHECK(status IN ('collecting','pending','processing','retry_wait','completed','failed','cancelled')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    collection_deadline_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(group_id,user_id,image_set_id)
                );
                CREATE INDEX IF NOT EXISTS idx_vision_jobs_due
                ON vision_jobs(status,next_attempt_at,created_at);
                CREATE INDEX IF NOT EXISTS idx_vision_jobs_active_owner
                ON vision_jobs(group_id,user_id,status,updated_at);
                CREATE TABLE IF NOT EXISTS gemini_budget_requests (
                    request_key TEXT PRIMARY KEY,
                    month TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    reserved_cost_microusd INTEGER NOT NULL CHECK(reserved_cost_microusd >= 0),
                    actual_cost_microusd INTEGER CHECK(actual_cost_microusd >= 0),
                    input_tokens INTEGER CHECK(input_tokens >= 0),
                    output_tokens INTEGER CHECK(output_tokens >= 0),
                    thought_tokens INTEGER CHECK(thought_tokens >= 0),
                    status TEXT NOT NULL CHECK(status IN ('reserved','started','settled','unknown_usage')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(job_id,attempt)
                );
                CREATE INDEX IF NOT EXISTS idx_gemini_budget_requests_month
                ON gemini_budget_requests(month,created_at);
                CREATE TABLE IF NOT EXISTS gemini_monthly_usage (
                    month TEXT PRIMARY KEY,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_microusd INTEGER NOT NULL DEFAULT 0,
                    actual_cost_microusd INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS enrollment_groups (
                    group_id TEXT PRIMARY KEY,
                    observed_at TEXT NOT NULL,
                    last_observed_at TEXT NOT NULL
                );"""
            )

    @staticmethod
    def _sync_gemini_monthly_usage(db: sqlite3.Connection, month: str) -> None:
        """Materialize a safe monthly diagnostic summary from the idempotent ledger."""

        row = db.execute(
            """SELECT COUNT(*) AS request_count,
                      COALESCE(SUM(COALESCE(actual_cost_microusd,reserved_cost_microusd)),0) AS estimated_cost,
                      COALESCE(SUM(actual_cost_microusd),0) AS actual_cost
                 FROM gemini_budget_requests WHERE month=?""",
            (month,),
        ).fetchone()
        db.execute(
            """INSERT INTO gemini_monthly_usage
               (month,request_count,estimated_cost_microusd,actual_cost_microusd,updated_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(month) DO UPDATE SET
                 request_count=excluded.request_count,
                 estimated_cost_microusd=excluded.estimated_cost_microusd,
                 actual_cost_microusd=excluded.actual_cost_microusd,
                 updated_at=excluded.updated_at""",
            (month, int(row["request_count"]), int(row["estimated_cost"]), int(row["actual_cost"]), iso_now()),
        )

    def reserve_gemini_request(
        self,
        *,
        job_id: str,
        attempt: int,
        budget_microusd: int,
        reserved_cost_microusd: int,
        month: str | None = None,
    ) -> dict[str, Any]:
        """Atomically reserve one bounded Gemini call, or decline before API use.

        A request key can only be reserved once.  In particular, a recovered
        worker may never re-run a previously reserved attempt merely because a
        process died between reservation and provider invocation.
        """

        if not job_id or attempt < 1 or budget_microusd <= 0 or reserved_cost_microusd < 0:
            raise ValueError("Unsafe Gemini budget reservation arguments.")
        selected_month = month or gemini_budget_month()
        request_key = f"{job_id}:{attempt}"
        with self.session() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT status FROM gemini_budget_requests WHERE request_key=?", (request_key,)
            ).fetchone()
            if existing:
                return {"allowed": False, "reason": "duplicate", "request_key": request_key}
            row = db.execute(
                """SELECT COALESCE(SUM(COALESCE(actual_cost_microusd,reserved_cost_microusd)),0) AS committed
                   FROM gemini_budget_requests WHERE month=?""",
                (selected_month,),
            ).fetchone()
            committed = int(row["committed"])
            if committed + reserved_cost_microusd > budget_microusd:
                return {
                    "allowed": False,
                    "reason": "budget_exhausted",
                    "request_key": request_key,
                    "committed_microusd": committed,
                }
            now = iso_now()
            db.execute(
                """INSERT INTO gemini_budget_requests
                   (request_key,month,job_id,attempt,reserved_cost_microusd,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,'reserved',?,?)""",
                (request_key, selected_month, job_id, attempt, reserved_cost_microusd, now, now),
            )
            self._sync_gemini_monthly_usage(db, selected_month)
            return {
                "allowed": True,
                "request_key": request_key,
                "reserved_cost_microusd": reserved_cost_microusd,
            }

    def start_gemini_request(self, request_key: str) -> bool:
        """Claim a reservation immediately before invoking Gemini exactly once."""

        with self.session() as db:
            cursor = db.execute(
                """UPDATE gemini_budget_requests SET status='started',updated_at=?
                   WHERE request_key=? AND status='reserved'""",
                (iso_now(), request_key),
            )
            return cursor.rowcount == 1

    def settle_gemini_request(
        self,
        request_key: str,
        *,
        actual_cost_microusd: int,
        input_tokens: int,
        output_tokens: int,
        thought_tokens: int,
    ) -> None:
        """Replace a conservative reservation with actual provider usage."""

        values = (actual_cost_microusd, input_tokens, output_tokens, thought_tokens)
        if any(int(value) < 0 for value in values):
            raise ValueError("Gemini usage values must be non-negative.")
        with self.session() as db:
            row = db.execute("SELECT month FROM gemini_budget_requests WHERE request_key=?", (request_key,)).fetchone()
            if not row:
                return
            db.execute(
                """UPDATE gemini_budget_requests
                   SET actual_cost_microusd=?,input_tokens=?,output_tokens=?,thought_tokens=?,
                       status='settled',updated_at=?
                   WHERE request_key=? AND status IN ('reserved','started')""",
                (*map(int, values), iso_now(), request_key),
            )
            self._sync_gemini_monthly_usage(db, row["month"])

    def retain_gemini_reservation(self, request_key: str) -> None:
        """Keep the full reservation when the provider returned no trustworthy usage."""

        with self.session() as db:
            row = db.execute("SELECT month FROM gemini_budget_requests WHERE request_key=?", (request_key,)).fetchone()
            if not row:
                return
            db.execute(
                """UPDATE gemini_budget_requests SET status='unknown_usage',updated_at=?
                   WHERE request_key=? AND status IN ('reserved','started')""",
                (iso_now(), request_key),
            )
            self._sync_gemini_monthly_usage(db, row["month"])

    def gemini_budget_diagnostics(self, budget_microusd: int, *, month: str | None = None) -> dict[str, Any]:
        """Return aggregate, secret-free monthly budget diagnostics."""

        if budget_microusd <= 0:
            raise ValueError("Gemini monthly budget must be positive.")
        selected_month = month or gemini_budget_month()
        with self.session() as db:
            row = db.execute(
                """SELECT request_count,estimated_cost_microusd,actual_cost_microusd
                   FROM gemini_monthly_usage WHERE month=?""",
                (selected_month,),
            ).fetchone()
        request_count = int(row["request_count"]) if row else 0
        estimated = int(row["estimated_cost_microusd"]) if row else 0
        actual = int(row["actual_cost_microusd"]) if row else 0
        return {
            "month": selected_month,
            "request_count": request_count,
            "estimated_cost_usd": _microusd_to_usd(estimated),
            "actual_cost_usd": _microusd_to_usd(actual),
            "remaining_budget_usd": _microusd_to_usd(max(0, budget_microusd - estimated)),
        }

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
                ("failed" if error else "processed", _safe_error_detail(error) or None, iso_now(), event_key),
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

    def group_conversation(self, group_id: str):
        """Return the newest unexpired flow in a group, regardless of member."""

        with self.session() as db:
            row = db.execute(
                """SELECT * FROM conversations WHERE group_id=? AND expires_at>?
                   ORDER BY updated_at DESC LIMIT 1""",
                (group_id, iso_now()),
            ).fetchone()
            if not row:
                return None
            return {
                "user_id": row["user_id"], "flow_id": row["flow_id"], "state": row["state"],
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
                (next_attempt, _safe_error_detail(error), iso_now() if first_outage else None, command_id),
            )
            return first_outage

    def fail_command(self, command_id: str, error: str) -> None:
        with self.session() as db:
            db.execute(
                "UPDATE pending_commands SET status='failed',completed_at=?,last_error=? WHERE command_id=?",
                (iso_now(), _safe_error_detail(error), command_id),
            )

    def enqueue_notification(self, notification_id: str, group_id: str, user_id: str, text: str) -> None:
        """Persist one group notification so a LINE delivery failure never loses the outcome."""

        if not notification_id or not group_id or not user_id or not text:
            raise ValueError("Notification requires an ID, group, user, and text.")
        now = iso_now()
        retry_key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"raisanngam-line-bot:{notification_id}"))
        with self.session() as db:
            db.execute(
                """INSERT INTO pending_notifications
                   (notification_id,group_id,user_id,text,retry_key,status,next_attempt_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,'pending',?,?,?)
                   ON CONFLICT(notification_id) DO NOTHING""",
                (notification_id, group_id, user_id, text, retry_key, now, now, now),
            )

    def claim_due_notifications(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.session() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """SELECT * FROM pending_notifications
                   WHERE status='pending' AND next_attempt_at<=?
                   ORDER BY created_at LIMIT ?""",
                (iso_now(), limit),
            ).fetchall()
            now = iso_now()
            for row in rows:
                db.execute(
                    """UPDATE pending_notifications
                       SET status='attempting',attempts=attempts+1,updated_at=? WHERE notification_id=?""",
                    (now, row["notification_id"]),
                )
            db.commit()
            return [dict(row) | {"attempts": int(row["attempts"]) + 1} for row in rows]

    def complete_notification(self, notification_id: str) -> None:
        now = iso_now()
        with self.session() as db:
            db.execute(
                """UPDATE pending_notifications
                   SET status='delivered',last_error=NULL,updated_at=?,delivered_at=?
                   WHERE notification_id=?""",
                (now, now, notification_id),
            )

    def retry_notification(self, notification_id: str, error: str, retry_seconds: int) -> None:
        if retry_seconds <= 0:
            raise ValueError("Notification retry delay must be positive.")
        next_attempt = (utc_now() + timedelta(seconds=retry_seconds)).isoformat(timespec="seconds")
        with self.session() as db:
            db.execute(
                """UPDATE pending_notifications
                   SET status='pending',next_attempt_at=?,last_error=?,updated_at=?
                   WHERE notification_id=?""",
                (next_attempt, _safe_error_detail(error), iso_now(), notification_id),
            )

    def fail_notification(self, notification_id: str, error: str) -> None:
        with self.session() as db:
            db.execute(
                """UPDATE pending_notifications
                   SET status='failed',last_error=?,updated_at=? WHERE notification_id=?""",
                (_safe_error_detail(error), iso_now(), notification_id),
            )

    def record_vision_image(
        self,
        group_id: str,
        user_id: str,
        message_id: str,
        *,
        image_set_id: str | None,
        image_index: int | None,
        reply_token: str,
    ) -> dict[str, str]:
        """Durably collect two images without ever storing their bytes."""

        now = iso_now()
        deadline = (utc_now() + VISION_COLLECTION_WINDOW).isoformat(timespec="seconds")
        with self.session() as db:
            db.execute("BEGIN IMMEDIATE")
            if image_set_id:
                collection_id = f"imageset:{image_set_id}"
                index = image_index
                row = db.execute(
                    "SELECT * FROM vision_jobs WHERE group_id=? AND user_id=? AND image_set_id=?",
                    (group_id, user_id, collection_id),
                ).fetchone()
            else:
                row = db.execute(
                    """SELECT * FROM vision_jobs WHERE group_id=? AND user_id=? AND status='collecting'
                       AND image_set_id LIKE 'fallback:%' AND collection_deadline_at>=?
                       ORDER BY created_at DESC LIMIT 1""",
                    (group_id, user_id, now),
                ).fetchone()
                collection_id = row["image_set_id"] if row else f"fallback:{secrets.token_urlsafe(12)}"
                index = None
            active = db.execute(
                """SELECT job_id,status FROM vision_jobs WHERE group_id=? AND user_id=?
                   AND status IN ('collecting','pending','processing','retry_wait')
                   ORDER BY updated_at DESC LIMIT 1""",
                (group_id, user_id),
            ).fetchone()
            # A second imageSet must not displace an incomplete collection,
            # while the missing index of that same imageSet must still be able
            # to complete it.
            if active and (not row or active["job_id"] != row["job_id"]):
                db.commit()
                return {"status": "active", "job_id": active["job_id"]}
            if row and row["status"] != "collecting":
                db.commit()
                return {"status": "active", "job_id": row["job_id"]}
            if row:
                image_ids = json.loads(row["image_message_ids_json"])
                job_id = row["job_id"]
            else:
                image_ids = {}
                job_id = secrets.token_urlsafe(18)
            if index is None:
                index = 1 if "1" not in image_ids else 2
            if index not in {1, 2}:
                db.commit()
                return {"status": "invalid", "job_id": job_id}
            key = str(index)
            if key in image_ids and image_ids[key] != message_id:
                db.execute(
                    """UPDATE vision_jobs SET status='failed',last_error=?,updated_at=?,completed_at=?
                       WHERE job_id=?""",
                    ("Conflicting image-set index.", now, now, job_id),
                )
                db.commit()
                return {"status": "invalid", "job_id": job_id}
            image_ids[key] = message_id
            ready = set(image_ids) == {"1", "2"}
            if row:
                db.execute(
                    """UPDATE vision_jobs SET image_message_ids_json=?,reply_token=?,status=?,next_attempt_at=?,
                       collection_deadline_at=?,updated_at=? WHERE job_id=?""",
                    (json.dumps(image_ids, separators=(",", ":")), reply_token, "pending" if ready else "collecting",
                     now if ready else None, deadline, now, job_id),
                )
            else:
                db.execute(
                    """INSERT INTO vision_jobs
                       (job_id,group_id,user_id,image_set_id,image_message_ids_json,reply_token,status,next_attempt_at,
                        collection_deadline_at,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (job_id, group_id, user_id, collection_id, json.dumps(image_ids, separators=(",", ":")),
                     reply_token, "pending" if ready else "collecting", now if ready else None, deadline, now, now),
                )
            db.commit()
            return {"status": "pending" if ready else "collecting", "job_id": job_id}

    def claim_due_vision_jobs(self, limit: int = 1) -> list[dict[str, Any]]:
        with self.session() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """SELECT * FROM vision_jobs WHERE (status IN ('pending','retry_wait') AND next_attempt_at<=?)
                   OR (status='processing' AND updated_at<=datetime('now','-2 minutes'))
                   ORDER BY created_at LIMIT ?""",
                (iso_now(), limit),
            ).fetchall()
            for row in rows:
                db.execute(
                    """UPDATE vision_jobs SET status='processing',attempts=attempts+1,updated_at=?,last_error=NULL
                       WHERE job_id=?""",
                    (iso_now(), row["job_id"]),
                )
            db.commit()
            return [
                dict(row) | {
                    "attempts": int(row["attempts"]) + 1,
                    "image_message_ids": json.loads(row["image_message_ids_json"]),
                }
                for row in rows
            ]

    def complete_vision_job(self, job_id: str) -> None:
        with self.session() as db:
            db.execute(
                """UPDATE vision_jobs SET status='completed',completed_at=?,updated_at=?,last_error=NULL
                   WHERE job_id=?""",
                (iso_now(), iso_now(), job_id),
            )

    def retry_vision_job(self, job_id: str, error: str, *, retry_seconds: int, max_attempts: int) -> bool:
        with self.session() as db:
            row = db.execute("SELECT attempts FROM vision_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row or row["attempts"] >= max_attempts:
                db.execute(
                    """UPDATE vision_jobs SET status='failed',completed_at=?,updated_at=?,last_error=? WHERE job_id=?""",
                    (iso_now(), iso_now(), _safe_error_detail(error), job_id),
                )
                return False
            next_attempt = (utc_now() + timedelta(seconds=retry_seconds)).isoformat(timespec="seconds")
            db.execute(
                """UPDATE vision_jobs SET status='retry_wait',next_attempt_at=?,updated_at=?,last_error=? WHERE job_id=?""",
                (next_attempt, iso_now(), _safe_error_detail(error), job_id),
            )
            return True

    def fail_vision_job(self, job_id: str, error: str) -> None:
        with self.session() as db:
            db.execute(
                """UPDATE vision_jobs SET status='failed',completed_at=?,updated_at=?,last_error=? WHERE job_id=?""",
                (iso_now(), iso_now(), _safe_error_detail(error), job_id),
            )

    def expire_vision_collections(self) -> int:
        with self.session() as db:
            cursor = db.execute(
                """UPDATE vision_jobs SET status='cancelled',completed_at=?,updated_at=?,last_error=?
                   WHERE status='collecting' AND collection_deadline_at<?""",
                (iso_now(), iso_now(), "Two-image collection timed out.", iso_now()),
            )
            return cursor.rowcount

    def purge_expired_vision_jobs(self) -> int:
        cutoff = (utc_now() - VISION_JOB_RETENTION).isoformat(timespec="seconds")
        with self.session() as db:
            cursor = db.execute(
                """DELETE FROM vision_jobs WHERE status IN ('completed','failed','cancelled')
                   AND completed_at IS NOT NULL AND completed_at<=?""",
                (cutoff,),
            )
            return cursor.rowcount

    def vision_job(self, job_id: str):
        with self.session() as db:
            row = db.execute("SELECT * FROM vision_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                return None
            return dict(row) | {"image_message_ids": json.loads(row["image_message_ids_json"])}
