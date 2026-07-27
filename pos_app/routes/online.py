import json
import hmac
import secrets
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import iso_time, utc_now
from ..customer_auth import (
    CUSTOMER_COOKIE_NAME, create_customer_session, customer_login_required,
    normalize_phone, phone_fingerprint, valid_customer_csrf,
)
from ..database import get_db
from ..services.online_orders import (
    OnlineOrderError, audit_order, cancel_customer_order, create_order, expire_pending_orders,
)


bp = Blueprint("online", __name__, url_prefix="/order")


@bp.context_processor
def customer_contact_context():
    settings = online_settings()
    store_name = (settings.get("store_name") or "แสนงาม มินิมาร์ท").strip()
    return {
        "customer_store_name_lines": store_name.split() or ["แสนงาม", "มินิมาร์ท"],
        "customer_contact": {
            "line": settings.get("online_contact_line") or "@114rbvoi",
            "phone": settings.get("online_contact_phone") or "09X-XXX-XXXX",
        }
    }


def public_form_csrf():
    token = session.get("online_public_csrf")
    if not token:
        token = secrets.token_urlsafe(24)
        session["online_public_csrf"] = token
    return token


def valid_public_csrf(value):
    expected = session.get("online_public_csrf")
    return bool(expected and value and hmac.compare_digest(expected, value))


def customer_event(event_type, customer_id=None, phone=None):
    get_db().execute(
        """INSERT INTO customer_login_events(customer_id,phone_fingerprint,event_type,ip_address,created_at)
           VALUES(?,?,?,?,?)""",
        (customer_id, phone_fingerprint(phone) if phone else None, event_type, request.remote_addr, iso_time(utc_now())),
    )


def online_settings():
    return dict(get_db().execute("SELECT key,value FROM settings").fetchall())


def ordering_open(settings=None):
    settings = settings or online_settings()
    if settings.get("online_ordering_enabled") != "1":
        return False
    start, end = settings.get("online_ordering_start"), settings.get("online_ordering_end")
    if not start or not end:
        return True
    now = datetime.now(timezone(timedelta(hours=7))).time()
    start_time, end_time = time.fromisoformat(start), time.fromisoformat(end)
    return start_time <= now <= end_time if start_time <= end_time else now >= start_time or now <= end_time


def available_products(query="", category_id=None):
    where = ["p.is_active=1", "p.is_online_available=1"]
    params = []
    if query:
        where.append("(p.name_th LIKE ? OR p.name_en LIKE ? OR p.barcode LIKE ?)")
        params.extend([f"%{query}%"] * 3)
    if category_id:
        where.append("p.category_id=?")
        params.append(category_id)
    return get_db().execute(
        f"""SELECT p.id,p.name_th,p.barcode,p.price_satang,p.image_path,p.allow_decimal_quantity,
                   p.online_max_quantity,c.id AS category_id,c.name_th AS category_name,
                   MAX(0,p.stock_quantity-COALESCE((SELECT SUM(sr.quantity) FROM stock_reservations sr
                     WHERE sr.product_id=p.id AND sr.status='active'),0)) AS available_quantity
            FROM products p JOIN categories c ON c.id=p.category_id
            WHERE {' AND '.join(where)}
            ORDER BY p.online_sort_order,p.name_th LIMIT 200""",
        params,
    ).fetchall()


