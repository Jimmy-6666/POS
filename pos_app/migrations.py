"""Small dependency-free migration history runner.

The existing startup migrations remain in database.initialize_database.
This module records their compatibility boundary and provides the deterministic
runner for future additive migrations.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable


class MigrationError(RuntimeError):
    """Raised when a migration cannot be safely applied."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]
    checksum: str | None = None

    def calculated_checksum(self) -> str:
        if self.checksum:
            return self.checksum
        payload = f"{self.version}:{self.name}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def _enable_configured_negative_stock(db: sqlite3.Connection) -> None:
    # Earlier releases displayed this setting but did not use it in sales.
    # Preserve the established behaviour while making the setting effective.
    db.execute(
        "UPDATE settings SET value='1',updated_at=CURRENT_TIMESTAMP WHERE key='allow_negative_stock'"
    )


def _add_line_customer_identity(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(customers)")}
    additions = (
        ("line_user_id", "TEXT"),
        ("line_display_name", "TEXT"),
        ("line_picture_url", "TEXT"),
        ("line_created_at", "TEXT"),
        ("line_last_login_at", "TEXT"),
        ("default_delivery_location_id", "INTEGER REFERENCES delivery_locations(id) ON DELETE SET NULL"),
        ("default_room_reference", "TEXT"),
        ("profile_completed", "INTEGER NOT NULL DEFAULT 0 CHECK(profile_completed IN (0,1))"),
    )
    for name, definition in additions:
        if name not in columns:
            db.execute(f"ALTER TABLE customers ADD COLUMN {name} {definition}")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_line_user_id "
        "ON customers(line_user_id) WHERE line_user_id IS NOT NULL"
    )


def _add_customer_lifecycle_fields(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(customers)")}
    additions = (
        ("registered_name", "TEXT"),
        ("is_deleted", "INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1))"),
        ("deleted_at", "TEXT"),
        ("deleted_by_staff_id", "INTEGER REFERENCES staff(id) ON DELETE SET NULL"),
    )
    for name, definition in additions:
        if name not in columns:
            db.execute(f"ALTER TABLE customers ADD COLUMN {name} {definition}")


MIGRATIONS: tuple[Migration, ...] = (
    Migration(20, "enable configured negative stock", _enable_configured_negative_stock),
    Migration(21, "add LINE customer identity", _add_line_customer_identity),
    Migration(22, "add customer lifecycle fields", _add_customer_lifecycle_fields),
)


def ensure_history_table(db: sqlite3.Connection) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT,
            application_version TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 1 CHECK(success IN (0,1))
        )"""
    )


def bootstrap_legacy_history(
    db: sqlite3.Connection,
    legacy_version: int,
    application_version: str,
) -> None:
    ensure_history_table(db)
    if db.execute("SELECT 1 FROM schema_migrations LIMIT 1").fetchone():
        return
    checksum = hashlib.sha256(f"legacy-ad-hoc:{legacy_version}".encode("utf-8")).hexdigest()
    db.execute(
        """INSERT INTO schema_migrations
           (version,name,checksum,application_version,applied_at,success)
           VALUES(?,?,?,?,?,1)""",
        (
            legacy_version,
            "legacy-ad-hoc-migrations",
            checksum,
            application_version,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )


def apply_migrations(
    db: sqlite3.Connection,
    migrations: Iterable[Migration],
    application_version: str,
) -> None:
    ensure_history_table(db)
    ordered = sorted(migrations, key=lambda migration: migration.version)
    previous_version = -1
    for migration in ordered:
        if migration.version <= previous_version:
            raise MigrationError("Migration versions must be strictly increasing.")
        previous_version = migration.version
        existing = db.execute(
            "SELECT checksum,success FROM schema_migrations WHERE version=?",
            (migration.version,),
        ).fetchone()
        checksum = migration.calculated_checksum()
        if existing:
            existing_checksum = existing["checksum"] if hasattr(existing, "keys") else existing[0]
            existing_success = existing["success"] if hasattr(existing, "keys") else existing[1]
            if not existing_success:
                raise MigrationError(f"Migration {migration.version} previously failed.")
            if existing_checksum != checksum:
                raise MigrationError(f"Migration {migration.version} checksum changed.")
            continue
        try:
            db.execute("BEGIN IMMEDIATE")
            migration.apply(db)
            db.execute(
                """INSERT INTO schema_migrations
                   (version,name,checksum,application_version,applied_at,success)
                   VALUES(?,?,?,?,?,1)""",
                (
                    migration.version,
                    migration.name,
                    checksum,
                    application_version,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            try:
                db.execute(
                    """INSERT OR REPLACE INTO schema_migrations
                       (version,name,checksum,application_version,applied_at,success)
                       VALUES(?,?,?,?,?,0)""",
                    (
                        migration.version,
                        migration.name,
                        checksum,
                        application_version,
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        ),
                )
                db.commit()
            except sqlite3.DatabaseError:
                db.rollback()
            raise MigrationError(f"Migration {migration.version} failed.") from exc
