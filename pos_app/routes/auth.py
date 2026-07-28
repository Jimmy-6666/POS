import json
import secrets
from urllib.parse import urlsplit

from flask import Blueprint, flash, g, make_response, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from datetime import timedelta

from ..auth import (COOKIE_NAME, admin_required, clear_login_csrf, create_session,
                    delete_session, iso_time, login_csrf_token, login_required,
                    session_cookie_options, token_hash, utc_now, valid_csrf,
                    valid_login_csrf)
from ..database import get_db
from ..display_state import signal_display
from ..public_host_access import is_remote_admin_request
from ..services.admin_two_factor import (TwoFactorError, consume_recovery_code,
                                         decrypt_secret, encrypt_secret,
                                         issuer_name, new_recovery_codes,
                                         new_totp_secret, provisioning_uri,
                                         qr_svg_data_uri, store_recovery_codes,
                                         verified_totp_counter)


bp = Blueprint("auth", __name__)
TWO_FACTOR_COOKIE_NAME = "pos_2fa_challenge"
TWO_FACTOR_CHALLENGE_MINUTES = 5
TWO_FACTOR_FAILURE_LIMIT = 5
TWO_FACTOR_FAILURE_WINDOW_MINUTES = 5


def safe_next_url(value):
    if not value:
        return None
    parts = urlsplit(value or "")
    return value if not parts.scheme and not parts.netloc and value.startswith("/") else None


def _two_factor_record(db, staff_id):
    return db.execute(
        "SELECT * FROM staff_two_factor WHERE staff_id=? AND is_enabled=1",
        (staff_id,),
    ).fetchone()


def _create_two_factor_challenge(db, staff_id, next_url):
    token = secrets.token_urlsafe(32)
    now = utc_now()
    db.execute("DELETE FROM staff_two_factor_challenges WHERE expires_at<=?", (iso_time(now),))
    db.execute(
        """INSERT INTO staff_two_factor_challenges
           (staff_id,token_hash,csrf_token,next_url,ip_address,user_agent,created_at,expires_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            staff_id, token_hash(token), secrets.token_urlsafe(24), safe_next_url(next_url),
            request.remote_addr, request.user_agent.string[:500], iso_time(now),
            iso_time(now + timedelta(minutes=TWO_FACTOR_CHALLENGE_MINUTES)),
        ),
    )
    return token


def _current_two_factor_challenge(db):
    token = request.cookies.get(TWO_FACTOR_COOKIE_NAME)
    if not token:
        return None
    row = db.execute(
        """SELECT c.*,st.display_name,st.pin_hash,st.is_active,r.code AS role_code
           FROM staff_two_factor_challenges c JOIN staff st ON st.id=c.staff_id
           JOIN roles r ON r.id=st.role_id WHERE c.token_hash=?""",
        (token_hash(token),),
    ).fetchone()
    if not row or row["expires_at"] <= iso_time(utc_now()) or not row["is_active"] or row["role_code"] != "admin":
        return None
    if row["ip_address"] and row["ip_address"] != request.remote_addr:
        return None
    return row


def _remove_two_factor_challenge(db, challenge_id):
    db.execute("DELETE FROM staff_two_factor_challenges WHERE id=?", (challenge_id,))


def _audit_two_factor(db, staff_id, action, detail=None):
    db.execute(
        """INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,new_value,ip_address,created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (
            staff_id, action, "staff_two_factor", str(staff_id),
            json.dumps(detail, ensure_ascii=False) if detail else None,
            request.remote_addr, iso_time(utc_now()),
        ),
    )


def _two_factor_rate_limited(db, staff_id):
    cutoff = iso_time(utc_now() - timedelta(minutes=TWO_FACTOR_FAILURE_WINDOW_MINUTES))
    return db.execute(
        """SELECT COUNT(*) FROM audit_logs WHERE staff_id=? AND action='admin_two_factor_failed'
           AND ip_address IS ? AND created_at>=?""",
        (staff_id, request.remote_addr, cutoff),
    ).fetchone()[0] >= TWO_FACTOR_FAILURE_LIMIT