def validate_cart(raw_items):
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("ตะกร้าสินค้าว่าง")
    settings = online_settings()
    max_total_quantity = Decimal(settings.get("online_max_order_quantity") or "50")
    total_quantity = Decimal("0")
    validated = []
    seen = set()
    for raw in raw_items:
        try:
            product_id = int(raw.get("product_id"))
            quantity = Decimal(str(raw.get("quantity")))
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError("จำนวนสินค้าไม่ถูกต้อง") from exc
        if product_id in seen or quantity <= 0:
            raise ValueError("รายการสินค้าไม่ถูกต้อง")
        seen.add(product_id)
        row = get_db().execute(
            """SELECT p.*,MAX(0,p.stock_quantity-COALESCE((SELECT SUM(sr.quantity) FROM stock_reservations sr
                 WHERE sr.product_id=p.id AND sr.status='active'),0)) AS available_quantity
               FROM products p WHERE p.id=? AND p.is_active=1 AND p.is_online_available=1""",
            (product_id,),
        ).fetchone()
        if not row:
            raise ValueError("มีสินค้าที่ปิดขายออนไลน์ กรุณาตรวจสอบตะกร้าอีกครั้ง")
        if not row["allow_decimal_quantity"] and quantity != quantity.to_integral_value():
            raise ValueError(f"จำนวน {row['name_th']} ต้องเป็นจำนวนเต็ม")
        limit = Decimal(str(row["online_max_quantity"])) if row["online_max_quantity"] else None
        available = Decimal(str(row["available_quantity"]))
        if limit and quantity > limit:
            raise ValueError(f"{row['name_th']} สั่งได้สูงสุด {limit} ต่อออเดอร์")
        if quantity > available:
            raise ValueError(f"{row['name_th']} มีสินค้าไม่เพียงพอ (พร้อมขาย {available})")
        total_quantity += quantity
        line_total = int(Decimal(row["price_satang"]) * quantity)
        validated.append({
            "product_id": row["id"], "name_th": row["name_th"], "barcode": row["barcode"],
            "image_path": row["image_path"], "quantity": float(quantity), "unit_price_satang": row["price_satang"],
            "line_total_satang": line_total, "available_quantity": float(available),
        })
    if total_quantity > max_total_quantity:
        raise ValueError(f"จำนวนสินค้ารวมต้องไม่เกิน {max_total_quantity}")
    return validated


@bp.route("/register", methods=("GET", "POST"))
def customer_register():
    if request.method == "POST":
        if not valid_public_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        try:
            phone = normalize_phone(request.form.get("phone"))
            pin = request.form.get("pin", "")
            if pin != request.form.get("pin_confirm") or not pin.isdigit() or len(pin) not in (4, 6):
                raise ValueError("PIN ต้องเป็นตัวเลข 4 หรือ 6 หลักและกรอกให้ตรงกัน")
            db = get_db()
            now = iso_time(utc_now())
            cursor = db.execute(
                """INSERT INTO customers(public_id,phone_normalized,display_name,pin_hash,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)""",
                (secrets.token_urlsafe(12), phone, request.form.get("display_name", "").strip() or None,
                 generate_password_hash(pin), now, now),
            )
            customer_event("registration", cursor.lastrowid, phone)
            db.execute(
                """INSERT INTO audit_logs(action,entity_type,entity_id,new_value,ip_address,created_at)
                   VALUES('customer_registration','customer',?,?,?,?)""",
                (str(cursor.lastrowid), json.dumps({"phone_tail": phone[-4:]}), request.remote_addr, now),
            )
            token = create_customer_session(cursor.lastrowid)
            db.commit()
            response = redirect(url_for("online.catalog"))
            response.set_cookie(CUSTOMER_COOKIE_NAME, token, httponly=True, samesite="Lax", secure=request.is_secure)
            return response
        except Exception as exc:
            get_db().rollback()
            message = "ไม่สามารถสมัครสมาชิกได้ กรุณาตรวจสอบข้อมูลหรือติดต่อร้าน" if "UNIQUE constraint" in str(exc) else str(exc)
            flash(message, "error")
    return render_template("online/register.html", public_csrf=public_form_csrf())


