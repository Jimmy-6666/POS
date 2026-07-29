import json
import sqlite3
import hmac
import secrets
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import iso_time, utc_now
from ..customer_auth import (
    CUSTOMER_COOKIE_NAME, create_customer_session, customer_login_required,
    delete_customer_cookie, normalize_phone, phone_fingerprint, set_customer_cookie,
    valid_customer_csrf,
)
from ..database import get_db
from ..product_identity import ProductIdentityError, canonical_product_uuid
from ..services.online_orders import (
    OnlineOrderError, audit_order, cancel_customer_order, create_order, expire_pending_orders,
)


bp = Blueprint("online", __name__, url_prefix="/order")


@bp.get("/policy")
def privacy_policy():
    return render_template("online/policy.html", embedded=request.args.get("embedded") == "1")


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


def negative_stock_allowed(settings=None):
    return (settings or online_settings()).get("online_allow_negative_stock") == "1"


def online_quantity_limit(row, settings):
    return float(row["online_max_quantity"] or Decimal(settings.get("online_max_order_quantity") or "50"))


def online_product_availability(rows, settings):
    if not negative_stock_allowed(settings):
        return rows
    return [{**dict(row), "available_quantity": online_quantity_limit(row, settings)} for row in rows]


def customer_product_payload(row, settings):
    """Return only the catalog data a customer needs; never stock or barcode data."""

    available = Decimal(str(row["available_quantity"]))
    return {
        "product_uuid": row["product_uuid"],
        "name_th": row["name_th"],
        "price_satang": row["price_satang"],
        "image_path": row["image_path"],
        "allow_decimal_quantity": bool(row["allow_decimal_quantity"]),
        "max_quantity": online_quantity_limit(row, settings),
        "is_available": negative_stock_allowed(settings) or available > 0,
    }


def customer_product_payloads(rows, settings):
    return [customer_product_payload(row, settings) for row in rows]


def safe_customer_next_url(value):
    parts = urlsplit(value or "")
    if parts.scheme or parts.netloc or not parts.path.startswith("/order"):
        return None
    return parts.path + (f"?{parts.query}" if parts.query else "")