def _verify_admin_second_factor(db, record, value):
    try:
        secret = decrypt_secret(record["secret_encrypted"])
    except TwoFactorError:
        return False
    counter = verified_totp_counter(secret, value)
    if counter is not None:
        if record["last_totp_counter"] is not None and counter <= record["last_totp_counter"]:
            return False
        db.execute(
            "UPDATE staff_two_factor SET last_totp_counter=?,updated_at=CURRENT_TIMESTAMP WHERE staff_id=?",
            (counter, record["staff_id"]),
        )
        return True
    return consume_recovery_code(db, record["staff_id"], value, iso_time(utc_now()))


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.staff:
        return redirect(url_for("pos.index"))
    db = get_db()
    remote_admin = is_remote_admin_request()
    staff_list = db.execute(
        """SELECT st.id, st.display_name, r.name_th AS role_name
           FROM staff st JOIN roles r ON r.id = st.role_id
           WHERE st.is_active = 1""" + (" AND r.code = 'admin'" if remote_admin else "") + " ORDER BY st.display_name"
    ).fetchall()
    login_csrf = login_csrf_token()
    if request.method == "POST":
        if not valid_login_csrf(request.form.get("login_csrf_token")):
            return ("คำขอเข้าสู่ระบบไม่ถูกต้อง กรุณาโหลดหน้าเข้าสู่ระบบใหม่", 400)
        recent_failures = db.execute(
            """SELECT COUNT(*) FROM login_events
               WHERE event_type = 'login_failed' AND ip_address IS ? AND created_at >= ?""",
            (request.remote_addr, iso_time(utc_now() - timedelta(minutes=5))),
        ).fetchone()[0]
        if recent_failures >= 5:
            flash("ลองรหัสผิดหลายครั้ง กรุณารอ 5 นาทีแล้วลองใหม่", "error")
            return render_template(
                "login.html", staff_list=staff_list, next_url="", remote_admin=remote_admin,
                login_csrf_token=login_csrf,
            ), 429
        staff_id = request.form.get("staff_id", type=int)
        pin = request.form.get("pin", "")
        staff = db.execute(
            """SELECT st.*, r.code AS role_code FROM staff st
               JOIN roles r ON r.id = st.role_id WHERE st.id = ? AND st.is_active = 1""",
            (staff_id,),
        ).fetchone()
        if (not staff or (remote_admin and staff["role_code"] != "admin")
                or len(pin) not in (4, 6) or not pin.isdigit() or not check_password_hash(staff["pin_hash"], pin)):
            db.execute(
                "INSERT INTO login_events (staff_id, event_type, ip_address, created_at) VALUES (?, 'login_failed', ?, ?)",
                (staff_id if staff else None, request.remote_addr, iso_time(utc_now())),
            )
            db.commit()
            flash("ชื่อพนักงานหรือรหัส PIN ไม่ถูกต้อง", "error")
        else:
            two_factor = _two_factor_record(db, staff["id"])
            if remote_admin and not two_factor:
                _audit_two_factor(db, staff["id"], "remote_admin_two_factor_enrollment_required")
                db.commit()
                flash("การเข้าใช้จากภายนอกต้องเปิดการยืนยันสองชั้นก่อน กรุณาเข้าสู่ระบบจากเครือข่ายร้านเพื่อตั้งค่า", "error")
                return render_template(
                    "login.html", staff_list=staff_list, next_url="", remote_admin=True,
                    login_csrf_token=login_csrf,
                ), 403
            if two_factor:
                challenge = _create_two_factor_challenge(db, staff["id"], request.form.get("next"))
                db.commit()
                clear_login_csrf()
                response = make_response(redirect(url_for("auth.verify_two_factor")))
                response.set_cookie(TWO_FACTOR_COOKIE_NAME, challenge, **session_cookie_options())
                return response
            token = create_session(staff["id"])
            db.execute(
                "INSERT INTO login_events (staff_id, event_type, ip_address, created_at) VALUES (?, 'login_success', ?, ?)",
                (staff["id"], request.remote_addr, iso_time(utc_now())),
            )
            db.commit()
            clear_login_csrf()
            response = make_response(redirect(safe_next_url(request.form.get("next")) or url_for("pos.index")))
            response.set_cookie(COOKIE_NAME, token, **session_cookie_options())
            signal_display("fullscreen")
            return response
    return render_template(
        "login.html", staff_list=staff_list,
        next_url=safe_next_url(request.args.get("next")) or "", remote_admin=remote_admin,
        login_csrf_token=login_csrf,
    )


