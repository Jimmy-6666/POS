"""Privacy-minimised diagnostic bundles for a staff-controlled support flow."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..runtime_paths import validate_runtime


SUPPORT_FORMAT_VERSION = 1
_MAX_LOG_BYTES = 256 * 1024
_SENSITIVE = re.compile(r"(?i)(authorization|bearer|token|secret|password|pin|line_user_id|phone)\s*([:=])\s*([^\s,;\"}]+)")
_PHONE = re.compile(r"(?<!\d)(?:0\d[\d -]{7,13}\d)(?!\d)")
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_-]{28,}\b")


def _redact(value: str) -> str:
    value = _SENSITIVE.sub(lambda match: f"{match.group(1)}{match.group(2)} [redacted]", value)
    value = _PHONE.sub("[phone redacted]", value)
    return _LONG_TOKEN.sub("[token redacted]", value)


def _tail_text(path: Path) -> str:
    with path.open("rb") as source:
        source.seek(0, 2)
        source.seek(max(0, source.tell() - _MAX_LOG_BYTES))
        return _redact(source.read().decode("utf-8", errors="replace"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_support_bundle(paths, runtime_config) -> Path:
    """Create a local ZIP that excludes databases, uploads, config, and secrets."""

    paths.support.mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc)
    name = "support-" + created.strftime("%Y%m%dT%H%M%SZ") + ".zip"
    destination = paths.support / name
    if destination.exists():
        destination = paths.support / (destination.stem + "-" + hashlib.sha256(created.isoformat().encode()).hexdigest()[:8] + ".zip")
    with tempfile.TemporaryDirectory(prefix="pos-support-", dir=paths.staging) as temporary:
        root = Path(temporary)
        _write_json(root / "runtime-validation.json", validate_runtime(runtime_config, database_required=True))
        _write_json(root / "bundle-manifest.json", {
            "format_version": SUPPORT_FORMAT_VERSION,
            "created_at_utc": created.isoformat().replace("+00:00", "Z"),
            "application_version": getattr(runtime_config, "app_version", "unknown"),
            "store_id": getattr(runtime_config, "store_id", "") or "unassigned",
            "included": ["runtime validation", "redacted recent application logs", "backup status if available"],
            "excluded": ["database", "uploads", "production config", "secret key", "browser profiles"],
        })
        backup_status = paths.support / "backup-status.json"
        if backup_status.is_file():
            try:
                _write_json(root / "backup-status.json", json.loads(backup_status.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
        log_sources = [paths.launcher_log]
        if paths.logs.is_dir():
            log_sources.extend(sorted(path for path in paths.logs.iterdir() if path.is_file() and path.suffix.lower() in {".log", ".jsonl"}))
        for source in log_sources:
            if source.is_file():
                (root / "logs").mkdir(exist_ok=True)
                (root / "logs" / source.name).write_text(_tail_text(source), encoding="utf-8")
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    package.write(path, path.relative_to(root).as_posix())
    return destination


def list_support_bundles(support: Path) -> list[Path]:
    if not support.is_dir():
        return []
    return sorted(support.glob("support-*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
