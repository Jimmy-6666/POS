"""Human-readable local diagnostics for the browser receipt print path."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from flask import current_app


MAX_LOG_BYTES = 512 * 1024
KEEP_LOG_BYTES = 256 * 1024


def diagnostic_log_path() -> Path:
    """Return the shared POS-user-readable runtime log without exposing tokens."""

    runtime_paths = current_app.config["RUNTIME_PATHS"]
    return runtime_paths.root / "pos-desktop" / "print-diagnostics.log"


def _safe(value: object, *, limit: int = 180) -> str:
    text = str(value if value is not None else "-")
    text = text.replace("\r", " ").replace("\n", " ").replace("|", "/")
    return text[:limit]


def record_print_event(event: str, *, source: str, details: Mapping[str, object] | None = None) -> None:
    """Append a short best-effort line; logging must never affect a sale or print."""

    try:
        path = diagnostic_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.stat().st_size > MAX_LOG_BYTES:
            with path.open("rb") as handle:
                handle.seek(-KEEP_LOG_BYTES, 2)
                tail = handle.read()
            path.write_bytes(tail[tail.find(b"\n") + 1:] if b"\n" in tail else tail)
        parts = [
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            f"source={_safe(source, limit=40)}",
            f"event={_safe(event, limit=60)}",
        ]
        for key, value in (details or {}).items():
            if value not in (None, ""):
                parts.append(f"{_safe(key, limit=40)}={_safe(value)}")
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(" | ".join(parts) + "\n")
    except OSError:
        # A completed transaction must not fail if a diagnostics file is locked.
        return