@bp.route("/login/2fa", methods=("GET", "POST"))
def verify_two_factor():
    db = get_db()
    challenge = _current_two_factor_challenge(db)
    if not challenge:
        response = make_response(redirect(url_for("auth.login")))
        response.delete_cookie(TWO_FACTOR_COOKIE_NAME, **session_cookie_options())
        return response
    if request.method == "POST":
        if not request.form.get("csrf_token") or request.form.get("csrf_token") != challenge["csrf_token"]:
            return ("คำขอไม่ถูกต้อง", 400)
        if _two_factor_rate_limited(db, challenge["staff_id"]):
            _audit_two_factor(db, challenge["staff_id"], "admin_two_factor_failed", {"reason": "rate_limited"})
            db.commit()
            return render_template("two_factor_login.html", challenge=challenge), 429
        record = _two_factor_record(db, challenge["staff_id"])
        if not record or not _verify_admin_second_factor(db, record, request.form.get("code")):
            db.execute("UPDATE staff_two_factor_challenges SET attempts=attempts+1 WHERE id=?", (challenge["id"],))
            _audit_two_factor(db, challenge["staff_id"], "admin_two_factor_failed", {"reason": "invalid_factor"})
            db.commit()
            flash("รหัสยืนยันไม่ถูกต้องหรือถูกใช้แล้ว", "error")
            return render_template("two_factor_login.html", challenge=challenge)
        _remove_two_factor_challenge(db, challenge["id"])
        db.commit()
        token = create_session(challenge["staff_id"], two_factor_verified=True)
        db.execute(
            "INSERT INTO login_events(staff_id,event_type,ip_address,created_at) VALUES(?, 'login_success', ?, ?)",
            (challenge["staff_id"], request.remote_addr, iso_time(utc_now())),
        )
        _audit_two_factor(db, challenge["staff_id"], "admin_login_success")
        db.commit()
        response = make_response(redirect(challenge["next_url"] or url_for("pos.index")))
        response.set_cookie(COOKIE_NAME, token, **session_cookie_options())
        response.delete_cookie(TWO_FACTOR_COOKIE_NAME, **session_cookie_options())
        signal_display("fullscreen")
        return response
    return render_template("two_factor_login.html", challenge=challenge)


@bp.post("/logout")
@login_required
def logout():
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง กรุณาลองใหม่", 400)
    delete_session()
    signal_display("normal")
    response = make_response(redirect(url_for("auth.login")))
    response.delete_cookie(COOKIE_NAME, **session_cookie_options())
    return response


@bp.route("/change-pin", methods=("GET", "POST"))
@login_required
def change_pin():
    if request.method == "POST":
        current_pin = request.form.get("current_pin", "")
        new_pin = request.form.get("new_pin", "")
        confirm_pin = request.form.get("confirm_pin", "")
        staff = get_db().execute("SELECT pin_hash FROM staff WHERE id = ?", (g.staff["id"],)).fetchone()
        error = None
        if not valid_csrf(request.form.get("csrf_token")):
            error = "คำขอไม่ถูกต้อง กรุณาลองใหม่"
        elif not check_password_hash(staff["pin_hash"], current_pin):
            error = "รหัส PIN ปัจจุบันไม่ถูกต้อง"
        elif len(new_pin) not in (4, 6) or not new_pin.isdigit():
            error = "รหัส PIN ใหม่ต้องเป็นตัวเลข 4 หรือ 6 หลัก"
        elif new_pin != confirm_pin:
            error = "รหัส PIN ใหม่ทั้งสองช่องไม่ตรงกัน"
        elif new_pin == current_pin:
            error = "รหัส PIN ใหม่ต้องไม่ซ้ำกับรหัสเดิม"
        if error:
            flash(error, "error")
        else:
            db = get_db()
            db.execute(
                "UPDATE staff SET pin_hash = ?, must_change_pin = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (generate_password_hash(new_pin), g.staff["id"]),
            )
            db.execute(
                """INSERT INTO audit_logs (staff_id, action, entity_type, entity_id, ip_address, created_at)
                   VALUES (?, 'change_pin', 'staff', ?, ?, ?)""",
                (g.staff["id"], str(g.staff["id"]), request.remote_addr, iso_time(utc_now())),
            )
            db.commit()
            flash("เปลี่ยนรหัส PIN เรียบร้อยแล้ว", "success")
            return redirect(url_for("pos.index"))
    return render_template("change_pin.html")


