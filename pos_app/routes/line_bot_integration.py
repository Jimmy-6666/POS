"""Private, signed HTTP boundary for the separately hosted LINE Bot."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, request

from ..database import get_db
from ..services.line_bot_products import (
    LineBotProductError,
    apply_command,
    product_lookup,
)


bp = Blueprint("line_bot_integration", __name__, url_prefix="/_internal/line-bot")


def _secret() -> bytes:
    if not current_app.config.get("POS_LINE_BOT_ENABLED"):
        abort(404)
    configured = str(current_app.config.get("POS_LINE_BOT_SHARED_SECRET") or "")
    if len(configured) < 32:
        # Do not expose an accidentally enabled integration before its secret exists.
        abort(404)
    return configured.encode("utf-8")


def _allowed_source() -> bool:
    allowed = {
        item.strip() for item in str(current_app.config.get("POS_LINE_BOT_ALLOWED_SOURCE_IPS") or "").split(",")
        if item.strip()
    }
    return not allowed or (request.remote_addr or "") in allowed


def _verified_raw_body() -> tuple[bytes, bytes]:
    secret = _secret()
    if not _allowed_source():
        abort(403)
    timestamp = request.headers.get("X-POS-LineBot-Timestamp", "")
    signature = request.headers.get("X-POS-LineBot-Signature", "")
    try:
        age = abs(time.time() - int(timestamp))
    except (TypeError, ValueError):
        abort(401)
    if age > int(current_app.config["POS_LINE_BOT_MAX_CLOCK_SKEW_SECONDS"]):
        abort(401)
    raw = request.get_data(cache=True)
    expected = hmac.new(secret, timestamp.encode("ascii") + b"." + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        abort(401)
    return raw, secret


def _json_body(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise LineBotProductError("Body must be a JSON object.")
    if not isinstance(payload, dict):
        raise LineBotProductError("Body must be a JSON object.")
    return payload


def _source_hashes(command: dict[str, Any], secret: bytes) -> dict[str, str]:
    source = command.get("source")
    if not isinstance(source, dict):
        raise LineBotProductError("source is required.")
    group_id = str(source.get("group_id") or "").strip()
    user_id = str(source.get("line_user_id") or "").strip()
    if not group_id or not user_id or len(group_id) > 256 or len(user_id) > 256:
        raise LineBotProductError("source is invalid.")

    def digest(value: str) -> str:
        return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()[:24]

    return {"group_hash": digest("group:" + group_id), "user_hash": digest("user:" + user_id)}


@bp.post("/lookup")
def lookup():
    raw, _secret_bytes = _verified_raw_body()
    try:
        payload = _json_body(raw)
        return jsonify(product_lookup(get_db(), payload.get("barcode")))
    except LineBotProductError as exc:
        return jsonify(ok=False, code=exc.code, message=str(exc)), exc.status_code


@bp.post("/commands")
def command():
    raw, secret = _verified_raw_body()
    try:
        command_payload = _json_body(raw)
        source = _source_hashes(command_payload, secret)
        result, status = apply_command(
            get_db(),
            command_payload,
            source=source,
        )
        return jsonify(result), status
    except LineBotProductError as exc:
        return jsonify(ok=False, code=exc.code, message=str(exc)), exc.status_code
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return jsonify(ok=False, code="invalid_command", message=str(exc) or "Invalid command."), 400
