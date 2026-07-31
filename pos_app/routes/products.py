import json
import secrets
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, send_file, session, url_for
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


def pos_button_position(value):
    try:
        position = int(value)
    except (TypeError, ValueError):
        raise ValueError("ตำแหน่งปุ่มต้องเป็นเลขจำนวนเต็ม")
    if position < 1 or position > 999:
        raise ValueError("ตำแหน่งปุ่มต้องอยู่ระหว่าง 1 ถึง 999")
    return position


def audit_pos_button_change(db, action, entity_type, entity_id, old_value=None, new_value=None):
    db.execute(
        """INSERT INTO audit_logs
           (staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            g.staff["id"],
            action,
            entity_type,
            str(entity_id),
            json.dumps(old_value, ensure_ascii=False) if old_value is not None else None,
            json.dumps(new_value, ensure_ascii=False) if new_value is not None else None,
            request.remote_addr,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
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


@bp.route("/pos-buttons", methods=("GET", "POST"))
@permission_required("products.manage")
def pos_buttons():
    db = get_db()
    selected_group_id = request.values.get("group_id", type=int)
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        action = request.form.get("action", "")
        try:
            db.execute("BEGIN IMMEDIATE")
            if action == "create_group":
                name = request.form.get("name_th", "").strip()
                if not name or len(name) > 80:
                    raise ValueError("กรุณากรอกชื่อเมนูไม่เกิน 80 ตัวอักษร")
                position = pos_button_position(request.form.get("position"))
                cursor = db.execute(
                    """INSERT INTO pos_button_groups
                       (name_th,position,is_active,created_by,updated_by)
                       VALUES (?,?,1,?,?)""",
                    (name, position, g.staff["id"], g.staff["id"]),
                )
                selected_group_id = cursor.lastrowid
                audit_pos_button_change(
                    db,
                    "create_pos_button_group",
                    "pos_button_group",
                    selected_group_id,
                    new_value={"name_th": name, "position": position, "is_active": 1},
                )
                flash("เพิ่มเมนูปุ่มขายแล้ว", "success")
            elif action == "update_group":
                group_id = request.form.get("group_id", type=int)
                old = db.execute("SELECT * FROM pos_button_groups WHERE id=?", (group_id,)).fetchone()
                if not old:
                    raise ValueError("ไม่พบเมนูปุ่มขาย")
                name = request.form.get("name_th", "").strip()
                if not name or len(name) > 80:
                    raise ValueError("กรุณากรอกชื่อเมนูไม่เกิน 80 ตัวอักษร")
                position = pos_button_position(request.form.get("position"))
                is_active = 1 if request.form.get("is_active") else 0
                db.execute(
                    """UPDATE pos_button_groups
                       SET name_th=?,position=?,is_active=?,updated_by=?,updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (name, position, is_active, g.staff["id"], group_id),
                )
                selected_group_id = group_id
                audit_pos_button_change(
                    db,
                    "update_pos_button_group",
                    "pos_button_group",
                    group_id,
                    old_value={
                        "name_th": old["name_th"],
                        "position": old["position"],
                        "is_active": old["is_active"],
                    },
                    new_value={"name_th": name, "position": position, "is_active": is_active},
                )
                flash("บันทึกเมนูปุ่มขายแล้ว", "success")
            elif action == "add_item":
                group_id = request.form.get("group_id", type=int)
                product_uuid = request.form.get("product_uuid", "").strip()
                position = pos_button_position(request.form.get("position"))
                group = db.execute("SELECT id FROM pos_button_groups WHERE id=?", (group_id,)).fetchone()
                product = db.execute(
                    "SELECT id,product_uuid,name_th FROM products WHERE product_uuid=? AND is_active=1",
                    (product_uuid,),
                ).fetchone()
                if not group:
                    raise ValueError("ไม่พบเมนูปุ่มขาย")
                if not product:
                    raise ValueError("ไม่พบสินค้าที่เปิดใช้งาน")
                cursor = db.execute(
                    """INSERT INTO pos_button_items
                       (group_id,product_id,position,created_by,updated_by)
                       VALUES (?,?,?,?,?)""",
                    (group_id, product["id"], position, g.staff["id"], g.staff["id"]),
                )
                selected_group_id = group_id
                audit_pos_button_change(
                    db,
                    "add_pos_button_item",
                    "pos_button_item",
                    cursor.lastrowid,
                    new_value={
                        "group_id": group_id,
                        "product_uuid": product["product_uuid"],
                        "product_name": product["name_th"],
                        "position": position,
                    },
                )
                flash("เพิ่มสินค้าลงเมนูแล้ว", "success")
            elif action == "update_item":
                item_id = request.form.get("item_id", type=int)
                position = pos_button_position(request.form.get("position"))
                old = db.execute(
                    """SELECT i.*,p.product_uuid,p.name_th
                       FROM pos_button_items i JOIN products p ON p.id=i.product_id
                       WHERE i.id=?""",
                    (item_id,),
                ).fetchone()
                if not old:
                    raise ValueError("ไม่พบปุ่มสินค้านี้")
                db.execute(
                    """UPDATE pos_button_items
                       SET position=?,updated_by=?,updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (position, g.staff["id"], item_id),
                )
                selected_group_id = old["group_id"]
                audit_pos_button_change(
                    db,
                    "update_pos_button_item",
                    "pos_button_item",
                    item_id,
                    old_value={"position": old["position"]},
                    new_value={
                        "position": position,
                        "product_uuid": old["product_uuid"],
                        "product_name": old["name_th"],
                    },
                )
                flash("ย้ายตำแหน่งปุ่มสินค้าแล้ว", "success")
            elif action == "remove_item":
                item_id = request.form.get("item_id", type=int)
                old = db.execute(
                    """SELECT i.*,p.product_uuid,p.name_th
                       FROM pos_button_items i JOIN products p ON p.id=i.product_id
                       WHERE i.id=?""",
                    (item_id,),
                ).fetchone()
                if not old:
                    raise ValueError("ไม่พบปุ่มสินค้านี้")
                selected_group_id = old["group_id"]
                db.execute("DELETE FROM pos_button_items WHERE id=?", (item_id,))
                audit_pos_button_change(
                    db,
                    "remove_pos_button_item",
                    "pos_button_item",
                    item_id,
                    old_value={
                        "group_id": old["group_id"],
                        "product_uuid": old["product_uuid"],
                        "product_name": old["name_th"],
                        "position": old["position"],
                    },
                )
                flash("นำสินค้าออกจากเมนูแล้ว", "success")
            else:
                db.rollback()
                return ("คำสั่งไม่ถูกต้อง", 400)
            db.commit()
        except Exception as exc:
            db.rollback()
            text = str(exc)
            if "UNIQUE constraint failed: pos_button_groups.position" in text:
                text = "ตำแหน่งเมนูนี้ถูกใช้งานแล้ว"
            elif "UNIQUE constraint failed: pos_button_items.group_id, pos_button_items.position" in text:
                text = "ตำแหน่งสินค้านี้ถูกใช้งานแล้วในเมนู"
            elif "UNIQUE constraint failed: pos_button_items.group_id, pos_button_items.product_id" in text:
                text = "สินค้านี้อยู่ในเมนูดังกล่าวแล้ว"
            flash(text or "บันทึกการตั้งค่าปุ่มขายไม่สำเร็จ", "error")
        return redirect(url_for("products.pos_buttons", group_id=selected_group_id or None))

    groups = db.execute(
        """SELECT g.*,COUNT(i.id) AS item_count
           FROM pos_button_groups g
           LEFT JOIN pos_button_items i ON i.group_id=g.id
           GROUP BY g.id
           ORDER BY g.position,g.id"""
    ).fetchall()
    if selected_group_id is None and groups:
        selected_group_id = groups[0]["id"]
    selected_group = next((row for row in groups if row["id"] == selected_group_id), None)
    items = []
    if selected_group:
        items = db.execute(
            """SELECT i.id,i.position,p.product_uuid,p.barcode,p.name_th,p.price_satang
               FROM pos_button_items i JOIN products p ON p.id=i.product_id
               WHERE i.group_id=? ORDER BY i.position,i.id""",
            (selected_group["id"],),
        ).fetchall()
    query = request.args.get("q", "").strip()
    search_products = []
    if selected_group and query:
        term = f"%{query}%"
        search_products = db.execute(
            """SELECT p.product_uuid,p.barcode,p.sku,p.name_th,p.price_satang,
                      existing.position AS existing_position
               FROM products p
               LEFT JOIN pos_button_items existing
                 ON existing.product_id=p.id AND existing.group_id=?
               WHERE p.is_active=1
                 AND (p.barcode LIKE ? OR p.sku LIKE ? OR p.name_th LIKE ? OR p.name_en LIKE ?)
               ORDER BY p.name_th,p.id LIMIT 30""",
            (selected_group["id"], term, term, term, term),
        ).fetchall()
    return render_template(
        "pos_button_settings.html",
        groups=groups,
        selected_group=selected_group,
        items=items,
        query=query,
        search_products=search_products,
        next_group_position=max((row["position"] for row in groups), default=0) + 1,
        next_item_position=max((row["position"] for row in items), default=0) + 1,
    )


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


@bp.route("/quick-edit", methods=("GET", "POST"))
@permission_required("products.manage")
def quick_edit():
    """Scan, update no-image products, or quickly create a missing product."""

    db = get_db()
    categories, units = reference_data()
    price_memory_key = f"quick_product_last_price_baht_{g.staff['id']}"
    category_memory_key = f"quick_product_last_category_id_{g.staff['id']}"
    unit_memory_key = f"quick_product_last_unit_id_{g.staff['id']}"
    remembered_price_baht = session.get(price_memory_key)
    try:
        remembered_price_baht = int(remembered_price_baht)
        if remembered_price_baht < 0:
            remembered_price_baht = None
    except (TypeError, ValueError):
        remembered_price_baht = None

    active_category_ids = {row["id"] for row in categories}
    active_unit_ids = {row["id"] for row in units}

    def remembered_reference_id(key, active_ids):
        try:
            value = int(session.get(key))
        except (TypeError, ValueError):
            return None
        return value if value in active_ids else None

    remembered_category_id = remembered_reference_id(category_memory_key, active_category_ids)
    remembered_unit_id = remembered_reference_id(unit_memory_key, active_unit_ids)

    def new_product_stub(barcode):
        return {
            "product_uuid": "",
            "barcode": barcode,
            "name_th": "",
            "category_id": remembered_category_id or (categories[0]["id"] if categories else 0),
            "unit_id": remembered_unit_id or (units[0]["id"] if units else 0),
            "price_satang": (remembered_price_baht or 0) * 100,
            "image_path": None,
        }

    def render_quick_page(
        *,
        product=None,
        form_values=None,
        creating_new=False,
        already_imaged=False,
    ):
        return render_template(
            "product_quick_edit.html",
            categories=categories,
            units=units,
            product=product,
            form_values=form_values or {},
            creating_new=creating_new,
            already_imaged=already_imaged,
            remembered_price_baht=remembered_price_baht,
            remembered_category_id=remembered_category_id,
            remembered_unit_id=remembered_unit_id,
        )

    def validate_quick_fields():
        name_th = request.form.get("name_th", "").strip()
        if not name_th:
            raise ValueError("กรุณากรอกชื่อสินค้าภาษาไทย")
        category_id = int(request.form.get("category_id") or 0)
        unit_id = int(request.form.get("unit_id") or 0)
        if category_id not in active_category_ids:
            raise ValueError("หมวดสินค้าไม่ถูกต้อง")
        if unit_id not in active_unit_ids:
            raise ValueError("หน่วยสินค้าไม่ถูกต้อง")
        price_text = request.form.get("price", "").strip()
        try:
            price_baht = int(price_text)
        except (TypeError, ValueError):
            raise ValueError("ราคาขายต้องเป็นจำนวนเต็มบาท") from None
        if price_baht < 0:
            raise ValueError("ราคาขายต้องไม่ติดลบ")
        return name_th, category_id, unit_id, price_baht, price_baht * 100

    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        barcode = request.form.get("barcode", "").strip()
        product_uuid = request.form.get("product_uuid", "").strip()
        creating_new = request.form.get("create_new") == "1"
        if not barcode:
            flash("กรุณากรอกบาร์โค้ดสินค้า", "error")
            return render_quick_page()

        barcode_product = db.execute(
            "SELECT * FROM products WHERE barcode=?",
            (barcode,),
        ).fetchone()
        if barcode_product and (barcode_product["image_path"] or "").strip():
            return render_quick_page(already_imaged=True)
        if creating_new and barcode_product:
            flash("พบบาร์โค้ดนี้ในระบบแล้ว กรุณาตรวจสอบและบันทึกข้อมูลต่อ", "info")
            product = barcode_product
            creating_new = False
        elif creating_new:
            product = new_product_stub(barcode)
        else:
            product = db.execute(
                "SELECT * FROM products WHERE product_uuid=? AND barcode=?",
                (product_uuid, barcode),
            ).fetchone()
            if not product:
                flash("ไม่พบสินค้าที่ต้องการแก้ไข กรุณาสแกนใหม่", "error")
                return redirect(url_for("products.quick_edit"))

        new_image_path = None
        try:
            name_th, category_id, unit_id, price_baht, price_satang = validate_quick_fields()

            db.execute("BEGIN IMMEDIATE")
            if creating_new:
                if db.execute(
                    "SELECT 1 FROM products WHERE barcode=?",
                    (barcode,),
                ).fetchone():
                    db.rollback()
                    return redirect(url_for("products.quick_edit", barcode=barcode))
                new_image_path = save_image(submitted_product_image())
                created_uuid = new_product_uuid()
                db.execute(
                    """INSERT INTO products
                       (product_uuid,barcode,name_th,category_id,unit_id,cost_satang,
                        price_satang,stock_quantity,minimum_stock,image_path,is_active)
                       VALUES (?,?,?,?,?,0,?,0,0,?,1)""",
                    (
                        created_uuid,
                        barcode,
                        name_th,
                        category_id,
                        unit_id,
                        price_satang,
                        new_image_path,
                    ),
                )
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                new_value = {
                    "barcode": barcode,
                    "name_th": name_th,
                    "category_id": category_id,
                    "unit_id": unit_id,
                    "price_satang": price_satang,
                    "image_path": new_image_path,
                    "is_active": 1,
                    "source": "quick_edit",
                }
                db.execute(
                    """INSERT INTO audit_logs
                       (staff_id,action,entity_type,entity_id,new_value,ip_address,created_at)
                       VALUES (?, 'create_product', 'product', ?, ?, ?, ?)""",
                    (
                        g.staff["id"],
                        created_uuid,
                        json.dumps(new_value, ensure_ascii=False),
                        request.remote_addr,
                        now,
                    ),
                )
                success_message = "เพิ่มสินค้าใหม่เรียบร้อยแล้ว สแกนสินค้าชิ้นถัดไปได้เลย"
            else:
                current = db.execute(
                    "SELECT * FROM products WHERE product_uuid=? AND barcode=?",
                    (product["product_uuid"], barcode),
                ).fetchone()
                if not current:
                    db.rollback()
                    flash("ไม่พบสินค้าที่ต้องการแก้ไข กรุณาสแกนใหม่", "error")
                    return redirect(url_for("products.quick_edit"))
                if (current["image_path"] or "").strip():
                    db.rollback()
                    return render_quick_page(already_imaged=True)

                new_image_path = save_image(submitted_product_image())
                image_path = new_image_path or current["image_path"]
                db.execute(
                    """UPDATE products
                       SET name_th=?,category_id=?,unit_id=?,price_satang=?,image_path=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (name_th, category_id, unit_id, price_satang, image_path, current["id"]),
                )
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                old_value = {
                    "name_th": current["name_th"],
                    "category_id": current["category_id"],
                    "unit_id": current["unit_id"],
                    "price_satang": current["price_satang"],
                    "image_path": current["image_path"],
                }
                new_value = {
                    "name_th": name_th,
                    "category_id": category_id,
                    "unit_id": unit_id,
                    "price_satang": price_satang,
                    "image_path": image_path,
                }
                db.execute(
                    """INSERT INTO audit_logs
                       (staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
                       VALUES (?, 'quick_edit_product', 'product', ?, ?, ?, ?, ?)""",
                    (
                        g.staff["id"],
                        current["product_uuid"],
                        json.dumps(old_value, ensure_ascii=False),
                        json.dumps(new_value, ensure_ascii=False),
                        request.remote_addr,
                        now,
                    ),
                )
                if current["price_satang"] != price_satang:
                    db.execute(
                        """INSERT INTO audit_logs
                           (staff_id,action,entity_type,entity_id,old_value,new_value,ip_address,created_at)
                           VALUES (?, 'change_price', 'product', ?, ?, ?, ?, ?)""",
                        (
                            g.staff["id"],
                            current["product_uuid"],
                            str(current["price_satang"]),
                            str(price_satang),
                            request.remote_addr,
                            now,
                        ),
                    )
                success_message = "บันทึกสินค้าเรียบร้อยแล้ว สแกนสินค้าชิ้นถัดไปได้เลย"
            db.commit()
            session[price_memory_key] = price_baht
            session[category_memory_key] = category_id
            session[unit_memory_key] = unit_id
            flash(success_message, "success")
            return redirect(url_for("products.quick_edit"))
        except Exception as exc:
            db.rollback()
            if new_image_path:
                try:
                    (current_app.config["RUNTIME_PATHS"].product_images / new_image_path).unlink(missing_ok=True)
                except OSError:
                    current_app.logger.warning("Could not remove failed quick-edit image %s", new_image_path)
            message = "บาร์โค้ดนี้มีสินค้าอยู่แล้ว กรุณาสแกนใหม่" if "UNIQUE constraint" in str(exc) else str(exc)
            flash(message, "error")
            return render_quick_page(
                product=product,
                form_values=request.form,
                creating_new=creating_new,
            )

    barcode = request.args.get("barcode", "").strip()
    product = None
    creating_new = False
    already_imaged = False
    if barcode:
        product = db.execute(
            "SELECT * FROM products WHERE barcode=?",
            (barcode,),
        ).fetchone()
        if product and (product["image_path"] or "").strip():
            product = None
            already_imaged = True
        elif product is None:
            product = new_product_stub(barcode)
            creating_new = True
    return render_quick_page(
        product=product,
        creating_new=creating_new,
        already_imaged=already_imaged,
    )


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


