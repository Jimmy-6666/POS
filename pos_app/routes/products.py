import json
import secrets
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from ..auth import admin_required, permission_required, valid_csrf
from ..database import get_db
from ..product_identity import ProductIdentityError, new_product_uuid, product_by_uuid
from ..services.money import baht_to_satang
from ..services.product_spreadsheet import (
    MAX_IMPORT_BYTES,
    SpreadsheetError,
    apply_import,
    build_export_workbook,
    export_audit_payload,
    parse_import,
    remember_preview,
    safe_filename,
    take_preview,
)


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


def submitted_product_image():
    """Treat a browser camera capture as a normal multipart product image."""

    camera_image = request.files.get("camera_image")
    return camera_image if camera_image and camera_image.filename else request.files.get("image")


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
        "price_satang": baht_to_satang(request.form.get("price")),
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


@bp.get("/xlsx/export")
@admin_required
def export_xlsx():
    """Download the current catalog as the only supported XLSX import template."""

    filename = f"products-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
    db = get_db()
    workbook = build_export_workbook(db)
    export_audit_payload(db, g.staff["id"], filename, request.remote_addr)
    return send_file(
        BytesIO(workbook),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        max_age=0,
    )


@bp.post("/xlsx/import")
@admin_required
def import_xlsx_preview():
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    uploaded = request.files.get("file")
    filename = safe_filename(uploaded.filename if uploaded else None)
    if not uploaded or not uploaded.filename or Path(filename).suffix.lower() != ".xlsx":
        flash("กรุณาเลือกไฟล์ .xlsx", "error")
        return redirect(url_for("products.index"))
    content = uploaded.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        flash("ไฟล์ XLSX ต้องมีขนาดไม่เกิน 2 MB", "error")
        return redirect(url_for("products.index"))
    try:
        preview = parse_import(get_db(), content)
    except SpreadsheetError as exc:
        flash(str(exc), "error")
        return redirect(url_for("products.index"))
    token = remember_preview(g.staff["id"], filename, preview)
    return render_template("product_import_preview.html", preview=preview, preview_token=token, filename=filename)


@bp.post("/xlsx/import/confirm")
@admin_required
def confirm_xlsx_import():
    if not valid_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    try:
        stored = take_preview(g.staff["id"], request.form.get("preview_token", ""))
        summary = apply_import(get_db(), g.staff["id"], stored.filename, stored.preview, request.remote_addr)
    except SpreadsheetError as exc:
        flash(str(exc), "error")
        return redirect(url_for("products.index"))
    except Exception:
        current_app.logger.exception("Product XLSX import failed")
        flash("นำเข้าไม่สำเร็จและไม่มีรายการใดถูกบันทึก", "error")
        return redirect(url_for("products.index"))
    flash(
        f"นำเข้าสินค้าเรียบร้อย: เพิ่ม {summary['created']} รายการ, แก้ไข {summary['updated']} รายการ, "
        f"ไม่เปลี่ยนแปลง {summary['unchanged']} รายการ",
        "success",
    )
    return redirect(url_for("products.index"))


