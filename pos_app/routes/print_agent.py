import hmac

from flask import Blueprint, current_app, jsonify, render_template, request

from ..database import get_db
from ..services.print_jobs import acknowledge_print, claim_print, get_print_job


bp = Blueprint("print_agent", __name__, url_prefix="/print-agent")


def authorized():
    expected = current_app.config.get("PRINT_AGENT_TOKEN") or ""
    supplied = request.args.get("token") or request.headers.get("X-Print-Agent-Token") or ""
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


@bp.get("")
def index():
    if not authorized():
        return ("ไม่พบหน้า", 404)
    return render_template("print_agent.html", token=current_app.config["PRINT_AGENT_TOKEN"])


@bp.get("/next")
def next_job():
    if not authorized():
        return jsonify(error="not found"), 404
    return jsonify(job=claim_print())


@bp.get("/render/<job_id>")
def render_job(job_id):
    if not authorized():
        return ("ไม่พบเอกสาร", 404)
    job = get_print_job(job_id)
    if not job:
        return ("ไม่พบเอกสาร", 404)
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
    return jsonify(ok=acknowledge_print(job_id))