@bp.route("/login", methods=("GET", "POST"))
def customer_login():
    if request.method == "POST":
        if not valid_public_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        try:
            phone = normalize_phone(request.form.get("phone"))
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("online/login.html", public_csrf=public_form_csrf())
        db = get_db()
        customer = db.execute("SELECT * FROM customers WHERE phone_normalized=? AND is_active=1 AND is_guest=0", (phone,)).fetchone()
        action = request.form.get("action", "lookup")
        if action == "lookup":
            return render_template("online/login.html", public_csrf=public_form_csrf(), phone=phone, customer_exists=bool(customer))
        if action == "create":
            pin = request.form.get("pin", "")
            if customer:
                flash("เบอร์นี้มีบัญชีแล้ว กรุณากรอก PIN", "error")
                return render_template("online/login.html", public_csrf=public_form_csrf(), phone=phone, customer_exists=True)
            if not pin.isdigit() or len(pin) != 4:
                flash("PIN ต้องเป็นตัวเลข 4 หลัก", "error")
                return render_template("online/login.html", public_csrf=public_form_csrf(), phone=phone, customer_exists=False)
            now = iso_time(utc_now())
            cursor = db.execute(
                """INSERT INTO customers(public_id,phone_normalized,display_name,pin_hash,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)""",
                (secrets.token_urlsafe(12), phone, request.form.get("display_name", "").strip() or None,
                 generate_password_hash(pin), now, now),
            )
            customer_event("registration", cursor.lastrowid, phone)
            token = create_customer_session(cursor.lastrowid)
            db.commit()
            response = redirect(url_for("online.catalog"))
            response.set_cookie(CUSTOMER_COOKIE_NAME, token, httponly=True, samesite="Lax", secure=request.is_secure)
            return response
        fingerprint = phone_fingerprint(phone)
        cutoff = iso_time(utc_now() - timedelta(minutes=15))
        failures = db.execute(
            """SELECT COUNT(*) FROM customer_login_events
               WHERE phone_fingerprint=? AND COALESCE(ip_address,'')=COALESCE(?,'')
               AND event_type='login_failed' AND created_at>=?""",
            (fingerprint, request.remote_addr, cutoff),
        ).fetchone()[0]
        if failures >= 5:
            flash("ลองเข้าสู่ระบบหลายครั้งเกินไป กรุณารอ 15 นาทีแล้วลองใหม่", "error")
            return render_template("online/login.html", public_csrf=public_form_csrf()), 429
        if not customer or not check_password_hash(customer["pin_hash"], request.form.get("pin", "")):
            customer_event("login_failed", customer["id"] if customer else None, phone)
            db.commit()
            flash("หมายเลขโทรศัพท์หรือ PIN ไม่ถูกต้อง", "error")
        else:
            now = iso_time(utc_now())
            customer_event("login_success", customer["id"], phone)
            db.execute("UPDATE customers SET last_login_at=?,updated_at=? WHERE id=?", (now, now, customer["id"]))
            token = create_customer_session(customer["id"])
            db.commit()
            response = redirect(request.args.get("next") or url_for("online.catalog"))
            response.set_cookie(CUSTOMER_COOKIE_NAME, token, httponly=True, samesite="Lax", secure=request.is_secure)
            return response
    return render_template("online/login.html", public_csrf=public_form_csrf())


@bp.post("/logout")
@customer_login_required
def customer_logout():
    if not valid_customer_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    db = get_db()
    customer_event("logout", g.customer["id"], g.customer["phone_normalized"])
    db.execute("DELETE FROM customer_sessions WHERE id=?", (g.customer_session["session_id"],))
    db.commit()
    response = redirect(url_for("online.customer_login"))
    response.delete_cookie(CUSTOMER_COOKIE_NAME)
    return response


@bp.route("/change-pin", methods=("GET", "POST"))
@customer_login_required
def customer_change_pin():
    if request.method == "POST":
        if not valid_customer_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        pin = request.form.get("new_pin", "")
        current_ok = g.customer["must_change_pin"] or check_password_hash(g.customer["pin_hash"], request.form.get("current_pin", ""))
        if not current_ok or pin != request.form.get("pin_confirm") or not pin.isdigit() or len(pin) not in (4, 6):
            flash("ข้อมูล PIN ไม่ถูกต้อง", "error")
        else:
            db = get_db()
            db.execute(
                "UPDATE customers SET pin_hash=?,must_change_pin=0,updated_at=? WHERE id=?",
                (generate_password_hash(pin), iso_time(utc_now()), g.customer["id"]),
            )
            customer_event("pin_changed", g.customer["id"], g.customer["phone_normalized"])
            db.commit()
            flash("เปลี่ยน PIN เรียบร้อยแล้ว", "success")
            return redirect(url_for("online.catalog"))
    return render_template("online/change_pin.html")


