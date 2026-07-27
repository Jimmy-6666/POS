"""Administrator-only maintenance dashboard and job controls."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from ..auth import permission_required, valid_csrf
from ..database import get_db
from ..services.maintenance_jobs import enqueue_job, get_job, list_jobs, start_job
from ..services.support import ACTION_TO_JOB, ALLOWED_REMOTE_ACTIONS, SupportError, verify_remote_request


bp = Blueprint("maintenance", __name__, url_prefix="/maintenance")
UTC = timezone.utc
REAUTH_SECONDS = 300


def admin_required(view):
    guarded = permission_required("backup.manage")(view)

    @wraps(view)
    def wrapped(**kwargs):
        if g.staff is None or g.staff["role_code"] != "admin":
            return ("ไม่มีสิทธิ์เข้าถึงหน้านี้", 403)
        return guarded(**kwargs)
    return wrapped


def _csrf_error():
    return ("คำขอไม่ถูกต้อง กรุณาลองใหม่", 400)


def _reauthenticated() -> bool:
    value = session.get("maintenance_reauth_at")
    if not value:
        return False
    try:
        return (datetime.now(UTC) - datetime.fromisoformat(value).astimezone(UTC)).total_seconds() <= REAUTH_SECONDS
    except ValueError:
        return False


def _require_reauth():
    if not _reauthenticated():
        return ("ต้องยืนยันตัวตนผู้ดูแลระบบอีกครั้งก่อนดำเนินการนี้", 428)
    return None


def _queue(job_type: str, *, high_risk: bool = False):
    if not valid_csrf(request.form.get("csrf_token")):
        return _csrf_error()
    if high_risk:
        error = _require_reauth()
        if error:
            return error
    paths = current_app.config["RUNTIME_PATHS"]
    job = enqueue_job(paths, job_type, requested_by=g.staff["id"])
    start_job(paths, current_app.config["RUNTIME_CONFIG"], str(job["id"]))
    db = get_db()
    db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,ip_address,created_at) VALUES(?,?,?,?,?,?)", (g.staff["id"], f"maintenance_{job_type}", "maintenance_job", job["id"], request.remote_addr, datetime.now(UTC).isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("maintenance.dashboard", job_id=job["id"]))


def _status_file(name: str):
    path = current_app.config["RUNTIME_PATHS"].support / name
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _schema_version():
    row = get_db().execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
    return row[0] if row else "unknown"


def _active_release():
    from ..services.update_agent import active_release
    return active_release(current_app.config["RUNTIME_PATHS"]) or {}


def _remote_requests():
    inbox = current_app.config["RUNTIME_PATHS"].support / "remote-inbox"
    results = []
    for path in sorted(inbox.glob("*.json")) if inbox.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and str(data.get("action")) in ALLOWED_REMOTE_ACTIONS:
                results.append({"request_id": data.get("request_id"), "action": data.get("action"), "expires_at": data.get("expires_at")})
        except (OSError, json.JSONDecodeError):
            continue
    return results[-50:]


@bp.get("")
@admin_required
def dashboard():
    paths = current_app.config["RUNTIME_PATHS"]
    image_files = [path for path in paths.product_images.rglob("*") if path.is_file()] if paths.product_images.is_dir() else []
    database_size = paths.database.stat().st_size if paths.database.is_file() else 0
    disk = shutil.disk_usage(paths.root)
    current_job_id = request.args.get("job_id", "")
    return render_template("maintenance.html", jobs=list_jobs(paths), selected_job=get_job(paths, current_job_id) if current_job_id else None, metrics={
        "application_version": current_app.config.get("POS_APP_VERSION", "unknown"), "schema_version": _schema_version(),
        "runtime_root": str(paths.root), "database_size": database_size, "image_count": len(image_files),
        "image_size": sum(path.stat().st_size for path in image_files), "free_disk": disk.free,
        "last_backup": _status_file("backup-status.json"), "last_sync": _status_file("sync-status.json"),
        "update": _status_file("update-status.json"), "active_release": _active_release(),
    }, remote_requests=_remote_requests())


@bp.post("/reauth")
@admin_required
def reauth():
    if not valid_csrf(request.form.get("csrf_token")):
        return _csrf_error()
    pin = request.form.get("pin", "")
    staff = get_db().execute("SELECT pin_hash FROM staff WHERE id=?", (g.staff["id"],)).fetchone()
    if not staff or not check_password_hash(staff["pin_hash"], pin):
        return ("ยืนยัน PIN ไม่สำเร็จ", 403)
    session["maintenance_reauth_at"] = datetime.now(UTC).isoformat()
    return redirect(url_for("maintenance.dashboard"))


@bp.get("/jobs/<job_id>")
@admin_required
def job_status(job_id):
    job = get_job(current_app.config["RUNTIME_PATHS"], job_id)
    return (jsonify(job) if job else (jsonify(error="ไม่พบงาน"), 404))


@bp.post("/backup")
@admin_required
def backup():
    return _queue("backup")


@bp.post("/sync")
@admin_required
def sync():
    return _queue("backup_and_sync")


@bp.post("/vps-test")
@admin_required
def vps_test():
    return _queue("vps_test")


@bp.post("/support-bundle")
@admin_required
def support_bundle():
    return _queue("support_bundle")


@bp.post("/restart")
@admin_required
def restart():
    return _queue("controlled_restart", high_risk=True)


@bp.post("/update/check")
@admin_required
def update_check():
    return _queue("update_check")


@bp.post("/update/download")
@admin_required
def update_download():
    return _queue("update_download")


@bp.post("/update/install")
@admin_required
def update_install():
    return _queue("update_install", high_risk=True)


@bp.post("/update/rollback")
@admin_required
def update_rollback():
    return _queue("update_rollback", high_risk=True)


@bp.post("/remote-requests/<request_id>/approve")
@admin_required
def approve_remote_request(request_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return _csrf_error()
    error = _require_reauth()
    if error:
        return error
    paths = current_app.config["RUNTIME_PATHS"]
    inbox = paths.support / "remote-inbox"
    request_path = None
    for candidate in inbox.glob("*.json") if inbox.is_dir() else []:
        try:
            if json.loads(candidate.read_text(encoding="utf-8")).get("request_id") == request_id:
                request_path = candidate
                break
        except (OSError, json.JSONDecodeError):
            continue
    if request_path is None:
        return ("ไม่พบคำขอระยะไกล", 404)
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        trusted_key = os.environ.get("POS_SUPPORT_TRUSTED_KEY_FILE", paths.configuration / "support-trusted.key")
        verified = verify_remote_request(payload, trusted_key=trusted_key, store_id=current_app.config["RUNTIME_CONFIG"].store_id, replay_dir=paths.support / "remote-replay")
    except (OSError, json.JSONDecodeError, SupportError) as exc:
        return (f"คำขอระยะไกลไม่ผ่านการตรวจสอบ: {exc}", 400)
    action = str(verified["action"])
    if action == "health_report":
        result = {"status": "ok", "application_version": current_app.config.get("POS_APP_VERSION")}
    else:
        job = enqueue_job(paths, ACTION_TO_JOB[action], requested_by=g.staff["id"], payload={"remote_request_id": request_id})
        start_job(paths, current_app.config["RUNTIME_CONFIG"], str(job["id"]))
        result = {"job_id": job["id"]}
    db = get_db()
    db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,ip_address,created_at) VALUES(?,?,?,?,?,?)", (g.staff["id"], "approve_remote_maintenance", "remote_request", request_id, request.remote_addr, datetime.now(UTC).isoformat(timespec="seconds")))
    db.commit()
    request_path.rename(request_path.with_suffix(".approved.json"))
    return redirect(url_for("maintenance.dashboard"))
