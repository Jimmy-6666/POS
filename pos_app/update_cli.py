"""Fixed-command update agent entry point for scheduled maintenance."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .runtime_paths import load_runtime_config
from .services.maintenance_jobs import run_job
from .services.update_agent import UpdateError, check_update, download_update, install_update, rollback_release


def _config():
    config = load_runtime_config(Path(__file__).resolve().parent.parent)
    config.paths.create_directories()
    return config


def _setting(config, name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is not None:
        return value
    if config.config_file.is_file():
        try:
            data = json.loads(config.config_file.read_text(encoding="utf-8"))
            return str(data.get("updates", {}).get(name.removeprefix("POS_").lower(), default))
        except (OSError, json.JSONDecodeError):
            pass
    return default


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Thai Minimart POS update agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("download")
    sub.add_parser("install")
    rollback = sub.add_parser("rollback")
    rollback.add_argument("--version", default="")
    run = sub.add_parser("run-job")
    run.add_argument("job_id")
    args = parser.parse_args(argv)
    try:
        config = _config()
        if args.command == "run-job":
            result = run_job(config.paths, config, args.job_id)
        elif args.command == "rollback":
            result = rollback_release(config.paths, target_version=args.version or None, current_schema_version=int(_setting(config, "POS_SCHEMA_VERSION", "0")))
        else:
            manifest_source = _setting(config, "POS_RELEASE_MANIFEST_SOURCE")
            trusted_key = _setting(config, "POS_RELEASE_TRUSTED_KEY_FILE", str(config.configuration / "release-trusted.key"))
            if not manifest_source:
                raise UpdateError("Release manifest source is not configured.")
            schema = int(_setting(config, "POS_SCHEMA_VERSION", "0"))
            if args.command == "check":
                result = check_update(config.paths, manifest_source, trusted_key, current_version=config.app_version, current_schema_version=schema)
            elif args.command == "download":
                package_source = _setting(config, "POS_RELEASE_PACKAGE_SOURCE")
                if not package_source:
                    raise UpdateError("Release package source is not configured.")
                result = download_update(config.paths, manifest_source, package_source, trusted_key, current_version=config.app_version, current_schema_version=schema)
            else:
                staged = config.paths.staging / "updates"
                candidates = sorted((item for item in staged.iterdir() if item.is_dir()), reverse=True) if staged.is_dir() else []
                if not candidates:
                    raise UpdateError("No downloaded release is ready to install.")
                result = install_update(config.paths, config, staged_path=candidates[0], current_version=config.app_version, current_schema_version=schema)
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0 if result.get("status") not in {"failed"} else 1
    except (OSError, ValueError, UpdateError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
