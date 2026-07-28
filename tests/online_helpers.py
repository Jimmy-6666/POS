import re
import secrets
from datetime import timedelta

from pos_app.auth import iso_time, token_hash, utc_now
from pos_app.customer_auth import CUSTOMER_COOKIE_NAME
from pos_app.database import get_db


def form_csrf(client, path):
    html = client.get(path).get_data(as_text=True)
    matches = re.findall(r'name="csrf_token" value="([^"]+)"', html)
    if not matches:
        raise AssertionError(f"missing csrf token on {path}")
    return matches[-1]


def register_customer(client, phone="0812345678", pin="2468", **extra):
    """Create a verified LINE customer fixture without exercising retired PIN routes."""
    app = client.application
    now = utc_now()
    token = secrets.token_urlsafe(32)
    line_user_id = extra.get("line_user_id") or f"U{secrets.token_hex(16)}"
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            """INSERT INTO customers
               (public_id,phone_normalized,display_name,pin_hash,is_guest,line_user_id,line_display_name,
                line_created_at,line_last_login_at,profile_completed,created_at,last_login_at,updated_at)
               VALUES(?,?,?,?,0,?,?,?,?,1,?,?,?)""",
            (
                secrets.token_urlsafe(12), phone, extra.get("display_name", "ลูกค้า LINE"), "retired-pin",
                line_user_id, extra.get("display_name", "ลูกค้า LINE"), iso_time(now), iso_time(now),
                iso_time(now), iso_time(now), iso_time(now),
            ),
        )
        customer_id = cursor.lastrowid
        db.execute(
            """INSERT INTO customer_sessions
               (customer_id,token_hash,csrf_token,ip_address,user_agent,created_at,last_seen_at,expires_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (customer_id, token_hash(token), secrets.token_urlsafe(24), "127.0.0.1", "test",
             iso_time(now), iso_time(now), iso_time(now + timedelta(days=14))),
        )
        db.commit()
    client.set_cookie(CUSTOMER_COOKIE_NAME, token)
    return client.get("/api/auth/me")


def login_customer(client, phone="0812345678", pin="2468"):
    return client.post("/order/login", data={"phone": phone, "pin": pin, "action": "login"})