@bp.get("/account/security")
@admin_required
def account_security():
    db = get_db()
    record = db.execute("SELECT * FROM staff_two_factor WHERE staff_id=?", (g.staff["id"],)).fetchone()
    other_admins = db.execute(
        """SELECT st.id,st.display_name,f.is_enabled FROM staff st JOIN roles r ON r.id=st.role_id
           LEFT JOIN staff_two_factor f ON f.staff_id=st.id
           WHERE r.code='admin' AND st.is_active=1 AND st.id<>? ORDER BY st.display_name""",
        (g.staff["id"],),
    ).fetchall()
    return render_template("account_security.html", record=record, other_admins=other_admins)


@bp.get("/account/security/setup")
@admin_required
def setup_two_factor():
    db = get_db()
    record = db.execute("SELECT * FROM staff_two_factor WHERE staff_id=?", (g.staff["id"],)).fetchone()
    if record and record["is_enabled"]:
        return redirect(url_for("auth.account_security"))
    if record and record["pending_secret_encrypted"]:
        secret = decrypt_secret(record["pending_secret_encrypted"])
    else:
        secret = new_totp_secret()
        db.execute(
            """INSERT INTO staff_two_factor(staff_id,pending_secret_encrypted,updated_at)
               VALUES(?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(staff_id) DO UPDATE SET pending_secret_encrypted=excluded.pending_secret_encrypted,
               updated_at=CURRENT_TIMESTAMP""",
            (g.staff["id"], encrypt_secret(secret)),
        )
        db.commit()
    issuer = issuer_name(db)
    uri = provisioning_uri(secret, g.staff["display_name"], issuer)
    return render_template(
        "two_factor_setup.html", secret=secret, issuer=issuer, qr_data_uri=qr_svg_data_uri(uri)
    )


@bp.post("/account/security/enable")
@admin_required
def enable_two_factor():
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    db = get_db()
    record = db.execute("SELECT * FROM staff_two_factor WHERE staff_id=?", (g.staff["id"],)).fetchone()
    if not record or record["is_enabled"]:
        return redirect(url_for("auth.account_security"))
    try:
        secret = decrypt_secret(record["pending_secret_encrypted"])
    except TwoFactorError:
        flash("กรุณาเริ่มตั้งค่าแอปยืนยันตัวตนใหม่", "error")
        return redirect(url_for("auth.setup_two_factor"))
    counter = verified_totp_counter(secret, request.form.get("code"))
    if counter is None:
        flash("รหัสยืนยันไม่ถูกต้อง", "error")
        return redirect(url_for("auth.setup_two_factor"))
    codes = new_recovery_codes()
    now = iso_time(utc_now())
    db.execute("BEGIN IMMEDIATE")
    db.execute(
        """UPDATE staff_two_factor SET secret_encrypted=?,pending_secret_encrypted=NULL,is_enabled=1,
           last_totp_counter=?,enabled_at=?,updated_at=? WHERE staff_id=?""",
        (encrypt_secret(secret), counter, now, now, g.staff["id"]),
    )
    store_recovery_codes(db, g.staff["id"], codes, now)
    _audit_two_factor(db, g.staff["id"], "admin_two_factor_enabled")
    db.commit()
    return render_template("two_factor_recovery_codes.html", codes=codes)


def _verify_current_pin(db, pin):
    row = db.execute("SELECT pin_hash FROM staff WHERE id=?", (g.staff["id"],)).fetchone()
    return bool(row and check_password_hash(row["pin_hash"], pin or ""))


