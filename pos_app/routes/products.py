import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from ..auth import permission_required, valid_csrf
from ..database import get_db
from ..services.money import baht_to_satang


bp = Blueprint("products", __name__, url_prefix="/products")
ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def reference_data(active_only=True):
    db = get_db()
    where = "WHERE is_active = 1" if active_only else ""
    return (
        db.execute(f"SELECT * FROM categories {where} ORDER BY sort_order, name_th").fetchall(),
        db.execute(f"SELECT * FROM units {where} ORDER BY sort_order, name_th").fetchall(),
    )


def save_image(file):
    if not file or not file.filename:
        return None
    extension = Path(secure_filename(file.filename)).suffix.lower()
    if extension not in ALLOWED_IMAGES:
        raise ValueError("รองรับรูป JPG, PNG, WEBP หรือ GIF เท่านั้น")
    filename = f"{secrets.token_hex(12)}{extension}"
    folder = current_app.config["RUNTIME_PATHS"].product_images
    file.save(folder / filename)
    return filename


def parse_product_form():
    name_th = request.form.get("name_th", "").strip()
    barcode = request.form.get("barcode", "").strip()
    if not name_th or not barcode:
        raise ValueError("กรุณากรอกบาร์โค้ดและชื่อสินค้า")
    return {
        "barcode": barcode,
        "sku": request.form.get("sku", "").strip() or None,
        "name_th": name_th,
        "name_en": request.form.get("name_en", "").strip() or None,
        "category_id": int(request.form.get("category_id", 0)),
        "unit_id": int(request.form.get("unit_id", 0)),
        "cost_satang": baht_to_satang(request.form.get("cost")),
        "minimum_stock": float(request.form.get("minimum_stock") or 0),
        "is_active": 1 if request.form.get("is_active") else 0,
        "is_favorite": 1 if request.form.get("is_favorite") else 0,
        "allow_decimal_quantity": 1 if request.form.get("allow_decimal_quantity") else 0,
        "is_online_available": 1 if request.form.get("is_online_available") else 0,
        "online_sort_order": int(request.form.get("online_sort_order") or 0),
        "online_max_quantity": float(request.form.get("online_max_quantity")) if request.form.get("online_max_quantity") else None,
    }


@bp.get("")
@permission_required("products.manage")
def index():
    query = request.args.get("q", "").strip()
    low_only = request.args.get("view") == "low"
    params = []
    conditions = []
    if query:
        conditions.append("(p.barcode LIKE ? OR p.sku LIKE ? OR p.name_th LIKE ? OR p.name_en LIKE ?)")
        term = f"%{query}%"
        params = [term] * 4
    if low_only:
        conditions.append("p.is_active=1 AND p.stock_quantity<=p.minimum_stock")
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    order = "p.stock_quantity ASC,p.name_th" if low_only else "p.updated_at DESC,p.id DESC"
    products = get_db().execute(
        f"""SELECT p.*, c.name_th AS category_name, u.name_th AS unit_name
            FROM products p JOIN categories c ON c.id=p.category_id JOIN units u ON u.id=p.unit_id
            {where} ORDER BY {order}""", params
    ).fetchall()
    return render_template("products.html", products=products, query=query, low_only=low_only)


