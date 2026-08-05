"""Atomic product commands received from the separately deployed LINE Bot.

The browser product routes remain staff-session protected.  This module is the
small, signed-service boundary used only by ``routes.line_bot_integration``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from ..product_identity import new_product_uuid


class LineBotProductError(ValueError):
    """Expected command error that is safe to return to the bot."""

    def __init__(self, message: str, *, status_code: int = 400, code: str = "invalid_command"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class LineBotConflict(LineBotProductError):
    def __init__(self, message: str = "Product changed after the bot read it."):
        super().__init__(message, status_code=409, code="product_conflict")


_WHOLE_BAHT_RE = re.compile(r"^(?:0|[1-9][0-9]{0,8})$")
_DECIMAL_BAHT_RE = re.compile(r"^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?$")
_SATANG_RE = re.compile(r"^(?:0|[1-9][0-9]{0,10})$")
_BARCODE_RE = re.compile(r"^[^\x00-\x1f]{1,128}$")
_COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_PLACEHOLDER_PREFIX = "สินค้าไม่ทราบชื่อ ("


def is_unknown_product_name(name: object) -> bool:
    return str(name or "").strip().startswith(_PLACEHOLDER_PREFIX)


def _whole_baht_to_satang(value: object, *, field: str, positive: bool = False) -> int:
    text = str(value if value is not None else "").strip()
    if not _WHOLE_BAHT_RE.fullmatch(text):
        raise LineBotProductError(f"{field} must be a whole-baht amount.")
    amount = int(text)
    if positive and amount <= 0:
        raise LineBotProductError(f"{field} must be greater than zero.")
    return amount * 100


def _decimal_baht_to_satang(value: object, *, field: str) -> int:
    text = str(value if value is not None else "").strip()
    if not _DECIMAL_BAHT_RE.fullmatch(text):
        raise LineBotProductError(f"{field} must be a baht amount with at most two satang digits.")
    whole, separator, fractional = text.partition(".")
    return int(whole) * 100 + (int(fractional.ljust(2, "0")) if separator else 0)


def _cost_satang(command: dict[str, Any]) -> int:
    """Use explicit satang for new bot clients, retaining prior baht payload compatibility."""

    if "cost_satang" in command:
        value = command.get("cost_satang")
        if isinstance(value, bool) or not _SATANG_RE.fullmatch(str(value if value is not None else "").strip()):
            raise LineBotProductError("cost_satang must be a non-negative integer.")
        return int(value)
    return _decimal_baht_to_satang(command.get("cost_baht"), field="cost_baht")


def _format_satang(satang: int) -> str:
    whole, fractional = divmod(int(satang), 100)
    return f"{whole}.{fractional:02d}"


def _command_text(command: dict[str, Any]) -> str:
    return json.dumps(command, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def command_payload_hash(command: dict[str, Any]) -> str:
    """Preserve the original no-image hash shape for existing retry records."""

    digest = hashlib.sha256(_command_text(command).encode("utf-8"))
    digest.update(b"\n")
    digest.update(hashlib.sha256(b"").digest())
    return digest.hexdigest()


def _safe_command_id(value: object) -> str:
    command_id = str(value or "").strip()
    if not _COMMAND_ID_RE.fullmatch(command_id):
        raise LineBotProductError("command_id is invalid.")
    return command_id


def _summary(product) -> dict[str, Any]:
    return {
        "product_uuid": product["product_uuid"],
        "barcode": product["barcode"],
        "name_th": product["name_th"],
        "cost_baht": _format_satang(product["cost_satang"]),
        "cost_satang": product["cost_satang"],
        "sale_baht": product["price_satang"] // 100,
        "has_image": bool(product["image_path"]),
        "is_placeholder": is_unknown_product_name(product["name_th"]),
        "revision": product_revision(product),
    }


def product_revision(product) -> str:
    """Fingerprint all master fields the bot must not overwrite blindly."""

    payload = {
        key: product[key]
        for key in (
            "product_uuid", "barcode", "name_th", "category_id", "unit_id",
            "cost_satang", "price_satang", "image_path", "is_active",
            "requires_manual_price", "updated_at",
        )
    }
    return hashlib.sha256(_command_text(payload).encode("utf-8")).hexdigest()


def product_lookup(db, barcode: object) -> dict[str, Any]:
    code = str(barcode or "").strip()
    if not _BARCODE_RE.fullmatch(code):
        raise LineBotProductError("barcode is invalid.")
    product = db.execute("SELECT * FROM products WHERE barcode=?", (code,)).fetchone()
    return {"barcode": code, "product": _summary(product) if product else None}


def _expected_product(db, command: dict[str, Any], barcode: str):
    product = db.execute("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()
    if not product:
        raise LineBotConflict("Product no longer exists.")
    if str(command.get("product_uuid") or "") != product["product_uuid"]:
        raise LineBotConflict()
    if str(command.get("expected_revision") or "") != product_revision(product):
        raise LineBotConflict()
    return product


def _default_reference_ids(db) -> tuple[int, int]:
    """Return the user-approved defaults, repairing a legacy missing row safely."""

    db.execute(
        "INSERT OR IGNORE INTO categories(name_th,is_active,sort_order) VALUES ('อื่น ๆ',1,9999)"
    )
    db.execute(
        "INSERT OR IGNORE INTO units(name_th,is_active,sort_order) VALUES ('ชิ้น',1,9999)"
    )
    category = db.execute(
        "SELECT id FROM categories WHERE name_th='อื่น ๆ' AND is_active=1"
    ).fetchone()
    unit = db.execute(
        "SELECT id FROM units WHERE name_th='ชิ้น' AND is_active=1"
    ).fetchone()
    if not category or not unit:
        raise LineBotProductError("The default category or unit is inactive.")
    return category["id"], unit["id"]


def _validated_name(command: dict[str, Any]) -> str:
    name = str(command.get("name_th") or "").strip()
    if not name or len(name) > 160:
        raise LineBotProductError("name_th is required and must be at most 160 characters.")
    if is_unknown_product_name(name):
        raise LineBotProductError("A placeholder product name cannot be saved.")
    return name


def _validated_prices(command: dict[str, Any]) -> tuple[int, int]:
    cost = _cost_satang(command)
    sale = _whole_baht_to_satang(command.get("sale_baht"), field="sale_baht", positive=True)
    if cost and sale <= cost:
        raise LineBotProductError("sale_baht must be greater than cost_baht when cost is set.")
    return cost, sale


def _audit(db, *, action: str, product, old: dict[str, Any] | None,
           new: dict[str, Any], source: dict[str, str]) -> None:
    db.execute(
        """INSERT INTO audit_logs
           (staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
           VALUES(NULL,?,?,?,?,?,?,?)""",
        (
            action,
            "product",
            product["product_uuid"],
            json.dumps(old, ensure_ascii=False) if old is not None else None,
            json.dumps({**new, "line_bot_source": source}, ensure_ascii=False),
            "line-bot-integration",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )


def _stored_result(row) -> dict[str, Any]:
    result = json.loads(row["result_json"])
    result["replayed"] = True
    return result


def _record_command(db, *, command_id: str, payload_hash: str, operation: str,
                    status: str, result: dict[str, Any], source: dict[str, str]) -> None:
    db.execute(
        """INSERT INTO line_bot_commands
           (command_id,payload_sha256,operation,status,result_json,source_group_hash,
            source_user_hash,applied_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            command_id,
            payload_hash,
            operation,
            status,
            json.dumps(result, ensure_ascii=False, sort_keys=True),
            source.get("group_hash"),
            source.get("user_hash"),
            datetime.now(timezone.utc).isoformat(timespec="seconds") if status == "applied" else None,
        ),
    )


