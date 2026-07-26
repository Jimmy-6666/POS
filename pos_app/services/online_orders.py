import json
import secrets
from datetime import datetime, timedelta, timezone

from flask import request

from ..auth import iso_time, utc_now
from ..database import get_db
from .sales import SaleError, complete_sale


class OnlineOrderError(ValueError):
    pass


def record_history(order_id, previous_status, new_status, actor_type, *, customer_id=None, staff_id=None, reason=None, customer_visible=True):
    get_db().execute(
        """INSERT INTO online_order_status_history
           (order_id,previous_status,new_status,actor_type,actor_customer_id,actor_staff_id,reason,customer_visible,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (order_id, previous_status, new_status, actor_type, customer_id, staff_id, reason,
         1 if customer_visible else 0, iso_time(utc_now())),
    )


def audit_order(action, order_id, *, staff_id=None, detail=None):
    get_db().execute(
        """INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,new_value,ip_address,created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (staff_id, action, "online_order", str(order_id),
         json.dumps(detail, ensure_ascii=False) if detail is not None else None,
         request.remote_addr if request else None, iso_time(utc_now())),
    )


def release_reservations(order_id, reason, *, status="released"):
    now = iso_time(utc_now())
    get_db().execute(
        """UPDATE stock_reservations SET status=?,released_at=?,release_reason=?
           WHERE order_id=? AND status='active'""",
        (status, now, reason, order_id),
    )


def expire_pending_orders():
    db = get_db()
    enabled = db.execute("SELECT value FROM settings WHERE key='online_auto_expiry'").fetchone()
    if not enabled or enabled[0] != "1":
        return 0
    rows = db.execute(
        """SELECT id,status FROM online_orders WHERE status IN ('submitted','accepted')
           AND expires_at IS NOT NULL AND expires_at<=?""",
        (iso_time(utc_now()),),
    ).fetchall()
    if not rows:
        return 0
    db.execute("BEGIN IMMEDIATE")
    for row in rows:
        release_reservations(row["id"], "order_expired")
        now = iso_time(utc_now())
        db.execute("UPDATE online_orders SET status='expired',cancelled_at=?,updated_at=? WHERE id=?", (now, now, row["id"]))
        record_history(row["id"], row["status"], "expired", "system", reason="หมดเวลารอการดำเนินการ")
        audit_order("online_order_expired", row["id"])
    db.commit()
    return len(rows)


