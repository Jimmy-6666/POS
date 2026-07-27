"""Durable, allow-listed maintenance jobs used by the admin UI."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .backup import BackupError, create_local_backup
from .file_sync import sync_files
from .remote_backup import SftpTransport, load_remote_config


UTC = timezone.utc
ALLOWED_JOBS = {"backup", "backup_and_sync", "sync_retry", "vps_test", "support_bundle", "update_check", "update_download", "update_install", "update_rollback", "controlled_restart"}
_threads: dict[str, threading.Thread] = {}
_threads_lock = threading.Lock()


def _job_dir(paths) -> Path:
    path = paths.support / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _job_path(paths, job_id: str) -> Path:
    if not job_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in job_id):
        raise ValueError("Invalid maintenance job id.")
    return _job_dir(paths) / f"{job_id}.json"


def _write(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Maintenance job record is invalid.") from exc
    if not isinstance(value, dict):
        raise ValueError("Maintenance job record is invalid.")
    return value


def enqueue_job(paths, job_type: str, *, requested_by: int | None = None, payload: dict[str, object] | None = None) -> dict[str, object]:
    if job_type not in ALLOWED_JOBS:
        raise ValueError("Maintenance action is not allow-listed.")
    job = {
        "id": uuid.uuid4().hex,
        "type": job_type,
        "status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
        "requested_by": requested_by,
        "payload": payload or {},
    }
    _write(_job_path(paths, str(job["id"])), job)
    return job


def get_job(paths, job_id: str) -> dict[str, object] | None:
    path = _job_path(paths, job_id)
    if not path.is_file():
        return None
    return _read(path)


def list_jobs(paths, limit: int = 50) -> list[dict[str, object]]:
    records = []
    for path in sorted(_job_dir(paths).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            records.append(_read(path))
        except ValueError:
            continue
        if len(records) >= limit:
            break
    return records


def _update(paths, job_id: str, **changes: object) -> dict[str, object]:
    path = _job_path(paths, job_id)
    job = _read(path)
    job.update(changes)
    _write(path, job)
    return job


def run_job(paths, runtime_config, job_id: str) -> dict[str, object]:
    job = get_job(paths, job_id)
    if not job:
        raise ValueError("Maintenance job was not found.")
    if job.get("status") not in {"queued", "running"}:
        return job
    _update(paths, job_id, status="running", started_at=datetime.now(UTC).isoformat())
    job_type = str(job["type"])
    def schema_version() -> int:
        connection = sqlite3.connect(paths.database)
        try:
            row = connection.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
            return int(row[0]) if row else 0
        finally:
            connection.close()
    try:
        if job_type == "backup":
            artifact = create_local_backup(paths, runtime_config)
            result = {"backup": str(artifact.path), "backup_id": artifact.backup_id, "sha256": artifact.archive_sha256}
        elif job_type in {"backup_and_sync", "sync_retry"}:
            remote = load_remote_config(paths, runtime_config)
            if remote is None:
                raise BackupError("VPS backup is not configured.")
            transport = SftpTransport(remote)
            backup_id = None
            if job_type == "backup_and_sync":
                artifact = create_local_backup(paths, runtime_config)
                transport.upload_backup(artifact, retries=int(os.environ.get("POS_VPS_RETRIES", "3")))
                backup_id = artifact.backup_id
            synced = sync_files(paths, transport, configured_paths=os.environ.get("POS_SYNC_PATHS"), backup_id=backup_id, retries=int(os.environ.get("POS_VPS_RETRIES", "3")))
            if synced.errors:
                raise BackupError("File sync completed with errors: " + "; ".join(synced.errors))
            transport.upload_sync_manifest({"status": "complete", "backup_id": backup_id, "uploaded": synced.uploaded, "scanned": synced.scanned})
            result = synced.__dict__
        elif job_type == "vps_test":
            remote = load_remote_config(paths, runtime_config)
            if remote is None:
                raise BackupError("VPS backup is not configured.")
            result = {"reachable": bool(SftpTransport(remote).test_connection())}
            if not result["reachable"]:
                raise BackupError("VPS connection test failed.")
        elif job_type == "support_bundle":
            from .support import create_support_bundle
            result = {"bundle": str(create_support_bundle(paths, runtime_config))}
        elif job_type == "update_check":
            from .update_agent import check_update
            source = os.environ.get("POS_RELEASE_MANIFEST_SOURCE", "")
            key = os.environ.get("POS_RELEASE_TRUSTED_KEY_FILE", str(paths.configuration / "release-trusted.key"))
            if not source:
                raise BackupError("Release manifest source is not configured.")
            schema = schema_version()
            result = check_update(paths, source, key, current_version=runtime_config.app_version, current_schema_version=schema)
        elif job_type == "update_download":
            from .update_agent import download_update
            source = os.environ.get("POS_RELEASE_MANIFEST_SOURCE", "")
            package = os.environ.get("POS_RELEASE_PACKAGE_SOURCE", "")
            key = os.environ.get("POS_RELEASE_TRUSTED_KEY_FILE", str(paths.configuration / "release-trusted.key"))
            if not source or not package:
                raise BackupError("Release manifest and package sources are not configured.")
            schema = schema_version()
            result = download_update(paths, source, package, key, current_version=runtime_config.app_version, current_schema_version=schema)
        elif job_type == "update_install":
            from .update_agent import install_update
            candidates = sorted((item for item in (paths.staging / "updates").iterdir() if item.is_dir()), reverse=True) if (paths.staging / "updates").is_dir() else []
            if not candidates:
                raise BackupError("No downloaded release is ready to install.")
            schema = schema_version()
            result = install_update(paths, runtime_config, staged_path=candidates[0], current_version=runtime_config.app_version, current_schema_version=schema)
        elif job_type == "update_rollback":
            from .update_agent import rollback_release
            result = rollback_release(paths, current_schema_version=schema_version())
        elif job_type == "controlled_restart":
            # The service manager performs the actual restart after the job is acknowledged.
            result = {"restart_requested": True}
        else:
            from .update_agent import UpdateError
            raise UpdateError(f"Job type {job_type} must be run by the update agent CLI.")
        return _update(paths, job_id, status="succeeded", finished_at=datetime.now(UTC).isoformat(), result=result)
    except Exception as exc:
        return _update(paths, job_id, status="failed", finished_at=datetime.now(UTC).isoformat(), error=str(exc))


def start_job(paths, runtime_config, job_id: str) -> dict[str, object]:
    job = get_job(paths, job_id)
    if not job:
        raise ValueError("Maintenance job was not found.")
    with _threads_lock:
        existing = _threads.get(job_id)
        if existing and existing.is_alive():
            return job
        thread = threading.Thread(target=run_job, args=(paths, runtime_config, job_id), name=f"pos-maintenance-{job_id}", daemon=True)
        _threads[job_id] = thread
        thread.start()
    return job


__all__ = ["ALLOWED_JOBS", "enqueue_job", "get_job", "list_jobs", "run_job", "start_job"]
