"""Small dependency-free migration history runner.

The existing startup migrations remain in database.initialize_database.
This module records their compatibility boundary and provides the deterministic
runner for future additive migrations.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from uuid import uuid4
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


def _add_product_uuid(db: sqlite3.Connection) -> None:
    """Backfill public product identity without disturbing numeric foreign keys."""

    columns = {row[1] for row in db.execute("PRAGMA table_info(products)")}
    if "product_uuid" not in columns:
        db.execute("ALTER TABLE products ADD COLUMN product_uuid TEXT")
    rows = db.execute("SELECT id,product_uuid FROM products").fetchall()
    for row in rows:
        if not row["product_uuid"]:
            db.execute("UPDATE products SET product_uuid=? WHERE id=?", (str(uuid4()), row["id"]))
    duplicates = db.execute(
        "SELECT product_uuid FROM products GROUP BY product_uuid HAVING COUNT(*) > 1"
    ).fetchall()
    if duplicates:
        raise MigrationError("Duplicate product UUIDs prevent migration.")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_products_product_uuid ON products(product_uuid)")
    db.execute(
        """CREATE TRIGGER IF NOT EXISTS products_product_uuid_required_insert
           BEFORE INSERT ON products
           WHEN NEW.product_uuid IS NULL OR TRIM(NEW.product_uuid) = ''
           BEGIN SELECT RAISE(ABORT, 'product_uuid is required'); END"""
    )
    db.execute(
        """CREATE TRIGGER IF NOT EXISTS products_product_uuid_required_update
           BEFORE UPDATE OF product_uuid ON products
           WHEN NEW.product_uuid IS NULL OR TRIM(NEW.product_uuid) = ''
           BEGIN SELECT RAISE(ABORT, 'product_uuid is required'); END"""
    )
    db.execute(
        """CREATE TRIGGER IF NOT EXISTS products_product_uuid_immutable
           BEFORE UPDATE OF product_uuid ON products
           WHEN NEW.product_uuid <> OLD.product_uuid
           BEGIN SELECT RAISE(ABORT, 'product_uuid is immutable'); END"""
    )

    product_uuids = {
        row["id"]: row["product_uuid"]
        for row in db.execute("SELECT id,product_uuid FROM products")
    }
    for row in db.execute("SELECT id,cart_json FROM held_bills").fetchall():
        try:
            cart = json.loads(row["cart_json"])
            items = cart.get("items", [])
            changed = False
            for item in items:
                if not isinstance(item, dict) or item.get("product_uuid"):
                    continue
                legacy_id = item.get("product_id")
                if isinstance(legacy_id, int) and legacy_id in product_uuids:
                    item["product_uuid"] = product_uuids[legacy_id]
                    item.pop("product_id", None)
                    changed = True
            if changed:
                db.execute(
                    "UPDATE held_bills SET cart_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (json.dumps(cart, ensure_ascii=False), row["id"]),
                )
        except (TypeError, ValueError, json.JSONDecodeError):
            # Historical malformed held bills remain intact and will be rejected on use.
            continue


def _add_admin_two_factor(db: sqlite3.Connection) -> None:
    """Add isolated encrypted-admin-TOTP state without changing staff sessions."""

    db.executescript(
        """CREATE TABLE IF NOT EXISTS staff_two_factor (
            staff_id INTEGER PRIMARY KEY REFERENCES staff(id) ON DELETE CASCADE,
            secret_encrypted TEXT,
            pending_secret_encrypted TEXT,
            is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0,1)),
            last_totp_counter INTEGER,
            enabled_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK ((is_enabled=0) OR secret_encrypted IS NOT NULL)
        );
        CREATE TABLE IF NOT EXISTS staff_two_factor_recovery_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            used_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_staff_two_factor_recovery_codes_staff
        ON staff_two_factor_recovery_codes(staff_id,used_at);
        CREATE TABLE IF NOT EXISTS staff_two_factor_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            csrf_token TEXT NOT NULL,
            next_url TEXT,
            ip_address TEXT,
            user_agent TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_staff_two_factor_challenges_expiry
        ON staff_two_factor_challenges(expires_at);"""
    )


def _add_reconciliation_void_total(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(reconciliations)")}
    if "void_total_satang" not in columns:
        db.execute(
            "ALTER TABLE reconciliations ADD COLUMN void_total_satang INTEGER NOT NULL DEFAULT 0"
        )


def _add_staff_session_two_factor_assurance(db: sqlite3.Connection) -> None:
    """Record which sessions were created only after a second-factor check."""

    columns = {row[1] for row in db.execute("PRAGMA table_info(staff_sessions)")}
    if "two_factor_verified_at" not in columns:
        db.execute("ALTER TABLE staff_sessions ADD COLUMN two_factor_verified_at TEXT")


def _add_sale_item_manual_price_reference(db: sqlite3.Connection) -> None:
    """Persist one traceable audit-backed reference for every manual-price line."""

    columns = {row[1] for row in db.execute("PRAGMA table_info(sale_items)")}
    if "manual_price_reference" not in columns:
        db.execute("ALTER TABLE sale_items ADD COLUMN manual_price_reference TEXT")
    db.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_sale_items_manual_price_reference
           ON sale_items(manual_price_reference)
           WHERE manual_price_reference IS NOT NULL"""
    )


def _add_pos_button_layout(db: sqlite3.Connection) -> None:
    """Add independently configured text-only POS button menus and products."""

    db.executescript(
        """CREATE TABLE IF NOT EXISTS pos_button_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_th TEXT NOT NULL CHECK(length(trim(name_th)) BETWEEN 1 AND 80),
            position INTEGER NOT NULL UNIQUE CHECK(position >= 1),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            created_by INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            updated_by INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pos_button_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL REFERENCES pos_button_groups(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            position INTEGER NOT NULL CHECK(position >= 1),
            created_by INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            updated_by INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, position),
            UNIQUE(group_id, product_id)
        );
        CREATE INDEX IF NOT EXISTS idx_pos_button_groups_active_position
        ON pos_button_groups(is_active,position);
        CREATE INDEX IF NOT EXISTS idx_pos_button_items_group_position
        ON pos_button_items(group_id,position);
        CREATE INDEX IF NOT EXISTS idx_pos_button_items_product
        ON pos_button_items(product_id);"""
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(20, "enable configured negative stock", _enable_configured_negative_stock),
    Migration(21, "add LINE customer identity", _add_line_customer_identity),
    Migration(22, "add customer lifecycle fields", _add_customer_lifecycle_fields),
    Migration(23, "add immutable product UUIDs", _add_product_uuid),
    Migration(24, "add admin TOTP two-factor authentication", _add_admin_two_factor),
    Migration(25, "add reconciliation void total", _add_reconciliation_void_total),
    Migration(26, "record second-factor verified staff sessions", _add_staff_session_two_factor_assurance),
    Migration(27, "add sale-item manual-price references", _add_sale_item_manual_price_reference),
    Migration(28, "add configurable POS button layout", _add_pos_button_layout),
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