def apply_command(db, command: dict[str, Any], *, source: dict[str, str]) -> tuple[dict[str, Any], int]:
    """Apply one idempotent bot command.  Caller owns no transaction."""

    if not isinstance(command, dict):
        raise LineBotProductError("command must be an object.")
    command_id = _safe_command_id(command.get("command_id"))
    operation = str(command.get("operation") or "")
    if operation not in {"update_prices", "create_or_complete"}:
        raise LineBotProductError("operation is invalid.")
    payload_hash = command_payload_hash(command)
    replay = db.execute(
        "SELECT payload_sha256,status,result_json FROM line_bot_commands WHERE command_id=?",
        (command_id,),
    ).fetchone()
    if replay:
        if replay["payload_sha256"] != payload_hash:
            raise LineBotProductError("command_id was reused with different content.", status_code=409, code="idempotency_mismatch")
        return _stored_result(replay), 200 if replay["status"] == "applied" else 409

    barcode = str(command.get("barcode") or "").strip()
    if not _BARCODE_RE.fullmatch(barcode):
        raise LineBotProductError("barcode is invalid.")
    try:
        db.execute("BEGIN IMMEDIATE")
        if operation == "update_prices":
            product = _expected_product(db, command, barcode)
            cost, sale = _validated_prices(command)
            old = {"cost_baht": _format_satang(product["cost_satang"]), "sale_baht": product["price_satang"] // 100}
            db.execute(
                "UPDATE products SET cost_satang=?,price_satang=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (cost, sale, product["id"]),
            )
            product = db.execute("SELECT * FROM products WHERE id=?", (product["id"],)).fetchone()
            _audit(db, action="line_bot_change_prices", product=product, old=old,
                   new={"cost_baht": _format_satang(cost), "sale_baht": sale // 100}, source=source)
        else:
            name = _validated_name(command)
            cost, sale = _validated_prices(command)
            product = db.execute("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()
            category_id, unit_id = _default_reference_ids(db)
            if product:
                if not is_unknown_product_name(product["name_th"]):
                    raise LineBotConflict("This barcode is already a named product.")
                if str(command.get("product_uuid") or "") != product["product_uuid"]:
                    raise LineBotConflict()
                if str(command.get("expected_revision") or "") != product_revision(product):
                    raise LineBotConflict()
                old = {"name_th": product["name_th"], "cost_baht": _format_satang(product["cost_satang"]),
                       "sale_baht": product["price_satang"] // 100, "has_image": bool(product["image_path"])}
                db.execute(
                    """UPDATE products
                       SET name_th=?,category_id=?,unit_id=?,cost_satang=?,price_satang=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (name, category_id, unit_id, cost, sale, product["id"]),
                )
                product = db.execute("SELECT * FROM products WHERE id=?", (product["id"],)).fetchone()
                _audit(db, action="line_bot_complete_placeholder", product=product, old=old,
                       new={"name_th": name, "cost_baht": _format_satang(cost), "sale_baht": sale // 100,
                            "has_image": bool(product["image_path"])}, source=source)
            else:
                if command.get("product_uuid") or command.get("expected_revision"):
                    raise LineBotConflict("Barcode state changed; look it up again.")
                cursor = db.execute(
                    """INSERT INTO products
                       (product_uuid,barcode,name_th,category_id,unit_id,cost_satang,price_satang,
                        stock_quantity,minimum_stock,image_path,is_active,is_online_available)
                       VALUES(?,?,?,?,?,?,?,0,0,?,1,0)""",
                    (new_product_uuid(), barcode, name, category_id, unit_id, cost, sale, None),
                )
                product = db.execute("SELECT * FROM products WHERE id=?", (cursor.lastrowid,)).fetchone()
                _audit(db, action="line_bot_create_product", product=product, old=None,
                       new={"name_th": name, "cost_baht": _format_satang(cost), "sale_baht": sale // 100,
                            "has_image": False, "category": "อื่น ๆ", "unit": "ชิ้น"}, source=source)
        result = {"ok": True, "status": "applied", "product": _summary(product)}
        _record_command(db, command_id=command_id, payload_hash=payload_hash, operation=operation,
                        status="applied", result=result, source=source)
        db.commit()
        return result, 200
    except LineBotProductError as exc:
        db.rollback()
        result = {"ok": False, "status": "conflict" if exc.status_code == 409 else "rejected",
                  "code": exc.code, "message": str(exc)}
        db.execute("BEGIN IMMEDIATE")
        _record_command(db, command_id=command_id, payload_hash=payload_hash, operation=operation,
                        status=result["status"], result=result, source=source)
        db.commit()
        return result, exc.status_code
    except Exception:
        db.rollback()
        raise
