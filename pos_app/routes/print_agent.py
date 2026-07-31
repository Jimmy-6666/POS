import hmac
import json

from flask import Blueprint, current_app, jsonify, render_template, request, url_for

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


def document_context(job, *, autoprint=False, print_job_id=None):
    """Return the existing receipt template context for a top-level print document."""
    db = get_db()
    settings = dict(db.execute("SELECT key,value FROM settings").fetchall())
    if job["document_type"] == "sale_receipt":
        sale = db.execute(
            "SELECT s.*,st.display_name FROM sales s JOIN staff st ON st.id=s.cashier_id WHERE s.id=?",
            (job["entity_id"],),
        ).fetchone()
        if not sale:
            return None
        items = db.execute(
            "SELECT *,quantity-voided_quantity AS remaining_quantity FROM sale_items WHERE sale_id=?",
            (sale["id"],),
        ).fetchall()
        return "receipt.html", {
            "sale": sale,
            "items": items,
            "settings": settings,
            "autoprint": autoprint,
            "print_job_id": print_job_id,
        }
    if job["document_type"] == "checked_order":
        order = db.execute(
            """SELECT o.*,c.phone_normalized,c.display_name FROM online_orders o
               JOIN customers c ON c.id=o.customer_id WHERE o.id=?""",
            (job["entity_id"],),
        ).fetchone()
        if not order or not order["reconciliation_completed_at"]:
            return None
        items = db.execute(
            "SELECT * FROM online_order_items WHERE order_id=? AND is_removed=0 ORDER BY id",
            (order["id"],),
        ).fetchall()
        return "online/order_receipt.html", {
            "order": order,
            "items": items,
            "settings": settings,
            "autoprint": autoprint,
            "print_job_id": print_job_id,
        }
    return None


def render_top_level_print_document(job, job_id, desktop_user):
    """Render the existing receipt directly in the kiosk's main frame.

    Chromium reliably prints a top-level receipt document, while an outer page
    that prints an iframe can leave the Windows driver dialog open and never
    emit ``afterprint``.  Keep the established receipt template/layout and add
    only the agent acknowledgement hook after its normal print hook.
    """
    context = document_context(job, autoprint=True, print_job_id=job_id)
    if not context:
        return None
    template_name, values = context
    receipt_html = render_template(template_name, **values)
    token = json.dumps(current_app.config["PRINT_AGENT_TOKEN"])
    user = json.dumps(desktop_user)
    job = json.dumps(job_id)
    ack_url = json.dumps(url_for("print_agent.acknowledge_job", job_id=job_id))
    agent_url = json.dumps(url_for("print_agent.index"))
    completion_hook = f"""
<script>
(() => {{
  const token = {token};
  const desktopUser = {user};
  const jobId = {job};
  const ackUrl = {ack_url};
  const agentUrl = {agent_url};
  let completed = false;

  function requestUrl(path) {{
    return `${{path}}?token=${{encodeURIComponent(token)}}&desktop_user=${{encodeURIComponent(desktopUser)}}`;
  }}

  function logEvent(event) {{
    return fetch(requestUrl('/print-agent/event'), {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{event, job_id: jobId}}),
      keepalive: true,
    }}).catch(() => undefined);
  }}

  async function finishPrint() {{
    if (completed) return;
    completed = true;
    await logEvent('browser_afterprint');
    const response = await fetch(requestUrl(ackUrl), {{method: 'POST', keepalive: true}}).catch(() => null);
    if (!response?.ok) await logEvent('browser_ack_failed');
    window.location.replace(requestUrl(agentUrl));
  }}

  logEvent('browser_job_loaded');
  addEventListener('afterprint', finishPrint, {{once: true}});
}})();
</script>"""
    return receipt_html.replace("</body>", f"{completion_hook}</body>")


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
    if not job or not document_context(job):
        return ("ไม่พบเอกสาร", 404)
    desktop_user = agent_user()
    record_print_event(
        "agent_render_opened",
        source="browser-agent",
        details={
            "desktop_user": desktop_user, "job_id": job_id,
            "document_type": job["document_type"], "entity_id": job["entity_id"],
        },
    )
    return render_top_level_print_document(job, job_id, desktop_user)


@bp.get("/document/<job_id>")
def print_document(job_id):
    if not authorized():
        return ("ไม่พบเอกสาร", 404)
    job = get_print_job(job_id)
    context = document_context(job) if job else None
    if not context:
        return ("ไม่พบเอกสาร", 404)
    template_name, values = context
    return render_template(template_name, **values)


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