def price_create_memory_key(reference_name):
    return f"price_control_create_last_{reference_name}_id_{g.staff['id']}"


def remembered_price_create_reference(reference_name, active_ids):
    key = price_create_memory_key(reference_name)
    try:
        value = int(session.get(key))
    except (TypeError, ValueError):
        session.pop(key, None)
        return None
    if value not in active_ids:
        session.pop(key, None)
        return None
    return value


def render_price_page(db, category_id, query, create_form_values=None):
    rows = price_rows(db, category_id, query)
    categories, units = reference_data()
    exact_barcode_uuid = next(
        (row["product_uuid"] for row in rows if row["barcode"] == query),
        None,
    ) if query else None
    barcode_exists = db.execute(
        "SELECT 1 FROM products WHERE barcode=?",
        (query,),
    ).fetchone() if query else None
    active_category_ids = {row["id"] for row in categories}
    active_unit_ids = {row["id"] for row in units}
    remembered_category_id = remembered_price_create_reference(
        "category",
        active_category_ids,
    )
    remembered_unit_id = remembered_price_create_reference(
        "unit",
        active_unit_ids,
    )
    default_create_category_id = (
        remembered_category_id
        or (category_id if category_id in active_category_ids else None)
        or (categories[0]["id"] if categories else 0)
    )
    return render_template(
        "product_prices.html",
        products=rows,
        categories=categories,
        units=units,
        selected_category=category_id,
        query=query,
        exact_barcode_uuid=exact_barcode_uuid,
        missing_product=bool(query and not rows and not barcode_exists),
        create_form_values=create_form_values or {},
        default_create_category_id=default_create_category_id,
        default_create_unit_id=(
            remembered_unit_id
            or (units[0]["id"] if units else 0)
        ),
    )


