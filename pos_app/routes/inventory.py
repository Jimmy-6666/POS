from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..auth import permission_required, valid_csrf
from ..database import get_db
from ..services.money import baht_to_satang


bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@bp.route("/receive", methods=("GET", "POST"))
@permission_required("inventory.manage")
def receive():
    db = get_db()
    category_id = request.args.get("category_id", type=int)
    query = request.args.get("q", "").strip()
    product_params = []
    product_filters = []
    if category_id:
        product_filters.append("p.category_id=?")
        product_params.append(category_id)
    if query:
        term = f"%{query}%"
        product_filters.append("(p.barcode LIKE ? OR p.sku LIKE ? OR p.name_th LIKE ? OR p.name_en LIKE ?)")
        product_params.extend([term] * 4)
    product_where = "".join(f" AND {condition}" for condition in product_filters)
    products = db.execute(
        f"""SELECT p.id,p.barcode,p.sku,p.name_th,p.stock_quantity,p.cost_satang,p.allow_decimal_quantity
            FROM products p WHERE p.is_active=1 {product_where} ORDER BY p.name_th""", product_params
    ).fetchall()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        try:
            product_id = request.form.get("product_id", type=int)
            product = db.execute("SELECT * FROM products WHERE id=? AND is_active=1", (product_id,)).fetchone()
            if not product:
                raise ValueError("ไม่พบสินค้า")
            quantity = Decimal(request.form.get("quantity", "0"))
            if quantity <= 0 or (not product["allow_decimal_quantity"] and quantity != quantity.to_integral_value()):
                raise ValueError("จำนวนรับเข้าไม่ถูกต้อง")
            unit_cost = baht_to_satang(request.form.get("unit_cost"))
            total_cost = int((quantity * unit_cost).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            previous = Decimal(str(product["stock_quantity"]))
            new_quantity = previous + quantity
            old_value = previous * product["cost_satang"]
            average_cost = int(((old_value + quantity * unit_cost) / new_quantity).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                """INSERT INTO stock_receipts
                   (supplier_name,invoice_number,lot_number,expiry_date,note,staff_id,total_cost_satang,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (request.form.get("supplier_name", "").strip() or None, request.form.get("invoice_number", "").strip() or None,
                 request.form.get("lot_number", "").strip() or None, request.form.get("expiry_date") or None,
                 request.form.get("note", "").strip() or None, g.staff["id"], total_cost, now),
            )
            receipt_id = cursor.lastrowid
            db.execute(
                "INSERT INTO stock_receipt_items (receipt_id,product_id,quantity,unit_cost_satang,total_cost_satang) VALUES (?,?,?,?,?)",
                (receipt_id, product_id, float(quantity), unit_cost, total_cost),
            )
            db.execute("UPDATE products SET stock_quantity=?,cost_satang=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (float(new_quantity), average_cost, product_id))
            db.execute(
                """INSERT INTO stock_movements
                   (product_id,movement_type,previous_quantity,changed_quantity,new_quantity,unit_cost_satang,
                    reference_type,reference_number,staff_id,note,created_at)
                   VALUES (?, 'receive_stock', ?, ?, ?, ?, 'stock_receipt', ?, ?, ?, ?)""",
                (product_id, float(previous), float(quantity), float(new_quantity), unit_cost, str(receipt_id), g.staff["id"], request.form.get("note"), now),
            )
            db.execute(
                """INSERT INTO audit_logs (staff_id,action,entity_type,entity_id,new_value,ip_address,created_at)
                   VALUES (?, 'receive_stock', 'stock_receipt', ?, ?, ?, ?)""",
                (g.staff["id"], str(receipt_id), f"product={product_id},quantity={quantity},unit_cost={unit_cost}", request.remote_addr, now),
            )
            db.commit()
            flash("รับสินค้าเข้าสต็อกเรียบร้อยแล้ว ราคาขายไม่เปลี่ยนแปลง", "success")
            return redirect(url_for("inventory.receive"))
        except (ValueError, InvalidOperation) as exc:
            db.rollback()
            flash(str(exc), "error")
    history = db.execute(
        """SELECT r.*,i.quantity,i.unit_cost_satang,p.name_th,st.display_name
           FROM stock_receipts r JOIN stock_receipt_items i ON i.receipt_id=r.id
           JOIN products p ON p.id=i.product_id JOIN staff st ON st.id=r.staff_id
           ORDER BY r.created_at DESC LIMIT 100"""
    ).fetchall()
    categories = db.execute("SELECT id,name_th FROM categories WHERE is_active=1 ORDER BY sort_order,name_th").fetchall()
    exact_barcode_id = next((row["id"] for row in products if row["barcode"] == query), None) if query else None
    return render_template(
        "receive_stock.html", products=products, history=history, categories=categories,
        selected_category=category_id, query=query, exact_barcode_id=exact_barcode_id,
    )


@bp.route("/adjust", methods=("GET", "POST"))
@permission_required("inventory.manage")
def adjust():
    db = get_db()
    query = request.args.get("q", "").strip()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        try:
            product = db.execute("SELECT * FROM products WHERE id=?", (request.form.get("product_id", type=int),)).fetchone()
            if not product:
                raise ValueError("ไม่พบสินค้า")
            value = Decimal(request.form.get("quantity", "0"))
            adjustment_type = request.form.get("adjustment_type")
            previous = Decimal(str(product["stock_quantity"]))
            if value < 0 or adjustment_type not in {"increase", "decrease", "set"}:
                raise ValueError("จำนวนหรือประเภทการปรับไม่ถูกต้อง")
            new = previous + value if adjustment_type == "increase" else previous - value if adjustment_type == "decrease" else value
            if new < 0:
                raise ValueError("สต็อกหลังปรับต้องไม่ติดลบ")
            changed = new - previous
            movement_type = "adjustment_increase" if changed >= 0 else "adjustment_decrease"
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE products SET stock_quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (float(new), product["id"]))
            db.execute("""INSERT INTO stock_movements
                (product_id,movement_type,previous_quantity,changed_quantity,new_quantity,unit_cost_satang,
                 reference_type,reference_number,staff_id,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (product["id"], movement_type, float(previous), float(changed), float(new), product["cost_satang"],
                 "adjustment", request.form.get("reason_id"), g.staff["id"], request.form.get("note"), now))
            db.execute("""INSERT INTO audit_logs (staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
                VALUES (?, 'adjust_stock', 'product', ?, ?, ?, ?, ?)""",
                (g.staff["id"], product["id"], str(previous), str(new), request.remote_addr, now))
            db.commit(); flash("ปรับสต็อกเรียบร้อยแล้ว", "success")
            return redirect(url_for("inventory.ledger"))
        except (ValueError, InvalidOperation) as exc:
            db.rollback(); flash(str(exc), "error")
    product_params = []
    product_where = ""
    if query:
        term = f"%{query}%"
        product_where = " AND (barcode LIKE ? OR sku LIKE ? OR name_th LIKE ? OR name_en LIKE ?)"
        product_params = [term] * 4
    products = db.execute(
        f"""SELECT id,barcode,sku,name_th,stock_quantity FROM products
            WHERE is_active=1 {product_where} ORDER BY name_th""",
        product_params,
    ).fetchall()
    reasons = db.execute("SELECT id,name_th FROM adjustment_reasons WHERE is_active=1 ORDER BY name_th").fetchall()
    exact_barcode_id = next((row["id"] for row in products if row["barcode"] == query), None) if query else None
    return render_template(
        "stock_adjustment.html", products=products, reasons=reasons,
        query=query, exact_barcode_id=exact_barcode_id,
    )


@bp.get("/ledger")
@permission_required("inventory.manage")
def ledger():
    product_id = request.args.get("product_id", type=int)
    params=[]; where=""
    if product_id: where="WHERE m.product_id=?"; params=[product_id]
    rows=get_db().execute(f"""SELECT m.*,p.name_th,st.display_name FROM stock_movements m
        JOIN products p ON p.id=m.product_id LEFT JOIN staff st ON st.id=m.staff_id
        {where} ORDER BY m.created_at DESC,m.id DESC LIMIT 1000""",params).fetchall()
    products=get_db().execute("SELECT id,name_th FROM products ORDER BY name_th").fetchall()
    return render_template("stock_ledger.html", movements=rows, products=products, selected_product=product_id)


@bp.route("/suppliers", methods=("GET", "POST"))
@permission_required("inventory.manage")
def suppliers():
    db=get_db()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")): return ("คำขอไม่ถูกต้อง",400)
        name=request.form.get("name","").strip()
        if not name: flash("กรุณากรอกชื่อผู้จำหน่าย","error")
        else:
            try:
                db.execute("""INSERT INTO suppliers (name,contact_name,phone,line_id,address,tax_id,note)
                    VALUES (?,?,?,?,?,?,?)""",(name,request.form.get("contact_name"),request.form.get("phone"),request.form.get("line_id"),request.form.get("address"),request.form.get("tax_id"),request.form.get("note")))
                db.commit();flash("เพิ่มผู้จำหน่ายแล้ว","success")
            except Exception: db.rollback();flash("ชื่อผู้จำหน่ายนี้มีอยู่แล้ว","error")
        return redirect(url_for("inventory.suppliers"))
    return render_template("suppliers.html",suppliers=db.execute("SELECT * FROM suppliers ORDER BY name").fetchall())