@bp.get("")
def catalog():
    expire_pending_orders()
    settings = online_settings()
    products = available_products(request.args.get("q", "").strip(), request.args.get("category_id", type=int))
    categories = get_db().execute(
        """SELECT DISTINCT c.id,c.name_th,c.sort_order FROM categories c JOIN products p ON p.category_id=c.id
           WHERE c.is_active=1 AND p.is_active=1 AND p.is_online_available=1
           ORDER BY c.sort_order,c.name_th"""
    ).fetchall()
    repeat_products = []
    if g.customer and not g.customer["is_guest"]:
        repeat_products = get_db().execute(
            """SELECT p.id,p.name_th,p.price_satang,p.image_path,p.allow_decimal_quantity,p.online_max_quantity,
                      MAX(0,p.stock_quantity-COALESCE((SELECT SUM(sr.quantity) FROM stock_reservations sr
                        WHERE sr.product_id=p.id AND sr.status='active'),0)) AS available_quantity
               FROM online_order_items oi JOIN online_orders o ON o.id=oi.order_id
               JOIN products p ON p.id=oi.product_id
               WHERE o.customer_id=? AND p.is_active=1 AND p.is_online_available=1
               GROUP BY p.id ORDER BY MAX(o.created_at) DESC LIMIT 8""", (g.customer["id"],)
        ).fetchall()
    return render_template("online/catalog.html", settings=settings, products=products, categories=categories,
                           repeat_products=repeat_products, is_open=ordering_open(settings))


@bp.get("/cart")
def cart():
    settings = online_settings()
    repeat_products = []
    if g.customer and not g.customer["is_guest"]:
        repeat_products = get_db().execute(
            """SELECT p.id,p.name_th,p.price_satang,p.image_path,p.allow_decimal_quantity,p.online_max_quantity,
                      MAX(0,p.stock_quantity-COALESCE((SELECT SUM(sr.quantity) FROM stock_reservations sr
                        WHERE sr.product_id=p.id AND sr.status='active'),0)) AS available_quantity
               FROM online_order_items oi JOIN online_orders o ON o.id=oi.order_id
               JOIN products p ON p.id=oi.product_id
               WHERE o.customer_id=? AND p.is_active=1 AND p.is_online_available=1
               GROUP BY p.id ORDER BY MAX(o.created_at) DESC LIMIT 8""", (g.customer["id"],)
        ).fetchall()
    return render_template(
        "online/cart.html", repeat_products=repeat_products,
        settings=settings, is_open=ordering_open(settings),
    )


@bp.get("/products/<path:filename>")
def customer_product_image(filename):
    allowed = get_db().execute(
        "SELECT 1 FROM products WHERE image_path=? AND is_active=1 AND is_online_available=1", (filename,)
    ).fetchone()
    if not allowed:
        return ("ไม่พบรูปสินค้า", 404)
    return send_from_directory(current_app.config["RUNTIME_PATHS"].product_images, filename)


@bp.get("/bank-qr")
def bank_qr():
    filename = online_settings().get("online_bank_qr_path")
    if not filename:
        return ("ไม่พบรูป QR", 404)
    return send_from_directory(current_app.config["RUNTIME_PATHS"].online_payment_evidence, filename)


@bp.get("/api/products")
def customer_products_api():
    return jsonify([dict(row) for row in available_products(request.args.get("q", "").strip(), request.args.get("category_id", type=int))])


@bp.post("/api/cart/validate")
def validate_cart_api():
    try:
        items = validate_cart((request.get_json(silent=True) or {}).get("items"))
        return jsonify(items=items, subtotal_satang=sum(item["line_total_satang"] for item in items))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@bp.post("/api/account/lookup")
