"""Incremental, allow-listed runtime file inventory for outbound sync."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .backup import BackupError, exclusive_lock, sha256_file


class FileSyncError(BackupError):
    """Raised when an incremental file sync cannot be safely completed."""


UTC = timezone.utc
SKIP_NAMES = {".git", ".venv", "__pycache__", "runtime", "uat_runtime", "backups", "logs", "staging"}
SKIP_SUFFIXES = {".tmp", ".part", ".crdownload"}


@dataclass(frozen=True)
class FileSyncResult:
    scanned: int
    uploaded: int
    unchanged: int
    pending_deletions: int
    quarantined: int
    errors: tuple[str, ...]
    backup_id: str | None


def _inventory_path(paths) -> Path:
    return paths.configuration / "file-sync-inventory.json"


def _log_path(paths) -> Path:
    return paths.logs / "file-sync.jsonl"


def _load_inventory(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("files", {}) if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise FileSyncError(f"File sync inventory is invalid: {path}") from exc


def _save_inventory(path: Path, files: dict[str, dict[str, object]], backup_id: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    data = {"format_version": 1, "updated_at": datetime.now(UTC).isoformat(), "backup_id": backup_id, "files": files}
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _audit(paths, event: dict[str, object]) -> None:
    paths.logs.mkdir(parents=True, exist_ok=True)
    with _log_path(paths).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"created_at": datetime.now(UTC).isoformat(), **event}, ensure_ascii=False) + "\n")


def _allowed_roots(paths, configured: str | None) -> tuple[Path, ...]:
    values = [item.strip().replace("\\", "/") for item in (configured or "uploads/products").split(",") if item.strip()]
    roots: list[Path] = []
    for value in values:
        candidate = paths.resolve_relative(value)
        if candidate == paths.data or candidate == paths.backups or candidate == paths.logs:
            raise FileSyncError(f"Sync path is not allow-listed: {value}")
        roots.append(candidate)
    return tuple(roots)


def _is_allowed_file(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if not path.is_file() or path.name.startswith(".") or path.suffix.lower() in SKIP_SUFFIXES:
        return False
    if any(part in SKIP_NAMES or part.startswith(".") for part in relative.parts):
        return False
    return True


def build_inventory(paths, configured_paths: str | None = None) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    for root in _allowed_roots(paths, configured_paths):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not _is_allowed_file(path, root):
                continue
            relative = path.relative_to(paths.root).as_posix()
            inventory[relative] = {"path": relative, "size": path.stat().st_size, "sha256": sha256_file(path), "remote_path": f"file-snapshots/{relative}"}
    return inventory


def sync_files(paths, transport, *, configured_paths: str | None = None, deletion_grace_days: int = 30, backup_id: str | None = None, now: datetime | None = None, retries: int = 3) -> FileSyncResult:
    """Upload changed allow-listed files and quarantine deletions after a grace period."""

    paths.create_directories()
    current = build_inventory(paths, configured_paths)
    inventory_file = _inventory_path(paths)
    previous = _load_inventory(inventory_file)
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    errors: list[str] = []
    uploaded = unchanged = quarantined = 0
    with exclusive_lock(paths.backups / ".file-sync.lock"):
        for relative, entry in current.items():
            prior = previous.get(relative)
            if prior and prior.get("sha256") == entry["sha256"] and not prior.get("missing_since"):
                unchanged += 1
                continue
            try:
                uploader = getattr(transport, "upload_with_retry", None)
                if uploader:
                    uploader(paths.root / relative, str(entry["remote_path"]), retries=retries)
                else:
                    transport.upload_file(paths.root / relative, str(entry["remote_path"]))
                entry["uploaded_at"] = current_time.isoformat()
                entry["backup_id"] = backup_id
                uploaded += 1
            except Exception as exc:  # one failed file must not block other files or sales
                errors.append(f"{relative}: {exc}")
                if prior:
                    entry.update({key: value for key, value in prior.items() if key not in {"path", "size", "sha256", "remote_path"}})
        merged = dict(current)
        for relative, prior in previous.items():
            if relative in current:
                continue
            missing_since = prior.get("missing_since") or current_time.isoformat()
            try:
                missing_at = datetime.fromisoformat(str(missing_since)).astimezone(UTC)
            except ValueError:
                missing_at = current_time
            age = current_time - missing_at
            tombstone = dict(prior)
            tombstone["missing_since"] = missing_since
            tombstone["status"] = "missing_local"
            if age >= timedelta(days=max(1, deletion_grace_days)) and not prior.get("quarantined_at"):
                quarantine_path = f"quarantine/{current_time.strftime('%Y%m%dT%H%M%SZ')}/{relative}"
                try:
                    quarantiner = getattr(transport, "quarantine_with_retry", None)
                    if quarantiner:
                        quarantiner(str(prior.get("remote_path", f"file-snapshots/{relative}")), quarantine_path, retries=retries)
                    else:
                        transport.quarantine_file(str(prior.get("remote_path", f"file-snapshots/{relative}")), quarantine_path)
                    tombstone["quarantined_at"] = current_time.isoformat()
                    tombstone["status"] = "quarantined"
                    quarantined += 1
                except Exception as exc:
                    errors.append(f"{relative}: {exc}")
            else:
                tombstone["status"] = "pending_deletion"
            merged[relative] = tombstone
        _save_inventory(inventory_file, merged, backup_id)
        _audit(paths, {"action": "sync", "scanned": len(current), "uploaded": uploaded, "quarantined": quarantined, "errors": len(errors), "backup_id": backup_id})
    return FileSyncResult(len(current), uploaded, unchanged, sum(1 for item in merged.values() if item.get("status") == "pending_deletion"), quarantined, tuple(errors), backup_id)