def create_missing_price_product(db):
    barcode = request.form.get("barcode", "").strip()
    return_category_id = request.form.get("return_category_id", type=int)
    try:
        name_th = request.form.get("name_th", "").strip()
        if not barcode:
            raise ValueError("กรุณากรอกบาร์โค้ดสินค้า")
        if not name_th:
            raise ValueError("กรุณากรอกชื่อสินค้าภาษาไทย")
        try:
            category_id = int(request.form.get("category_id") or 0)
            unit_id = int(request.form.get("unit_id") or 0)
        except (TypeError, ValueError):
            raise ValueError("หมวดสินค้าและหน่วยไม่ถูกต้อง") from None
        categories, units = reference_data()
        if category_id not in {row["id"] for row in categories}:
            raise ValueError("หมวดสินค้าไม่ถูกต้อง")
        if unit_id not in {row["id"] for row in units}:
            raise ValueError("หน่วยสินค้าไม่ถูกต้อง")
        price_text = request.form.get("price", "").strip()
        try:
            price_baht = int(price_text)
        except (TypeError, ValueError):
            raise ValueError("ราคาขายต้องเป็นจำนวนเต็มบาท") from None
        if price_baht < 0:
            raise ValueError("ราคาขายต้องไม่ติดลบ")

        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT 1 FROM products WHERE barcode=?",
            (barcode,),
        ).fetchone():
            db.rollback()
            flash("พบบาร์โค้ดนี้ในระบบแล้ว กรุณาตรวจสอบราคาสินค้าเดิม", "info")
            return redirect(url_for("products.prices", q=barcode))

        created_uuid = new_product_uuid()
        price_satang = price_baht * 100
        db.execute(
            """INSERT INTO products
               (product_uuid,barcode,name_th,category_id,unit_id,cost_satang,
                price_satang,stock_quantity,minimum_stock,image_path,is_active)
               VALUES (?,?,?,?,?,0,?,0,0,NULL,1)""",
            (
                created_uuid,
                barcode,
                name_th,
                category_id,
                unit_id,
                price_satang,
            ),
        )
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        new_value = {
            "barcode": barcode,
            "name_th": name_th,
            "category_id": category_id,
            "unit_id": unit_id,
            "price_satang": price_satang,
            "image_path": None,
            "is_active": 1,
            "source": "price_control",
        }
        db.execute(
            """INSERT INTO audit_logs
               (staff_id,action,entity_type,entity_id,new_value,ip_address,created_at)
               VALUES (?, 'create_product', 'product', ?, ?, ?, ?)""",
            (
                g.staff["id"],
                created_uuid,
                json.dumps(new_value, ensure_ascii=False),
                request.remote_addr,
                now,
            ),
        )
        db.commit()
        session[price_create_memory_key("category")] = category_id
        session[price_create_memory_key("unit")] = unit_id
        flash("เพิ่มสินค้าใหม่เรียบร้อยแล้ว สแกนสินค้าชิ้นถัดไปได้เลย", "success")
        return redirect(url_for(
            "products.prices",
            category_id=return_category_id,
        ))
    except Exception as exc:
        db.rollback()
        message = (
            "พบบาร์โค้ดนี้ในระบบแล้ว กรุณาตรวจสอบราคาสินค้าเดิม"
            if "UNIQUE constraint" in str(exc)
            else str(exc)
        )
        flash(message, "error")
        return render_price_page(
            db,
            return_category_id,
            barcode,
            create_form_values=request.form,
        )