def checkout_account_lookup():
    payload = request.get_json(silent=True) or {}
    if not valid_public_csrf(request.headers.get("X-CSRF-Token")):
        return jsonify(error="คำขอไม่ถูกต้อง"), 400
    try:
        phone = normalize_phone(payload.get("phone"))
        customer = get_db().execute(
            "SELECT id FROM customers WHERE phone_normalized=? AND is_active=1 AND is_guest=0", (phone,)
        ).fetchone()
        return jsonify(account_exists=bool(customer))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@bp.post("/api/account/login")
def checkout_account_login():
    payload = request.get_json(silent=True) or {}
    if not valid_public_csrf(request.headers.get("X-CSRF-Token")):
        return jsonify(error="คำขอไม่ถูกต้อง"), 400
    try:
        phone = normalize_phone(payload.get("phone"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    db = get_db()
    customer = db.execute(
        "SELECT * FROM customers WHERE phone_normalized=? AND is_active=1 AND is_guest=0", (phone,)
    ).fetchone()
    cutoff = iso_time(utc_now() - timedelta(minutes=15))
    failures = db.execute(
        """SELECT COUNT(*) FROM customer_login_events
           WHERE phone_fingerprint=? AND COALESCE(ip_address,'')=COALESCE(?,'')
           AND event_type='login_failed' AND created_at>=?""",
        (phone_fingerprint(phone), request.remote_addr, cutoff),
    ).fetchone()[0]
    if failures >= 5:
        return jsonify(error="ลองเข้าสู่ระบบหลายครั้งเกินไป กรุณารอ 15 นาทีแล้วลองใหม่"), 429
    pin = str(payload.get("pin") or "")
    if not customer or not check_password_hash(customer["pin_hash"], pin):
        customer_event("login_failed", customer["id"] if customer else None, phone)
        db.commit()
        return jsonify(error="หมายเลขโทรศัพท์หรือ PIN ไม่ถูกต้อง"), 400
    now = iso_time(utc_now())
    customer_event("login_success", customer["id"], phone)
    db.execute("UPDATE customers SET last_login_at=?,updated_at=? WHERE id=?", (now, now, customer["id"]))
    token = create_customer_session(customer["id"])
    csrf = db.execute(
        "SELECT csrf_token FROM customer_sessions WHERE customer_id=? ORDER BY id DESC LIMIT 1", (customer["id"],)
    ).fetchone()[0]
    db.commit()
    response = jsonify(ok=True, csrf_token=csrf, display_name=customer["display_name"] or "")
    response.set_cookie(CUSTOMER_COOKIE_NAME, token, httponly=True, samesite="Lax", secure=request.is_secure)
    return response


@bp.get("/checkout")
def checkout():
    settings = online_settings()
    locations = get_db().execute(
        "SELECT * FROM delivery_locations WHERE is_active=1 AND is_available=1 ORDER BY sort_order,name"
    ).fetchall()
    return render_template(
        "online/checkout.html", settings=settings, locations=locations,
        is_open=ordering_open(settings), public_csrf=public_form_csrf(),
    )


def owned_order(public_id):
    return get_db().execute(
        """SELECT o.*,dl.room_required,c.phone_normalized,c.display_name
           FROM online_orders o LEFT JOIN delivery_locations dl ON dl.id=o.delivery_location_id
           JOIN customers c ON c.id=o.customer_id
           WHERE o.public_id=? AND o.customer_id=?""",
        (public_id, g.customer["id"]),
    ).fetchone()


@bp.post("/api/orders")
def submit_order():
    is_member = g.customer is not None
    csrf_ok = valid_customer_csrf(request.headers.get("X-CSRF-Token")) if is_member else valid_public_csrf(request.headers.get("X-CSRF-Token"))
    if not csrf_ok:
        return jsonify(error="คำขอไม่ถูกต้อง"), 400
    settings = online_settings()
    if not ordering_open(settings):
        return jsonify(error=settings.get("online_closed_message")), 400
    payload = request.get_json(silent=True) or {}
    location = get_db().execute(
        "SELECT * FROM delivery_locations WHERE id=? AND is_active=1 AND is_available=1",
        (payload.get("delivery_location_id"),),
    ).fetchone()
    if not location:
        return jsonify(error="สถานที่จัดส่งไม่พร้อมใช้งาน"), 400
    try:
        token = None
        customer_id = g.customer["id"] if is_member else None
        if not customer_id:
            phone = normalize_phone(payload.get("phone"))
            name = str(payload.get("display_name") or "").strip()
            if not name:
                raise OnlineOrderError("กรุณาระบุชื่อลูกค้า")
            existing = get_db().execute(
                "SELECT id FROM customers WHERE phone_normalized=? AND is_guest=0", (phone,)
            ).fetchone()
            if existing:
                raise OnlineOrderError("เบอร์นี้มีบัญชีแล้ว กรุณาเข้าสู่ระบบก่อนสั่งซื้อ")
            pin = str(payload.get("new_pin") or "")
            if pin and (not pin.isdigit() or len(pin) != 4):
                raise OnlineOrderError("PIN ต้องเป็นตัวเลข 4 หลัก")
            now = iso_time(utc_now())
            public_id = secrets.token_urlsafe(12)
            stored_phone = phone if pin else f"guest:{public_id}"
            cursor = get_db().execute(
                """INSERT INTO customers(public_id,phone_normalized,display_name,pin_hash,is_guest,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (public_id, stored_phone, name, generate_password_hash(pin or secrets.token_urlsafe(16)),
                 0 if pin else 1, now, now),
            )
            customer_id = cursor.lastrowid
            payload["contact_phone"] = phone
            payload["contact_name"] = name
            token = create_customer_session(customer_id)
        result, duplicate = create_order(customer_id, payload, validate_cart, settings, location)
        response = jsonify(public_id=result["public_id"], order_number=result["order_number"], duplicate=duplicate,
                           detail_url=url_for("online.order_detail", public_id=result["public_id"]))
        if token:
            response.set_cookie(CUSTOMER_COOKIE_NAME, token, httponly=True, samesite="Lax", secure=request.is_secure)
        return response
    except (OnlineOrderError, ValueError) as exc:
        return jsonify(error=str(exc)), 400


def sniff_image(content):
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp", "image/webp"
    raise OnlineOrderError("ไฟล์สลิปต้องเป็น JPG, PNG หรือ WEBP")


@bp.post("/orders/<public_id>/slips")
@customer_login_required
def upload_slip(public_id):
    if not valid_customer_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    order = owned_order(public_id)
    blocked = {"completed", "customer_cancelled", "staff_cancelled", "rejected", "expired"}
    if not order or order["payment_method_code"] != "transfer" or order["status"] in blocked:
        return ("ไม่สามารถอัปโหลดสลิปสำหรับออเดอร์นี้", 400)
    upload = request.files.get("slip")
    if not upload or not upload.filename:
        flash("กรุณาเลือกไฟล์สลิป", "error")
        return redirect(url_for("online.order_detail", public_id=public_id))
    content = upload.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        flash("ไฟล์สลิปต้องไม่เกิน 5 MB", "error")
        return redirect(url_for("online.order_detail", public_id=public_id))
    try:
        ext, content_type = sniff_image(content)
        filename = f"slip-{secrets.token_hex(16)}{ext}"
        path = current_app.config["RUNTIME_PATHS"].online_payment_evidence / filename
        path.write_bytes(content)
        db = get_db()
        now = iso_time(utc_now())
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """INSERT INTO online_order_payments
               (order_id,method_code,amount_satang,status,slip_path,content_type,uploaded_by_customer_id,created_at,updated_at)
               VALUES(?,'transfer',?,'awaiting_verification',?,?,?,?,?)""",
            (order["id"], order["total_satang"], filename, content_type, g.customer["id"], now, now),
        )
        db.execute("UPDATE online_orders SET payment_status='awaiting_verification',updated_at=? WHERE id=?", (now, order["id"]))
        audit_order("online_payment_slip_uploaded", order["id"], detail={"payment_status": "awaiting_verification"})
        db.commit()
        flash("อัปโหลดสลิปแล้ว รอร้านตรวจสอบการชำระเงิน", "success")
    except OnlineOrderError as exc:
        flash(str(exc), "error")
    return redirect(url_for("online.order_detail", public_id=public_id))


@bp.get("/orders")
@customer_login_required
def order_history():
    expire_pending_orders()
    orders = get_db().execute(
        "SELECT * FROM online_orders WHERE customer_id=? ORDER BY created_at DESC", (g.customer["id"],)
    ).fetchall()
    return render_template("online/orders.html", orders=orders)


@bp.get("/orders/<public_id>")
@customer_login_required
def order_detail(public_id):
    expire_pending_orders()
    order = owned_order(public_id)
    if not order:
        return ("ไม่พบออเดอร์", 404)
    db = get_db()
    items = db.execute("SELECT * FROM online_order_items WHERE order_id=? ORDER BY id", (order["id"],)).fetchall()
    history = db.execute(
        "SELECT * FROM online_order_status_history WHERE order_id=? AND customer_visible=1 ORDER BY created_at,id",
        (order["id"],),
    ).fetchall()
    slips = db.execute(
        """SELECT id,status,rejection_reason,created_at FROM online_order_payments
           WHERE order_id=? AND slip_path IS NOT NULL ORDER BY created_at DESC""", (order["id"],)
    ).fetchall()
    return render_template("online/order_detail.html", order=order, items=items, history=history, slips=slips, settings=online_settings())


@bp.get("/orders/<public_id>/slips/<int:payment_id>")
@customer_login_required
def view_own_slip(public_id, payment_id):
    order = owned_order(public_id)
    if not order:
        return ("ไม่พบไฟล์", 404)
    payment = get_db().execute(
        "SELECT slip_path FROM online_order_payments WHERE id=? AND order_id=? AND slip_path IS NOT NULL",
        (payment_id, order["id"]),
    ).fetchone()
    if not payment:
        return ("ไม่พบไฟล์", 404)
    return send_from_directory(current_app.config["RUNTIME_PATHS"].online_payment_evidence, payment["slip_path"])


@bp.post("/orders/<public_id>/cancel")
@customer_login_required
def customer_cancel(public_id):
    if not valid_customer_csrf(request.form.get("csrf_token")):
        return ("คำขอไม่ถูกต้อง", 400)
    order = owned_order(public_id)
    if not order:
        return ("ไม่พบออเดอร์", 404)
    try:
        cancel_customer_order(order, g.customer["id"], request.form.get("reason"))
        flash("ยกเลิกออเดอร์และคืนจำนวนสินค้าพร้อมขายแล้ว", "success")
    except OnlineOrderError as exc:
        flash(str(exc), "error")
    return redirect(url_for("online.order_detail", public_id=public_id))


@bp.get("/orders/<public_id>/repeat")
@customer_login_required
def repeat_order(public_id):
    order = owned_order(public_id)
    if not order:
        return jsonify(error="ไม่พบออเดอร์"), 404
    old_items = get_db().execute(
        "SELECT product_id,ordered_quantity,unit_price_satang FROM online_order_items WHERE order_id=?", (order["id"],)
    ).fetchall()
    available = {row["id"]: row for row in available_products()}
    cart, notices = [], []
    for old in old_items:
        current = available.get(old["product_id"])
        if not current or current["available_quantity"] <= 0:
            notices.append(f"นำสินค้ารหัส {old['product_id']} ออก เพราะไม่พร้อมขาย")
            continue
        quantity = min(old["ordered_quantity"], current["available_quantity"], current["online_max_quantity"] or old["ordered_quantity"])
        cart.append({"product_id": current["id"], "name_th": current["name_th"], "price_satang": current["price_satang"],
                     "quantity": quantity, "max": current["available_quantity"], "allow_decimal_quantity": current["allow_decimal_quantity"]})
        if current["price_satang"] != old["unit_price_satang"]:
            notices.append(f"{current['name_th']} ใช้ราคาปัจจุบัน")
    return jsonify(items=cart, notices=notices)
