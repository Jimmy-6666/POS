import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from functools import wraps

from flask import current_app, g, redirect, request, url_for

from .auth import iso_time, token_hash, utc_now
from .database import get_db


CUSTOMER_COOKIE_NAME = "online_customer_session"
PHONE_RE = re.compile(r"^0[689]\d{8}$")


def normalize_phone(value):
    phone = re.sub(r"\D", "", str(value or ""))
    if phone.startswith("66") and len(phone) == 11:
        phone = "0" + phone[2:]
    if not PHONE_RE.fullmatch(phone):
        raise ValueError("กรุณากรอกหมายเลขโทรศัพท์มือถือไทยให้ถูกต้อง")
    return phone


def phone_fingerprint(phone):
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()


def create_customer_session(customer_id):
    token = secrets.token_urlsafe(32)
    now = utc_now()
    expires = now + timedelta(days=current_app.config.get("CUSTOMER_SESSION_DAYS", 14))
    db = get_db()
    db.execute(
        """INSERT INTO customer_sessions
           (customer_id,token_hash,csrf_token,ip_address,user_agent,created_at,last_seen_at,expires_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (customer_id, token_hash(token), secrets.token_urlsafe(24), request.remote_addr,
         request.user_agent.string[:500], iso_time(now), iso_time(now), iso_time(expires)),
    )
    return token


def load_logged_in_customer():
    g.customer = None
    g.customer_session = None
    token = request.cookies.get(CUSTOMER_COOKIE_NAME)
    if not token:
        return
    db = get_db()
    row = db.execute(
        """SELECT cs.id AS session_id,cs.csrf_token,cs.expires_at,c.*
           FROM customer_sessions cs JOIN customers c ON c.id=cs.customer_id
           WHERE cs.token_hash=?""",
        (token_hash(token),),
    ).fetchone()
    if not row:
        return
    if not row["is_active"] or row["expires_at"] <= iso_time(utc_now()):
        db.execute("DELETE FROM customer_sessions WHERE id=?", (row["session_id"],))
        db.commit()
        g.clear_customer_cookie = True
        return
    g.customer = row
    g.customer_session = row
    now = utc_now()
    db.execute(
        "UPDATE customer_sessions SET last_seen_at=?,expires_at=? WHERE id=?",
        (iso_time(now), iso_time(now + timedelta(days=current_app.config.get("CUSTOMER_SESSION_DAYS", 14))), row["session_id"]),
    )
    db.commit()


def customer_login_required(view):
    @wraps(view)
    def wrapped(**kwargs):
        if g.customer is None:
            return redirect(url_for("online.customer_login", next=request.path))
        if g.customer["must_change_pin"] and request.endpoint not in ("online.customer_change_pin", "online.customer_logout"):
            return redirect(url_for("online.customer_change_pin"))
        return view(**kwargs)
    return wrapped


def valid_customer_csrf(value):
    return bool(g.customer_session and value and hmac.compare_digest(value, g.customer_session["csrf_token"]))


def add_customer_cookie_cleanup(response):
    if getattr(g, "clear_customer_cookie", False):
        response.delete_cookie(CUSTOMER_COOKIE_NAME)
    return response


def init_app(app):
    app.before_request(load_logged_in_customer)
    app.after_request(add_customer_cookie_cleanup)