@bp.route("/new", methods=("GET", "POST"))
@permission_required("products.manage")
def create():
    categories, units = reference_data()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        try:
            data = parse_product_form()
            data["product_uuid"] = new_product_uuid()
            opening_stock = float(request.form.get("stock_quantity") or 0)
            if opening_stock < 0 or (not data["allow_decimal_quantity"] and not opening_stock.is_integer()):
                raise ValueError("จำนวนสต็อกเริ่มต้นไม่ถูกต้อง")
            data["image_path"] = save_image(submitted_product_image())
            db = get_db()
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                """INSERT INTO products
                   (product_uuid, barcode, sku, name_th, name_en, category_id, unit_id, cost_satang, price_satang,
                    stock_quantity, minimum_stock, image_path, is_active, is_favorite, allow_decimal_quantity,
                    is_online_available,online_sort_order,online_max_quantity)
                   VALUES (:product_uuid,:barcode,:sku,:name_th,:name_en,:category_id,:unit_id,:cost_satang,:price_satang,
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
                    (product_id, opening_stock, opening_stock, data["cost_satang"], data["product_uuid"], g.staff["id"], now),
                )
            db.execute(
                """INSERT INTO audit_logs (staff_id,action,entity_type,entity_id,new_value,ip_address,created_at)
                   VALUES (?, 'create_product', 'product', ?, ?, ?, ?)""",
                (g.staff["id"], data["product_uuid"], json.dumps({"barcode": data["barcode"], "name": data["name_th"]}, ensure_ascii=False), request.remote_addr, now),
            )
            db.commit()
            flash("เพิ่มสินค้าเรียบร้อยแล้ว", "success")
            return redirect(url_for("products.index"))
        except Exception as exc:
            get_db().rollback()
            message = "บาร์โค้ดหรือ SKU นี้มีอยู่แล้ว" if "UNIQUE constraint" in str(exc) else str(exc)
            flash(message, "error")
    return render_template("product_form.html", product=None, categories=categories, units=units)


@bp.route("/<product_uuid>/edit", methods=("GET", "POST"))
@permission_required("products.manage")
def edit(product_uuid):
    db = get_db()
    try:
        product = product_by_uuid(db, product_uuid)
    except ProductIdentityError:
        product = None
    if not product:
        return ("ไม่พบสินค้า", 404)
    categories, units = reference_data()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        try:
            data = parse_product_form()
            data["image_path"] = save_image(submitted_product_image()) or product["image_path"]
            data["id"] = product["id"]
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
                (g.staff["id"], product["product_uuid"], json.dumps(dict(product), ensure_ascii=False), json.dumps(data, ensure_ascii=False), request.remote_addr, now),
            )
            if product["price_satang"] != data["price_satang"]:
                db.execute(
                    """INSERT INTO audit_logs (staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
                       VALUES (?, 'change_price', 'product', ?, ?, ?, ?, ?)""",
                    (
                        g.staff["id"], product["product_uuid"], str(product["price_satang"]),
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
            for product_uuid in request.form.getlist("product_uuid"):
                price = baht_to_satang(request.form.get(f"price_{product_uuid}"))
                old = product_by_uuid(db, product_uuid)
                if old and old["price_satang"] != price:changes.append({"product_uuid":old["product_uuid"],"name":old["name_th"],"barcode":old["barcode"],"old":old["price_satang"],"new":price})
            if request.form.get("action")!="confirm":
                return render_template("product_price_confirm.html",changes=changes)
            db.execute("BEGIN IMMEDIATE")
            for change in changes:
                current=db.execute("SELECT price_satang FROM products WHERE product_uuid=?",(change["product_uuid"],)).fetchone()
                if current and current[0] != change["new"]:
                    db.execute("UPDATE products SET price_satang=?,updated_at=CURRENT_TIMESTAMP WHERE product_uuid=?", (change["new"], change["product_uuid"]))
                    db.execute(
                        """INSERT INTO audit_logs (staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
                           VALUES (?, 'change_price', 'product', ?, ?, ?, ?, ?)""",
                        (g.staff["id"], change["product_uuid"], str(current[0]), str(change["new"]), request.remote_addr, datetime.now(timezone.utc).isoformat(timespec="seconds")),
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
    rows = price_rows(db, category_id, query)
    categories = db.execute("SELECT id,name_th FROM categories WHERE is_active=1 ORDER BY sort_order,name_th").fetchall()
    exact_barcode_uuid = next((row["product_uuid"] for row in rows if row["barcode"] == query), None) if query else None
    return render_template(
        "product_prices.html", products=rows, categories=categories,
        selected_category=category_id, query=query, exact_barcode_uuid=exact_barcode_uuid,
    )


def price_rows(db, category_id, query):
    """Fetch latest receiving costs with the price rows, never per product."""

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
    return db.execute(
        f"""WITH latest_receipt_cost AS (
                SELECT sri.product_id,sri.unit_cost_satang,
                       ROW_NUMBER() OVER (
                           PARTITION BY sri.product_id
                           ORDER BY sr.created_at DESC,sr.id DESC,sri.id DESC
                       ) AS row_number
                FROM stock_receipt_items sri
                JOIN stock_receipts sr ON sr.id=sri.receipt_id
            )
            SELECT p.product_uuid,p.barcode,p.sku,p.name_th,p.cost_satang,p.price_satang,
                   c.name_th AS category_name,
                   latest_receipt_cost.unit_cost_satang AS latest_cost_satang
            FROM products p
            JOIN categories c ON c.id=p.category_id
            LEFT JOIN latest_receipt_cost
              ON latest_receipt_cost.product_id=p.id AND latest_receipt_cost.row_number=1
            WHERE p.is_active=1 {filter_sql}
            ORDER BY c.name_th,p.name_th""", params
    ).fetchall()
