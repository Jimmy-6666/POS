"""Verified, offline-safe local backup and recovery helpers.

The backup service deliberately does not depend on Flask's request lifecycle.
It snapshots SQLite through the online backup API, copies mutable runtime files
into a staging directory, verifies the result, and only then publishes a ZIP.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Iterator, Mapping


class BackupError(RuntimeError):
    """Raised when a backup cannot be safely completed or verified."""


class BackupBusyError(BackupError):
    """Raised when another backup owns the local backup lock."""


UTC = timezone.utc
BANGKOK = timezone(timedelta(hours=7))
BACKUP_FORMAT_VERSION = 1


@dataclass(frozen=True)
class BackupArtifact:
    path: Path
    backup_id: str
    manifest: dict[str, object]
    archive_sha256: str


def _now_utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current.astimezone(UTC)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_zip_name(name: str) -> str:
    pure = PurePosixPath(name)
    if not name or pure.is_absolute() or ".." in pure.parts or "\\" in name:
        raise BackupError(f"Unsafe archive path: {name!r}")
    return pure.as_posix()


def _write_json(path: Path, data: Mapping[str, object]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record_backup_status(paths, status: str, payload: Mapping[str, object]) -> None:
    event = {"status": status, "updated_at": datetime.now(UTC).isoformat(), **payload}
    paths.logs.mkdir(parents=True, exist_ok=True)
    with (paths.logs / "backup.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    paths.support.mkdir(parents=True, exist_ok=True)
    temporary = paths.support / ".backup-status.json.part"
    _write_json(temporary, event)
    os.replace(temporary, paths.support / "backup-status.json")


def record_remote_backup_status(paths, status: str, payload: Mapping[str, object]) -> None:
    """Publish the latest remote database/image-sync result for operators."""

    event = {"status": status, "updated_at": datetime.now(UTC).isoformat(), **payload}
    paths.logs.mkdir(parents=True, exist_ok=True)
    with (paths.logs / "remote-backup.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    paths.support.mkdir(parents=True, exist_ok=True)
    temporary = paths.support / ".remote-backup-status.json.part"
    _write_json(temporary, event)
    os.replace(temporary, paths.support / "remote-backup-status.json")


def _database_schema_version(database: Path) -> str:
    try:
        connection = sqlite3.connect(database, timeout=30)
        row = connection.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
        connection.close()
        return str(row[0]) if row else "unknown"
    except sqlite3.DatabaseError:
        return "unknown"


def _verify_sqlite(database: Path) -> None:
    connection = sqlite3.connect(database, timeout=30)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok":
            raise BackupError(f"SQLite integrity check failed: {integrity}")
        if foreign_keys:
            raise BackupError(f"SQLite foreign-key check failed: {len(foreign_keys)} violation(s)")
    finally:
        connection.close()


def _snapshot_sqlite(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BackupError(f"SQLite database is missing: {source}")
    source_db = sqlite3.connect(source, timeout=30)
    target_db = sqlite3.connect(destination, timeout=30)
    try:
        source_db.execute("PRAGMA busy_timeout=30000")
        target_db.execute("PRAGMA foreign_keys=ON")
        source_db.backup(target_db, pages=100, sleep=0.05)
        target_db.commit()
    except sqlite3.DatabaseError as exc:
        target_db.rollback()
        raise BackupError("SQLite online backup failed") from exc
    finally:
        target_db.close()
        source_db.close()
    _verify_sqlite(destination)


@contextlib.contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    """Create an exclusive lock file and always remove it on exit."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise BackupBusyError(f"Backup lock is already held: {path}") from exc
    try:
        os.write(descriptor, json.dumps({"pid": os.getpid(), "created_at": datetime.now(UTC).isoformat()}).encode("utf-8"))
        os.close(descriptor)
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _manifest_files(root: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "size": path.stat().st_size, "sha256": sha256_file(path)})
    return files


