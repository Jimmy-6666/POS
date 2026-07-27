"""Command-line entry point for scheduled local backup, sync, and recovery."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from .runtime_paths import load_runtime_config
from .services.backup import BackupError, create_local_backup, restore_backup_to_runtime, verify_backup
from .services.file_sync import sync_files
from .services.remote_backup import SftpTransport, load_remote_config


def _config():
    project_root = Path(__file__).resolve().parent.parent
    config = load_runtime_config(project_root)
    config.paths.create_directories()
    return config


def _remote(config):
    remote = load_remote_config(config.paths, config)
    if remote is None:
        raise BackupError("VPS backup is not configured. Local backup remains available offline.")
    return SftpTransport(remote)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Saengngam POS maintenance backup tool")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup")
    sub.add_parser("backup-and-sync")
    sub.add_parser("sync")
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("archive", type=Path)
    restore_parser = sub.add_parser("restore-drill")
    restore_parser.add_argument("archive", type=Path)
    restore_parser.add_argument("target", type=Path)
    args = parser.parse_args(argv)
    try:
        config = _config()
        retention = int(os.environ.get("POS_BACKUP_RETENTION", "7"))
        if args.command == "verify":
            print(json.dumps(verify_backup(args.archive), ensure_ascii=False))
            return 0
        if args.command == "restore-drill":
            target = restore_backup_to_runtime(args.archive, args.target)
            print(json.dumps({"status": "verified", "target": str(target)}, ensure_ascii=False))
            return 0
        if args.command == "backup":
            artifact = create_local_backup(config.paths, config, retention=retention)
            print(json.dumps({"status": "complete", "backup": str(artifact.path), "sha256": artifact.archive_sha256}, ensure_ascii=False))
            return 0
        if args.command == "sync":
            transport = _remote(config)
            result = sync_files(config.paths, transport, configured_paths=os.environ.get("POS_SYNC_PATHS"), deletion_grace_days=int(os.environ.get("POS_SYNC_DELETION_GRACE_DAYS", "30")), backup_id=os.environ.get("POS_LAST_BACKUP_ID"), retries=int(os.environ.get("POS_VPS_RETRIES", "3")))
            if result.errors:
                raise BackupError("File sync completed with errors: " + "; ".join(result.errors))
            transport.upload_sync_manifest({"status": "complete", "backup_id": result.backup_id, "scanned": result.scanned, "uploaded": result.uploaded})
            print(json.dumps(result.__dict__, ensure_ascii=False))
            return 0
        artifact = create_local_backup(config.paths, config, retention=retention)
        transport = _remote(config)
        remote_status = transport.upload_backup(artifact, retries=int(os.environ.get("POS_VPS_RETRIES", "3")))
        result = sync_files(config.paths, transport, configured_paths=os.environ.get("POS_SYNC_PATHS"), deletion_grace_days=int(os.environ.get("POS_SYNC_DELETION_GRACE_DAYS", "30")), backup_id=artifact.backup_id, retries=int(os.environ.get("POS_VPS_RETRIES", "3")))
        transport.upload_sync_manifest({"status": "complete", "backup_id": artifact.backup_id, "scanned": result.scanned, "uploaded": result.uploaded})
        print(json.dumps({"status": "complete", "backup": str(artifact.path), "remote": remote_status, "sync": result.__dict__}, ensure_ascii=False))
        return 0
    except (BackupError, OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
