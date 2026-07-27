"""Offline-safe release verification, staging, activation, and rollback."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .backup import BackupError, create_local_backup, sha256_file


class UpdateError(ValueError):
    """Raised when a release cannot be trusted or safely installed."""


UTC = timezone.utc
MANIFEST_VERSION = 1
FORBIDDEN_PARTS = {".git", ".venv", "runtime", "data", "uploads", "backups", "logs", "staging", "browser-profile"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".db", ".db-wal", ".db-shm", ".key", ".pem"}


@dataclass(frozen=True)
class ReleaseManifest:
    application_version: str
    release_timestamp: str
    minimum_supported_current_version: str
    minimum_supported_schema_version: int
    target_schema_version: int
    restart_required: bool
    release_notes: str
    package_url: str
    package_sha256: str
    files: tuple[dict[str, object], ...]
    signature_hmac_sha256: str


def _version(value: str) -> tuple[int, ...]:
    parts = str(value).strip().lstrip("v").split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise UpdateError(f"Invalid application version: {value}")
    return tuple(int(part) for part in parts)


def _canonical(data: Mapping[str, object]) -> bytes:
    unsigned = {key: value for key, value in data.items() if key != "signature_hmac_sha256"}
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_member(value: str) -> str:
    name = str(value).replace("\\", "/")
    path = Path(name)
    if not name or name.startswith("/") or ".." in path.parts or ":" in name:
        raise UpdateError(f"Unsafe release path: {value}")
    if any(part.lower() in FORBIDDEN_PARTS or part.startswith(".") for part in path.parts):
        raise UpdateError(f"Release contains a forbidden path: {value}")
    if any(name.lower().endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
        raise UpdateError(f"Release contains a forbidden file: {value}")
    return name


def load_manifest(source: str | os.PathLike[str] | Mapping[str, object]) -> dict[str, object]:
    if isinstance(source, Mapping):
        data = dict(source)
    else:
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UpdateError("Release manifest cannot be read.") from exc
    if not isinstance(data, dict) or data.get("manifest_version", MANIFEST_VERSION) != MANIFEST_VERSION:
        raise UpdateError("Unsupported release manifest.")
    required = {
        "application_version", "release_timestamp", "minimum_supported_current_version",
        "minimum_supported_schema_version", "target_schema_version", "files", "package_sha256",
        "signature_hmac_sha256",
    }
    missing = sorted(required - data.keys())
    if missing:
        raise UpdateError("Release manifest is missing: " + ", ".join(missing))
    _version(str(data["application_version"]))
    _version(str(data["minimum_supported_current_version"]))
    try:
        minimum_schema = int(data["minimum_supported_schema_version"])
        target_schema = int(data["target_schema_version"])
    except (TypeError, ValueError) as exc:
        raise UpdateError("Release schema versions must be integers.") from exc
    if minimum_schema < 0 or target_schema < minimum_schema:
        raise UpdateError("Release schema compatibility range is invalid.")
    digest = str(data["package_sha256"]).lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise UpdateError("Release package checksum is invalid.")
    files = data["files"]
    if not isinstance(files, list) or not files:
        raise UpdateError("Release must declare at least one file.")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict) or not {"path", "size", "sha256"} <= entry.keys():
            raise UpdateError("Release file entry is invalid.")
        relative = _safe_member(str(entry["path"]))
        if relative in seen:
            raise UpdateError(f"Release file is declared twice: {relative}")
        seen.add(relative)
        try:
            size = int(entry["size"])
        except (TypeError, ValueError) as exc:
            raise UpdateError(f"Release file size is invalid: {relative}") from exc
        file_digest = str(entry["sha256"]).lower()
        if size < 0 or len(file_digest) != 64 or any(char not in "0123456789abcdef" for char in file_digest):
            raise UpdateError(f"Release file checksum is invalid: {relative}")
        normalized.append({"path": relative, "size": size, "sha256": file_digest})
    data["files"] = normalized
    data["restart_required"] = bool(data.get("restart_required", True))
    data["release_notes"] = str(data.get("release_notes", ""))[:4000]
    data["package_url"] = str(data.get("package_url", ""))
    data["signature_hmac_sha256"] = str(data["signature_hmac_sha256"]).lower()
    return data


def verify_manifest(source: str | os.PathLike[str] | Mapping[str, object], trusted_key: bytes | str | os.PathLike[str]) -> ReleaseManifest:
    data = load_manifest(source)
    key = trusted_key if isinstance(trusted_key, bytes) else Path(trusted_key).read_bytes()
    expected = hmac.new(key, _canonical(data), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(data["signature_hmac_sha256"])):
        raise UpdateError("Release manifest signature verification failed.")
    return ReleaseManifest(
        application_version=str(data["application_version"]),
        release_timestamp=str(data["release_timestamp"]),
        minimum_supported_current_version=str(data["minimum_supported_current_version"]),
        minimum_supported_schema_version=int(data["minimum_supported_schema_version"]),
        target_schema_version=int(data["target_schema_version"]),
        restart_required=bool(data["restart_required"]),
        release_notes=str(data["release_notes"]),
        package_url=str(data["package_url"]),
        package_sha256=str(data["package_sha256"]).lower(),
        files=tuple(data["files"]),
        signature_hmac_sha256=str(data["signature_hmac_sha256"]),
    )


def validate_compatibility(manifest: ReleaseManifest, current_version: str, current_schema_version: int) -> None:
    if _version(manifest.application_version) <= _version(current_version):
        raise UpdateError("Release is not newer than the running application.")
    if _version(current_version) < _version(manifest.minimum_supported_current_version):
        raise UpdateError("Current application version is outside the release compatibility range.")
    if current_schema_version < manifest.minimum_supported_schema_version:
        raise UpdateError("Current database schema is older than this release supports.")


def verify_release_package(package: str | os.PathLike[str], manifest: ReleaseManifest) -> dict[str, object]:
    package_path = Path(package).expanduser().resolve()
    if not package_path.is_file() or sha256_file(package_path) != manifest.package_sha256:
        raise UpdateError("Release package checksum verification failed.")
    expected = {str(entry["path"]): entry for entry in manifest.files}
    with zipfile.ZipFile(package_path) as archive:
        members: dict[str, zipfile.ZipInfo] = {}
        for info in archive.infolist():
            name = _safe_member(info.filename)
            if name in members:
                raise UpdateError(f"Release package contains duplicate path: {name}")
            members[name] = info
        if set(expected) != set(members):
            raise UpdateError("Release package contents do not match its manifest.")
        for relative, entry in expected.items():
            info = members[relative]
            if info.is_dir() or info.file_size != int(entry["size"]):
                raise UpdateError(f"Release package size mismatch: {relative}")
            with archive.open(info) as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            if digest != entry["sha256"]:
                raise UpdateError(f"Release package file checksum mismatch: {relative}")
    return {"status": "verified", "package": str(package_path), "package_sha256": manifest.package_sha256, "file_count": len(expected)}


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _status(paths, status: str, **details: object) -> None:
    _atomic_json(paths.support / "update-status.json", {"status": status, "updated_at": datetime.now(UTC).isoformat(), **details})
    paths.logs.mkdir(parents=True, exist_ok=True)
    with (paths.logs / "update.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"status": status, "updated_at": datetime.now(UTC).isoformat(), **details}, ensure_ascii=False) + "\n")


def active_release(paths) -> dict[str, object] | None:
    path = paths.releases / "active-release.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = str(data.get("version", "")) if isinstance(data, dict) else ""
    if not version:
        return None
    release_dir = paths.releases / version
    try:
        release_dir.resolve().relative_to(paths.releases.resolve())
    except ValueError:
        return None
    if not (release_dir / "manifest.json").is_file():
        return None
    return {**data, "path": str(release_dir)}


def _stage(paths, package: Path, manifest: ReleaseManifest) -> Path:
    stage_root = paths.staging / "updates"
    stage_root.mkdir(parents=True, exist_ok=True)
    target = stage_root / manifest.application_version
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with zipfile.ZipFile(package) as archive:
        for entry in manifest.files:
            destination = target / str(entry["path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(str(entry["path"])) as source, destination.open("wb") as sink:
                shutil.copyfileobj(source, sink)
    _atomic_json(target / "manifest.json", {"manifest_version": MANIFEST_VERSION, **{**manifest.__dict__, "files": list(manifest.files)}})
    _status(paths, "downloaded", version=manifest.application_version, staged_path=str(target))
    return target


def download_update(paths, manifest_source, package_source, trusted_key, *, current_version: str, current_schema_version: int) -> dict[str, object]:
    manifest = verify_manifest(manifest_source, trusted_key)
    validate_compatibility(manifest, current_version, current_schema_version)
    if isinstance(package_source, (str, os.PathLike)) and str(package_source).lower().startswith(("http://", "https://")):
        if not str(package_source).lower().startswith("https://"):
            raise UpdateError("Release downloads must use HTTPS.")
        package_path = paths.staging / f"release-{manifest.application_version}.zip.part"
        with urllib.request.urlopen(str(package_source), timeout=60) as response, package_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    else:
        package_path = Path(package_source).expanduser().resolve()
    verify_release_package(package_path, manifest)
    staged = _stage(paths, package_path, manifest)
    return {"status": "downloaded", "version": manifest.application_version, "staged_path": str(staged)}


def check_update(paths, manifest_source, trusted_key, *, current_version: str, current_schema_version: int) -> dict[str, object]:
    manifest = verify_manifest(manifest_source, trusted_key)
    validate_compatibility(manifest, current_version, current_schema_version)
    result = {"status": "available", "version": manifest.application_version, "release_notes": manifest.release_notes, "package_url": manifest.package_url, "target_schema_version": manifest.target_schema_version}
    _status(paths, "available", **result)
    return result


def install_update(paths, runtime_config, *, staged_path: str | os.PathLike[str], current_version: str, current_schema_version: int, backup_factory: Callable | None = None, smoke_test: Callable[[Path], None] | None = None) -> dict[str, object]:
    staged = Path(staged_path).expanduser().resolve()
    try:
        staged.relative_to(paths.staging.resolve())
    except ValueError as exc:
        raise UpdateError("Update staging path must remain inside runtime staging.") from exc
    try:
        manifest = verify_manifest(staged / "manifest.json", os.environ.get("POS_RELEASE_TRUSTED_KEY_FILE", paths.configuration / "release-trusted.key"))
    except (OSError, UpdateError) as exc:
        raise UpdateError("Staged release cannot be trusted.") from exc
    validate_compatibility(manifest, current_version, current_schema_version)
    previous = active_release(paths)
    backup_factory = backup_factory or (lambda: create_local_backup(paths, runtime_config))
    safety_backup = backup_factory()
    release_dir = paths.releases / manifest.application_version
    if release_dir.exists():
        raise UpdateError("A release with this version already exists.")
    marker = paths.support / "maintenance.json"
    _atomic_json(marker, {"status": "requested", "started_at": datetime.now(UTC).isoformat(), "reason": "update", "version": manifest.application_version})
    try:
        shutil.copytree(staged, release_dir)
        _atomic_json(paths.releases / "active-release.json", {"version": manifest.application_version, "previous_version": (previous or {}).get("version"), "activated_at": datetime.now(UTC).isoformat()})
        if smoke_test:
            smoke_test(release_dir)
        _status(paths, "installed", version=manifest.application_version, previous_version=(previous or {}).get("version"), safety_backup=str(safety_backup.path if hasattr(safety_backup, "path") else safety_backup))
        marker.unlink(missing_ok=True)
        return {"status": "installed", "version": manifest.application_version, "previous_version": (previous or {}).get("version"), "backup": str(safety_backup.path if hasattr(safety_backup, "path") else safety_backup)}
    except Exception as exc:
        if previous and (paths.releases / str(previous["version"])).is_dir():
            _atomic_json(paths.releases / "active-release.json", {key: value for key, value in previous.items() if key != "path"})
        else:
            (paths.releases / "active-release.json").unlink(missing_ok=True)
        shutil.rmtree(release_dir, ignore_errors=True)
        _status(paths, "rolled_back", attempted_version=manifest.application_version, error=str(exc))
        marker.unlink(missing_ok=True)
        raise UpdateError("Update verification failed; previous release was restored.") from exc


def rollback_release(paths, *, target_version: str | None = None, current_schema_version: int) -> dict[str, object]:
    current = active_release(paths)
    if not current:
        raise UpdateError("There is no active versioned release to roll back.")
    target = target_version or str(current.get("previous_version") or "")
    if not target:
        raise UpdateError("No previous known-good release is available.")
    target_dir = paths.releases / target
    manifest_path = target_dir / "manifest.json"
    if not target_dir.is_dir() or not manifest_path.is_file():
        raise UpdateError("Requested rollback release is missing.")
    trusted_key = os.environ.get("POS_RELEASE_TRUSTED_KEY_FILE", paths.configuration / "release-trusted.key")
    manifest = verify_manifest(manifest_path, trusted_key)
    if current_schema_version < manifest.minimum_supported_schema_version or current_schema_version > manifest.target_schema_version:
        raise UpdateError("Rollback is blocked because the database schema is not compatible.")
    _atomic_json(paths.releases / "active-release.json", {"version": target, "previous_version": current.get("version"), "activated_at": datetime.now(UTC).isoformat()})
    _status(paths, "rolled_back", version=target, previous_version=current.get("version"))
    return {"status": "rolled_back", "version": target, "previous_version": current.get("version")}


__all__ = ["ReleaseManifest", "UpdateError", "active_release", "check_update", "download_update", "install_update", "load_manifest", "rollback_release", "validate_compatibility", "verify_manifest", "verify_release_package"]
