import csv
import io
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, Response, current_app, flash, g, redirect, render_template, request, send_from_directory, url_for
from werkzeug.security import generate_password_hash

from ..auth import permission_required, valid_csrf
from ..database import get_db
from ..services.backup import BackupError, create_local_backup, list_verified_backups
from ..services.backup_scheduler import is_valid_schedule
from ..services.money import baht_to_satang


bp=Blueprint("admin",__name__)


@bp.route("/staff",methods=("GET","POST"))
@permission_required("staff.manage")
def staff():
    db=get_db()
    if request.method=="POST":
        if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
        name=request.form.get("display_name","").strip();pin=request.form.get("pin","");role_id=request.form.get("role_id",type=int)
        if not name or len(pin) not in (4,6) or not pin.isdigit():flash("ชื่อและ PIN ตัวเลข 4 หรือ 6 หลักไม่ถูกต้อง","error")
        else:
            db.execute("INSERT INTO staff (display_name,pin_hash,role_id,must_change_pin) VALUES (?,?,?,1)",(name,generate_password_hash(pin),role_id));db.commit();flash("เพิ่มพนักงานแล้ว","success")
        return redirect(url_for("admin.staff"))
    rows=db.execute("SELECT st.*,r.name_th role_name FROM staff st JOIN roles r ON r.id=st.role_id ORDER BY st.display_name").fetchall();roles=db.execute("SELECT * FROM roles ORDER BY id").fetchall()
    return render_template("staff.html",staff_rows=rows,roles=roles)


@bp.post("/staff/<int:staff_id>/toggle")
@permission_required("staff.manage")
def toggle_staff(staff_id):
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    if staff_id==g.staff["id"]:flash("ไม่สามารถปิดบัญชีตนเอง","error")
    else:get_db().execute("UPDATE staff SET is_active=1-is_active,updated_at=CURRENT_TIMESTAMP WHERE id=?",(staff_id,));get_db().commit()
    return redirect(url_for("admin.staff"))


@bp.route("/settings",methods=("GET","POST"))
@permission_required("settings.manage")
def settings():
    db=get_db()
    if request.method=="POST":
        if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
        allowed={"store_name","store_address","store_phone","tax_id","receipt_prefix","allow_negative_stock"}
        for key in allowed:
            value="1" if key=="allow_negative_stock" and request.form.get(key) else "0" if key=="allow_negative_stock" else request.form.get(key,"").strip()
            db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",(key,value))
        db.commit();flash("บันทึกการตั้งค่าแล้ว","success");return redirect(url_for("admin.settings"))
    values=dict(db.execute("SELECT key,value FROM settings").fetchall());reasons=db.execute("SELECT * FROM adjustment_reasons ORDER BY name_th").fetchall();payments=db.execute("SELECT * FROM payment_methods ORDER BY id").fetchall();billing_customers=db.execute("SELECT * FROM billing_customers ORDER BY name").fetchall()
    return render_template("settings.html",settings=values,reasons=reasons,payments=payments,billing_customers=billing_customers)


@bp.post("/settings/billing-customers")
@permission_required("settings.manage")
def add_billing_customer():
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    name=request.form.get("name","").strip()
    if not name:flash("กรุณาระบุชื่อลูกค้า","error");return redirect(url_for("admin.settings"))
    try:
        get_db().execute("""INSERT INTO billing_customers(name,contact_name,phone,address,tax_id,credit_limit_satang)
            VALUES(?,?,?,?,?,?)""",(name,request.form.get("contact_name","").strip(),request.form.get("phone","").strip(),request.form.get("address","").strip(),request.form.get("tax_id","").strip(),baht_to_satang(request.form.get("credit_limit") or 0)))
        get_db().commit();flash("เพิ่มรายชื่อลูกค้าวางบิลแล้ว","success")
    except Exception:get_db().rollback();flash("ชื่อลูกค้าซ้ำหรือข้อมูลไม่ถูกต้อง","error")
    return redirect(url_for("admin.settings"))


@bp.post("/settings/billing-customers/<int:customer_id>/toggle")
@permission_required("settings.manage")
def toggle_billing_customer(customer_id):
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    get_db().execute("UPDATE billing_customers SET is_active=1-is_active,updated_at=CURRENT_TIMESTAMP WHERE id=?",(customer_id,));get_db().commit()
    return redirect(url_for("admin.settings"))