def customer_repeat_products(customer_id, settings):
    rows = get_db().execute(
        """SELECT p.product_uuid,p.name_th,p.price_satang,p.image_path,p.allow_decimal_quantity,p.online_max_quantity,
                  MAX(0,p.stock_quantity-COALESCE((SELECT SUM(sr.quantity) FROM stock_reservations sr
                    WHERE sr.product_id=p.id AND sr.status='active'),0)) AS available_quantity
           FROM online_order_items oi JOIN online_orders o ON o.id=oi.order_id
           JOIN products p ON p.id=oi.product_id
           WHERE o.customer_id=? AND p.is_active=1 AND p.is_online_available=1
           GROUP BY p.id ORDER BY MAX(o.created_at) DESC LIMIT 8""",
        (customer_id,),
    ).fetchall()
    return online_product_availability(rows, settings)


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
    settings = online_settings()
    where = ["p.is_active=1", "p.is_online_available=1"]
    params = []
    if query:
        where.append("(p.name_th LIKE ? OR p.name_en LIKE ? OR p.barcode LIKE ?)")
        params.extend([f"%{query}%"] * 3)
    if category_id and not query:
        where.append("p.category_id=?")
        params.append(category_id)
    rows = get_db().execute(
        f"""SELECT p.product_uuid,p.name_th,p.barcode,p.price_satang,p.image_path,p.allow_decimal_quantity,
                   p.online_max_quantity,c.id AS category_id,c.name_th AS category_name,
                   MAX(0,p.stock_quantity-COALESCE((SELECT SUM(sr.quantity) FROM stock_reservations sr
                     WHERE sr.product_id=p.id AND sr.status='active'),0)) AS available_quantity
            FROM products p JOIN categories c ON c.id=p.category_id
            LEFT JOIN (
                SELECT product_id,SUM(quantity-voided_quantity) AS net_sold_quantity
                FROM sale_items GROUP BY product_id
            ) sales_totals ON sales_totals.product_id=p.id
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(sales_totals.net_sold_quantity,0) DESC,p.online_sort_order,p.name_th
            LIMIT 200""",
        params,
    ).fetchall()
    return online_product_availability(rows, settings)


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
            product_uuid = canonical_product_uuid(raw.get("product_uuid"))
            quantity = Decimal(str(raw.get("quantity")))
        except (ProductIdentityError, TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError("จำนวนสินค้าไม่ถูกต้อง") from exc
        if product_uuid in seen or quantity <= 0:
            raise ValueError("รายการสินค้าไม่ถูกต้อง")
        seen.add(product_uuid)
        row = get_db().execute(
            """SELECT p.*,MAX(0,p.stock_quantity-COALESCE((SELECT SUM(sr.quantity) FROM stock_reservations sr
                 WHERE sr.product_id=p.id AND sr.status='active'),0)) AS available_quantity
               FROM products p WHERE p.product_uuid=? AND p.is_active=1 AND p.is_online_available=1""",
            (product_uuid,),
        ).fetchone()
        if not row:
            raise ValueError("มีสินค้าที่ปิดขายออนไลน์ กรุณาตรวจสอบตะกร้าอีกครั้ง")
        if not row["allow_decimal_quantity"] and quantity != quantity.to_integral_value():
            raise ValueError(f"จำนวน {row['name_th']} ต้องเป็นจำนวนเต็ม")
        limit = Decimal(str(row["online_max_quantity"])) if row["online_max_quantity"] else None
        available = Decimal(str(row["available_quantity"]))
        if limit and quantity > limit:
            raise ValueError(f"{row['name_th']} สั่งได้สูงสุด {limit} ต่อออเดอร์")
        if not negative_stock_allowed(settings) and quantity > available:
            raise ValueError(f"{row['name_th']} มีสินค้าไม่เพียงพอ กรุณาลดจำนวนหรือเลือกสินค้าอื่น")
        total_quantity += quantity
        line_total = int(Decimal(row["price_satang"]) * quantity)
        validated.append({
            "product_id": row["id"], "barcode": row["barcode"], "product_uuid": row["product_uuid"], "name_th": row["name_th"],
            "image_path": row["image_path"], "quantity": float(quantity), "unit_price_satang": row["price_satang"],
            "line_total_satang": line_total, "max_quantity": online_quantity_limit(row, settings),
        })
    if total_quantity > max_total_quantity:
        raise ValueError(f"จำนวนสินค้ารวมต้องไม่เกิน {max_total_quantity}")
    return validated


@bp.route("/register", methods=("GET", "POST"))
def customer_register():
    return ("การสมัครด้วยเบอร์โทรศัพท์และ PIN ถูกยกเลิกแล้ว กรุณาเปิดผ่าน LINE", 410)

    # Historical implementation retained only until its removal in Sprint 2.
    if request.method == "POST":
        if not valid_public_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        try:
            phone = normalize_phone(request.form.get("phone"))
            registered_name = str(request.form.get("registered_name") or "").strip()[:120]
            if not registered_name:
                raise ValueError("กรุณาระบุชื่อสำหรับติดต่อ")
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
            set_customer_cookie(response, token)
            return response
        except Exception as exc:
            get_db().rollback()
            message = "ไม่สามารถสมัครสมาชิกได้ กรุณาตรวจสอบข้อมูลหรือติดต่อร้าน" if "UNIQUE constraint" in str(exc) else str(exc)
            flash(message, "error")
    return render_template("online/register.html", public_csrf=public_form_csrf())


@bp.route("/login", methods=("GET", "POST"))
def customer_login():
    return ("การเข้าสู่ระบบด้วยเบอร์โทรศัพท์และ PIN ถูกยกเลิกแล้ว กรุณาเปิดผ่าน LINE", 410)

    # Historical implementation retained only until its removal in Sprint 2.
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
            set_customer_cookie(response, token)
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
            set_customer_cookie(response, token)
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
    delete_customer_cookie(response)
    return response


@bp.route("/change-pin", methods=("GET", "POST"))
@customer_login_required
def customer_change_pin():
    return ("การเปลี่ยน PIN สำหรับการสั่งออนไลน์ถูกยกเลิกแล้ว", 410)

    # Historical implementation retained only until its removal in Sprint 2.
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
    query = request.args.get("q", "").strip()
    selected_category_id = None if query else request.args.get("category_id", type=int)
    products = customer_product_payloads(
        available_products(query, selected_category_id), settings
    )
    categories = get_db().execute(
        """SELECT DISTINCT c.id,c.name_th,c.sort_order FROM categories c JOIN products p ON p.category_id=c.id
           WHERE c.is_active=1 AND p.is_active=1 AND p.is_online_available=1
           ORDER BY c.sort_order,c.name_th"""
    ).fetchall()
    repeat_products = customer_product_payloads(customer_repeat_products(g.customer["id"], settings), settings) if g.customer and not g.customer["is_guest"] else []
    return render_template(
        "online/catalog.html", settings=settings, products=products, categories=categories,
        repeat_products=repeat_products, is_open=ordering_open(settings),
        allow_negative_stock=negative_stock_allowed(settings), query=query,
        selected_category_id=selected_category_id,
    )


@bp.get("/cart")
def cart():
    settings = online_settings()
    repeat_products = customer_product_payloads(customer_repeat_products(g.customer["id"], settings), settings) if g.customer and not g.customer["is_guest"] else []
    return render_template(
        "online/cart.html", repeat_products=repeat_products,
        settings=settings, is_open=ordering_open(settings),
        allow_negative_stock=negative_stock_allowed(settings),
    )


@bp.get("/products/<path:filename>")
def customer_product_image(filename):
    allowed = get_db().execute(
        "SELECT 1 FROM products WHERE image_path=? AND is_active=1 AND is_online_available=1", (filename,)
    ).fetchone()
    if not allowed:
        return ("ไม่พบรูปสินค้า", 404)
    return send_from_directory(current_app.config["RUNTIME_PATHS"].product_images, filename)


@bp.get("/api/products")
def customer_products_api():
    settings = online_settings()
    return jsonify(customer_product_payloads(
        available_products(request.args.get("q", "").strip(), request.args.get("category_id", type=int)), settings
    ))


@bp.post("/api/cart/validate")
def validate_cart_api():
    try:
        items = validate_cart((request.get_json(silent=True) or {}).get("items"))
        public_items = [
            {key: value for key, value in item.items() if key not in {"product_id", "barcode"}}
            for item in items
        ]
        return jsonify(items=public_items, subtotal_satang=sum(item["line_total_satang"] for item in items))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@bp.post("/api/account/lookup")
def checkout_account_lookup():
    return jsonify(error="การค้นหาบัญชีด้วยเบอร์โทรศัพท์ถูกยกเลิกแล้ว"), 410

    # Historical implementation retained only until its removal in Sprint 2.
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
    return jsonify(error="การเข้าสู่ระบบด้วย PIN ถูกยกเลิกแล้ว"), 410

    # Historical implementation retained only until its removal in Sprint 2.
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
    set_customer_cookie(response, token)
    return response


@bp.get("/checkout")
@customer_login_required
def checkout():
    settings = online_settings()
    locations = get_db().execute(
        "SELECT * FROM delivery_locations WHERE is_active=1 AND is_available=1 ORDER BY sort_order,name"
    ).fetchall()
    return render_template(
        "online/checkout.html", settings=settings, locations=locations,
        is_open=ordering_open(settings),
    )


@bp.get("/suspended")
def customer_suspended():
    return render_template("online/suspended.html"), 403


@bp.route("/profile", methods=("GET", "POST"))
@customer_login_required
def customer_profile():
    db = get_db()
    locations = db.execute(
        "SELECT * FROM delivery_locations WHERE is_active=1 AND is_available=1 ORDER BY sort_order,name"
    ).fetchall()
    requires_policy_acceptance = not bool(g.customer["profile_completed"])
    if request.method == "POST":
        if not valid_customer_csrf(request.form.get("csrf_token")):
            return ("คำขอไม่ถูกต้อง", 400)
        action = request.form.get("profile_action", "review")
        if action == "edit":
            session.pop("pending_customer_profile", None)
            return render_template("online/profile.html", locations=locations, form_values=request.form)
        try:
            if action == "review" and requires_policy_acceptance and request.form.get("policy_accepted") != "yes":
                raise ValueError("กรุณายอมรับเงื่อนไขการใช้งานและนโยบายความเป็นส่วนตัว (PDPA) ก่อนดำเนินการต่อ")
            phone = normalize_phone(request.form.get("phone"))
            registered_name = str(request.form.get("registered_name") or g.customer["registered_name"] or g.customer["line_display_name"] or g.customer["display_name"] or "").strip()[:120]
            if not registered_name:
                raise ValueError("กรุณาระบุชื่อสำหรับติดต่อ")
            location_id = int(request.form.get("delivery_location_id") or 0)
            room_reference = str(request.form.get("room_reference") or "").strip()[:200]
            location = db.execute(
                "SELECT * FROM delivery_locations WHERE id=? AND is_active=1 AND is_available=1", (location_id,)
            ).fetchone()
            if not location:
                raise ValueError("กรุณาเลือกสถานที่จัดส่ง")
            if location["room_required"] and not room_reference:
                raise ValueError("กรุณาระบุห้องหรือจุดรับ")
            if action == "review":
                pending_profile = {
                    "customer_id": g.customer["id"], "phone": phone,
                    "registered_name": registered_name,
                    "location_id": location_id, "location_name": location["name"],
                    "room_reference": room_reference,
                    "policy_accepted": not requires_policy_acceptance or request.form.get("policy_accepted") == "yes",
                }
                session["pending_customer_profile"] = pending_profile
                return render_template("online/profile.html", locations=locations, pending_profile=pending_profile)
            if action != "confirm":
                return ("คำขอไม่ถูกต้อง", 400)
            pending_profile = session.pop("pending_customer_profile", None)
            if not pending_profile or (
                pending_profile["customer_id"] != g.customer["id"]
                or pending_profile["phone"] != phone
                or pending_profile["registered_name"] != registered_name
                or pending_profile["location_id"] != location_id
                or pending_profile["room_reference"] != room_reference
                or (requires_policy_acceptance and not pending_profile.get("policy_accepted"))
            ):
                flash("กรุณาตรวจสอบเบอร์อีกครั้งก่อนยืนยัน", "error")
                return redirect(url_for("online.customer_profile"))
            db.execute(
                """UPDATE customers SET phone_normalized=?,registered_name=?,default_delivery_location_id=?,default_room_reference=?,
                   profile_completed=1,updated_at=? WHERE id=?""",
                (phone, registered_name, location_id, room_reference or None, iso_time(utc_now()), g.customer["id"]),
            )
            db.commit()
            return redirect(safe_customer_next_url(request.args.get("next")) or url_for("online.catalog"))
        except sqlite3.IntegrityError:
            db.rollback()
            flash("หมายเลขโทรศัพท์นี้ถูกใช้กับบัญชีลูกค้าอื่นแล้ว กรุณาใช้หมายเลขอื่นหรือติดต่อร้านค้า", "error")
        except (ValueError, TypeError) as exc:
            db.rollback()
            flash(str(exc), "error")
    return render_template("online/profile.html", locations=locations, form_values=request.form)


def owned_order(public_id):
    return get_db().execute(
        """SELECT o.*,dl.room_required,c.phone_normalized,c.display_name
           FROM online_orders o LEFT JOIN delivery_locations dl ON dl.id=o.delivery_location_id
           JOIN customers c ON c.id=o.customer_id
           WHERE o.public_id=? AND o.customer_id=?""",
        (public_id, g.customer["id"]),
    ).fetchone()


@bp.get("/api/delivery-history")
@customer_login_required
def delivery_history():
    rows = get_db().execute(
        """SELECT contact_name,contact_phone,delivery_location_id,location_name_snapshot,room_reference,MAX(created_at) AS last_used_at
           FROM online_orders WHERE customer_id=? GROUP BY contact_name,contact_phone,delivery_location_id,location_name_snapshot,room_reference
           ORDER BY last_used_at DESC LIMIT 5""",
        (g.customer["id"],),
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@bp.post("/api/orders")
def submit_order():
    if g.customer is None or not g.customer["line_user_id"]:
        return jsonify(error="กรุณายืนยันตัวตนผ่าน LINE ก่อนสั่งซื้อ"), 401
    if not g.customer["profile_completed"]:
        return jsonify(error="กรุณากรอกข้อมูลการจัดส่งให้ครบก่อนสั่งซื้อ"), 403
    if not valid_customer_csrf(request.headers.get("X-CSRF-Token")):
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
        payload["contact_phone"] = normalize_phone(
            payload.get("contact_phone") or g.customer["phone_normalized"]
        )
        payload["contact_name"] = str(
            payload.get("contact_name")
            or g.customer["registered_name"]
            or g.customer["line_display_name"]
            or g.customer["display_name"]
            or ""
        ).strip()[:120]
        if not payload["contact_name"]:
            raise ValueError("กรุณาระบุชื่อสำหรับติดต่อ")
        result, duplicate = create_order(g.customer["id"], payload, validate_cart, settings, location)
        response = jsonify(public_id=result["public_id"], order_number=result["order_number"], duplicate=duplicate,
                           detail_url=url_for("online.order_detail", public_id=result["public_id"]))
        return response
    except (OnlineOrderError, ValueError) as exc:
        return jsonify(error=str(exc)), 400


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
    return render_template("online/order_detail.html", order=order, items=items, history=history, settings=online_settings())


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
        """SELECT p.product_uuid,oi.ordered_quantity,oi.unit_price_satang
           FROM online_order_items oi JOIN products p ON p.id=oi.product_id WHERE oi.order_id=?""", (order["id"],)
    ).fetchall()
    settings = online_settings()
    available = {
        row["product_uuid"]: row for row in customer_product_payloads(available_products(), settings)
    }
    cart, notices = [], []
    for old in old_items:
        current = available.get(old["product_uuid"])
        if not current or not current["is_available"]:
            notices.append("นำสินค้าที่ไม่พร้อมขายออกจากตะกร้าแล้ว")
            continue
        quantity = min(old["ordered_quantity"], current["max_quantity"])
        cart.append({"product_uuid": current["product_uuid"], "name_th": current["name_th"], "price_satang": current["price_satang"],
                     "quantity": quantity, "max": current["max_quantity"], "allow_decimal_quantity": current["allow_decimal_quantity"]})
        if current["price_satang"] != old["unit_price_satang"]:
            notices.append(f"{current['name_th']} ใช้ราคาปัจจุบัน")
    return jsonify(items=cart, notices=notices)
