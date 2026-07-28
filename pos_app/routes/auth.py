from urllib.parse import urlsplit

from flask import Blueprint, flash, g, make_response, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from datetime import timedelta

from ..auth import COOKIE_NAME, create_session, delete_session, iso_time, login_required, session_cookie_options, utc_now, valid_csrf
from ..database import get_db
from ..display_state import signal_display


bp = Blueprint("auth", __name__)


def safe_next_url(value):
    if not value:
        return None
    parts = urlsplit(value or "")
    return value if not parts.scheme and not parts.netloc and value.startswith("/") else None


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.staff:
        return redirect(url_for("pos.index"))
    db = get_db()
    staff_list = db.execute(
        """SELECT st.id, st.display_name, r.name_th AS role_name
           FROM staff st JOIN roles r ON r.id = st.role_id
           WHERE st.is_active = 1 ORDER BY st.display_name"""
    ).fetchall()
    if request.method == "POST":
        recent_failures = db.execute(
            """SELECT COUNT(*) FROM login_events
               WHERE event_type = 'login_failed' AND ip_address IS ? AND created_at >= ?""",
            (request.remote_addr, iso_time(utc_now() - timedelta(minutes=5))),
        ).fetchone()[0]
        if recent_failures >= 5:
            flash("ลองรหัสผิดหลายครั้ง กรุณารอ 5 นาทีแล้วลองใหม่", "error")
            return render_template("login.html", staff_list=staff_list, next_url=""), 429
        staff_id = request.form.get("staff_id", type=int)
        pin = request.form.get("pin", "")
        staff = db.execute("SELECT * FROM staff WHERE id = ? AND is_active = 1", (staff_id,)).fetchone()
        if not staff or len(pin) not in (4, 6) or not pin.isdigit() or not check_password_hash(staff["pin_hash"], pin):
            db.execute(
                "INSERT INTO login_events (staff_id, event_type, ip_address, created_at) VALUES (?, 'login_failed', ?, ?)",
                (staff_id if staff else None, request.remote_addr, iso_time(utc_now())),
            )
            db.commit()
            flash("ชื่อพนักงานหรือรหัส PIN ไม่ถูกต้อง", "error")
        else:
            token = create_session(staff["id"])
            db.execute(
                "INSERT INTO login_events (staff_id, event_type, ip_address, created_at) VALUES (?, 'login_success', ?, ?)",
                (staff["id"], request.remote_addr, iso_time(utc_now())),
            )
            db.commit()
            response = make_response(redirect(safe_next_url(request.form.get("next")) or url_for("pos.index")))
            response.set_cookie(COOKIE_NAME, token, **session_cookie_options())
            signal_display("fullscreen")
            return response
    return render_template("login.html", staff_list=staff_list, next_url=safe_next_url(request.args.get("next")) or "")


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
