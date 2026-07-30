"""Canonical, data-preserving runtime path and startup configuration helpers."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import secrets
import shutil
import tempfile
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Mapping


DEFAULT_MIN_FREE_SPACE_MB = 512
DEFAULT_APP_VERSION = "3.0.6"
DEFAULT_SERVER_IP = "192.168.0.200"
DEFAULT_LAN_NETWORKS = "192.168.0.0/24"
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_BACKUP_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class RuntimePathError(ValueError):
    """Raised when a configured path or runtime setting is unsafe."""


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    data: Path
    database: Path
    secret_key: Path
    uploads: Path
    product_images: Path
    pos_payment_evidence: Path
    online_payment_evidence: Path
    backups: Path
    logs: Path
    launcher_log: Path
    support: Path
    staging: Path
    releases: Path
    browser_profile: Path
    print_browser_profile: Path
    configuration: Path
    display_state: Path

    @classmethod
    def from_root(cls, root: str | os.PathLike[str]) -> "RuntimePaths":
        resolved_root = Path(root).expanduser().resolve()
        data = resolved_root / "data"
        uploads = resolved_root / "uploads"
        return cls(
            root=resolved_root,
            data=data,
            database=data / "pos.db",
            secret_key=data / ".secret_key",
            uploads=uploads,
            product_images=uploads / "products",
            pos_payment_evidence=uploads / "payments",
            online_payment_evidence=uploads / "online-payments",
            backups=resolved_root / "backups",
            logs=resolved_root / "logs",
            launcher_log=resolved_root / "launcher.log",
            support=resolved_root / "support",
            staging=resolved_root / "staging",
            releases=resolved_root / "releases",
            browser_profile=resolved_root / "browser-profile",
            print_browser_profile=resolved_root / "print-browser-profile",
            configuration=resolved_root / "config",
            display_state=resolved_root / "display_state.json",
        )

    @classmethod
    def from_environment(
        cls,
        project_root: str | os.PathLike[str],
        environ: Mapping[str, str] | None = None,
    ) -> "RuntimePaths":
        environ = os.environ if environ is None else environ
        return cls.from_root(environ.get("POS_RUNTIME_ROOT") or project_root)

    @property
    def directories(self) -> tuple[Path, ...]:
        return (
            self.data,
            self.uploads,
            self.product_images,
            self.pos_payment_evidence,
            self.online_payment_evidence,
            self.backups,
            self.logs,
            self.support,
            self.staging,
            self.releases,
            self.browser_profile,
            self.print_browser_profile,
            self.configuration,
        )

    @property
    def managed_paths(self) -> tuple[Path, ...]:
        return (
            self.data,
            self.database,
            self.secret_key,
            self.uploads,
            self.product_images,
            self.pos_payment_evidence,
            self.online_payment_evidence,
            self.backups,
            self.logs,
            self.launcher_log,
            self.support,
            self.staging,
            self.releases,
            self.browser_profile,
            self.print_browser_profile,
            self.configuration,
            self.display_state,
        )

    def assert_safe(self) -> None:
        if self.root == Path(self.root.anchor):
            raise RuntimePathError("Runtime root must not be a filesystem root.")
        windir = os.environ.get("WINDIR")
        if windir and self.root == Path(windir).resolve():
            raise RuntimePathError("Runtime root must not be the Windows directory.")
        for path in self.managed_paths:
            try:
                path.relative_to(self.root)
            except ValueError as exc:
                raise RuntimePathError(f"Runtime path escapes the selected root: {path}") from exc

    def create_directories(self) -> None:
        self.assert_safe()
        for directory in self.directories:
            directory.mkdir(parents=True, exist_ok=True)

    def with_database(self, database: str | os.PathLike[str]) -> "RuntimePaths":
        database = Path(database).expanduser().resolve()
        try:
            database.relative_to(self.root)
        except ValueError as exc:
            raise RuntimePathError("Database path must remain inside the selected runtime root.") from exc
        return replace(self, database=database)

    def ensure_secret_key(self) -> None:
        self.data.mkdir(parents=True, exist_ok=True)
        try:
            with self.secret_key.open("x", encoding="ascii") as handle:
                handle.write(secrets.token_hex(32))
        except FileExistsError:
            pass

    def resolve_relative(self, relative_path: str | os.PathLike[str]) -> Path:
        candidate = (self.root / Path(relative_path)).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise RuntimePathError("Runtime relative path escapes the selected root.") from exc
        return candidate


@dataclass(frozen=True)
class RuntimeConfig:
    paths: RuntimePaths
    host: str
    port: int
    min_free_space_mb: int
    store_id: str
    app_version: str
    production: bool
    config_file: Path
    update_signer_thumbprint: str = ""
    server_ip: str = DEFAULT_SERVER_IP
    lan_access_enabled: bool = True
    lan_networks: str = DEFAULT_LAN_NETWORKS


def _read_local_config(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimePathError(f"Cannot read production configuration: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimePathError("Production configuration must contain a JSON object.")
    return data


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_runtime_config(
    project_root: str | os.PathLike[str],
    environ: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    environ = os.environ if environ is None else environ
    project_root = Path(project_root).expanduser().resolve()
    config_hint = environ.get("POS_CONFIG_FILE")
    config_root = environ.get("POS_RUNTIME_ROOT") or str(project_root)
    config_file = Path(config_hint).expanduser().resolve() if config_hint else (
        Path(config_root).expanduser().resolve() / "config" / "production.json"
    )
    local = _read_local_config(config_file)

    def setting(env_name: str, json_name: str, default: object) -> object:
        return environ.get(env_name, local.get(json_name, default))

    root = Path(setting("POS_RUNTIME_ROOT", "runtime_root", str(project_root))).expanduser().resolve()
    paths = RuntimePaths.from_root(root)
    try:
        port = int(setting("POS_PORT", "port", 8000))
        min_free_space_mb = int(setting("POS_MIN_FREE_SPACE_MB", "min_free_space_mb", DEFAULT_MIN_FREE_SPACE_MB))
    except (TypeError, ValueError) as exc:
        raise RuntimePathError("POS_PORT and POS_MIN_FREE_SPACE_MB must be integers.") from exc
    return RuntimeConfig(
        paths=paths,
        host=str(setting("POS_BIND_HOST", "bind_host", "0.0.0.0")).strip(),
        port=port,
        min_free_space_mb=min_free_space_mb,
        store_id=str(setting("POS_STORE_ID", "store_id", "")).strip(),
        app_version=str(setting("POS_APP_VERSION", "app_version", DEFAULT_APP_VERSION)).strip(),
        production=_as_bool(setting("POS_PRODUCTION", "production", False)),
        config_file=config_file,
        update_signer_thumbprint=str(setting("POS_UPDATE_SIGNER_THUMBPRINT", "update_signer_thumbprint", "")).strip(),
        server_ip=str(setting("POS_SERVER_IP", "server_ip", DEFAULT_SERVER_IP)).strip(),
        lan_access_enabled=_as_bool(setting("POS_LAN_ACCESS_ENABLED", "lan_access_enabled", True), True),
        lan_networks=str(setting("POS_LAN_NETWORKS", "lan_networks", DEFAULT_LAN_NETWORKS)).strip(),
    )


def validate_runtime(
    config: RuntimeConfig,
    *,
    create_directories: bool = False,
    database_required: bool = True,
) -> dict[str, object]:
    checks: dict[str, dict[str, object]] = {}
    fatal: list[str] = []
    warnings: list[str] = []
    repairable: list[str] = []

    def check(name: str, ok: bool, message: str, severity: str = "fatal") -> None:
        checks[name] = {"ok": ok, "message": message, "severity": severity}
        if not ok:
            if severity == "fatal":
                fatal.append(message)
            elif severity == "repairable":
                repairable.append(message)
            else:
                warnings.append(message)

    try:
        config.paths.assert_safe()
        check("path_containment", True, "Runtime paths remain inside the selected root.")
    except RuntimePathError as exc:
        check("path_containment", False, str(exc))

    if create_directories:
        try:
            config.paths.create_directories()
        except OSError as exc:
            check("directories", False, f"Cannot create runtime directories: {exc}")

    for directory in config.paths.directories:
        check(
            f"directory:{directory.name}",
            directory.is_dir(),
            f"Runtime directory is unavailable: {directory}",
            "repairable",
        )

    check(
        "secret_key",
        config.paths.secret_key.is_file() and bool(config.paths.secret_key.read_text(encoding="ascii").strip()),
        "Secret key is missing or unreadable.",
    )
    check("database_parent", config.paths.database.parent.is_dir(), "Database directory is unavailable.")
    if database_required:
        check("database", config.paths.database.is_file(), "Database file is missing.")

    try:
        usage_path = config.paths.root if config.paths.root.exists() else config.paths.root.parent
        free_mb = shutil.disk_usage(usage_path).free // (1024 * 1024)
        check(
            "free_disk_space",
            free_mb >= config.min_free_space_mb,
            f"Free disk space is {free_mb} MB; required minimum is {config.min_free_space_mb} MB.",
        )
    except OSError as exc:
        check("free_disk_space", False, f"Cannot inspect free disk space: {exc}")

    for directory in (config.paths.data, config.paths.backups, config.paths.logs):
        if directory.is_dir():
            try:
                with tempfile.NamedTemporaryFile(dir=directory, prefix=".runtime-check-", delete=True):
                    pass
                writable = True
            except OSError:
                writable = False
            check(f"write:{directory.name}", writable, f"Runtime directory is not writable: {directory}")

    valid_host = bool(config.host) and not any(char.isspace() for char in config.host)
    if valid_host:
        try:
            ipaddress.ip_address(config.host)
        except ValueError:
            valid_host = bool(_HOSTNAME_RE.fullmatch(config.host))
    check("host", valid_host, "Configured bind host is invalid.")
    check("port", 1 <= config.port <= 65535, "Configured port must be between 1 and 65535.")
    configured_server_ip = getattr(config, "server_ip", DEFAULT_SERVER_IP)
    lan_access_enabled = getattr(config, "lan_access_enabled", True)
    configured_lan_networks = getattr(config, "lan_networks", DEFAULT_LAN_NETWORKS)
    try:
        server_ip = ipaddress.ip_address(configured_server_ip)
        valid_server_ip = server_ip.version == 4 and server_ip.is_private
    except ValueError:
        server_ip = None
        valid_server_ip = False
    check("server_ip", valid_server_ip, "Configured POS server IP must be a private IPv4 address.")
    lan_networks = []
    try:
        lan_networks = [
            ipaddress.ip_network(item.strip(), strict=False)
            for item in configured_lan_networks.split(",")
            if item.strip()
        ]
        valid_lan_networks = bool(lan_networks) and all(network.is_private for network in lan_networks)
    except ValueError:
        valid_lan_networks = False
    check(
        "lan_networks",
        not lan_access_enabled or valid_lan_networks,
        "LAN staff access requires one or more valid private IP networks.",
    )
    check(
        "server_ip_in_lan",
        not lan_access_enabled or (
            valid_server_ip
            and valid_lan_networks
            and any(server_ip in network for network in lan_networks)
        ),
        "Configured POS server IP must belong to an allowed LAN network.",
    )

    if config.paths.database.is_file() and database_required:
        try:
            import sqlite3

            connection = sqlite3.connect(config.paths.database)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            has_settings = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'"
            ).fetchone()
            settings = {}
            if has_settings:
                settings = dict(connection.execute(
                    "SELECT key,value FROM settings "
                    "WHERE key IN ('backup_schedule_enabled','backup_schedule_time')"
                ).fetchall())
            connection.close()
            check("database_integrity", integrity == "ok", "SQLite integrity check failed.")
            check("foreign_keys", not foreign_keys, "SQLite foreign-key check failed.")
            schedule_enabled = settings.get("backup_schedule_enabled", "1")
            schedule_time = settings.get("backup_schedule_time", "02:00")
            check(
                "backup_schedule",
                schedule_enabled in {"0", "1"} and bool(_BACKUP_TIME_RE.fullmatch(schedule_time)),
                "In-process backup schedule must use enabled 0/1 and a 24-hour HH:MM time.",
            )
        except (OSError, sqlite3.DatabaseError) as exc:
            check("database_integrity", False, f"Cannot validate the SQLite database: {exc}")

    return {
        "ok": not fatal and not repairable,
        "fatal": fatal,
        "warnings": warnings,
        "repairable": repairable,
        "checks": checks,
        "runtime_root": str(config.paths.root),
        "database": str(config.paths.database),
        "host": config.host,
        "port": config.port,
        "app_version": config.app_version,
        "store_id": config.store_id,
        "server_ip": configured_server_ip,
        "lan_access_enabled": lan_access_enabled,
        "lan_networks": configured_lan_networks,
    }


def format_validation_report(report: Mapping[str, object]) -> str:
    lines = ["Runtime validation: " + ("OK" if report.get("ok") else "FAILED")]
    lines.append(f"Runtime root: {report.get('runtime_root')}")
    for message in report.get("fatal", []):
        lines.append(f"ERROR: {message}")
    for message in report.get("warnings", []):
        lines.append(f"WARNING: {message}")
    for message in report.get("repairable", []):
        lines.append(f"REPAIRABLE: {message}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the POS runtime configuration.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--create", action="store_true", help="Create configured runtime directories and secret key.")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    try:
        config = load_runtime_config(project_root)
        if args.create:
            config.paths.create_directories()
            config.paths.ensure_secret_key()
        report = validate_runtime(config)
    except (OSError, RuntimePathError) as exc:
        report = {"ok": False, "fatal": [str(exc)], "warnings": [], "repairable": [], "checks": {}}
    print(json.dumps(report, ensure_ascii=False) if args.as_json else format_validation_report(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
