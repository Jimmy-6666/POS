"""Host-based separation for the approved public customer and Admin surfaces."""

from __future__ import annotations

import re
from ipaddress import ip_address, ip_network
from datetime import datetime, timezone

from flask import abort, current_app, g, request

from .database import get_db


_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
_CUSTOMER_ENDPOINT_PREFIXES = ("online.", "line_auth.")


def normalize_public_host(value: str | None) -> str:
    """Return a configured DNS hostname or fail closed on unsafe values."""

    host = (value or "").strip().lower().rstrip(".")
    if not host:
        return ""
    if not _HOST_RE.fullmatch(host):
        raise ValueError("Public host settings must be DNS hostnames without a scheme, path, or port.")
    return host


def request_hostname() -> str:
    """Return the normalized hostname from the already-routed request."""

    return request.host.partition(":")[0].lower().rstrip(".")


def public_surface() -> str | None:
    host = request_hostname()
    if host and host == current_app.config.get("POS_PUBLIC_ORDER_HOST", ""):
        return "customer"
    if host and host == current_app.config.get("POS_ADMIN_HOST", ""):
        return "admin"
    return None


def is_remote_admin_request() -> bool:
    return public_surface() == "admin"


def is_local_request() -> bool:
    try:
        return ip_address(request.remote_addr or "").is_loopback
    except ValueError:
        return False


def is_allowed_lan_request() -> bool:
    """Return whether the direct client belongs to an explicitly allowed LAN."""

    if is_local_request():
        return True
    if not current_app.config.get("POS_LAN_ACCESS_ENABLED"):
        return False
    try:
        client = ip_address(request.remote_addr or "")
        networks = (
            ip_network(item.strip(), strict=False)
            for item in str(current_app.config.get("POS_LAN_NETWORKS", "")).split(",")
            if item.strip()
        )
        return any(client in network for network in networks)
    except ValueError:
        return False


def _is_customer_endpoint(endpoint: str | None) -> bool:
    return bool(endpoint and (endpoint == "static" or endpoint.startswith(_CUSTOMER_ENDPOINT_PREFIXES)))


def _is_admin_blocked_endpoint(endpoint: str | None) -> bool:
    return bool(
        endpoint
        and (
            endpoint.startswith(_CUSTOMER_ENDPOINT_PREFIXES)
            or endpoint == "main.health"
            or endpoint.startswith("print_agent.")
        )
    )


def _remote_admin_session_is_two_factor_verified() -> bool:
    if not g.staff["two_factor_verified_at"]:
        return False
    return bool(get_db().execute(
        "SELECT 1 FROM staff_two_factor WHERE staff_id=? AND is_enabled=1",
        (g.staff["id"],),
    ).fetchone())


def _revoke_unverified_remote_admin_session():
    db = get_db()
    db.execute("DELETE FROM staff_sessions WHERE id=?", (g.session_row["session_id"],))
    db.execute(
        """INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,ip_address,created_at)
           VALUES(?,?,?,?,?,?)""",
        (
            g.staff["id"], "remote_admin_session_revoked_missing_two_factor", "staff_session",
            str(g.session_row["session_id"]), request.remote_addr,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    db.commit()
    g.staff = None
    g.session_row = None
    g.clear_session_cookie = True


def enforce_public_host_access():
    """Keep customer and remote-Admin requests inside their approved route sets."""

    surface = public_surface()
    if surface == "customer":
        if not _is_customer_endpoint(request.endpoint):
            abort(404)
        return None
    if surface is None:
        if not is_allowed_lan_request() and (request.endpoint == "auth.login" or getattr(g, "staff", None)):
            abort(403)
        return None
    if _is_admin_blocked_endpoint(request.endpoint):
        abort(404)
    if getattr(g, "staff", None):
        if g.staff["role_code"] != "admin":
            abort(403)
        if not _remote_admin_session_is_two_factor_verified():
            _revoke_unverified_remote_admin_session()
    return None


def init_app(app):
    app.before_request(enforce_public_host_access)
