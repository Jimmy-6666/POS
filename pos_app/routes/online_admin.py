import json
import secrets
from datetime import datetime, timezone

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash

from ..auth import permission_required, valid_csrf
from ..database import get_db
from ..services.money import baht_to_satang


bp = Blueprint("online_admin", __name__, url_prefix="/online-admin")
def audit(action, entity_type, entity_id, old=None, new=None):
    get_db().execute(
        """INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (g.staff["id"], action, entity_type, str(entity_id), json.dumps(old, ensure_ascii=False) if old is not None else None,
         json.dumps(new, ensure_ascii=False) if new is not None else None, request.remote_addr,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )


@bp.route("/settings", methods=("GET", "POST"))
@permission_required("online_settings.manage")
def settings():
    db = get_db()
    section = request.args.get("section", "schedule")
    if section not in {"schedule", "locations"}:
        section = "schedule"
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        try:
            values = {
                "online_ordering_enabled": "1" if request.form.get("online_ordering_enabled") else "0",
                "online_allow_negative_stock": "1" if request.form.get("online_allow_negative_stock") else "0",
                "online_auto_expiry": "1" if request.form.get("online_auto_expiry") else "0",
                "online_closed_message": request.form.get("online_closed_message", "").strip(),
                "online_minimum_order_satang": str(baht_to_satang(request.form.get("online_minimum_order") or 0)),
                "online_order_expiry_minutes": str(max(5, int(request.form.get("online_order_expiry_minutes") or 60))),
                "online_max_order_quantity": str(max(1, int(request.form.get("online_max_order_quantity") or 50))),
                "online_ordering_start": request.form.get("online_ordering_start", "").strip(),
                "online_ordering_end": request.form.get("online_ordering_end", "").strip(),
                "online_contact": request.form.get("online_contact", "").strip(),
                "online_contact_line": request.form.get("online_contact_line", "").strip() or "@114rbvoi",
                "online_contact_phone": request.form.get("online_contact_phone", "").strip() or "09X-XXX-XXXX",
            }
            db.execute("BEGIN IMMEDIATE")
            for key, value in values.items():
                db.execute(
                    "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",
                    (key, value),
                )
            audit("update_online_settings", "online_settings", "global", new={k: v for k, v in values.items() if "account_number" not in k})
            db.commit()
            flash("บันทึกเวลาเปิด-ปิดร้านแล้ว", "success")
            return redirect(url_for("online_admin.settings", section="schedule"))
        except Exception as exc:
            db.rollback()
            flash(str(exc), "error")
    values = dict(db.execute("SELECT key,value FROM settings").fetchall())
    locations = db.execute("SELECT * FROM delivery_locations ORDER BY sort_order,name").fetchall()
    return render_template(
        "online/admin_settings.html", settings=values, locations=locations,
        section=section,
    )


@bp.post("/locations")
@permission_required("online_settings.manage")
def save_location():
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    db = get_db()
    location_id = request.form.get("location_id", type=int)
    name = request.form.get("name", "").strip()
    if not name:
        flash("กรุณาระบุชื่อสถานที่", "error")
        return redirect(url_for("online_admin.settings", section="locations"))
    data = {
        "name": name,
        "is_active": 1 if request.form.get("is_active") else 0,
        "is_available": 1 if request.form.get("is_available") else 0,
        "sort_order": int(request.form.get("sort_order") or 0),
        "delivery_fee_satang": baht_to_satang(request.form.get("delivery_fee") or 0),
        "minimum_order_satang": baht_to_satang(request.form.get("minimum_order") or 0),
        "room_required": 1 if request.form.get("room_required") else 0,
        "estimated_note": request.form.get("estimated_note", "").strip() or None,
        "instructions": request.form.get("instructions", "").strip() or None,
    }
    try:
        db.execute("BEGIN IMMEDIATE")
        if location_id:
            old = db.execute("SELECT * FROM delivery_locations WHERE id=?", (location_id,)).fetchone()
            if not old:
                return ("ไม่พบสถานที่", 404)
            db.execute(
                """UPDATE delivery_locations SET name=:name,is_active=:is_active,is_available=:is_available,
                   sort_order=:sort_order,delivery_fee_satang=:delivery_fee_satang,minimum_order_satang=:minimum_order_satang,
                   room_required=:room_required,estimated_note=:estimated_note,instructions=:instructions,
                   updated_at=CURRENT_TIMESTAMP WHERE id=:id""",
                {**data, "id": location_id},
            )
            audit("update_delivery_location", "delivery_location", location_id, dict(old), data)
        else:
            cursor = db.execute(
                """INSERT INTO delivery_locations(name,is_active,is_available,sort_order,delivery_fee_satang,
                   minimum_order_satang,room_required,estimated_note,instructions)
                   VALUES(:name,:is_active,:is_available,:sort_order,:delivery_fee_satang,
                   :minimum_order_satang,:room_required,:estimated_note,:instructions)""",
                data,
            )
            location_id = cursor.lastrowid
            audit("create_delivery_location", "delivery_location", location_id, new=data)
        db.commit()
        flash("บันทึกสถานที่จัดส่งแล้ว", "success")
    except Exception:
        db.rollback()
        flash("ชื่อสถานที่ซ้ำหรือข้อมูลไม่ถูกต้อง", "error")
    return redirect(url_for("online_admin.settings", section="locations"))


@bp.get("/customers")
@permission_required("online_customers.manage")
def customers():
    query = request.args.get("q", "").strip()
    params = []
    where = ""
    if query:
        term = f"%{query}%"
        where = """WHERE c.phone_normalized LIKE ? OR COALESCE(c.registered_name,'') LIKE ?
                   OR COALESCE(c.line_display_name,'') LIKE ? OR c.public_id LIKE ?"""
        params = [term, term, term, term]
    rows = get_db().execute(
        f"""SELECT c.*,(SELECT COUNT(*) FROM online_orders o WHERE o.customer_id=c.id) AS order_count
            FROM customers c {where} ORDER BY c.created_at DESC""",
        params,
    ).fetchall()
    return render_template("online/customers.html", customers=rows, query=query)


@bp.post("/customers/<int:customer_id>/reset-pin")
@permission_required("online_customers.manage")
def reset_customer_pin(customer_id):
    return ("ระบบ PIN ลูกค้าถูกยกเลิกแล้ว", 410)


@bp.post("/customers/<int:customer_id>/delete")
@permission_required("online_customers.manage")
def delete_customer(customer_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    if g.staff["role_code"] != "admin":
        return ("เฉพาะผู้ดูแลระบบเท่านั้น", 403)
    staff_pin_hash = get_db().execute("SELECT pin_hash FROM staff WHERE id=?", (g.staff["id"],)).fetchone()[0]
    if not check_password_hash(staff_pin_hash, request.form.get("admin_pin", "")):
        flash("PIN ผู้ดูแลระบบไม่ถูกต้อง จึงไม่ลบลูกค้า", "error")
        return redirect(url_for("online_admin.customers"))
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not customer or customer["is_deleted"]:
        return ("ไม่พบลูกค้า", 404)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    replacement = f"deleted:{customer_id}:{secrets.token_hex(6)}"
    db.execute("BEGIN IMMEDIATE")
    db.execute(
        """UPDATE customers SET is_active=0,is_deleted=1,deleted_at=?,deleted_by_staff_id=?,
           line_user_id=NULL,line_display_name=NULL,line_picture_url=NULL,registered_name=NULL,display_name='ลูกค้าที่ลบแล้ว',
           phone_normalized=?,profile_completed=0,updated_at=? WHERE id=?""",
        (now, g.staff["id"], replacement, now, customer_id),
    )
    db.execute("DELETE FROM customer_sessions WHERE customer_id=?", (customer_id,))
    audit("delete_online_customer", "customer", customer_id,
          {"public_id": customer["public_id"], "line_user_id": customer["line_user_id"], "phone": customer["phone_normalized"]},
          {"replacement": replacement, "is_deleted": True})
    db.commit()
    flash("ลบข้อมูลการใช้งานลูกค้าแล้ว โดยเก็บรหัสอ้างอิงและประวัติออเดอร์ไว้ตรวจสอบ", "success")
    return redirect(url_for("online_admin.customers"))


@bp.post("/customers/<int:customer_id>/toggle")
@permission_required("online_customers.manage")
def toggle_customer(customer_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    db.execute("UPDATE customers SET is_active=1-is_active,updated_at=CURRENT_TIMESTAMP WHERE id=?", (customer_id,))
    db.execute("DELETE FROM customer_sessions WHERE customer_id=? AND (SELECT is_active FROM customers WHERE id=?)=0", (customer_id, customer_id))
    audit("toggle_customer", "customer", customer_id)
    db.commit()
    return redirect(url_for("online_admin.customers"))


@bp.post("/customers/<int:customer_id>/phone")
@permission_required("online_customers.manage")
def correct_customer_phone(customer_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    from ..customer_auth import normalize_phone
    try:
        phone = normalize_phone(request.form.get("phone"))
        db = get_db()
        old = db.execute("SELECT phone_normalized FROM customers WHERE id=?", (customer_id,)).fetchone()
        if not old:
            return ("ไม่พบลูกค้า", 404)
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE customers SET phone_normalized=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (phone, customer_id))
        audit("correct_customer_phone", "customer", customer_id, {"phone_tail": old[0][-4:]}, {"phone_tail": phone[-4:]})
        db.commit()
        flash("แก้ไขเบอร์โทรและบันทึก Audit แล้ว", "success")
    except Exception:
        get_db().rollback()
        flash("เบอร์โทรไม่ถูกต้องหรือมีบัญชีอื่นใช้อยู่แล้ว", "error")
    return redirect(url_for("online_admin.customers"))
