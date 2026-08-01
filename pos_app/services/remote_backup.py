"""Restricted outbound SFTP transport using the platform OpenSSH client."""

from __future__ import annotations

import json
import os
import posixpath
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .backup import BackupError, BackupArtifact, sha256_file


class RemoteBackupError(BackupError):
    """Raised when a remote backup transfer fails."""


@dataclass(frozen=True)
class RemoteBackupConfig:
    host: str
    username: str
    key_file: Path
    known_hosts: Path
    store_id: str
    root: str = "/"
    port: int = 22
    connect_timeout: int = 15
    verify_download: bool = True

    @property
    def base_path(self) -> str:
        safe_store = self.store_id.strip().replace("\\", "/")
        if not safe_store or safe_store in {".", ".."} or "/" in safe_store:
            raise RemoteBackupError("VPS store id must be a single safe path component.")
        return posixpath.join(self.root.rstrip("/") or "/", safe_store)


def load_remote_config(runtime_paths, runtime_config, environ: dict[str, str] | None = None) -> RemoteBackupConfig | None:
    environ = os.environ if environ is None else environ
    local: dict[str, object] = {}
    config_file = getattr(runtime_config, "config_file", None)
    if config_file and Path(config_file).is_file():
        try:
            data = json.loads(Path(config_file).read_text(encoding="utf-8"))
            local = data.get("backup", {}).get("vps", {}) if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            raise RemoteBackupError("Configured production.json cannot be read for VPS backup settings.")

    def value(env_name: str, config_name: str, default: str = "") -> str:
        return str(environ.get(env_name, local.get(config_name, default)) or "").strip()

    host = value("POS_VPS_HOST", "host")
    if not host:
        return None
    username = value("POS_VPS_USER", "username", "posbackup")
    key_file = Path(value("POS_VPS_KEY_FILE", "key_file")).expanduser()
    known_hosts = Path(value("POS_VPS_KNOWN_HOSTS", "known_hosts")).expanduser()
    store_id = value("POS_VPS_STORE_ID", "store_id", getattr(runtime_config, "store_id", ""))
    try:
        port = int(value("POS_VPS_PORT", "port", "22"))
        timeout = int(value("POS_VPS_CONNECT_TIMEOUT", "connect_timeout", "15"))
    except ValueError as exc:
        raise RemoteBackupError("VPS port and timeout must be integers.") from exc
    if not key_file.is_file() or not known_hosts.is_file():
        raise RemoteBackupError("VPS key_file and known_hosts must point to existing local files.")
    return RemoteBackupConfig(host, username, key_file, known_hosts, store_id, value("POS_VPS_ROOT", "root", "/"), port, timeout, value("POS_VPS_VERIFY_DOWNLOAD", "verify_download", "1").lower() not in {"0", "false", "no"})


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "/").replace('"', '\\"') + '"'


