"""Admin TOTP, recovery-code, and pending-login helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

import pyotp
import qrcode
import qrcode.image.svg
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash


class TwoFactorError(ValueError):
    """Raised for unusable two-factor state without exposing secrets."""


def _cipher() -> Fernet:
    key_material = hashlib.sha256(
        current_app.config["SECRET_KEY"].encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def encrypt_secret(secret: str) -> str:
    return _cipher().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(value: str | None) -> str:
    if not value:
        raise TwoFactorError("ไม่พบการตั้งค่าแอปยืนยันตัวตน")
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeError) as exc:
        raise TwoFactorError("ไม่สามารถอ่านการตั้งค่าแอปยืนยันตัวตนได้") from exc


def new_totp_secret() -> str:
    return pyotp.random_base32()


def issuer_name(db) -> str:
    row = db.execute("SELECT value FROM settings WHERE key='store_name'").fetchone()
    return (row["value"] if row and row["value"] else "Thai Minishop POS")[:80]


def provisioning_uri(secret: str, staff_name: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=staff_name, issuer_name=issuer)


def qr_svg_data_uri(uri: str) -> str:
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    svg = image.to_string(encoding="utf-8")
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")


def normalized_code(value: object) -> str:
    return "".join(str(value or "").strip().upper().split())


def verified_totp_counter(secret: str, value: object, *, valid_window: int = 1) -> int | None:
    code = normalized_code(value)
    if len(code) != 6 or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=valid_window):
        return None
    current = int(time.time() // totp.interval)
    for counter in range(current - valid_window, current + valid_window + 1):
        if hmac.compare_digest(totp.at(counter * totp.interval), code):
            return counter
    return None


def new_recovery_codes(count: int = 10) -> list[str]:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return [
        "".join(secrets.choice(alphabet) for _ in range(4))
        + "-"
        + "".join(secrets.choice(alphabet) for _ in range(4))
        for _ in range(count)
    ]


def store_recovery_codes(db, staff_id: int, codes: list[str], created_at: str) -> None:
    db.execute("DELETE FROM staff_two_factor_recovery_codes WHERE staff_id=?", (staff_id,))
    db.executemany(
        """INSERT INTO staff_two_factor_recovery_codes(staff_id,code_hash,created_at)
           VALUES(?,?,?)""",
        ((staff_id, generate_password_hash(code), created_at) for code in codes),
    )


def consume_recovery_code(db, staff_id: int, value: object, used_at: str) -> bool:
    code = normalized_code(value)
    if len(code) != 9 or code[4] != "-":
        return False
    rows = db.execute(
        """SELECT id,code_hash FROM staff_two_factor_recovery_codes
           WHERE staff_id=? AND used_at IS NULL""",
        (staff_id,),
    ).fetchall()
    for row in rows:
        if check_password_hash(row["code_hash"], code):
            db.execute(
                "UPDATE staff_two_factor_recovery_codes SET used_at=? WHERE id=? AND used_at IS NULL",
                (used_at, row["id"]),
            )
            return True
    return False
