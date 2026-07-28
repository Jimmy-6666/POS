import base64
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, render_template, request, send_from_directory

from ..auth import login_required, permission_required, valid_csrf
from ..database import get_db
from ..product_identity import ProductIdentityError, canonical_product_uuid
from ..services.money import change_breakdown
from ..services.print_jobs import enqueue_print
from ..services.sales import SaleError, calculate_cart, complete_sale, void_sale


bp = Blueprint("pos", __name__)


@bp.get("/uploads/products/<path:filename>")
@login_required
def product_image(filename):
    return send_from_directory(current_app.config["RUNTIME_PATHS"].product_images, filename)


@bp.get("/pos")
@permission_required("pos.use")
def index():
    db = get_db()
    categories = db.execute("SELECT id, name_th FROM categories WHERE is_active=1 ORDER BY sort_order,name_th").fetchall()
    billing_customers = db.execute("SELECT id,name FROM billing_customers WHERE is_active=1 ORDER BY name").fetchall()
    return render_template("pos.html", categories=categories, billing_customers=billing_customers)


@bp.get("/api/pos/products")
@permission_required("pos.use")
def products_api():
    query = request.args.get("q", "").strip()
    category_id = request.args.get("category_id", type=int)
    barcode = request.args.get("barcode", "").strip()
    where = ["p.is_active=1"]
    params = []
    if barcode:
        where.append("p.barcode=?")
        params.append(barcode)
    elif query:
        where.append("(p.name_th LIKE ? OR p.name_en LIKE ? OR p.barcode LIKE ? OR p.sku LIKE ?)")
        params.extend([f"%{query}%"] * 4)
    if category_id:
        where.append("p.category_id=?")
        params.append(category_id)
    rows = get_db().execute(
        f"""SELECT p.product_uuid,p.barcode,p.name_th,p.price_satang,p.stock_quantity,p.image_path,
                   p.allow_decimal_quantity,p.is_favorite,u.name_th AS unit_name
            FROM products p JOIN units u ON u.id=p.unit_id
            WHERE {' AND '.join(where)} ORDER BY p.is_favorite DESC,p.name_th LIMIT 100""", params
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@bp.post("/api/pos/quote")
@permission_required("pos.use")
def quote_api():
    data = request.get_json(silent=True) or {}
    if not valid_csrf(request.headers.get("X-CSRF-Token")):
        return jsonify(error="คำขอไม่ถูกต้อง"), 400
    try:
        cart = calculate_cart(data.get("items"), data.get("bill_discount_satang"))
        return jsonify({key: value for key, value in cart.items() if key != "items"})
    except SaleError as exc:
        return jsonify(error=str(exc)), 400


def save_evidence(data):
    encoded = data.get("evidence_base64")
    if not encoded:
        return None
    try:
        header, encoded = encoded.split(",", 1)
        if header not in {"data:image/png;base64", "data:image/jpeg;base64"}:
            raise ValueError("unsupported image")
        extension = ".png" if "png" in header else ".jpg"
        content = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise SaleError("ไฟล์หลักฐานการชำระเงินไม่ถูกต้อง") from exc
    if len(content) > 5 * 1024 * 1024:
        raise SaleError("ไฟล์หลักฐานต้องมีขนาดไม่เกิน 5 MB")
    filename = f"payment-{secrets.token_hex(12)}{extension}"
    folder = current_app.config["RUNTIME_PATHS"].pos_payment_evidence
    (folder / filename).write_bytes(content)
    return filename


@bp.post("/api/pos/complete")
@permission_required("pos.use")
def complete_api():
    data = request.get_json(silent=True) or {}
    if not valid_csrf(request.headers.get("X-CSRF-Token")):
        return jsonify(error="คำขอไม่ถูกต้อง"), 400
    try:
        data["evidence_image_path"] = save_evidence(data)
        sale_id, receipt, cart, change = complete_sale(data, g.staff["id"])
        print_queued = bool(enqueue_print("sale_receipt", sale_id))
        return jsonify(
            sale_id=sale_id, receipt_number=receipt, total_satang=cart["total_satang"],
            change_satang=change, breakdown=change_breakdown(change), receipt_url=f"/sales/{sale_id}/receipt",
            print_queued=print_queued,
        )
    except SaleError as exc:
        return jsonify(error=str(exc)), 400


@bp.route("/api/pos/held", methods=("GET", "POST"))
@permission_required("pos.use")
def held_bills_api():
    db = get_db()
    if request.method == "GET":
        rows = db.execute("SELECT id,label,cart_json,updated_at FROM held_bills WHERE staff_id=? ORDER BY updated_at DESC", (g.staff["id"],)).fetchall()
        return jsonify([dict(row) for row in rows])
    data = request.get_json(silent=True) or {}
    if not valid_csrf(request.headers.get("X-CSRF-Token")) or not data.get("cart"):
        return jsonify(error="คำขอไม่ถูกต้อง"), 400
    try:
        items = data["cart"].get("items", [])
        if not items:
            raise ProductIdentityError("ไม่พบสินค้าในบิลพัก")
        for item in items:
            canonical_product_uuid(item.get("product_uuid"))
    except (AttributeError, ProductIdentityError) as exc:
        return jsonify(error=str(exc)), 400
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cursor = db.execute(
        "INSERT INTO held_bills (staff_id,label,cart_json,created_at,updated_at) VALUES (?,?,?,?,?)",
        (g.staff["id"], data.get("label", "พักบิล"), json.dumps(data["cart"], ensure_ascii=False), now, now),
    )
    db.commit()
    return jsonify(id=cursor.lastrowid)


@bp.delete("/api/pos/held/<int:bill_id>")
@permission_required("pos.use")
def delete_held_bill(bill_id):
    if not valid_csrf(request.headers.get("X-CSRF-Token")):
        return jsonify(error="คำขอไม่ถูกต้อง"), 400
    db = get_db()
    db.execute("DELETE FROM held_bills WHERE id=? AND staff_id=?", (bill_id, g.staff["id"]))
    db.commit()
    return jsonify(ok=True)


@bp.get("/sales")
@login_required
def sales_history():
    db = get_db()
    params = []
    where = ""
    if g.staff["role_code"] == "cashier":
        where = "WHERE s.cashier_id=?"
        params.append(g.staff["id"])
    rows = db.execute(
        f"""SELECT s.*,st.display_name,(SELECT COUNT(*) FROM sale_voids v WHERE v.sale_id=s.id) AS void_count
            FROM sales s JOIN staff st ON st.id=s.cashier_id
            {where} ORDER BY s.created_at DESC LIMIT 500""", params
    ).fetchall()
    return render_template("sales_history.html", sales=rows)


@bp.get("/sales/<int:sale_id>/receipt")
@login_required
def receipt(sale_id):
    db = get_db()
    sale = db.execute(
        "SELECT s.*,st.display_name FROM sales s JOIN staff st ON st.id=s.cashier_id WHERE s.id=?", (sale_id,)
    ).fetchone()
    if not sale or (g.staff["role_code"] == "cashier" and sale["cashier_id"] != g.staff["id"]):
        return ("ไม่พบใบเสร็จ", 404)
    items = db.execute("SELECT *,quantity-voided_quantity AS remaining_quantity FROM sale_items WHERE sale_id=?", (sale_id,)).fetchall()
    settings = dict(db.execute("SELECT key,value FROM settings").fetchall())
    return render_template("receipt.html", sale=sale, items=items, settings=settings, autoprint=False)


@bp.route("/sales/<int:sale_id>/void", methods=("GET", "POST"))
@permission_required("sales.approve")
def void_receipt(sale_id):
    db = get_db()
    sale = db.execute(
        "SELECT s.*,st.display_name FROM sales s JOIN staff st ON st.id=s.cashier_id WHERE s.id=?", (sale_id,)
    ).fetchone()
    if not sale:
        return ("ไม่พบใบเสร็จ", 404)
    items = db.execute(
        "SELECT *,quantity-voided_quantity AS remaining_quantity FROM sale_items WHERE sale_id=? ORDER BY id", (sale_id,)
    ).fetchall()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        payload = {"void_type": request.form.get("void_type"), "reason": request.form.get("reason"), "items": []}
        for item in items:
            value = request.form.get(f"quantity_{item['id']}", "0")
            payload["items"].append({"sale_item_id": item["id"], "quantity": value})
        try:
            void_sale(sale_id, payload, g.staff["id"])
            return ("", 302, {"Location": "/sales"})
        except SaleError as exc:
            return render_template("sale_void.html", sale=sale, items=items, error=str(exc)), 400
    history = db.execute(
        """SELECT v.*,st.display_name FROM sale_voids v JOIN staff st ON st.id=v.voided_by
           WHERE v.sale_id=? ORDER BY v.created_at DESC""", (sale_id,)
    ).fetchall()
    return render_template("sale_void.html", sale=sale, items=items, history=history)
