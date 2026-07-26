import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, send_from_directory, url_for

from ..auth import permission_required, valid_csrf
from ..database import get_db
from ..services.online_orders import (
    OnlineOrderError, audit_order, complete_online_order_sale, expire_pending_orders,
    record_history, release_reservations,
)
from ..services.print_jobs import enqueue_print
from ..services.sales import SaleError


bp = Blueprint("online_staff", __name__, url_prefix="/online-orders")
FINAL = {"completed", "customer_cancelled", "staff_cancelled", "rejected", "expired"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_order(order_id):
    return get_db().execute(
        """SELECT o.*,c.phone_normalized,c.display_name,st.display_name AS assigned_name
           FROM online_orders o JOIN customers c ON c.id=o.customer_id
           LEFT JOIN staff st ON st.id=o.assigned_staff_id WHERE o.id=?""", (order_id,)
    ).fetchone()


def transition(order, new_status, allowed, reason=None, customer_visible=True):
    if order["status"] not in allowed:
        raise ValueError("ไม่สามารถเปลี่ยนสถานะออเดอร์จากขั้นตอนปัจจุบันได้")
    db = get_db()
    db.execute("UPDATE online_orders SET status=?,updated_at=? WHERE id=?", (new_status, now(), order["id"]))
    record_history(order["id"], order["status"], new_status, "staff", staff_id=g.staff["id"],
                   reason=reason, customer_visible=customer_visible)
    audit_order(f"online_order_{new_status}", order["id"], staff_id=g.staff["id"], detail={"reason": reason})


def refresh_order_totals(order_id):
    db = get_db()
    subtotal = db.execute(
        "SELECT COALESCE(SUM(line_total_satang),0) FROM online_order_items WHERE order_id=? AND is_removed=0",
        (order_id,),
    ).fetchone()[0]
    order = db.execute("SELECT delivery_fee_satang FROM online_orders WHERE id=?", (order_id,)).fetchone()
    total = subtotal + order["delivery_fee_satang"]
    db.execute(
        "UPDATE online_orders SET subtotal_satang=?,total_satang=?,updated_at=? WHERE id=?",
        (subtotal, total, now(), order_id),
    )
    db.execute(
        """UPDATE online_order_payments SET amount_satang=?,updated_at=?
           WHERE order_id=? AND status IN ('unpaid','awaiting_verification')""",
        (total, now(), order_id),
    )
    return subtotal, total


@bp.get("")
@permission_required("online_orders.view")
def index():
    expire_pending_orders()
    db = get_db()
    status = request.args.get("status", "").strip()
    location_id = request.args.get("location_id", type=int)
    payment_method = request.args.get("payment_method", "").strip()
    date = request.args.get("date", "").strip()
    where, params = [], []
    if status:
        where.append("o.status=?"); params.append(status)
    if location_id:
        where.append("o.delivery_location_id=?"); params.append(location_id)
    if payment_method in {"cash", "transfer"}:
        where.append("o.payment_method_code=?"); params.append(payment_method)
    if date:
        where.append("substr(o.created_at,1,10)=?"); params.append(date)
    clause = "WHERE " + " AND ".join(where) if where else ""
    rows = db.execute(
        f"""SELECT o.*,c.phone_normalized,c.display_name,st.display_name AS assigned_name
            FROM online_orders o JOIN customers c ON c.id=o.customer_id
            LEFT JOIN staff st ON st.id=o.assigned_staff_id {clause}
            ORDER BY CASE o.status WHEN 'submitted' THEN 0 WHEN 'accepted' THEN 1 ELSE 2 END,o.created_at""", params
    ).fetchall()
    locations = db.execute("SELECT id,name FROM delivery_locations ORDER BY sort_order,name").fetchall()
    return render_template("online/staff_orders.html", orders=rows, locations=locations)


@bp.get("/api/summary")
@permission_required("online_orders.view")
def summary():
    expire_pending_orders()
    db = get_db()
    row = db.execute(
        """SELECT SUM(status='submitted') AS new_count,
                  SUM(payment_status='awaiting_verification') AS payment_count,
                  MAX(CASE WHEN status='submitted' THEN id ELSE 0 END) AS latest_id
           FROM online_orders"""
    ).fetchone()
    return jsonify(dict(row))


@bp.get("/<int:order_id>")
@permission_required("online_orders.view")
def detail(order_id):
    expire_pending_orders()
    order = load_order(order_id)
    if not order:
        return ("ไม่พบออเดอร์", 404)
    db = get_db()
    items = db.execute(
        """SELECT oi.*,p.stock_quantity,p.image_path,p.price_satang AS current_price_satang,
                  p.allow_decimal_quantity
           FROM online_order_items oi
           JOIN products p ON p.id=oi.product_id WHERE oi.order_id=? ORDER BY oi.id""", (order_id,)
    ).fetchall()
    history = db.execute(
        """SELECT h.*,st.display_name FROM online_order_status_history h
           LEFT JOIN staff st ON st.id=h.actor_staff_id WHERE h.order_id=? ORDER BY h.created_at,h.id""", (order_id,)
    ).fetchall()
    payments = db.execute("SELECT * FROM online_order_payments WHERE order_id=? ORDER BY created_at DESC", (order_id,)).fetchall()
    staff = db.execute("SELECT id,display_name FROM staff WHERE is_active=1 ORDER BY display_name").fetchall()
    product_rows = db.execute(
        """SELECT id,name_th,barcode,price_satang,stock_quantity,allow_decimal_quantity
           FROM products WHERE is_active=1 ORDER BY name_th"""
    ).fetchall()
    confirmed_subtotal = sum(
        round(item["customer_confirmed_unit_price_satang"] * item["original_quantity"])
        for item in items if item["customer_confirmed_unit_price_satang"] is not None
    )
    has_catalog_price_change = any(
        item["customer_confirmed_unit_price_satang"] is not None
        and item["current_price_satang"] != item["customer_confirmed_unit_price_satang"]
        for item in items if not item["is_removed"]
    )
    return render_template(
        "online/staff_order_detail.html", order=order, items=items, history=history,
        payments=payments, staff_rows=staff, product_rows=product_rows,
        confirmed_subtotal=confirmed_subtotal,
        order_price_changed=order["subtotal_satang"] != confirmed_subtotal or has_catalog_price_change,
        print_status=request.args.get("print_status"),
    )


@bp.get("/<int:order_id>/receipt")
@permission_required("online_orders.view")
def order_receipt(order_id):
    order = load_order(order_id)
    if not order or not order["reconciliation_completed_at"]:
        return ("ยังไม่สามารถออกใบสรุปออเดอร์ได้", 400)
    items = get_db().execute(
        "SELECT * FROM online_order_items WHERE order_id=? AND is_removed=0 ORDER BY id", (order_id,)
    ).fetchall()
    settings = dict(get_db().execute("SELECT key,value FROM settings").fetchall())
    return render_template("online/order_receipt.html", order=order, items=items, settings=settings, autoprint=False)


@bp.post("/<int:order_id>/accept")
@permission_required("online_orders.accept")
def accept(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    order = load_order(order_id)
    try:
        assigned_staff_id = request.form.get("staff_id", type=int)
        if not assigned_staff_id or not get_db().execute("SELECT 1 FROM staff WHERE id=? AND is_active=1", (assigned_staff_id,)).fetchone():
            raise ValueError("กรุณาเลือกผู้ดำเนินการออเดอร์")
        db = get_db(); db.execute("BEGIN IMMEDIATE")
        transition(order, "accepted", {"submitted"}, request.form.get("note") or "ร้านรับออเดอร์แล้ว")
        db.execute("UPDATE online_orders SET accepted_by=?,assigned_staff_id=?,accepted_at=?,assigned_at=? WHERE id=?",
                   (assigned_staff_id, assigned_staff_id, now(), now(), order_id))
        db.commit(); flash("รับออเดอร์แล้ว", "success")
    except ValueError as exc:
        get_db().rollback(); flash(str(exc), "error")
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.post("/<int:order_id>/reject")
@permission_required("online_orders.accept")
def reject(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    order, reason = load_order(order_id), request.form.get("reason", "").strip()
    if not reason:
        flash("กรุณาระบุเหตุผล", "error")
    else:
        try:
            db = get_db(); db.execute("BEGIN IMMEDIATE")
            transition(order, "rejected", {"submitted", "accepted"}, reason)
            release_reservations(order_id, "staff_rejected")
            db.execute("UPDATE online_orders SET cancellation_reason=?,cancelled_at=? WHERE id=?", (reason, now(), order_id))
            audit_order("stock_reservation_released", order_id, staff_id=g.staff["id"], detail={"reason": "staff_rejected"})
            db.commit()
        except ValueError as exc:
            get_db().rollback(); flash(str(exc), "error")
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.post("/<int:order_id>/payment/<int:payment_id>")
@permission_required("online_orders.verify_payment")
def verify_payment(order_id, payment_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    action = request.form.get("action")
    reason = request.form.get("reason", "").strip()
    if action not in {"confirm", "reject"} or (action == "reject" and not reason):
        flash("กรุณาระบุผลตรวจสอบและเหตุผล", "error")
        return redirect(url_for("online_staff.detail", order_id=order_id))
    db = get_db(); db.execute("BEGIN IMMEDIATE")
    payment = db.execute("SELECT * FROM online_order_payments WHERE id=? AND order_id=? AND slip_path IS NOT NULL", (payment_id, order_id)).fetchone()
    if not payment:
        db.rollback(); return ("ไม่พบสลิป", 404)
    status = "confirmed" if action == "confirm" else "rejected"
    db.execute(
        """UPDATE online_order_payments SET status=?,verified_by=?,verified_at=?,rejection_reason=?,updated_at=?
           WHERE id=?""", (status, g.staff["id"], now(), reason or None, now(), payment_id)
    )
    db.execute("UPDATE online_orders SET payment_status=?,updated_at=? WHERE id=?", (status, now(), order_id))
    audit_order(f"online_payment_{status}", order_id, staff_id=g.staff["id"], detail={"reason": reason or None})
    db.commit()
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.get("/<int:order_id>/payment/<int:payment_id>/slip")
@permission_required("online_orders.verify_payment")
def staff_slip(order_id, payment_id):
    payment = get_db().execute(
        "SELECT slip_path FROM online_order_payments WHERE id=? AND order_id=? AND slip_path IS NOT NULL", (payment_id, order_id)
    ).fetchone()
    if not payment:
        return ("ไม่พบสลิป", 404)
    return send_from_directory(Path(current_app.config["PROJECT_ROOT"]) / "uploads" / "online-payments", payment["slip_path"])


@bp.post("/<int:order_id>/items/<int:item_id>")
@permission_required("online_orders.accept")
def adjust_item(order_id, item_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    order, reason = load_order(order_id), request.form.get("reason", "").strip()
    try:
        quantity = float(request.form.get("quantity") or 0)
    except ValueError:
        quantity = -1
    if not order or order["status"] not in {"submitted", "accepted"} or not reason or quantity < 0:
        flash("แก้ไขได้ก่อนเริ่มจัดสินค้าและต้องมีคำอธิบายให้ลูกค้า", "error")
        return redirect(url_for("online_staff.detail", order_id=order_id))
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        item = db.execute(
            """SELECT oi.*,p.stock_quantity,p.allow_decimal_quantity,p.price_satang AS current_price_satang
               FROM online_order_items oi
               JOIN products p ON p.id=oi.product_id WHERE oi.id=? AND oi.order_id=?""", (item_id, order_id)
        ).fetchone()
        if not item or (not item["allow_decimal_quantity"] and quantity != int(quantity)):
            raise ValueError("จำนวนสินค้าไม่ถูกต้อง")
        reserved_elsewhere = db.execute(
            """SELECT COALESCE(SUM(quantity),0) FROM stock_reservations
               WHERE product_id=? AND status='active' AND order_id<>?""", (item["product_id"], order_id)
        ).fetchone()[0]
        if quantity > item["stock_quantity"] - reserved_elsewhere:
            raise ValueError("สินค้าไม่เพียงพอ")
        line_total = round(item["current_price_satang"] * quantity)
        db.execute(
            """UPDATE online_order_items SET ordered_quantity=?,unit_price_satang=?,line_total_satang=?,is_removed=?
               WHERE id=?""",
            (max(quantity, 0.000001), item["current_price_satang"], line_total,
             1 if quantity == 0 else 0, item_id),
        )
        if quantity == 0:
            db.execute("""UPDATE stock_reservations SET status='released',released_at=?,release_reason='item_removed'
                          WHERE order_id=? AND product_id=? AND status='active'""", (now(), order_id, item["product_id"]))
        else:
            db.execute(
                """INSERT INTO stock_reservations(order_id,product_id,quantity,status,created_at) VALUES(?,?,?,'active',?)
                   ON CONFLICT(order_id,product_id) DO UPDATE SET quantity=excluded.quantity,status='active',
                   released_at=NULL,release_reason=NULL""", (order_id, item["product_id"], quantity, now())
            )
        subtotal, total = refresh_order_totals(order_id)
        db.execute(
            "UPDATE online_orders SET customer_visible_note=?,updated_at=? WHERE id=?",
            (reason, now(), order_id),
        )
        record_history(order_id, order["status"], order["status"], "staff", staff_id=g.staff["id"], reason=reason)
        audit_order("online_order_item_adjusted", order_id, staff_id=g.staff["id"],
                    detail={"item_id": item_id, "old_quantity": item["ordered_quantity"], "new_quantity": quantity,
                            "old_unit_price_satang": item["unit_price_satang"],
                            "new_unit_price_satang": item["current_price_satang"],
                            "subtotal_satang": subtotal, "total_satang": total, "reason": reason})
        db.commit()
    except ValueError as exc:
        db.rollback(); flash(str(exc), "error")
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.post("/<int:order_id>/items")
@permission_required("online_orders.accept")
def add_item(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    order = load_order(order_id)
    product_id = request.form.get("product_id", type=int)
    reason = request.form.get("reason", "").strip()
    try:
        quantity = float(request.form.get("quantity") or 0)
    except ValueError:
        quantity = 0
    if not order or order["status"] != "accepted" or not reason or quantity <= 0:
        flash("เพิ่มสินค้าได้ก่อนเริ่มจัดสินค้าและต้องมีคำอธิบายให้ลูกค้า", "error")
        return redirect(url_for("online_staff.detail", order_id=order_id))
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        product = db.execute(
            """SELECT id,name_th,barcode,price_satang,stock_quantity,allow_decimal_quantity
               FROM products WHERE id=? AND is_active=1""",
            (product_id,),
        ).fetchone()
        if not product or (not product["allow_decimal_quantity"] and quantity != int(quantity)):
            raise ValueError("สินค้าและจำนวนไม่ถูกต้อง")
        existing = db.execute(
            "SELECT id,is_removed FROM online_order_items WHERE order_id=? AND product_id=?",
            (order_id, product_id),
        ).fetchone()
        if existing and not existing["is_removed"]:
            raise ValueError("สินค้านี้อยู่ในออเดอร์แล้ว กรุณาแก้จำนวนที่รายการเดิม")
        reserved_elsewhere = db.execute(
            """SELECT COALESCE(SUM(quantity),0) FROM stock_reservations
               WHERE product_id=? AND status='active' AND order_id<>?""",
            (product_id, order_id),
        ).fetchone()[0]
        if quantity > product["stock_quantity"] - reserved_elsewhere:
            raise ValueError("สินค้าไม่เพียงพอ")
        line_total = round(product["price_satang"] * quantity)
        if existing:
            db.execute(
                """UPDATE online_order_items SET product_name_snapshot=?,barcode_snapshot=?,
                   unit_price_satang=?,ordered_quantity=?,prepared_quantity=0,reconciled_quantity=0,
                   delivered_quantity=0,line_total_satang=?,missing_flag=0,preparation_note=NULL,is_removed=0
                   WHERE id=?""",
                (product["name_th"], product["barcode"], product["price_satang"],
                 quantity, line_total, existing["id"]),
            )
            item_id = existing["id"]
        else:
            cursor = db.execute(
                """INSERT INTO online_order_items
                   (order_id,product_id,product_name_snapshot,barcode_snapshot,unit_price_satang,
                    customer_confirmed_unit_price_satang,original_quantity,ordered_quantity,line_total_satang)
                   VALUES(?,?,?,?,?,NULL,?,?,?)""",
                (order_id, product_id, product["name_th"], product["barcode"], product["price_satang"],
                 quantity, quantity, line_total),
            )
            item_id = cursor.lastrowid
        db.execute(
            """INSERT INTO stock_reservations(order_id,product_id,quantity,status,created_at)
               VALUES(?,?,?,'active',?)
               ON CONFLICT(order_id,product_id) DO UPDATE SET quantity=excluded.quantity,status='active',
               released_at=NULL,release_reason=NULL""",
            (order_id, product_id, quantity, now()),
        )
        subtotal, total = refresh_order_totals(order_id)
        db.execute(
            "UPDATE online_orders SET customer_visible_note=?,updated_at=? WHERE id=?",
            (reason, now(), order_id),
        )
        record_history(order_id, order["status"], order["status"], "staff",
                       staff_id=g.staff["id"], reason=reason)
        audit_order(
            "online_order_item_added", order_id, staff_id=g.staff["id"],
            detail={"item_id": item_id, "product_id": product_id, "quantity": quantity,
                    "unit_price_satang": product["price_satang"],
                    "subtotal_satang": subtotal, "total_satang": total, "reason": reason},
        )
        db.commit()
        flash("เพิ่มสินค้าแล้ว กรุณาแจ้งลูกค้าเพื่อยืนยันยอดราคาใหม่", "success")
    except ValueError as exc:
        db.rollback()
        flash(str(exc), "error")
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.post("/<int:order_id>/notes")
@permission_required("online_orders.view")
def notes(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    internal = request.form.get("internal_note", "").strip()[:1000]
    visible = request.form.get("customer_visible_note", "").strip()[:1000]
    db = get_db()
    db.execute("UPDATE online_orders SET internal_note=?,customer_visible_note=?,updated_at=? WHERE id=?", (internal or None, visible or None, now(), order_id))
    audit_order("online_order_notes_updated", order_id, staff_id=g.staff["id"], detail={"customer_visible": bool(visible)})
    db.commit()
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.post("/<int:order_id>/preparation/start")
@permission_required("online_orders.prepare")
def start_preparation(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    order = load_order(order_id)
    try:
        db = get_db(); db.execute("BEGIN IMMEDIATE")
        transition(order, "preparing", {"accepted"}, "เริ่มจัดสินค้า")
        db.execute("UPDATE online_orders SET prepared_by=?,preparation_started_at=? WHERE id=?", (g.staff["id"], now(), order_id))
        db.commit()
    except ValueError as exc:
        get_db().rollback(); flash(str(exc), "error")
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.post("/<int:order_id>/preparation")
@permission_required("online_orders.prepare")
def save_preparation(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    order = load_order(order_id)
    if not order or order["status"] != "preparing":
        return ("สถานะออเดอร์ไม่ถูกต้อง", 400)
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        items = db.execute("SELECT * FROM online_order_items WHERE order_id=? AND is_removed=0", (order_id,)).fetchall()
        for item in items:
            if f"prepared_{item['id']}" not in request.form:
                continue
            quantity = float(request.form.get(f"prepared_{item['id']}") or 0)
            if quantity < 0 or quantity > item["ordered_quantity"]:
                raise ValueError("จำนวนที่จัดต้องไม่เกินจำนวนที่สั่ง")
            missing = 1 if request.form.get(f"missing_{item['id']}") else 0
            note = request.form.get(f"note_{item['id']}", "").strip()[:300] or None
            db.execute("UPDATE online_order_items SET prepared_quantity=?,missing_flag=?,preparation_note=? WHERE id=?",
                       (quantity, missing, note, item["id"]))
        incomplete = db.execute(
            """SELECT COUNT(*) FROM online_order_items WHERE order_id=? AND is_removed=0
               AND (ABS(prepared_quantity-ordered_quantity)>0.000001 OR missing_flag=1)""", (order_id,)
        ).fetchone()[0]
        all_ready = incomplete == 0
        if request.form.get("complete"):
            if not all_ready:
                raise ValueError("ยังจัดสินค้าไม่ครบหรือมีรายการสูญหาย")
            transition(order, "reconciling", {"preparing"}, "จัดสินค้าครบ รอตรวจสอบก่อนส่ง")
        audit_order("online_order_preparation_saved", order_id, staff_id=g.staff["id"], detail={"complete": all_ready})
        db.commit()
    except ValueError as exc:
        db.rollback(); flash(str(exc), "error")
    if request.form.get("complete") and all_ready:
        return redirect(url_for("online_staff.reconcile", order_id=order_id))
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.get("/<int:order_id>/reconcile")
@permission_required("online_orders.reconcile")
def reconcile(order_id):
    order = load_order(order_id)
    if not order or order["status"] not in {"reconciling", "ready"}:
        return ("ออเดอร์ยังไม่พร้อมตรวจสินค้า", 400)
    items = get_db().execute("SELECT * FROM online_order_items WHERE order_id=? AND is_removed=0 ORDER BY id", (order_id,)).fetchall()
    events = get_db().execute(
        """SELECT e.*,st.display_name,oi.product_name_snapshot FROM order_reconciliation_events e
           JOIN staff st ON st.id=e.staff_id JOIN online_order_items oi ON oi.id=e.order_item_id
           WHERE e.order_id=? ORDER BY e.created_at DESC,e.id DESC""", (order_id,)
    ).fetchall()
    return render_template("online/reconcile.html", order=order, items=items, events=events)


@bp.post("/<int:order_id>/reconcile/scan")
@permission_required("online_orders.reconcile")
def reconcile_scan(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    barcode = request.form.get("barcode", "").strip()
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        order = load_order(order_id)
        if not order or order["status"] != "reconciling":
            raise ValueError("สถานะออเดอร์ไม่พร้อมตรวจสินค้า")
        item = db.execute("SELECT * FROM online_order_items WHERE order_id=? AND is_removed=0 AND barcode_snapshot=?", (order_id, barcode)).fetchone()
        if not item:
            raise ValueError("บาร์โค้ดนี้ไม่อยู่ในออเดอร์")
        if item["reconciled_quantity"] + 1 > item["ordered_quantity"]:
            raise ValueError("สแกนเกินจำนวนที่สั่ง")
        db.execute("UPDATE online_order_items SET reconciled_quantity=reconciled_quantity+1 WHERE id=?", (item["id"],))
        db.execute("""INSERT INTO order_reconciliation_events(order_id,order_item_id,method,quantity,barcode_scanned,staff_id,created_at)
                      VALUES(?,?,'barcode',1,?,?,?)""", (order_id, item["id"], barcode, g.staff["id"], now()))
        if not order["reconciliation_started_at"]:
            db.execute("UPDATE online_orders SET reconciliation_started_at=? WHERE id=?", (now(), order_id))
        audit_order("online_item_scanned", order_id, staff_id=g.staff["id"], detail={"item_id": item["id"], "barcode": barcode})
        db.commit()
        flash(f"สแกน {item['product_name_snapshot']} แล้ว", "success")
    except ValueError as exc:
        db.rollback(); flash(str(exc), "error")
    return redirect(url_for("online_staff.reconcile", order_id=order_id))


@bp.post("/<int:order_id>/reconcile/manual/<int:item_id>")
@permission_required("online_orders.reconcile")
def reconcile_manual(order_id, item_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    reason = request.form.get("reason", "").strip() or "ยืนยันด้วยตนเอง"
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        order = load_order(order_id)
        item = db.execute("SELECT * FROM online_order_items WHERE id=? AND order_id=? AND is_removed=0", (item_id, order_id)).fetchone()
        if not order or order["status"] != "reconciling" or not item:
            raise ValueError("สถานะออเดอร์หรือรายการไม่ถูกต้อง")
        remaining = item["ordered_quantity"] - item["reconciled_quantity"]
        if remaining <= 0:
            raise ValueError("รายการนี้ตรวจครบแล้ว")
        db.execute("UPDATE online_order_items SET reconciled_quantity=ordered_quantity WHERE id=?", (item_id,))
        db.execute("""INSERT INTO order_reconciliation_events(order_id,order_item_id,method,quantity,reason,staff_id,created_at)
                      VALUES(?,?,'manual',?,?,?,?)""", (order_id, item_id, remaining, reason, g.staff["id"], now()))
        if not order["reconciliation_started_at"]:
            db.execute("UPDATE online_orders SET reconciliation_started_at=? WHERE id=?", (now(), order_id))
        audit_order("online_item_manual_reconciliation", order_id, staff_id=g.staff["id"], detail={"item_id": item_id, "quantity": remaining, "reason": reason})
        db.commit()
    except ValueError as exc:
        db.rollback(); flash(str(exc), "error")
    return redirect(url_for("online_staff.reconcile", order_id=order_id))


@bp.post("/<int:order_id>/reconcile/complete")
@permission_required("online_orders.reconcile")
def complete_reconciliation(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        order = load_order(order_id)
        if not order or order["status"] != "reconciling":
            raise ValueError("สถานะออเดอร์ไม่ถูกต้อง")
        incomplete = db.execute(
            """SELECT COUNT(*) FROM online_order_items WHERE order_id=? AND is_removed=0
               AND (ABS(reconciled_quantity-ordered_quantity)>0.000001 OR missing_flag=1)""", (order_id,)
        ).fetchone()[0]
        if incomplete:
            raise ValueError("ยังตรวจสินค้าไม่ครบหรือมีสินค้าขาด")
        transition(order, "ready", {"reconciling"}, "ตรวจสินค้าครบ พร้อมจัดส่ง")
        db.execute("UPDATE online_orders SET reconciled_by=?,reconciliation_completed_at=? WHERE id=?", (g.staff["id"], now(), order_id))
        audit_order("online_reconciliation_completed", order_id, staff_id=g.staff["id"], detail={"same_as_preparer": order["prepared_by"] == g.staff["id"]})
        db.commit()
        print_status = "queued" if enqueue_print("checked_order", order_id) else "manual"
    except ValueError as exc:
        db.rollback(); flash(str(exc), "error")
        print_status = None
    return redirect(url_for("online_staff.detail", order_id=order_id, print_status=print_status))


@bp.post("/<int:order_id>/items/reopen")
@permission_required("online_orders.accept")
def reopen_items(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    order = load_order(order_id)
    try:
        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        transition(order, "accepted", {"ready"}, "เปิดแก้ไขรายการสินค้าหลังตรวจ")
        db.execute(
            """UPDATE online_orders SET reconciliation_started_at=NULL,reconciliation_completed_at=NULL,
               reconciled_by=NULL,updated_at=? WHERE id=?""", (now(), order_id)
        )
        db.execute(
            """UPDATE online_order_items SET prepared_quantity=0,reconciled_quantity=0,
               missing_flag=0,preparation_note=NULL WHERE order_id=?""", (order_id,)
        )
        audit_order("online_order_items_reopened", order_id, staff_id=g.staff["id"])
        db.commit()
        flash("เปิดให้แก้ไขรายการแล้ว เมื่อเสร็จให้เริ่มจัดและตรวจสินค้าใหม่", "success")
    except (TypeError, ValueError) as exc:
        get_db().rollback()
        flash(str(exc), "error")
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.post("/<int:order_id>/assign")
@permission_required("online_orders.assign")
def assign_delivery(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    staff_id = request.form.get("staff_id", type=int)
    staff = get_db().execute("SELECT id FROM staff WHERE id=? AND is_active=1", (staff_id,)).fetchone()
    if not staff:
        flash("ไม่พบพนักงานที่เลือก", "error")
    else:
        db = get_db(); db.execute("BEGIN IMMEDIATE")
        db.execute("""UPDATE online_orders SET assigned_staff_id=?,assigned_at=?,updated_at=? WHERE id=?
                      AND status NOT IN ('completed','customer_cancelled','staff_cancelled','rejected','expired')""",
                   (staff_id, now(), now(), order_id))
        audit_order("online_delivery_assigned", order_id, staff_id=g.staff["id"], detail={"assigned_staff_id": staff_id})
        db.commit()
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.post("/<int:order_id>/delivery/start")
@permission_required("online_orders.deliver")
def start_delivery(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    try:
        db = get_db(); db.execute("BEGIN IMMEDIATE")
        order = load_order(order_id)
        staff_id = request.form.get("staff_id", type=int) or (order["assigned_staff_id"] if order else None)
        staff = db.execute("SELECT id FROM staff WHERE id=? AND is_active=1", (staff_id,)).fetchone()
        if not staff or not order or not order["reconciliation_completed_at"]:
            raise ValueError("ต้องตรวจสินค้าครบและเลือกผู้จัดส่งก่อน")
        transition(order, "delivering", {"ready"}, "ออกจัดส่งแล้ว")
        db.execute(
            """UPDATE online_orders SET assigned_staff_id=?,assigned_at=?,delivery_started_at=?,updated_at=?
               WHERE id=?""",
            (staff_id, now(), now(), now(), order_id),
        )
        audit_order("online_delivery_assigned", order_id, staff_id=g.staff["id"],
                    detail={"assigned_staff_id": staff_id, "saved_with_delivery_start": True})
        db.commit()
    except ValueError as exc:
        get_db().rollback(); flash(str(exc), "error")
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.post("/<int:order_id>/cancel")
@permission_required("online_orders.cancel")
def staff_cancel(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    reason = request.form.get("reason", "").strip()
    order = load_order(order_id)
    if not reason or not order or order["status"] in FINAL:
        flash("กรุณาระบุเหตุผลหรือออเดอร์สิ้นสุดแล้ว", "error")
    else:
        db = get_db(); db.execute("BEGIN IMMEDIATE")
        release_reservations(order_id, "staff_cancelled")
        payment_status = "refund_pending" if order["payment_status"] == "confirmed" else order["payment_status"]
        db.execute("""UPDATE online_orders SET status='staff_cancelled',payment_status=?,cancellation_reason=?,
                      cancelled_at=?,updated_at=? WHERE id=?""", (payment_status, reason, now(), now(), order_id))
        record_history(order_id, order["status"], "staff_cancelled", "staff", staff_id=g.staff["id"], reason=reason)
        audit_order("online_order_staff_cancelled", order_id, staff_id=g.staff["id"], detail={"reason": reason})
        db.commit()
    return redirect(url_for("online_staff.detail", order_id=order_id))


@bp.post("/<int:order_id>/delivery/complete")
@permission_required("online_orders.deliver")
def complete_delivery(order_id):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    try:
        received = round(float(request.form.get("cash_received") or 0) * 100)
        sale_id, receipt, change = complete_online_order_sale(
            order_id, g.staff["id"], g.staff["role_code"],
            {"cash_received_satang": received, "delivery_result": request.form.get("delivery_result"),
             "delivery_note": request.form.get("delivery_note"),
             "payment_method": request.form.get("payment_method"),
             "payment_method_confirmed": request.form.get("payment_method_confirmed"),
             "payment_override_reason": request.form.get("payment_override_reason")},
        )
        change_message = f" เงินทอน {change / 100:,.2f} บาท" if change else ""
        flash(f"ยืนยันส่งสำเร็จและปิดออเดอร์แล้ว{change_message}", "success")
        return redirect(url_for("online_staff.detail", order_id=order_id))
    except (OnlineOrderError, SaleError, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("online_staff.detail", order_id=order_id))