@bp.post("/account/security/recovery-codes")
@admin_required
def regenerate_recovery_codes():
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    db = get_db()
    record = _two_factor_record(db, g.staff["id"])
    if not record or not _verify_current_pin(db, request.form.get("current_pin")):
        flash("PIN ปัจจุบันไม่ถูกต้อง", "error")
        return redirect(url_for("auth.account_security"))
    if not _verify_admin_second_factor(db, record, request.form.get("code")):
        _audit_two_factor(db, g.staff["id"], "admin_two_factor_failed", {"reason": "recovery_regeneration"})
        db.commit()
        flash("รหัสยืนยันไม่ถูกต้องหรือถูกใช้แล้ว", "error")
        return redirect(url_for("auth.account_security"))
    codes = new_recovery_codes()
    store_recovery_codes(db, g.staff["id"], codes, iso_time(utc_now()))
    _audit_two_factor(db, g.staff["id"], "admin_recovery_codes_regenerated")
    db.commit()
    return render_template("two_factor_recovery_codes.html", codes=codes)


@bp.post("/account/security/disable")
@admin_required
def disable_two_factor():
    if is_remote_admin_request():
        return ("การปิดการยืนยันสองชั้นต้องทำจากเครือข่ายร้าน", 403)
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    db = get_db()
    record = _two_factor_record(db, g.staff["id"])
    if not record or not _verify_current_pin(db, request.form.get("current_pin")):
        flash("PIN ปัจจุบันไม่ถูกต้อง", "error")
        return redirect(url_for("auth.account_security"))
    if not _verify_admin_second_factor(db, record, request.form.get("code")):
        _audit_two_factor(db, g.staff["id"], "admin_two_factor_failed", {"reason": "disable"})
        db.commit()
        flash("รหัสยืนยันไม่ถูกต้องหรือถูกใช้แล้ว", "error")
        return redirect(url_for("auth.account_security"))
    db.execute(
        """UPDATE staff_two_factor SET secret_encrypted=NULL,pending_secret_encrypted=NULL,is_enabled=0,
           last_totp_counter=NULL,enabled_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE staff_id=?""",
        (g.staff["id"],),
    )
    db.execute("DELETE FROM staff_two_factor_recovery_codes WHERE staff_id=?", (g.staff["id"],))
    _audit_two_factor(db, g.staff["id"], "admin_two_factor_disabled")
    db.commit()
    flash("ปิดการยืนยันตัวตนสองชั้นแล้ว", "success")
    return redirect(url_for("auth.account_security"))


@bp.post("/account/security/admin-recovery")
@admin_required
def administrative_two_factor_recovery():
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    db = get_db()
    target_id = request.form.get("target_staff_id", type=int)
    record = _two_factor_record(db, g.staff["id"])
    target = db.execute(
        """SELECT st.id FROM staff st JOIN roles r ON r.id=st.role_id
           WHERE st.id=? AND st.is_active=1 AND r.code='admin' AND st.id<>?""",
        (target_id, g.staff["id"]),
    ).fetchone()
    if not target or not record or not _verify_current_pin(db, request.form.get("current_pin")):
        flash("ข้อมูลสำหรับกู้คืนไม่ถูกต้อง", "error")
        return redirect(url_for("auth.account_security"))
    if not _verify_admin_second_factor(db, record, request.form.get("code")):
        _audit_two_factor(db, g.staff["id"], "admin_two_factor_failed", {"reason": "administrative_recovery"})
        db.commit()
        flash("รหัสยืนยันไม่ถูกต้องหรือถูกใช้แล้ว", "error")
        return redirect(url_for("auth.account_security"))
    db.execute(
        """UPDATE staff_two_factor SET secret_encrypted=NULL,pending_secret_encrypted=NULL,is_enabled=0,
           last_totp_counter=NULL,enabled_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE staff_id=?""",
        (target_id,),
    )
    db.execute("DELETE FROM staff_two_factor_recovery_codes WHERE staff_id=?", (target_id,))
    db.execute("DELETE FROM staff_two_factor_challenges WHERE staff_id=?", (target_id,))
    db.execute("DELETE FROM staff_sessions WHERE staff_id=?", (target_id,))
    _audit_two_factor(db, g.staff["id"], "admin_two_factor_recovered", {"target_staff_id": target_id})
    db.commit()
    flash("รีเซ็ตการยืนยันสองชั้นของผู้ดูแลระบบแล้ว", "success")
    return redirect(url_for("auth.account_security"))