def _config_snapshot(runtime_config, paths: object, schema_version: str, created_at: datetime) -> dict[str, object]:
    return {
        "format_version": BACKUP_FORMAT_VERSION,
        "store_id": getattr(runtime_config, "store_id", "") or "unassigned",
        "application_version": getattr(runtime_config, "app_version", "unknown"),
        "schema_version": schema_version,
        "timezone": "Asia/Bangkok",
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "created_at_bangkok": created_at.astimezone(BANGKOK).isoformat(),
        "runtime_layout": {
            "database": "data/pos.db",
            "product_images": "separate SFTP file-snapshots/uploads/products/",
            "config": "config/",
        },
        "note": "Product images use separate incremental SFTP sync. Secrets, private keys, tokens, and the local Flask secret are intentionally excluded.",
    }


def verify_backup(archive: str | os.PathLike[str], *, _allow_staging: bool = False) -> dict[str, object]:
    """Verify a published backup and return its manifest."""

    archive_path = Path(archive).expanduser().resolve()
    if not archive_path.is_file() or (archive_path.name.startswith(".") and not _allow_staging) or not archive_path.name.endswith(".zip.part" if _allow_staging else ".zip"):
        raise BackupError("Only a published .zip backup can be verified.")
    with zipfile.ZipFile(archive_path) as package:
        names = {_safe_zip_name(info.filename) for info in package.infolist()}
        if "manifest.json" not in names or "checksums.sha256" not in names or "database/pos.db" not in names:
            raise BackupError("Backup is incomplete: manifest, checksums, or database is missing.")
        try:
            manifest = json.loads(package.read("manifest.json").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError("Backup manifest is invalid.") from exc
        if manifest.get("status") != "complete" or manifest.get("format_version") != BACKUP_FORMAT_VERSION:
            raise BackupError("Backup is not marked complete or uses an unsupported format.")
        for entry in manifest.get("files", []):
            relative = _safe_zip_name(str(entry["path"]))
            if relative not in names:
                raise BackupError(f"Manifest file is missing from archive: {relative}")
            info = package.getinfo(relative)
            if info.file_size != int(entry["size"]):
                raise BackupError(f"Archive size mismatch: {relative}")
            digest = hashlib.sha256(package.read(relative)).hexdigest()
            if digest != entry["sha256"]:
                raise BackupError(f"Archive checksum mismatch: {relative}")
        checksum_lines = package.read("checksums.sha256").decode("utf-8").splitlines()
        for line in checksum_lines:
            if not line.strip():
                continue
            expected, relative = line.split("  ", 1)
            relative = _safe_zip_name(relative)
            if relative not in names:
                raise BackupError(f"Checksum file references a missing path: {relative}")
            actual = hashlib.sha256(package.read(relative)).hexdigest()
            if actual != expected:
                raise BackupError(f"Checksum verification failed: {relative}")
        with tempfile.TemporaryDirectory(prefix="pos-backup-verify-") as temp:
            extracted_db = Path(temp) / "pos.db"
            extracted_db.write_bytes(package.read("database/pos.db"))
            _verify_sqlite(extracted_db)
    return {**manifest, "archive_sha256": sha256_file(archive_path), "archive": str(archive_path)}


def create_local_backup(runtime_paths, runtime_config, *, retention: int = 7, now: datetime | None = None) -> BackupArtifact:
    """Create and verify one local backup without blocking the Flask app."""

    paths = runtime_paths
    paths.create_directories()
    created = _now_utc(now)
    backup_id = "backup-" + created.strftime("%Y%m%dT%H%M%SZ")
    if (paths.backups / f"{backup_id}.zip").exists():
        backup_id += "-" + uuid.uuid4().hex[:8]
    final_archive = paths.backups / f"{backup_id}.zip"
    temporary_archive = paths.staging / f".{backup_id}.{uuid.uuid4().hex}.zip.part"
    with exclusive_lock(paths.backups / ".backup.lock"):
        try:
            with tempfile.TemporaryDirectory(prefix=f"{backup_id}-", dir=paths.staging) as temp:
                root = Path(temp)
                database = root / "database" / "pos.db"
                database.parent.mkdir(parents=True, exist_ok=True)
                _snapshot_sqlite(paths.database, database)
                # Keep the legacy archive member for existing operator tooling;
                # database/pos.db remains the canonical Sprint 2 location.
                legacy_database = root / "data" / "pos.db"
                legacy_database.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(database, legacy_database)
                schema_version = _database_schema_version(database)
                config_snapshot = _config_snapshot(runtime_config, paths, schema_version, created)
                config_path = root / "config" / "recovery-config.json"
                config_path.parent.mkdir(parents=True, exist_ok=True)
                _write_json(config_path, config_snapshot)
                entries = _manifest_files(root)
                manifest: dict[str, object] = {
                    "status": "complete",
                    "format_version": BACKUP_FORMAT_VERSION,
                    "backup_id": backup_id,
                    "created_at_utc": created.isoformat().replace("+00:00", "Z"),
                    "created_at_bangkok": created.astimezone(BANGKOK).isoformat(),
                    "application_version": getattr(runtime_config, "app_version", "unknown"),
                    "schema_version": schema_version,
                    "store_id": getattr(runtime_config, "store_id", "") or "unassigned",
                    "files": entries,
                    "file_count": len(entries),
                    "product_images_separate_sync": True,
                }
                _write_json(root / "manifest.json", manifest)
                checksums = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in sorted(root.rglob("*")) if path.is_file()]
                (root / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")
                with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
                    for path in sorted(root.rglob("*")):
                        if path.is_file():
                            package.write(path, path.relative_to(root).as_posix())
            verified = verify_backup(temporary_archive, _allow_staging=True)
            os.replace(temporary_archive, final_archive)
        except Exception:
            _record_backup_status(paths, "failed", {"backup_id": backup_id})
            with contextlib.suppress(FileNotFoundError):
                temporary_archive.unlink()
            raise
        prune_local_backups(paths.backups, retention)
        _record_backup_status(paths, "complete", {"backup_id": backup_id, "archive": final_archive.name, "archive_sha256": verified["archive_sha256"]})
    return BackupArtifact(final_archive, backup_id, dict(verified), str(verified["archive_sha256"]))


def list_verified_backups(backups: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for archive in sorted(backups.glob("backup-*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            results.append(verify_backup(archive))
        except (BackupError, OSError, zipfile.BadZipFile):
            continue
    return results


def prune_local_backups(backups: Path, retention: int = 7) -> list[Path]:
    """Retain at least one verified archive and leave invalid archives untouched."""

    keep_count = max(1, int(retention))
    verified: list[Path] = []
    for archive in sorted(backups.glob("backup-*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            verify_backup(archive)
        except (BackupError, OSError, zipfile.BadZipFile):
            continue
        verified.append(archive)
    removed: list[Path] = []
    for archive in verified[keep_count:]:
        archive.unlink()
        removed.append(archive)
    return removed


def restore_backup_to_runtime(archive: str | os.PathLike[str], target_runtime: str | os.PathLike[str]) -> Path:
    """Restore into a new/non-production runtime directory only."""

    archive_path = Path(archive).expanduser().resolve()
    target = Path(target_runtime).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise BackupError("Recovery target must be empty so existing data cannot be overwritten.")
    target.mkdir(parents=True, exist_ok=True)
    manifest = verify_backup(archive_path)
    with zipfile.ZipFile(archive_path) as package:
        for info in package.infolist():
            name = _safe_zip_name(info.filename)
            if name in {"manifest.json", "checksums.sha256"}:
                continue
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with package.open(info) as source, destination.open("wb") as sink:
                shutil.copyfileobj(source, sink)
    database = target / "database" / "pos.db"
    runtime_database = target / "data" / "pos.db"
    runtime_database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database, runtime_database)
    uploads = target / "uploads"
    if uploads.exists():
        pass
    _verify_sqlite(runtime_database)
    _write_json(target / "recovery-verification.json", {"status": "verified", "manifest": manifest})
    return target
