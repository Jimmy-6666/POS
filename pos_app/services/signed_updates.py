"""Verification and controlled hand-off for Windows-signed update scripts.

Update payloads never arrive through the POS web server. An administrator
places a JSON manifest and its PowerShell update script in ``staging``. The
script must have a valid Authenticode signature from the configured publisher.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


UPDATE_FORMAT_VERSION = 1
_SAFE_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class UpdateVerificationError(RuntimeError):
    """Raised when an update cannot be trusted or safely handed off."""


@dataclass(frozen=True)
class VerifiedUpdate:
    manifest_path: Path
    script_path: Path
    release_id: str
    version: str
    script_sha256: str
    signer_thumbprint: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_name(value: object, field: str, suffix: str) -> str:
    name = str(value or "").strip()
    if not _SAFE_FILE_NAME.fullmatch(name) or not name.lower().endswith(suffix):
        raise UpdateVerificationError(f"Update {field} must be a simple {suffix} file name.")
    return name


def _read_manifest(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateVerificationError("Update manifest is unreadable or invalid JSON.") from exc
    if not isinstance(data, dict) or data.get("format_version") != UPDATE_FORMAT_VERSION:
        raise UpdateVerificationError("Update manifest uses an unsupported format.")
    return data


def inspect_authenticode_signature(script_path: Path, *, powershell: str | None = None) -> tuple[str, str]:
    """Return the Authenticode status and signer thumbprint without interpolation."""

    executable = powershell or os.environ.get("POS_UPDATE_POWERSHELL", "powershell.exe")
    command = (
        "$signature=Get-AuthenticodeSignature -LiteralPath $args[0];"
        "[pscustomobject]@{status=[string]$signature.Status;"
        "thumbprint=[string]$signature.SignerCertificate.Thumbprint}|ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-Command", command, "--", str(script_path)],
            capture_output=True, text=True, check=False, timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateVerificationError("Windows signature verification is unavailable on this computer.") from exc
    if completed.returncode != 0:
        raise UpdateVerificationError("Windows could not inspect the update signature.")
    try:
        result = json.loads(completed.stdout)
        return str(result.get("status", "")), str(result.get("thumbprint", ""))
    except (AttributeError, json.JSONDecodeError) as exc:
        raise UpdateVerificationError("Windows returned an invalid signature result.") from exc


def verify_staged_update(
    staging: Path, manifest_name: str, signer_thumbprint: str,
    *, signature_inspector: Callable[[Path], tuple[str, str]] | None = None,
) -> VerifiedUpdate:
    """Verify a staged manifest, file hash, and pinned Authenticode signer."""

    manifest_name = _safe_name(manifest_name, "manifest", ".update.json")
    expected_thumbprint = re.sub(r"\s+", "", signer_thumbprint or "").upper()
    if not expected_thumbprint:
        raise UpdateVerificationError("No update signing certificate is configured.")
    manifest_path = (staging / manifest_name).resolve()
    try:
        manifest_path.relative_to(staging.resolve())
    except ValueError as exc:
        raise UpdateVerificationError("Update manifest escapes the staging directory.") from exc
    if not manifest_path.is_file():
        raise UpdateVerificationError("The selected update manifest was not found.")
    manifest = _read_manifest(manifest_path)
    release_id = str(manifest.get("release_id") or "").strip()
    version = str(manifest.get("version") or "").strip()
    if not release_id or not version:
        raise UpdateVerificationError("Update manifest requires release_id and version.")
    script_name = _safe_name(manifest.get("script"), "script", ".ps1")
    script_path = (staging / script_name).resolve()
    try:
        script_path.relative_to(staging.resolve())
    except ValueError as exc:
        raise UpdateVerificationError("Update script escapes the staging directory.") from exc
    if not script_path.is_file():
        raise UpdateVerificationError("The update script named by the manifest was not found.")
    expected_hash = str(manifest.get("script_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise UpdateVerificationError("Update manifest has no valid script SHA-256.")
    actual_hash = sha256_file(script_path)
    if actual_hash != expected_hash:
        raise UpdateVerificationError("Update script hash does not match its manifest.")
    status, actual_thumbprint = (signature_inspector or inspect_authenticode_signature)(script_path)
    normalized_actual = re.sub(r"\s+", "", actual_thumbprint).upper()
    if status.lower() != "valid" or normalized_actual != expected_thumbprint:
        raise UpdateVerificationError("Update script is not signed by the configured publisher.")
    return VerifiedUpdate(manifest_path, script_path, release_id, version, actual_hash, normalized_actual)


def staged_manifests(staging: Path) -> list[str]:
    if not staging.is_dir():
        return []
    return [path.name for path in sorted(staging.glob("*.update.json"), key=lambda item: item.name.lower()) if _SAFE_FILE_NAME.fullmatch(path.name)]
