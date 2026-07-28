"""Immutable product identity helpers.

The database continues to use integer primary keys for relationships, while
product UUIDs are the only identifiers accepted at browser and API boundaries.
"""

from __future__ import annotations

from uuid import UUID, uuid4


class ProductIdentityError(ValueError):
    """Raised when an external product UUID is missing or invalid."""


def new_product_uuid() -> str:
    return str(uuid4())


def canonical_product_uuid(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductIdentityError("ไม่พบรหัสประจำสินค้าถาวร")
    try:
        return str(UUID(value.strip()))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProductIdentityError("รหัสประจำสินค้าถาวรไม่ถูกต้อง") from exc


def product_by_uuid(db, value: object, *, active_only: bool = False):
    product_uuid = canonical_product_uuid(value)
    query = "SELECT * FROM products WHERE product_uuid=?"
    if active_only:
        query += " AND is_active=1"
    return db.execute(query, (product_uuid,)).fetchone()