@bp.route("/new", methods=("GET", "POST"))
@permission_required("products.manage")
def create():
    categories, units = reference_data()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        try:
            data = parse_product_form()
            data["price_satang"] = 0
            opening_stock = float(request.form.get("stock_quantity") or 0)
            if opening_stock < 0 or (not data["allow_decimal_quantity"] and not opening_stock.is_integer()):
                raise ValueError("จำนวนสต็อกเริ่มต้นไม่ถูกต้อง")
            data["image_path"] = save_image(request.files.get("image"))
            db = get_db()
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                """INSERT INTO products
                   (barcode, sku, name_th, name_en, category_id, unit_id, cost_satang, price_satang,
                    stock_quantity, minimum_stock, image_path, is_active, is_favorite, allow_decimal_quantity,
                    is_online_available,online_sort_order,online_max_quantity)
                   VALUES (:barcode,:sku,:name_th,:name_en,:category_id,:unit_id,:cost_satang,:price_satang,
                           :stock_quantity,:minimum_stock,:image_path,:is_active,:is_favorite,:allow_decimal_quantity,
                           :is_online_available,:online_sort_order,:online_max_quantity)""",
                {**data, "stock_quantity": opening_stock},
            )
            product_id = cursor.lastrowid
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if opening_stock:
                db.execute(
                    """INSERT INTO stock_movements
                       (product_id,movement_type,previous_quantity,changed_quantity,new_quantity,unit_cost_satang,
                        reference_type,reference_number,staff_id,note,created_at)
                       VALUES (?, 'opening_balance', 0, ?, ?, ?, 'product', ?, ?, 'ยอดเริ่มต้น', ?)""",
                    (product_id, opening_stock, opening_stock, data["cost_satang"], str(product_id), g.staff["id"], now),
                )
            db.execute(
                """INSERT INTO audit_logs (staff_id,action,entity_type,entity_id,new_value,ip_address,created_at)
                   VALUES (?, 'create_product', 'product', ?, ?, ?, ?)""",
                (g.staff["id"], str(product_id), json.dumps({"barcode": data["barcode"], "name": data["name_th"]}, ensure_ascii=False), request.remote_addr, now),
            )
            db.commit()
            flash("เพิ่มสินค้าเรียบร้อยแล้ว", "success")
            return redirect(url_for("products.index"))
        except Exception as exc:
            get_db().rollback()
            message = "บาร์โค้ดหรือ SKU นี้มีอยู่แล้ว" if "UNIQUE constraint" in str(exc) else str(exc)
            flash(message, "error")
    return render_template("product_form.html", product=None, categories=categories, units=units)