@bp.route("/prices", methods=("GET", "POST"))
@permission_required("products.manage")
def prices():
    db = get_db()
    if request.method == "POST":
        if not valid_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        if request.form.get("action") == "create_missing":
            return create_missing_price_product(db)
        changes=[]
        submitted_barcodes = []
        return_query = request.form.get("return_q", "").strip()
        save_succeeded = False
        try:
            for product_uuid in request.form.getlist("product_uuid"):
                price = baht_to_satang(request.form.get(f"price_{product_uuid}"))
                old = product_by_uuid(db, product_uuid)
                if old:
                    submitted_barcodes.append(old["barcode"])
                    if old["price_satang"] != price:changes.append({"product_uuid":old["product_uuid"],"name":old["name_th"],"barcode":old["barcode"],"old":old["price_satang"],"new":price})
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
            save_succeeded = True
            flash(f"บันทึกราคาขาย {len(changes)} รายการเรียบร้อยแล้ว", "success")
        except Exception as exc:
            db.rollback()
            flash(str(exc), "error")
        return_to_scan = (
            save_succeeded
            and len(submitted_barcodes) == 1
            and submitted_barcodes[0] == return_query
        )
        return redirect(url_for(
            "products.prices",
            q=None if return_to_scan else return_query or None,
            category_id=request.form.get("return_category_id", type=int),
        ))
    category_id = request.args.get("category_id", type=int)
    query = request.args.get("q", "").strip()
    return render_price_page(db, category_id, query)


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
