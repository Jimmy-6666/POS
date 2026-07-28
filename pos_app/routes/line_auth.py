"""LINE LIFF authentication API for the customer ordering surface."""

import secrets
from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import generate_password_hash

from ..auth import iso_time, utc_now
from ..customer_auth import (
    create_customer_session,
    delete_customer_cookie,
    line_auth_csrf,
    set_customer_cookie,
    valid_customer_csrf,
    valid_line_auth_csrf,
)
from ..database import get_db
from ..services.line_login import LineLoginError, LineLoginUnavailable, verify_id_token


bp = Blueprint("line_auth", __name__, url_prefix="/api/auth")


def _event(event_type, customer_id=None):
    get_db().execute(
        """INSERT INTO customer_login_events(customer_id,event_type,ip_address,created_at)
           VALUES(?,?,?,?)""",
        (customer_id, event_type, request.remote_addr, iso_time(utc_now())),
    )


def _too_many_failures():
    cutoff = iso_time(utc_now() - timedelta(minutes=current_app.config["LINE_LOGIN_FAILURE_WINDOW_MINUTES"]))
    return get_db().execute(
        """SELECT COUNT(*) FROM customer_login_events
           WHERE COALESCE(ip_address,'')=COALESCE(?, '') AND event_type='login_failed' AND created_at>=?""",
        (request.remote_addr, cutoff),
    ).fetchone()[0] >= current_app.config["LINE_LOGIN_FAILURE_LIMIT"]


def _customer_payload(customer):
    return {
        "id": customer["id"],
        "lineUserId": customer["line_user_id"],
        "displayName": customer["line_display_name"] or customer["display_name"] or "",
        "registeredName": customer["registered_name"] or "",
        "pictureUrl": customer["line_picture_url"] or "",
        "profileComplete": bool(customer["profile_completed"]),
    }


@bp.get("/config")
def config():
    configured = bool(
        current_app.config["LINE_LIFF_ID"]
        and current_app.config["LINE_LOGIN_CHANNEL_ID"]
        and current_app.config["APP_BASE_URL"]
    )
    return jsonify(
        configured=configured,
        liffId=current_app.config["LINE_LIFF_ID"],
        csrfToken=line_auth_csrf(),
    )


@bp.post("/line")
def line_login():
    if not valid_line_auth_csrf(request.headers.get("X-CSRF-Token")):
        return jsonify(error="คำขอยืนยันตัวตนไม่ถูกต้อง กรุณาเปิดหน้าใหม่แล้วลองอีกครั้ง"), 400
    if _too_many_failures():
        return jsonify(error="ลองยืนยันตัวตนหลายครั้งเกินไป กรุณารอ 15 นาทีแล้วลองใหม่"), 429
    payload = request.get_json(silent=True) or {}
    try:
        verified = verify_id_token(payload.get("idToken"), current_app.config["LINE_LOGIN_CHANNEL_ID"])
    except LineLoginError:
        _event("login_failed")
        get_db().commit()
        return jsonify(error="LINE ไม่สามารถยืนยันตัวตนได้ กรุณาเข้าสู่ระบบ LINE ใหม่แล้วลองอีกครั้ง"), 401
    except LineLoginUnavailable:
        current_app.logger.warning("LINE ID token verification unavailable", extra={"remote_addr": request.remote_addr})
        return jsonify(error="ระบบยืนยันตัวตน LINE ใช้งานไม่ได้ชั่วคราว กรุณาลองใหม่ภายหลัง"), 503

    db = get_db()
    now = iso_time(utc_now())
    customer = db.execute("SELECT * FROM customers WHERE line_user_id=?", (verified["line_user_id"],)).fetchone()
    if customer and not customer["is_active"]:
        return jsonify(error="บัญชีลูกค้านี้ถูกระงับการใช้งาน", code="suspended"), 403
    if customer:
        db.execute(
            """UPDATE customers SET line_display_name=?,line_picture_url=?,line_last_login_at=?,
               last_login_at=?,updated_at=? WHERE id=?""",
            (verified["display_name"], verified["picture_url"], now, now, now, customer["id"]),
        )
        customer_id = customer["id"]
    else:
        cursor = db.execute(
            """INSERT INTO customers
               (public_id,phone_normalized,display_name,pin_hash,is_guest,line_user_id,line_display_name,
                line_picture_url,line_created_at,line_last_login_at,created_at,last_login_at,updated_at)
               VALUES(?,?,?,?,0,?,?,?,?,?,?,?,?)""",
            (
                secrets.token_urlsafe(12), f"line:{verified['line_user_id']}", verified["display_name"],
                generate_password_hash(secrets.token_urlsafe(32)), verified["line_user_id"],
                verified["display_name"], verified["picture_url"], now, now, now, now, now,
            ),
        )
        customer_id = cursor.lastrowid
        db.execute(
            """INSERT INTO audit_logs(action,entity_type,entity_id,new_value,ip_address,created_at)
               VALUES('line_customer_created','customer',?,?,?,?)""",
            (str(customer_id), '{"source":"line_liff"}', request.remote_addr, now),
        )
    if getattr(g, "customer_session", None):
        db.execute("DELETE FROM customer_sessions WHERE id=?", (g.customer_session["session_id"],))
    _event("login_success", customer_id)
    token = create_customer_session(customer_id)
    csrf_token = db.execute(
        "SELECT csrf_token FROM customer_sessions WHERE customer_id=? ORDER BY id DESC LIMIT 1", (customer_id,)
    ).fetchone()[0]
    db.commit()
    customer = db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    response = jsonify(authenticated=True, customer=_customer_payload(customer), csrfToken=csrf_token)
    set_customer_cookie(response, token)
    return response


@bp.get("/me")
def me():
    if not getattr(g, "customer", None):
        return jsonify(authenticated=False)
    return jsonify(authenticated=True, customer=_customer_payload(g.customer))


@bp.post("/logout")
def logout():
    if not getattr(g, "customer_session", None):
        return jsonify(error="ไม่มีเซสชันลูกค้า"), 401
    if not valid_customer_csrf(request.headers.get("X-CSRF-Token")):
        return jsonify(error="คำขอไม่ถูกต้อง"), 400
    db = get_db()
    _event("logout", g.customer["id"])
    db.execute("DELETE FROM customer_sessions WHERE id=?", (g.customer_session["session_id"],))
    db.commit()
    response = jsonify(ok=True)
    delete_customer_cookie(response)
    return response