@bp.route("/<int:product_id>/edit", methods=("GET", "POST"))
@permission_required("products.manage")
def edit(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        return ("ไม่พบสินค้า", 404)
    categories, units = reference_data()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        try:
            data = parse_product_form()
            price_value = request.form.get("price")
            data["price_satang"] = (
                product["price_satang"] if price_value is None else baht_to_satang(price_value)
            )
            data["image_path"] = save_image(request.files.get("image")) or product["image_path"]
            data["id"] = product_id
            db.execute(
                """UPDATE products SET barcode=:barcode,sku=:sku,name_th=:name_th,name_en=:name_en,
                   category_id=:category_id,unit_id=:unit_id,cost_satang=:cost_satang,price_satang=:price_satang,
                   minimum_stock=:minimum_stock,image_path=:image_path,is_active=:is_active,is_favorite=:is_favorite,
                   allow_decimal_quantity=:allow_decimal_quantity,is_online_available=:is_online_available,
                   online_sort_order=:online_sort_order,online_max_quantity=:online_max_quantity,
                   updated_at=CURRENT_TIMESTAMP WHERE id=:id""", data,
            )
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            db.execute(
                """INSERT INTO audit_logs (staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
                   VALUES (?, 'edit_product', 'product', ?, ?, ?, ?, ?)""",
                (g.staff["id"], str(product_id), json.dumps(dict(product), ensure_ascii=False), json.dumps(data, ensure_ascii=False), request.remote_addr, now),
            )
            if product["price_satang"] != data["price_satang"]:
                db.execute(
                    """INSERT INTO audit_logs (staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
                       VALUES (?, 'change_price', 'product', ?, ?, ?, ?, ?)""",
                    (
                        g.staff["id"], str(product_id), str(product["price_satang"]),
                        str(data["price_satang"]), request.remote_addr, now,
                    ),
                )
            db.commit()
            flash("บันทึกสินค้าเรียบร้อยแล้ว", "success")
            return redirect(url_for("products.index"))
        except Exception as exc:
            db.rollback()
            flash("บาร์โค้ดหรือ SKU นี้มีอยู่แล้ว" if "UNIQUE constraint" in str(exc) else str(exc), "error")
    return render_template("product_form.html", product=product, categories=categories, units=units)


@bp.route("/references", methods=("GET", "POST"))
@permission_required("settings.manage")
def references():
    db = get_db()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        table = request.form.get("table")
        if table not in {"categories", "units"}:
            return ("ข้อมูลไม่ถูกต้อง", 400)
        name = request.form.get("name_th", "").strip()
        if not name:
            flash("กรุณากรอกชื่อ", "error")
        else:
            try:
                db.execute(f"INSERT INTO {table} (name_th) VALUES (?)", (name,))
                db.commit()
                flash("เพิ่มรายการเรียบร้อยแล้ว", "success")
            except Exception:
                db.rollback()
                flash("ชื่อนี้มีอยู่แล้ว", "error")
        return redirect(url_for("products.references"))
    categories, units = reference_data(False)
    return render_template("references.html", categories=categories, units=units)


@bp.post("/references/<table>/save")
@permission_required("settings.manage")
def save_references(table):
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    if table not in {"categories", "units"}:
        return ("ข้อมูลไม่ถูกต้อง", 400)
    try:
        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        item_ids = request.form.getlist("item_id")
        active_ids = set(request.form.getlist("active_id"))
        for item_id in item_ids:
            name = request.form.get(f"name_{item_id}", "").strip()
            if not name:
                raise ValueError("ชื่อรายการต้องไม่ว่าง")
            get_db().execute(
                f"UPDATE {table} SET name_th=?, is_active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (name, 1 if item_id in active_ids else 0, int(item_id)),
            )
        db.commit()
        flash("บันทึกรายการทั้งหมดเรียบร้อยแล้ว", "success")
    except Exception as exc:
        get_db().rollback()
        flash("บันทึกไม่สำเร็จ: ชื่อซ้ำหรือข้อมูลไม่ถูกต้อง", "error")
    return redirect(url_for("products.references"))


@bp.route("/prices", methods=("GET", "POST"))
@permission_required("products.manage")
def prices():
    db = get_db()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        changes=[]
        try:
            for product_id in request.form.getlist("product_id"):
                price = baht_to_satang(request.form.get(f"price_{product_id}"))
                old = db.execute("SELECT id,name_th,barcode,price_satang FROM products WHERE id=?", (product_id,)).fetchone()
                if old and old["price_satang"] != price:changes.append({"id":old["id"],"name":old["name_th"],"barcode":old["barcode"],"old":old["price_satang"],"new":price})
            if request.form.get("action")!="confirm":
                return render_template("product_price_confirm.html",changes=changes)
            db.execute("BEGIN IMMEDIATE")
            for change in changes:
                current=db.execute("SELECT price_satang FROM products WHERE id=?",(change["id"],)).fetchone()
                if current and current[0] != change["new"]:
                    db.execute("UPDATE products SET price_satang=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (change["new"], change["id"]))
                    db.execute(
                        """INSERT INTO audit_logs (staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
                           VALUES (?, 'change_price', 'product', ?, ?, ?, ?, ?)""",
                        (g.staff["id"], change["id"], str(current[0]), str(change["new"]), request.remote_addr, datetime.now(timezone.utc).isoformat(timespec="seconds")),
                    )
            db.commit()
            flash(f"บันทึกราคาขาย {len(changes)} รายการเรียบร้อยแล้ว", "success")
        except Exception as exc:
            db.rollback()
            flash(str(exc), "error")
        return redirect(url_for(
            "products.prices",
            q=request.form.get("return_q", "").strip() or None,
            category_id=request.form.get("return_category_id", type=int),
        ))
    category_id = request.args.get("category_id", type=int)
    query = request.args.get("q", "").strip()
    params = []
    filters = []
    if category_id:
        filters.append("p.category_id=?")
        params.append(category_id)
    if query:
        term = f"%{query}%"
        filters.append("(p.barcode LIKE ? OR p.sku LIKE ? OR p.name_th LIKE ? OR p.name_en LIKE ?)")
        params.extend([term] * 4)
    filter_sql = "".join(f" AND {condition}" for condition in filters)
    rows = db.execute(
        f"""SELECT p.id,p.barcode,p.sku,p.name_th,p.price_satang,c.name_th AS category_name
            FROM products p JOIN categories c ON c.id=p.category_id
            WHERE p.is_active=1 {filter_sql} ORDER BY c.name_th,p.name_th""", params
    ).fetchall()
    categories = db.execute("SELECT id,name_th FROM categories WHERE is_active=1 ORDER BY sort_order,name_th").fetchall()
    exact_barcode_id = next((row["id"] for row in rows if row["barcode"] == query), None) if query else None
    return render_template(
        "product_prices.html", products=rows, categories=categories,
        selected_category=category_id, query=query, exact_barcode_id=exact_barcode_id,
    )
