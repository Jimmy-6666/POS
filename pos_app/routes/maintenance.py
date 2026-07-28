"""Administrator-only Sprint 3 maintenance, support, and update controls."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, send_from_directory, url_for
from werkzeug.security import check_password_hash

from ..auth import permission_required, valid_csrf
from ..database import get_db
from ..runtime_paths import validate_runtime
from ..services.backup import list_verified_backups
from ..services.signed_updates import UpdateVerificationError, staged_manifests, verify_staged_update
from ..services.support_bundle import create_support_bundle, list_support_bundles


bp = Blueprint("maintenance", __name__)


def _audit(action: str, entity_id: str, payload: dict[str, object] | None = None) -> None:
    get_db().execute(
        """INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,new_value,ip_address,created_at)
           VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (g.staff["id"], action, "maintenance", entity_id, json.dumps(payload or {}, ensure_ascii=False), request.remote_addr),
    )
    get_db().commit()


def _verification(manifest_name: str):
    return verify_staged_update(
        current_app.config["RUNTIME_PATHS"].staging,
        manifest_name,
        current_app.config.get("POS_UPDATE_SIGNER_THUMBPRINT", ""),
    )


@bp.get("/maintenance")
@permission_required("maintenance.manage")
def index():
    paths = current_app.config["RUNTIME_PATHS"]
    runtime = validate_runtime(current_app.config["RUNTIME_CONFIG"], database_required=True)
    updates = []
    for manifest_name in staged_manifests(paths.staging):
        try:
            updates.append({"manifest": manifest_name, "verified": _verification(manifest_name), "error": ""})
        except UpdateVerificationError as exc:
            updates.append({"manifest": manifest_name, "verified": None, "error": str(exc)})
    return render_template(
        "maintenance.html", runtime=runtime, backups=list_verified_backups(paths.backups)[:3],
        support_bundles=list_support_bundles(paths.support)[:5], updates=updates,
        signing_configured=bool(current_app.config.get("POS_UPDATE_SIGNER_THUMBPRINT", "")),
    )


@bp.post("/maintenance/support-bundles")
@permission_required("maintenance.manage")
def create_bundle():
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    try:
        bundle = create_support_bundle(current_app.config["RUNTIME_PATHS"], current_app.config["RUNTIME_CONFIG"])
    except OSError as exc:
        flash(f"สร้างชุดข้อมูลช่วยเหลือไม่สำเร็จ: {exc}", "error")
    else:
        _audit("create_support_bundle", bundle.name)
        flash("สร้างชุดข้อมูลช่วยเหลือแล้ว กรุณาดาวน์โหลดและส่งให้ทีมสนับสนุนผ่านช่องทางที่ตกลงกัน", "success")
    return redirect(url_for("maintenance.index"))


@bp.get("/maintenance/support-bundles/<path:filename>")
@permission_required("maintenance.manage")
def download_bundle(filename):
    if Path(filename).name != filename or not filename.startswith("support-") or not filename.endswith(".zip"):
        return ("ไม่พบไฟล์", 404)
    return send_from_directory(current_app.config["RUNTIME_PATHS"].support, filename, as_attachment=True)


@bp.post("/maintenance/updates/<path:manifest_name>/apply")
@permission_required("maintenance.manage")
def apply_update(manifest_name):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    if not check_password_hash(g.staff["pin_hash"], request.form.get("admin_pin", "")):
        flash("PIN ผู้ดูแลระบบไม่ถูกต้อง จึงยังไม่เริ่มอัปเดต", "error")
        return redirect(url_for("maintenance.index"))
    try:
        verified = _verification(manifest_name)
        paths = current_app.config["RUNTIME_PATHS"]
        project_root = current_app.config["POS_INSTALL_ROOT"]
        runner = Path(project_root) / "apply-signed-update.ps1"
        if not runner.is_file():
            raise UpdateVerificationError("ไม่พบตัวเรียกใช้อัปเดตที่ระบบติดตั้งไว้")
        subprocess.Popen(
            [
                current_app.config.get("POS_UPDATE_POWERSHELL", "powershell.exe"), "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(runner), "-UpdateScript", str(verified.script_path),
                "-ExpectedThumbprint", verified.signer_thumbprint,
                "-InstallRoot", str(project_root), "-RuntimeRoot", str(paths.root), "-Port", str(current_app.config["POS_PORT"]),
            ], cwd=project_root, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, UpdateVerificationError) as exc:
        flash(f"ยังไม่เริ่มอัปเดต: {exc}", "error")
    else:
        _audit("apply_signed_update_requested", verified.release_id, {"version": verified.version, "manifest": manifest_name})
        flash("ส่งคำสั่งอัปเดตที่ตรวจลายเซ็นแล้ว ระบบจะบันทึกผลใน logs และอาจเริ่มบริการใหม่", "success")
    return redirect(url_for("maintenance.index"))
