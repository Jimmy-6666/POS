import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import current_app

from ..database import get_db
from ..product_identity import ProductIdentityError, product_by_uuid


class SaleError(ValueError):
    pass


MANUAL_PRICE_BARCODE = "MANUALPRICE"
MAX_MANUAL_PRICE_SATANG = 9_999_999 * 100
MANUAL_PRICE_REFERENCE_PATTERN = re.compile(r"MP-(\d{8})")


def negative_stock_allowed():
    row = get_db().execute("SELECT value FROM settings WHERE key='allow_negative_stock'").fetchone()
    return bool(row and row[0] == "1")


def _quantity(value, allow_decimal):
    try:
        quantity = Decimal(str(value))
    except InvalidOperation as exc:
        raise SaleError("จำนวนสินค้าไม่ถูกต้อง") from exc
    if quantity <= 0 or (not allow_decimal and quantity != quantity.to_integral_value()):
        raise SaleError("จำนวนสินค้าไม่ถูกต้อง")
    return quantity


def _validated_manual_price(db, raw, product, staff_id, seen_references):
    reference = str(raw.get("manual_price_reference") or "").strip()
    match = MANUAL_PRICE_REFERENCE_PATTERN.fullmatch(reference)
    try:
        raw_price = Decimal(str(raw.get("manual_price_satang")))
        if raw_price != raw_price.to_integral_value():
            raise InvalidOperation
        price_satang = int(raw_price)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SaleError(f"กรุณาระบุราคาขายของ {product['name_th']}") from exc
    if (
        not match
        or staff_id is None
        or price_satang <= 0
        or price_satang > MAX_MANUAL_PRICE_SATANG
        or price_satang % 100
    ):
        raise SaleError(f"ราคาขายที่ระบุสำหรับ {product['name_th']} ไม่ถูกต้อง")
    if reference in seen_references:
        raise SaleError(f"เลขอ้างอิงราคาหน้างาน {reference} ซ้ำในตะกร้า")
    if db.execute(
        "SELECT 1 FROM sale_items WHERE manual_price_reference=?",
        (reference,),
    ).fetchone():
        raise SaleError(f"เลขอ้างอิงราคาหน้างาน {reference} ถูกใช้แล้ว")
    audit = db.execute(
        """SELECT id,staff_id,entity_id,new_value FROM audit_logs
           WHERE id=? AND action='enter_pos_manual_price'""",
        (int(match.group(1)),),
    ).fetchone()
    if (
        not audit
        or audit["staff_id"] != staff_id
        or audit["entity_id"] != product["product_uuid"]
    ):
        raise SaleError(f"ไม่สามารถยืนยันเลขอ้างอิงราคาหน้างาน {reference}")
    try:
        detail = json.loads(audit["new_value"] or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise SaleError(f"ข้อมูลราคาหน้างาน {reference} ไม่ถูกต้อง") from exc
    if (
        detail.get("manual_price_reference") != reference
        or detail.get("manual_price_satang") != price_satang
        or detail.get("barcode") != product["barcode"]
    ):
        raise SaleError(f"ข้อมูลราคาหน้างาน {reference} ไม่ตรงกับรายการขาย")
    seen_references.add(reference)
    return {
        "price_satang": price_satang,
        "reference": reference,
        "reason": detail.get("reason"),
        "barcode": product["barcode"],
    }


def calculate_cart(
    items,
    bill_discount_satang=0,
    *,
    unit_price_overrides=None,
    reservation_order_id=None,
    manual_price_staff_id=None,
):
    if not items:
        raise SaleError("ตะกร้าสินค้าว่าง")
    db = get_db()
    calculated = []
    seen_manual_references = set()
    subtotal = item_discounts = total_cost = 0
    for raw in items:
        try:
            product = product_by_uuid(db, raw.get("product_uuid"), active_only=True)
        except ProductIdentityError as exc:
            raise SaleError(str(exc)) from exc
        if not product:
            raise SaleError("ไม่พบสินค้าหรือสินค้าถูกปิดใช้งาน")
        quantity = _quantity(raw.get("quantity"), product["allow_decimal_quantity"])
        reserved_params = [product["id"]]
        reserved_where = ""
        if reservation_order_id is not None:
            reserved_where = " AND order_id<>?"
            reserved_params.append(reservation_order_id)
        reserved = db.execute(
            f"SELECT COALESCE(SUM(quantity),0) FROM stock_reservations WHERE product_id=? AND status='active'{reserved_where}",
            reserved_params,
        ).fetchone()[0]
        available = Decimal(str(product["stock_quantity"])) - Decimal(str(reserved))
        if not negative_stock_allowed() and quantity > available:
            if reserved > 0:
                raise SaleError(f"{product['name_th']} ถูกสำรองไว้สำหรับออเดอร์ออนไลน์")
            raise SaleError(f"{product['name_th']} มีสต็อกไม่เพียงพอ")
        unit_price = product["price_satang"]
        manual_price = None
        if unit_price_overrides is not None and product["product_uuid"] in unit_price_overrides:
            unit_price = int(unit_price_overrides[product["product_uuid"]])
        elif (
            product["price_satang"] <= 0
            or product["barcode"] == MANUAL_PRICE_BARCODE
            or product["requires_manual_price"]
        ):
            manual_price = _validated_manual_price(
                db, raw, product, manual_price_staff_id, seen_manual_references
            )
            unit_price = manual_price["price_satang"]
        elif raw.get("manual_price_satang") is not None or raw.get("manual_price_reference"):
            raise SaleError(f"{product['name_th']} มีราคาขายในระบบแล้ว")
        line_subtotal = int((Decimal(unit_price) * quantity).quantize(Decimal("1")))
        discount = int(raw.get("discount_satang") or 0)
        if discount < 0 or discount > line_subtotal:
            raise SaleError(f"ส่วนลดของ {product['name_th']} ไม่ถูกต้อง")
        subtotal += line_subtotal
        item_discounts += discount
        total_cost += int((Decimal(product["cost_satang"]) * quantity).quantize(Decimal("1")))
        calculated.append({
            "product": product, "quantity": float(quantity), "discount_satang": discount, "unit_price_satang": unit_price,
            "line_subtotal_satang": line_subtotal, "line_total_satang": line_subtotal - discount,
            "manual_price": manual_price,
        })
    bill_discount_satang = int(bill_discount_satang or 0)
    after_items = subtotal - item_discounts
    if bill_discount_satang < 0 or bill_discount_satang > after_items:
        raise SaleError("ส่วนลดท้ายบิลไม่ถูกต้อง")
    total = after_items - bill_discount_satang
    return {
        "items": calculated, "subtotal_satang": subtotal,
        "item_discount_satang": item_discounts, "bill_discount_satang": bill_discount_satang,
        "total_satang": total, "total_cost_satang": total_cost,
        "gross_profit_satang": total - total_cost,
    }


def complete_sale(
    payload,
    staff_id,
    *,
    manage_transaction=True,
    online_order_id=None,
    unit_price_overrides=None,
    audit_ip=None,
):
    db = get_db()
    try:
        if manage_transaction:
            db.execute("BEGIN IMMEDIATE")
        elif not db.in_transaction:
            raise RuntimeError("complete_sale(manage_transaction=False) requires an active transaction")
        cart = calculate_cart(
            payload.get("items"), payload.get("bill_discount_satang"),
            unit_price_overrides=unit_price_overrides,
            reservation_order_id=online_order_id,
            manual_price_staff_id=staff_id,
        )
        delivery_fee_satang = int(payload.get("delivery_fee_satang") or 0)
        if delivery_fee_satang < 0 or (delivery_fee_satang and online_order_id is None):
            raise SaleError("ค่าจัดส่งไม่ถูกต้อง")
        cart["delivery_fee_satang"] = delivery_fee_satang
        cart["total_satang"] += delivery_fee_satang
        cart["gross_profit_satang"] += delivery_fee_satang
        method = payload.get("payment_method")
        if method not in {"cash", "scan", "transfer", "billing"}:
            raise SaleError("วิธีชำระเงินไม่ถูกต้อง")
        try:
            received = int(payload.get("amount_received_satang") or 0)
        except (TypeError, ValueError) as exc:
            raise SaleError("จำนวนเงินที่รับไม่ถูกต้อง") from exc
        if method == "cash" and received < cart["total_satang"]:
            raise SaleError("จำนวนเงินที่รับน้อยกว่ายอดชำระ")
        if method in {"scan", "transfer"} and not payload.get("payment_confirmed"):
            raise SaleError("กรุณายืนยันว่าได้รับเงินแล้ว")
        if method != "cash":
            received = 0 if method == "billing" else cart["total_satang"]
        change = received - cart["total_satang"] if method == "cash" else 0
    except Exception:
        if manage_transaction:
            db.rollback()
        raise
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    local_date = datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d")
    try:
        row = db.execute("SELECT last_number FROM receipt_sequences WHERE sale_date = ?", (local_date,)).fetchone()
        sequence = (row[0] if row else 0) + 1
        db.execute(
            "INSERT INTO receipt_sequences (sale_date, last_number) VALUES (?, ?) ON CONFLICT(sale_date) DO UPDATE SET last_number=excluded.last_number",
            (local_date, sequence),
        )
        prefix = db.execute("SELECT value FROM settings WHERE key = 'receipt_prefix'").fetchone()[0]
        receipt_number = f"{prefix}-{local_date}-{sequence:04d}"
        cursor = db.execute(
            """INSERT INTO sales
               (receipt_number, cashier_id, subtotal_satang, item_discount_satang, bill_discount_satang, delivery_fee_satang,
                total_satang, total_cost_satang, gross_profit_satang, payment_method_code,
                amount_received_satang, change_satang, bank_name, payment_reference, evidence_image_path, customer_note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (receipt_number, staff_id, cart["subtotal_satang"], cart["item_discount_satang"],
             cart["bill_discount_satang"], delivery_fee_satang, cart["total_satang"], cart["total_cost_satang"],
             cart["gross_profit_satang"], method, received, change, payload.get("bank_name"),
             payload.get("payment_reference"), payload.get("evidence_image_path"), payload.get("customer_note"), now),
        )
        sale_id = cursor.lastrowid
        if method == "billing":
            customer_id = int(payload.get("billing_customer_id") or 0)
            customer = db.execute("SELECT id,credit_limit_satang FROM billing_customers WHERE id=? AND is_active=1", (customer_id,)).fetchone()
            if not customer:
                raise SaleError("กรุณาเลือกลูกค้าที่ได้รับสิทธิ์วางบิล")
            outstanding = db.execute("SELECT COALESCE(SUM(original_satang-paid_satang),0) FROM billed_sales WHERE customer_id=? AND status IN ('outstanding','partial')", (customer_id,)).fetchone()[0]
            if customer["credit_limit_satang"] and outstanding + cart["total_satang"] > customer["credit_limit_satang"]:
                raise SaleError("ยอดวางบิลเกินวงเงินของลูกค้า")
            db.execute("""INSERT INTO billed_sales(sale_id,customer_id,original_satang,due_date,note,status,created_at,updated_at)
                VALUES(?,?,?,?,?,'outstanding',?,?)""", (sale_id,customer_id,cart["total_satang"],payload.get("billing_due_date") or None,payload.get("billing_note") or None,now,now))
        for item in cart["items"]:
            product = db.execute("SELECT * FROM products WHERE id = ?", (item["product"]["id"],)).fetchone()
            new_stock = product["stock_quantity"] - item["quantity"]
            manual_reference = (
                item["manual_price"]["reference"] if item["manual_price"] else None
            )
            sale_item_name = product["name_th"]
            if (
                manual_reference
                and item["manual_price"]["reason"] != "product_manual_price"
            ):
                sale_item_name = f"รายการระบุราคา {manual_reference}"
            sale_item = db.execute(
                """INSERT INTO sale_items
                   (sale_id, product_id, product_name, quantity, unit_price_satang, discount_satang,
                    cost_satang, line_total_satang, manual_price_reference)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sale_id,
                    product["id"],
                    sale_item_name,
                    item["quantity"],
                    item["unit_price_satang"],
                    item["discount_satang"],
                    product["cost_satang"],
                    item["line_total_satang"],
                    manual_reference,
                ),
            )
            db.execute("UPDATE products SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_stock, product["id"]))
            db.execute(
                """INSERT INTO stock_movements
                   (product_id, movement_type, previous_quantity, changed_quantity, new_quantity,
                    unit_cost_satang, reference_type, reference_number, staff_id, created_at)
                   VALUES (?, 'sale', ?, ?, ?, ?, 'sale', ?, ?, ?)""",
                (product["id"], product["stock_quantity"], -item["quantity"], new_stock,
                 product["cost_satang"], receipt_number, staff_id, now),
            )
            if item["manual_price"]:
                db.execute(
                    """INSERT INTO audit_logs
                       (staff_id,action,entity_type,entity_id,new_value,ip_address,created_at)
                       VALUES (?,'sell_with_manual_price','sale_item',?,?,?,?)""",
                    (
                        staff_id,
                        str(sale_item.lastrowid),
                        json.dumps(
                            {
                                "sale_id": sale_id,
                                "receipt_number": receipt_number,
                                "manual_price_reference": manual_reference,
                                "product_uuid": product["product_uuid"],
                                "product_name": product["name_th"],
                                "barcode": item["manual_price"]["barcode"],
                                "manual_price_satang": item["unit_price_satang"],
                                "quantity": item["quantity"],
                                "reason": item["manual_price"]["reason"],
                            },
                            ensure_ascii=False,
                        ),
                        audit_ip,
                        now,
                    ),
                )
        db.execute(
            """INSERT INTO audit_logs (staff_id, action, entity_type, entity_id, new_value, created_at)
               VALUES (?, 'complete_sale', 'sale', ?, ?, ?)""",
            (staff_id, str(sale_id), json.dumps({"receipt": receipt_number, "total": cart["total_satang"]}), now),
        )
        if manage_transaction:
            db.commit()
        return sale_id, receipt_number, cart, change
    except Exception:
        if manage_transaction:
            db.rollback()
        raise


def void_sale(sale_id, payload, authorizer_id):
    """Void selected quantities with an active manager/admin authorizer in one transaction."""
    db = get_db()
    reason = str(payload.get("reason") or "").strip()
    full = payload.get("void_type") == "full"
    tolerance = Decimal("0.000001")
    try:
        db.execute("BEGIN IMMEDIATE")
        authorizer = db.execute(
            """SELECT st.id FROM staff st JOIN roles r ON r.id=st.role_id
               WHERE st.id=? AND st.is_active=1 AND r.code IN ('manager','admin')""",
            (authorizer_id,),
        ).fetchone()
        if not authorizer:
            raise SaleError("ผู้อนุมัติไม่พร้อมใช้งานหรือไม่มีสิทธิ์อนุมัติ Void")
        sale = db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if not sale or sale["status"] != "completed":
            raise SaleError("ใบเสร็จนี้ไม่สามารถ Void ได้")
        rows = db.execute(
            """SELECT si.*,p.allow_decimal_quantity
               FROM sale_items si JOIN products p ON p.id=si.product_id
               WHERE si.sale_id=? ORDER BY si.id""",
            (sale_id,),
        ).fetchall()
        rows_by_id = {row["id"]: row for row in rows}
        requested = {}
        if full:
            for row in rows:
                remaining = Decimal(str(row["quantity"])) - Decimal(str(row["voided_quantity"]))
                if remaining > tolerance:
                    requested[row["id"]] = remaining
        else:
            for raw in payload.get("items") or []:
                try:
                    item_id = int(raw.get("sale_item_id"))
                    raw_quantity = Decimal(str(raw.get("quantity") or 0))
                except (InvalidOperation, TypeError, ValueError) as exc:
                    raise SaleError("จำนวนสินค้าที่ Void ไม่ถูกต้อง") from exc
                if raw_quantity == 0:
                    continue
                row = rows_by_id.get(item_id)
                if not row or item_id in requested:
                    raise SaleError("รายการสินค้าที่ Void ไม่ถูกต้อง")
                sold_quantity = Decimal(str(row["quantity"]))
                allow_decimal = bool(row["allow_decimal_quantity"]) or sold_quantity != sold_quantity.to_integral_value()
                requested[item_id] = _quantity(raw_quantity, allow_decimal)
        selected = []
        for row in rows:
            quantity = requested.get(row["id"], Decimal("0"))
            remaining = Decimal(str(row["quantity"])) - Decimal(str(row["voided_quantity"]))
            if quantity > remaining:
                if quantity - remaining <= tolerance:
                    quantity = remaining
                else:
                    raise SaleError(f"จำนวน Void ของ {row['product_name']} ไม่ถูกต้อง")
            if quantity > tolerance:
                selected.append((row, quantity))
        if not selected:
            raise SaleError("กรุณาเลือกรายการที่จะ Void")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        current_net = sum(
            round(
                row["line_total_satang"]
                * float(Decimal(str(row["quantity"])) - Decimal(str(row["voided_quantity"])))
                / row["quantity"]
            )
            for row in rows
        )
        refund_total = cost_total = subtotal_refund = item_discount_refund = bill_discount_refund = 0
        audit_items = []
        cursor = db.execute(
            "INSERT INTO sale_voids (sale_id,void_type,reason,voided_by,created_at) VALUES (?,?,?,?,?)",
            (sale_id, "full" if full else "partial", reason, authorizer_id, now),
        )
        void_id = cursor.lastrowid
        for row, quantity in selected:
            ratio = Decimal(str(quantity)) / Decimal(str(row["quantity"]))
            line_refund = int((Decimal(row["line_total_satang"]) * ratio).quantize(Decimal("1")))
            item_discount = int((Decimal(row["discount_satang"]) * ratio).quantize(Decimal("1")))
            subtotal = int((Decimal(row["unit_price_satang"]) * quantity).quantize(Decimal("1")))
            cost = int((Decimal(row["cost_satang"]) * quantity).quantize(Decimal("1")))
            bill_share = round(sale["bill_discount_satang"] * line_refund / current_net) if current_net else 0
            refund = max(0, line_refund - bill_share)
            product = db.execute("SELECT stock_quantity,cost_satang FROM products WHERE id=?", (row["product_id"],)).fetchone()
            quantity_value = int(quantity) if quantity == quantity.to_integral_value() else float(quantity)
            new_stock_decimal = Decimal(str(product["stock_quantity"])) + quantity
            new_stock = int(new_stock_decimal) if new_stock_decimal == new_stock_decimal.to_integral_value() else float(new_stock_decimal)
            db.execute(
                "UPDATE products SET stock_quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_stock, row["product_id"]),
            )
            updated = db.execute(
                """UPDATE sale_items SET voided_quantity=voided_quantity+?
                   WHERE id=? AND voided_quantity+?<=quantity+0.000001""",
                (quantity_value, row["id"], quantity_value),
            )
            if updated.rowcount != 1:
                raise SaleError(f"จำนวน Void ของ {row['product_name']} ไม่ถูกต้อง")
            db.execute(
                "INSERT INTO sale_void_items (void_id,sale_item_id,product_id,quantity,refund_satang,cost_satang) VALUES (?,?,?,?,?,?)",
                (void_id, row["id"], row["product_id"], quantity_value, refund, cost),
            )
            db.execute(
                """INSERT INTO stock_movements
                   (product_id,movement_type,previous_quantity,changed_quantity,new_quantity,unit_cost_satang,
                    reference_type,reference_number,staff_id,note,created_at)
                   VALUES (?,'sale_void',?,?,?,?, 'sale_void',?,?,?,?)""",
                (row["product_id"], product["stock_quantity"], quantity_value, new_stock, product["cost_satang"],
                 sale["receipt_number"], authorizer_id, reason, now),
            )
            audit_items.append({
                "sale_item_id": row["id"], "product_id": row["product_id"], "product_name": row["product_name"],
                "quantity": quantity_value, "unit_price_satang": row["unit_price_satang"], "void_amount_satang": refund,
            })
            refund_total += refund
            cost_total += cost
            subtotal_refund += subtotal
            item_discount_refund += item_discount
            bill_discount_refund += bill_share
        remaining_count = db.execute(
            "SELECT COUNT(*) FROM sale_items WHERE sale_id=? AND quantity-voided_quantity>0.000001", (sale_id,)
        ).fetchone()[0]
        if remaining_count == 0:
            db.execute("UPDATE sales SET status='voided' WHERE id=?", (sale_id,))
        else:
            db.execute(
                """UPDATE sales SET subtotal_satang=subtotal_satang-?,item_discount_satang=item_discount_satang-?,
                   bill_discount_satang=MAX(0,bill_discount_satang-?),total_satang=MAX(0,total_satang-?),
                   total_cost_satang=MAX(0,total_cost_satang-?),gross_profit_satang=gross_profit_satang-?-? WHERE id=?""",
                (subtotal_refund, item_discount_refund, bill_discount_refund, refund_total, cost_total,
                 refund_total, -cost_total, sale_id),
            )
        db.execute(
            "INSERT INTO audit_logs (staff_id,action,entity_type,entity_id,new_value,created_at) VALUES (?,'void_sale','sale',?,?,?)",
            (authorizer_id, str(sale_id), json.dumps({
                "void_id": void_id, "cashier_id": sale["cashier_id"], "authorizing_manager_id": authorizer_id,
                "full": full, "refund": refund_total, "reason": reason, "items": audit_items,
            }, ensure_ascii=False), now),
        )
        db.commit()
        return void_id, refund_total
    except Exception:
        db.rollback()
        raise