def create_order(customer_id, payload, validate_cart, settings, location):
    db = get_db()
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if len(idempotency_key) < 12 or len(idempotency_key) > 100:
        raise OnlineOrderError("คำขอยืนยันออเดอร์ไม่ถูกต้อง กรุณาลองใหม่")
    existing = db.execute(
        "SELECT public_id,order_number FROM online_orders WHERE customer_id=? AND idempotency_key=?",
        (customer_id, idempotency_key),
    ).fetchone()
    if existing:
        return existing, True
    method = payload.get("payment_method")
    if method not in {"cash", "transfer"} or (method == "transfer" and settings.get("online_transfer_enabled") != "1"):
        raise OnlineOrderError("วิธีชำระเงินไม่พร้อมใช้งาน")
    room = str(payload.get("room_reference") or "").strip()
    if location["room_required"] and not room:
        raise OnlineOrderError("กรุณาระบุห้อง วิลล่า หรือจุดรับสินค้า")
    now = utc_now()
    try:
        if not db.in_transaction:
            db.execute("BEGIN IMMEDIATE")
        items = validate_cart(payload.get("items"))
        subtotal = sum(item["line_total_satang"] for item in items)
        minimum = max(int(settings.get("online_minimum_order_satang") or 0), location["minimum_order_satang"])
        if subtotal < minimum:
            raise OnlineOrderError(f"ยอดสินค้าขั้นต่ำ {minimum / 100:,.2f} บาท")
        local_date = datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d")
        sequence_row = db.execute("SELECT last_number FROM online_order_sequences WHERE order_date=?", (local_date,)).fetchone()
        sequence = (sequence_row[0] if sequence_row else 0) + 1
        db.execute("""INSERT INTO online_order_sequences(order_date,last_number) VALUES(?,?)
                      ON CONFLICT(order_date) DO UPDATE SET last_number=excluded.last_number""", (local_date, sequence))
        order_number = f"WEB-{local_date}-{sequence:04d}"
        public_id = secrets.token_urlsafe(12)
        delivery_fee = 0 if subtotal >= 10000 else location["delivery_fee_satang"]
        total = subtotal + delivery_fee
        expires_at = iso_time(now + timedelta(minutes=max(5, int(settings.get("online_order_expiry_minutes") or 60))))
        cursor = db.execute(
            """INSERT INTO online_orders
               (public_id,order_number,customer_id,contact_phone,contact_name,delivery_location_id,location_name_snapshot,delivery_fee_satang,
                room_reference,payment_method_code,payment_status,status,subtotal_satang,total_satang,customer_note,
                idempotency_key,expires_at,cash_expected_satang,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,'submitted',?,?,?,?,?,?,?,?)""",
            (public_id, order_number, customer_id, payload.get("contact_phone"), payload.get("contact_name"),
             location["id"], location["name"], delivery_fee,
             room, method, "unpaid", subtotal, total, str(payload.get("customer_note") or "").strip()[:500] or None,
             idempotency_key, expires_at, int(payload.get("cash_expected_satang") or 0) or None, iso_time(now), iso_time(now)),
        )
        order_id = cursor.lastrowid
        for item in items:
            db.execute(
                """INSERT INTO online_order_items
                   (order_id,product_id,product_name_snapshot,barcode_snapshot,unit_price_satang,
                    customer_confirmed_unit_price_satang,original_quantity,ordered_quantity,line_total_satang)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (order_id, item["product_id"], item["name_th"], item["barcode"], item["unit_price_satang"],
                 item["unit_price_satang"], item["quantity"], item["quantity"], item["line_total_satang"]),
            )
            db.execute("""INSERT INTO stock_reservations(order_id,product_id,quantity,status,created_at)
                          VALUES(?,?,?,'active',?)""", (order_id, item["product_id"], item["quantity"], iso_time(now)))
        db.execute("""INSERT INTO online_order_payments(order_id,method_code,amount_satang,status,created_at,updated_at)
                      VALUES(?,?,?,'unpaid',?,?)""", (order_id, method, total, iso_time(now), iso_time(now)))
        record_history(order_id, None, "submitted", "customer", customer_id=customer_id, reason="ส่งออเดอร์ให้ร้านตรวจสอบ")
        audit_order("online_order_submitted", order_id, detail={"order_number": order_number, "total_satang": total})
        audit_order("stock_reserved", order_id, detail={"items": len(items)})
        db.commit()
        return {"public_id": public_id, "order_number": order_number}, False
    except Exception:
        db.rollback()
        raise


def cancel_customer_order(order, customer_id, reason):
    if order["status"] not in {"submitted", "accepted"}:
        raise OnlineOrderError("ออเดอร์นี้เริ่มจัดสินค้าแล้ว กรุณาติดต่อร้าน")
    reason = str(reason or "").strip()
    if not reason:
        raise OnlineOrderError("กรุณาระบุเหตุผลการยกเลิก")
    db = get_db()
    now = iso_time(utc_now())
    db.execute("BEGIN IMMEDIATE")
    payment_status = "refund_pending" if order["payment_status"] == "confirmed" else order["payment_status"]
    release_reservations(order["id"], "customer_cancelled")
    cursor = db.execute(
        """UPDATE online_orders SET status='customer_cancelled',payment_status=?,cancellation_reason=?,
           cancelled_at=?,updated_at=? WHERE id=? AND status IN ('submitted','accepted')""",
        (payment_status, reason, now, now, order["id"]),
    )
    if cursor.rowcount != 1:
        db.rollback()
        raise OnlineOrderError("ออเดอร์นี้ไม่สามารถยกเลิกได้")
    record_history(order["id"], order["status"], "customer_cancelled", "customer", customer_id=customer_id, reason=reason)
    audit_order("online_order_customer_cancelled", order["id"], detail={"reason": reason})
    audit_order("stock_reservation_released", order["id"], detail={"reason": "customer_cancelled"})
    db.commit()


def complete_online_order_sale(order_id, staff_id, staff_role, payload):
    db = get_db()
    delivery_result = str(payload.get("delivery_result") or "").strip()
    if delivery_result not in {"delivered", "reception", "customer_pickup"}:
        raise OnlineOrderError("กรุณายืนยันวิธีส่งมอบสินค้า")
    payment_method = str(payload.get("payment_method") or "").strip()
    if payment_method not in {"cash", "transfer"}:
        raise OnlineOrderError("กรุณาเลือกช่องทางการชำระเงินจริงหน้างาน")
    if str(payload.get("payment_method_confirmed") or "") != "1":
        raise OnlineOrderError("กรุณายืนยันว่าตรวจสอบช่องทางการชำระเงินกับลูกค้าแล้ว")
    try:
        cash_received = int(payload.get("cash_received_satang") or 0)
    except (TypeError, ValueError) as exc:
        raise OnlineOrderError("จำนวนเงินสดไม่ถูกต้อง") from exc
    override_reason = str(payload.get("payment_override_reason") or "").strip()
    try:
        db.execute("BEGIN IMMEDIATE")
        order = db.execute("SELECT * FROM online_orders WHERE id=?", (order_id,)).fetchone()
        if not order or order["status"] != "delivering" or order["sale_id"] is not None:
            raise OnlineOrderError("ออเดอร์นี้ไม่พร้อมปิดการจัดส่งหรือถูกปิดแล้ว")
        incomplete = db.execute(
            """SELECT COUNT(*) FROM online_order_items WHERE order_id=? AND is_removed=0
               AND ABS(reconciled_quantity-ordered_quantity)>0.000001""", (order_id,)
        ).fetchone()[0]
        if incomplete or not order["reconciliation_completed_at"]:
            raise OnlineOrderError("การตรวจสินค้ายังไม่ครบ")
        # Delivery staff confirms the actual method at handoff because customers may change it on site.
        if payment_method == "cash" and cash_received < order["total_satang"]:
            raise OnlineOrderError("เงินสดที่รับน้อยกว่ายอดออเดอร์")
        rows = db.execute("SELECT * FROM online_order_items WHERE order_id=? AND is_removed=0 ORDER BY id", (order_id,)).fetchall()
        items = [{"product_id": row["product_id"], "quantity": row["ordered_quantity"], "discount_satang": 0} for row in rows]
        prices = {row["product_id"]: row["unit_price_satang"] for row in rows}
        latest_slip = db.execute(
            "SELECT slip_path FROM online_order_payments WHERE order_id=? AND slip_path IS NOT NULL ORDER BY id DESC LIMIT 1", (order_id,)
        ).fetchone()
        sale_id, receipt, cart, change = complete_sale(
            {"items": items, "bill_discount_satang": 0, "delivery_fee_satang": order["delivery_fee_satang"],
             "payment_method": payment_method, "amount_received_satang": cash_received,
             "payment_confirmed": payment_method == "transfer",
             "evidence_image_path": latest_slip["slip_path"] if latest_slip else None,
             "customer_note": f"ออเดอร์ออนไลน์ {order['order_number']}"},
            staff_id, manage_transaction=False, online_order_id=order_id, unit_price_overrides=prices,
        )
        if cart["total_satang"] != order["total_satang"]:
            raise OnlineOrderError("ยอดออเดอร์กับยอดขายไม่ตรงกัน")
        current = iso_time(utc_now())
        db.execute("""UPDATE stock_reservations SET status='converted',released_at=?,release_reason='converted_to_sale'
                      WHERE order_id=? AND status='active'""", (current, order_id))
        db.execute("UPDATE online_order_items SET delivered_quantity=ordered_quantity WHERE order_id=? AND is_removed=0", (order_id,))
        db.execute(
            """UPDATE online_orders SET status='completed',payment_status='confirmed',payment_method_code=?,sale_id=?,cash_received_satang=?,
               change_satang=?,cash_received_by=?,delivery_result=?,delivery_note=?,completed_at=?,updated_at=?
               WHERE id=? AND sale_id IS NULL""",
            (payment_method, sale_id, cash_received if payment_method == "cash" else None, change,
             staff_id if payment_method == "cash" else None, delivery_result,
             str(payload.get("delivery_note") or "").strip()[:500] or None, current, current, order_id),
        )
        db.execute(
            """UPDATE online_order_payments SET method_code=?,amount_satang=?,status='confirmed',verified_by=COALESCE(verified_by,?),
               verified_at=COALESCE(verified_at,?),updated_at=? WHERE id=(
                 SELECT id FROM online_order_payments WHERE order_id=? ORDER BY id DESC LIMIT 1)""",
            (payment_method, order["total_satang"], staff_id, current, current, order_id),
        )
        record_history(order_id, "delivering", "completed", "staff", staff_id=staff_id, reason="ส่งมอบสินค้าเรียบร้อย")
        if payment_method == "cash":
            audit_order("online_cash_collected", order_id, staff_id=staff_id, detail={"received": cash_received, "change": change})
        if payment_method != order["payment_method_code"]:
            audit_order("online_payment_override", order_id, staff_id=staff_id, detail={
                "from": order["payment_method_code"], "to": payment_method,
                "reason": override_reason or "ลูกค้าเปลี่ยนช่องทางชำระเงินหน้างาน",
            })
        audit_order("online_payment_method_confirmed", order_id, staff_id=staff_id, detail={"method": payment_method})
        audit_order("online_delivery_completed", order_id, staff_id=staff_id, detail={"result": delivery_result, "payment_method": payment_method})
        audit_order("online_sale_created", order_id, staff_id=staff_id, detail={"sale_id": sale_id, "receipt": receipt})
        db.commit()
        return sale_id, receipt, change
    except Exception:
        db.rollback()
        raise