@bp.post("/settings/lists/<table>")
@permission_required("settings.manage")
def save_setting_list(table):
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    if table not in {"adjustment_reasons","payment_methods"}:return ("ข้อมูลไม่ถูกต้อง",400)
    db=get_db()
    try:
        db.execute("BEGIN IMMEDIATE");active=set(request.form.getlist("active_id"))
        for item_id in request.form.getlist("item_id"):
            name=request.form.get(f"name_{item_id}","").strip()
            if not name:raise ValueError()
            db.execute(f"UPDATE {table} SET name_th=?,is_active=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(name,1 if item_id in active else 0,item_id))
        db.commit();flash("บันทึกรายการแล้ว","success")
    except Exception:db.rollback();flash("ชื่อซ้ำหรือข้อมูลไม่ถูกต้อง","error")
    return redirect(url_for("admin.settings"))


@bp.get("/audit-logs")
@permission_required("audit.view")
def audit_logs():
    db = get_db()
    selected_action = request.args.get("action", "").strip()
    if len(selected_action) > 128:
        selected_action = ""
    actions = db.execute(
        "SELECT DISTINCT action FROM audit_logs ORDER BY action"
    ).fetchall()
    params = []
    where = ""
    if selected_action:
        where = "WHERE a.action=?"
        params.append(selected_action)
    rows = db.execute(
        f"""SELECT a.*,st.display_name
            FROM audit_logs a LEFT JOIN staff st ON st.id=a.staff_id
            {where}
            ORDER BY a.created_at DESC,a.id DESC LIMIT 1000""",
        params,
    ).fetchall()
    return render_template(
        "audit_logs.html",
        logs=rows,
        actions=actions,
        selected_action=selected_action,
    )


@bp.post("/audit-logs/export")
@permission_required("audit.view")
def export_audit_logs():
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    db = get_db()
    selected_action = request.form.get("action", "").strip()
    if len(selected_action) > 128:
        return ("ตัวกรองการกระทำไม่ถูกต้อง", 400)
    params = []
    where = ""
    if selected_action:
        where = "WHERE a.action=?"
        params.append(selected_action)
    rows = db.execute(
        f"""SELECT a.id,a.created_at,st.display_name,a.action,a.entity_type,a.entity_id,
                   a.old_value,a.new_value,a.ip_address
            FROM audit_logs a LEFT JOIN staff st ON st.id=a.staff_id
            {where}
            ORDER BY a.created_at DESC,a.id DESC""",
        params,
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "audit_id",
            "created_at",
            "staff",
            "action",
            "entity_type",
            "entity_id",
            "old_value",
            "new_value",
            "ip_address",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["created_at"],
                row["display_name"] or "",
                row["action"],
                row["entity_type"],
                row["entity_id"] or "",
                row["old_value"] or "",
                row["new_value"] or "",
                row["ip_address"] or "",
            ]
        )

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.execute(
        """INSERT INTO audit_logs
           (staff_id,action,entity_type,entity_id,new_value,ip_address,created_at)
           VALUES (?,'export_audit_logs','audit_log',?,?,?,?)""",
        (
            g.staff["id"],
            selected_action or "all",
            json.dumps(
                {"action_filter": selected_action or None, "row_count": len(rows)},
                ensure_ascii=False,
            ),
            request.remote_addr,
            now,
        ),
    )
    db.commit()
    safe_action = re.sub(r"[^A-Za-z0-9_-]+", "-", selected_action).strip("-") or "all"
    filename = f"audit-logs-{safe_action}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/backups",methods=("GET","POST"))
@permission_required("backup.manage")
def backups():
    paths=current_app.config["RUNTIME_PATHS"];folder=paths.backups
    if request.method=="POST" and not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง",400)
    if request.method=="POST" and valid_csrf(request.form.get("csrf_token")):
        action=request.form.get("action","create_local")
        if action=="schedule":
            schedule=request.form.get("backup_schedule_time","").strip()
            if not is_valid_schedule(schedule):
                flash("กรุณาระบุเวลาเป็น HH:MM เช่น 02:00","error")
            else:
                db=get_db()
                for key,value in (("backup_schedule_time",schedule),("backup_schedule_enabled","1" if request.form.get("backup_schedule_enabled") else "0")):
                    db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",(key,value))
                db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,new_value,created_at) VALUES(?,'update_backup_schedule','backup_schedule','daily',?,CURRENT_TIMESTAMP)",(g.staff["id"],json.dumps({"time":schedule,"enabled":bool(request.form.get("backup_schedule_enabled"))})))
                db.commit();flash("บันทึกเวลาส่งฐานข้อมูลและรูปสินค้าแล้ว","success")
        elif action=="send_remote":
            scheduler=current_app.extensions.get("backup_scheduler")
            if scheduler is None:
                flash("ตัวส่งข้อมูลอัตโนมัติยังไม่พร้อม กรุณาตรวจการตั้งค่า runtime","error")
            else:
                scheduler.start_backup("manual")
                get_db().execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,created_at) VALUES(?,'start_remote_backup','backup','manual',CURRENT_TIMESTAMP)",(g.staff["id"],));get_db().commit();flash("เริ่มสร้างฐานข้อมูลและ sync รูปสินค้าไป server แล้ว โปรดรีเฟรชเพื่อตรวจสถานะ","success")
        else:
            try:
                artifact=create_local_backup(paths,current_app.config["RUNTIME_CONFIG"],retention=int(current_app.config.get("POS_BACKUP_RETENTION",7)))
            except (BackupError,OSError,ValueError) as exc:
                flash(f"สร้างไฟล์สำรองไม่สำเร็จ: {exc}","error")
            else:
                db=get_db();db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,created_at) VALUES(?,'create_backup','backup',?,CURRENT_TIMESTAMP)",(g.staff["id"],artifact.path.name));db.commit();flash("สร้างไฟล์สำรองฐานข้อมูลและตรวจสอบความถูกต้องแล้ว","success")
        return redirect(url_for("admin.backups"))
    files=[Path(item["archive"]) for item in list_verified_backups(folder)]
    settings=dict(get_db().execute("SELECT key,value FROM settings WHERE key IN ('backup_schedule_enabled','backup_schedule_time')").fetchall())
    remote_status={}
    try:
        remote_status=json.loads((paths.support/"remote-backup-status.json").read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):
        pass
    return render_template("backups.html",files=files,schedule_time=settings.get("backup_schedule_time","02:00"),schedule_enabled=settings.get("backup_schedule_enabled","1")=="1",remote_status=remote_status)


@bp.get("/backups/<path:filename>")
@permission_required("backup.manage")
def download_backup(filename):
    return send_from_directory(current_app.config["RUNTIME_PATHS"].backups,filename,as_attachment=True)
