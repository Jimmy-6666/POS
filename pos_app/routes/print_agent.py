import hmac

from flask import Blueprint, current_app, jsonify, render_template, request

from ..database import get_db
from ..services.print_diagnostics import record_print_event
from ..services.print_jobs import acknowledge_print, claim_print, get_print_job


bp = Blueprint("print_agent", __name__, url_prefix="/print-agent")


def authorized():
    expected = current_app.config.get("PRINT_AGENT_TOKEN") or ""
    supplied = request.args.get("token") or request.headers.get("X-Print-Agent-Token") or ""
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def agent_user():
    return (request.args.get("desktop_user") or "unknown").strip()[:80]


@bp.get("")
def index():
    if not authorized():
        return ("ไม่พบหน้า", 404)
    desktop_user = agent_user()
    record_print_event(
        "agent_page_opened",
        source="browser-agent",
        details={"desktop_user": desktop_user, "remote_addr": request.remote_addr},
    )
    return render_template(
        "print_agent.html",
        token=current_app.config["PRINT_AGENT_TOKEN"],
        desktop_user=desktop_user,
    )


@bp.get("/next")
def next_job():
    if not authorized():
        return jsonify(error="not found"), 404
    job = claim_print()
    if job:
        record_print_event(
            "agent_received_job",
            source="browser-agent",
            details={
                "desktop_user": agent_user(), "job_id": job["id"],
                "document_type": job["document_type"], "entity_id": job["entity_id"],
            },
        )
    return jsonify(job=job)


@bp.get("/render/<job_id>")
def render_job(job_id):
    if not authorized():
        return ("ไม่พบเอกสาร", 404)
    job = get_print_job(job_id)
    if not job:
        return ("ไม่พบเอกสาร", 404)
    record_print_event(
        "agent_render_opened",
        source="browser-agent",
        details={
            "desktop_user": agent_user(), "job_id": job_id,
            "document_type": job["document_type"], "entity_id": job["entity_id"],
        },
    )
    db = get_db()
    settings = dict(db.execute("SELECT key,value FROM settings").fetchall())
    context = {"autoprint": True, "print_job_id": job_id}
    if job["document_type"] == "sale_receipt":
        sale = db.execute(
            "SELECT s.*,st.display_name FROM sales s JOIN staff st ON st.id=s.cashier_id WHERE s.id=?",
            (job["entity_id"],),
        ).fetchone()
        if not sale:
            return ("ไม่พบใบเสร็จ", 404)
        items = db.execute(
            "SELECT *,quantity-voided_quantity AS remaining_quantity FROM sale_items WHERE sale_id=?",
            (sale["id"],),
        ).fetchall()
        return render_template("receipt.html", sale=sale, items=items, settings=settings, **context)
    if job["document_type"] == "checked_order":
        order = db.execute(
            """SELECT o.*,c.phone_normalized,c.display_name FROM online_orders o
               JOIN customers c ON c.id=o.customer_id WHERE o.id=?""",
            (job["entity_id"],),
        ).fetchone()
        if not order or not order["reconciliation_completed_at"]:
            return ("ไม่พบใบสรุปออเดอร์", 404)
        items = db.execute(
            "SELECT * FROM online_order_items WHERE order_id=? AND is_removed=0 ORDER BY id",
            (order["id"],),
        ).fetchall()
        return render_template("online/order_receipt.html", order=order, items=items, settings=settings, **context)
    return ("ไม่รองรับเอกสารนี้", 400)


@bp.post("/ack/<job_id>")
def acknowledge_job(job_id):
    if not authorized():
        return jsonify(error="not found"), 404
    acknowledged = acknowledge_print(job_id)
    record_print_event(
        "agent_acknowledged_job" if acknowledged else "agent_acknowledge_missing",
        source="browser-agent",
        details={"desktop_user": agent_user(), "job_id": job_id},
    )
    return jsonify(ok=acknowledged)


@bp.post("/event")
def event():
    if not authorized():
        return jsonify(error="not found"), 404
    payload = request.get_json(silent=True) or {}
    event_name = str(payload.get("event") or "")
    allowed = {"browser_job_loaded", "browser_print_requested", "browser_afterprint", "browser_ack_timeout", "browser_ack_failed"}
    if event_name not in allowed:
        return jsonify(error="invalid event"), 400
    record_print_event(
        event_name,
        source="browser-agent",
        details={
            "desktop_user": agent_user(), "job_id": payload.get("job_id"),
            "document_type": payload.get("document_type"),
        },
    )
    return jsonify(ok=True)
