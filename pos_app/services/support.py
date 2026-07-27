"""Sanitized local support bundles and signed remote action requests."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import os
import platform
import re
import shutil
import sqlite3
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from .backup import sha256_file


UTC = timezone.utc
ALLOWED_REMOTE_ACTIONS = {"health_report", "support_bundle", "backup", "sync_retry", "update_check", "schedule_update", "controlled_restart"}
ACTION_TO_JOB = {"support_bundle": "support_bundle", "backup": "backup", "sync_retry": "sync_retry", "schedule_update": "update_install", "controlled_restart": "controlled_restart", "update_check": "update_check"}
_SECRET_WORDS = re.compile(r"(?i)(password|passwd|secret|token|private.?key|api.?key|pin_hash|credential)")
_PHONE = re.compile(r"(?<!\d)(?:0\d{8,9}|\+66\d{8,9})(?!\d)")
_SECRET_VALUE = re.compile(r'(?i)("(?:password|passwd|secret|token|private.?key|api.?key)"\s*:\s*)"[^"]*"')


class SupportError(ValueError):
    """Raised when a support artifact or signed request is unsafe."""


def _redact(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_WORDS.search(str(key)) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _PHONE.sub("[REDACTED_PHONE]", value)
    return value


def _read_json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    except (OSError, json.JSONDecodeError):
        return default


def _sanitize_log_line(line: str) -> str:
    try:
        return json.dumps(_redact(json.loads(line)), ensure_ascii=False, sort_keys=True)
    except json.JSONDecodeError:
        return _SECRET_VALUE.sub(r'\1"[REDACTED]"', _PHONE.sub("[REDACTED_PHONE]", line))


def create_support_bundle(paths, runtime_config) -> Path:
    bundle_id = "support-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    staging = paths.staging / f".{bundle_id}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        safe_config = {"store_id": getattr(runtime_config, "store_id", ""), "app_version": getattr(runtime_config, "app_version", "unknown"), "production": getattr(runtime_config, "production", False), "runtime_root": str(paths.root)}
        schema_version = "unknown"
        migration_history = []
        if paths.database.is_file():
            connection = sqlite3.connect(paths.database)
            try:
                row = connection.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
                schema_version = str(row[0]) if row else "unknown"
                if connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone():
                    migration_history = [
                        {"version": row[0], "description": row[1], "checksum": row[2], "applied_at": row[3]}
                        for row in connection.execute("SELECT version,name,checksum,applied_at FROM schema_migrations ORDER BY version DESC LIMIT 100").fetchall()
                    ]
            finally:
                connection.close()
        report = {
            "created_at": datetime.now(UTC).isoformat(), "application_version": safe_config["app_version"],
            "schema_version": schema_version,
            "operating_system": platform.platform(), "python": platform.python_version(),
            "disk_free_bytes": shutil.disk_usage(paths.root).free,
            "health": {"database_file": paths.database.is_file(), "runtime_root": str(paths.root)},
            "configuration": safe_config,
            "migration_history": migration_history,
        }
        (staging / "report.json").write_text(json.dumps(_redact(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log_dir = staging / "logs"
        log_dir.mkdir()
        for source in (paths.logs / "backup.jsonl", paths.logs / "file-sync.jsonl", paths.logs / "update.jsonl", paths.logs / "launcher.log"):
            if not source.is_file():
                continue
            target = log_dir / source.name
            lines = source.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
            target.write_text("\n".join(_sanitize_log_line(line) for line in lines) + "\n", encoding="utf-8")
        manifest_files = []
        for file in sorted(staging.rglob("*")):
            if file.is_file():
                manifest_files.append({"path": file.relative_to(staging).as_posix(), "size": file.stat().st_size, "sha256": sha256_file(file)})
        (staging / "manifest.json").write_text(json.dumps({"status": "complete", "bundle_id": bundle_id, "files": manifest_files}, indent=2) + "\n", encoding="utf-8")
        archive = paths.support / f"{bundle_id}.zip"
        temporary = paths.staging / f".{bundle_id}.zip.part"
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for file in sorted(staging.rglob("*")):
                if file.is_file():
                    package.write(file, file.relative_to(staging).as_posix())
        os.replace(temporary, archive)
        return archive
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _canonical_request(request: Mapping[str, object]) -> bytes:
    return json.dumps({key: value for key, value in request.items() if key != "signature"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_remote_request(request: Mapping[str, object], *, trusted_key: bytes | str | os.PathLike[str], store_id: str, now: datetime | None = None, replay_dir: Path | None = None) -> dict[str, object]:
    required = {"request_id", "store_id", "action", "issued_at", "expires_at", "nonce", "signature"}
    if not required <= request.keys() or str(request["action"]) not in ALLOWED_REMOTE_ACTIONS:
        raise SupportError("Remote maintenance request is invalid or not allow-listed.")
    if str(request["store_id"]) != store_id:
        raise SupportError("Remote maintenance request targets another store.")
    try:
        issued = datetime.fromisoformat(str(request["issued_at"]).replace("Z", "+00:00"))
        expires = datetime.fromisoformat(str(request["expires_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise SupportError("Remote maintenance request timestamps are invalid.") from exc
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if issued.tzinfo is None or expires.tzinfo is None or issued.astimezone(UTC) > current + timedelta(minutes=5) or expires.astimezone(UTC) < current or expires <= issued or expires - issued > timedelta(hours=1):
        raise SupportError("Remote maintenance request has expired or an invalid time window.")
    key = trusted_key if isinstance(trusted_key, bytes) else Path(trusted_key).read_bytes()
    expected = hmac.new(key, _canonical_request(request), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(request["signature"])):
        raise SupportError("Remote maintenance request signature verification failed.")
    if replay_dir is not None:
        replay_dir.mkdir(parents=True, exist_ok=True)
        replay = replay_dir / (hashlib.sha256(str(request["nonce"]).encode()).hexdigest() + ".seen")
        if replay.exists():
            raise SupportError("Remote maintenance request has already been processed.")
        replay.write_text(current.isoformat(), encoding="ascii")
    return dict(request)


__all__ = ["ALLOWED_REMOTE_ACTIONS", "ACTION_TO_JOB", "SupportError", "create_support_bundle", "verify_remote_request"]