class SftpTransport:
    def __init__(self, config: RemoteBackupConfig, runner=subprocess.run, sftp_command: str = "sftp"):
        self.config = config
        self.runner = runner
        self.sftp_command = sftp_command

    def _run(self, commands: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
        args = [
            self.sftp_command, "-b", "-", "-P", str(self.config.port),
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "IdentitiesOnly=yes", "-o", f"ConnectTimeout={self.config.connect_timeout}",
            "-o", "UserKnownHostsFile=" + str(self.config.known_hosts),
            "-i", str(self.config.key_file), f"{self.config.username}@{self.config.host}",
        ]
        result = self.runner(args, input="\n".join(commands) + "\n", text=True, capture_output=True, check=False)
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout or "SFTP command failed").strip()
            raise RemoteBackupError(f"SFTP transfer failed: {detail[:300]}")
        return result

    def _base(self, relative: str) -> str:
        normalized = relative.replace("\\", "/").lstrip("/")
        if not normalized or ".." in normalized.split("/"):
            raise RemoteBackupError("Remote path is unsafe.")
        return posixpath.join(self.config.base_path, normalized)

    def ensure_layout(self) -> None:
        base = self.config.base_path
        self._run([f"-mkdir {_quote(base)}", f"-mkdir {_quote(posixpath.join(base, 'database-backups'))}", f"-mkdir {_quote(posixpath.join(base, 'file-snapshots'))}", f"-mkdir {_quote(posixpath.join(base, 'file-backups'))}", f"-mkdir {_quote(posixpath.join(base, 'manifests'))}", f"-mkdir {_quote(posixpath.join(base, 'status'))}", f"-mkdir {_quote(posixpath.join(base, 'quarantine'))}"])

    def _ensure_parent(self, remote_path: str) -> None:
        parts = remote_path.split("/")
        commands = []
        current = ""
        for part in parts[:-1]:
            if not part:
                current = "/"
                continue
            current = posixpath.join(current, part) if current != "/" else "/" + part
            commands.append(f"-mkdir {_quote(current)}")
        if commands:
            self._run(commands)

    @staticmethod
    def _parent_commands(remote_path: str) -> list[str]:
        parts = remote_path.split("/")
        commands = []
        current = ""
        for part in parts[:-1]:
            if not part:
                current = "/"
                continue
            current = posixpath.join(current, part) if current != "/" else "/" + part
            commands.append(f"-mkdir {_quote(current)}")
        return commands

    def upload_file(self, local: Path, remote_relative: str) -> str:
        remote = self._base(remote_relative)
        self._ensure_parent(remote)
        temporary = remote + ".part"
        self._run([f"-rm {_quote(temporary)}", f"put {_quote(str(local))} {_quote(temporary)}", f"rename {_quote(temporary)} {_quote(remote)}"])
        return sha256_file(local)

    def upload_files(self, files: list[tuple[Path, str]]) -> dict[str, str]:
        """Upload a set of new snapshots in one SFTP connection."""

        commands: list[str] = []
        made_directories: set[str] = set()
        results: dict[str, str] = {}
        for local, remote_relative in files:
            remote = self._base(remote_relative)
            for command in self._parent_commands(remote):
                if command not in made_directories:
                    commands.append(command)
                    made_directories.add(command)
            temporary = remote + ".part"
            commands.extend([f"-rm {_quote(temporary)}", f"put {_quote(str(local))} {_quote(temporary)}", f"rename {_quote(temporary)} {_quote(remote)}"])
            results[remote_relative] = sha256_file(local)
        if commands:
            self._run(commands)
        return results

    def upload_versioned_file(self, local: Path, remote_relative: str, archive_relative: str) -> str:
        """Keep the prior remote product image before replacing its snapshot."""

        source = self._base(remote_relative)
        archive = self._base(archive_relative)
        self._ensure_parent(archive)
        # The leading dash keeps first-time uploads successful when no prior
        # snapshot exists. Existing snapshots are moved atomically first.
        self._run([f"-rename {_quote(source)} {_quote(archive)}"])
        return self.upload_file(local, remote_relative)

    def upload_with_retry(self, local: Path, remote_relative: str, *, retries: int = 3) -> str:
        return self._retry(lambda: self.upload_file(local, remote_relative), retries)

    def _retry(self, operation, retries: int):
        last_error = None
        attempts = max(1, retries)
        for attempt in range(attempts):
            try:
                return operation()
            except (RemoteBackupError, OSError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(2**attempt)
        detail = " ".join(str(last_error or "unknown remote error").split())[:300]
        raise RemoteBackupError(
            f"Remote operation failed after {attempts} attempt(s): {detail}"
        ) from last_error

    def quarantine_file(self, remote_relative: str, quarantine_relative: str) -> None:
        source = self._base(remote_relative)
        target = self._base(quarantine_relative)
        self._ensure_parent(target)
        self._run([f"rename {_quote(source)} {_quote(target)}"])

    def quarantine_with_retry(self, remote_relative: str, quarantine_relative: str, *, retries: int = 3) -> None:
        self._retry(lambda: self.quarantine_file(remote_relative, quarantine_relative), retries)

    def _download(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        self._run([f"get {_quote(remote)} {_quote(str(local))}"])

    def upload_backup(self, artifact: BackupArtifact, *, retries: int = 3) -> dict[str, object]:
        self._retry(self.ensure_layout, retries)
        remote_relative = f"database-backups/{artifact.path.name}"
        self._retry(lambda: self.upload_file(artifact.path, remote_relative), retries)
        if self.config.verify_download:
            with tempfile.TemporaryDirectory(prefix="pos-vps-verify-") as temp:
                downloaded = Path(temp) / artifact.path.name
                self._download(self._base(remote_relative), downloaded)
                if sha256_file(downloaded) != artifact.archive_sha256:
                    raise RemoteBackupError("Remote backup checksum verification failed.")
        manifest_payload = json.dumps({"status": "complete", "backup_id": artifact.backup_id, "archive": artifact.path.name, "archive_sha256": artifact.archive_sha256, "manifest": artifact.manifest}, ensure_ascii=False, indent=2) + "\n"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            handle.write(manifest_payload)
            manifest_file = Path(handle.name)
        try:
            manifest_relative = f"manifests/{artifact.backup_id}.json"
            self.upload_file(manifest_file, manifest_relative)
            marker_relative = f"status/{artifact.backup_id}.complete"
            self.upload_file(manifest_file, marker_relative)
        finally:
            manifest_file.unlink(missing_ok=True)
        return {"backup_id": artifact.backup_id, "remote_archive": self._base(remote_relative), "archive_sha256": artifact.archive_sha256, "status": "complete"}

    def upload_sync_manifest(self, payload: dict[str, object]) -> None:
        backup_id = str(payload.get("backup_id") or "unlinked")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            manifest_file = Path(handle.name)
        try:
            self.ensure_layout()
            self.upload_file(manifest_file, f"manifests/file-sync-{backup_id}.json")
            self.upload_file(manifest_file, f"status/file-sync-{backup_id}.complete")
        finally:
            manifest_file.unlink(missing_ok=True)

    def test_connection(self) -> bool:
        return self._run(["pwd"]).returncode == 0
