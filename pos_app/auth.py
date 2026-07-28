import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import current_app, g, redirect, request, url_for

from .database import get_db


COOKIE_NAME = "pos_session"


def session_cookie_options():
    """Keep local HTTP usable while requiring Secure cookies for HTTPS requests."""

    return {"httponly": True, "samesite": "Lax", "secure": request.is_secure}


def utc_now():
    return datetime.now(timezone.utc)


def iso_time(value):
    return value.isoformat(timespec="seconds")


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(staff_id):
    token = secrets.token_urlsafe(32)
    now = utc_now()
    expires = now + timedelta(minutes=current_app.config["SESSION_TIMEOUT_MINUTES"])
    get_db().execute(
        """INSERT INTO staff_sessions
           (staff_id, token_hash, csrf_token, ip_address, user_agent, created_at, last_seen_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            staff_id, token_hash(token), secrets.token_urlsafe(24), request.remote_addr,
            request.user_agent.string[:500], iso_time(now), iso_time(now), iso_time(expires),
        ),
    )
    get_db().commit()
    return token


def delete_session(event_type="logout"):
    if not getattr(g, "session_row", None):
        return
    db = get_db()
    db.execute("DELETE FROM staff_sessions WHERE id = ?", (g.session_row["session_id"],))
    db.execute(
        "INSERT INTO login_events (staff_id, event_type, ip_address, created_at) VALUES (?, ?, ?, ?)",
        (g.staff["id"], event_type, request.remote_addr, iso_time(utc_now())),
    )
    db.commit()


def load_logged_in_staff():
    g.staff = None
    g.session_row = None
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return
    db = get_db()
    row = db.execute(
        """SELECT s.id AS session_id, s.created_at, s.expires_at, s.csrf_token,
                  st.id, st.display_name, st.must_change_pin, st.is_active,
                  r.code AS role_code, r.name_th AS role_name
           FROM staff_sessions s
           JOIN staff st ON st.id = s.staff_id
           JOIN roles r ON r.id = st.role_id
           WHERE s.token_hash = ?""",
        (token_hash(token),),
    ).fetchone()
    if row is None:
        return
    if not row["is_active"] or datetime.fromisoformat(row["expires_at"]) <= utc_now():
        db.execute("DELETE FROM staff_sessions WHERE id = ?", (row["session_id"],))
        db.execute(
            "INSERT INTO login_events (staff_id, event_type, ip_address, created_at) VALUES (?, 'session_expired', ?, ?)",
            (row["id"], request.remote_addr, iso_time(utc_now())),
        )
        db.commit()
        g.clear_session_cookie = True
        return
    g.staff = row
    g.session_row = row
    now = utc_now()
    db.execute(
        "UPDATE staff_sessions SET last_seen_at = ?, expires_at = ? WHERE id = ?",
        (iso_time(now), iso_time(now + timedelta(minutes=current_app.config["SESSION_TIMEOUT_MINUTES"])), row["session_id"]),
    )
    db.commit()


def add_cookie_cleanup(response):
    if getattr(g, "clear_session_cookie", False):
        response.delete_cookie(COOKIE_NAME)
    return response


def login_required(view):
    @wraps(view)
    def wrapped(**kwargs):
        if g.staff is None:
            return redirect(url_for("auth.login", next=request.path))
        if g.staff["must_change_pin"] and request.endpoint not in ("auth.change_pin", "auth.logout"):
            return redirect(url_for("auth.change_pin"))
        return view(**kwargs)
    return wrapped


def permission_required(permission_code):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(**kwargs):
            allowed = get_db().execute(
                """SELECT 1 FROM role_permissions rp
                   JOIN roles r ON r.id = rp.role_id
                   JOIN permissions p ON p.id = rp.permission_id
                   WHERE r.code = ? AND p.code = ?""",
                (g.staff["role_code"], permission_code),
            ).fetchone()
            if not allowed:
                return ("ไม่มีสิทธิ์เข้าถึงหน้านี้", 403)
            return view(**kwargs)
        return wrapped
    return decorator


def admin_required(view):
    """Restrict an account-security action to an authenticated administrator."""

    @wraps(view)
    @login_required
    def wrapped(**kwargs):
        if g.staff["role_code"] != "admin":
            return ("เฉพาะผู้ดูแลระบบเท่านั้น", 403)
        return view(**kwargs)
    return wrapped


def valid_csrf(value):
    return bool(g.session_row and value and hmac.compare_digest(value, g.session_row["csrf_token"]))


def init_app(app):
    app.before_request(load_logged_in_staff)
    app.after_request(add_cookie_cleanup)
