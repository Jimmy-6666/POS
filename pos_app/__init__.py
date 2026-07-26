import secrets
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask

from .database import init_app
from .auth import init_app as init_auth
from .customer_auth import init_app as init_customer_auth
from .routes.auth import bp as auth_bp
from .routes.products import bp as products_bp
from .routes.pos import bp as pos_bp
from .routes.inventory import bp as inventory_bp
from .routes.stock_count import bp as stock_count_bp
from .routes.reporting import bp as reporting_bp
from .routes.admin import bp as admin_bp
from .routes.main import bp as main_bp
from .routes.online import bp as online_bp
from .routes.online_admin import bp as online_admin_bp
from .routes.online_staff import bp as online_staff_bp
from .routes.print_agent import bp as print_agent_bp
from .services.print_jobs import init_app as init_print_jobs


def create_app(test_config=None):
    project_root = Path(__file__).resolve().parent.parent
    runtime_root = Path(os.environ.get("POS_RUNTIME_ROOT", project_root)).resolve()
    secret_path = runtime_root / "data" / ".secret_key"
    if not secret_path.exists():
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(secrets.token_hex(32), encoding="ascii")
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_mapping(
        DATABASE=str(runtime_root / "data" / "pos.db"),
        PROJECT_ROOT=str(runtime_root),
        SECRET_KEY=secret_path.read_text(encoding="ascii").strip(),
        SESSION_TIMEOUT_MINUTES=30,
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        CUSTOMER_SESSION_DAYS=14,
        PRINT_AGENT_TOKEN=os.environ.get("POS_PRINT_AGENT_TOKEN", ""),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    (runtime_root / "backups").mkdir(parents=True, exist_ok=True)
    (runtime_root / "uploads" / "products").mkdir(parents=True, exist_ok=True)
    (runtime_root / "uploads" / "online-payments").mkdir(parents=True, exist_ok=True)

    init_app(app)
    init_auth(app)
    init_customer_auth(app)
    init_print_jobs(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(stock_count_bp)
    app.register_blueprint(reporting_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(online_bp)
    app.register_blueprint(online_admin_bp)
    app.register_blueprint(online_staff_bp)
    app.register_blueprint(print_agent_bp)

    @app.context_processor
    def auth_context():
        from flask import g
        session_row = getattr(g, "session_row", None)
        return {
            "current_staff": getattr(g, "staff", None),
            "csrf_token": session_row["csrf_token"] if session_row else "",
        }

    @app.template_filter("thai_datetime")
    def thai_datetime(value):
        if not value:
            return ""
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")

    @app.template_filter("online_status")
    def online_status(value):
        return {
            "submitted": "รอร้านตรวจสอบ", "accepted": "ร้านรับออเดอร์แล้ว",
            "preparing": "กำลังจัดสินค้า", "reconciling": "รอตรวจสินค้า",
            "ready": "พร้อมจัดส่ง", "delivering": "กำลังจัดส่ง",
            "completed": "ส่งสำเร็จ", "customer_cancelled": "ลูกค้ายกเลิก",
            "staff_cancelled": "ร้านยกเลิก", "rejected": "ร้านปฏิเสธ", "expired": "หมดอายุ",
        }.get(value, value)

    @app.template_filter("online_payment_status")
    def online_payment_status(value):
        return {
            "unpaid": "ยังไม่ชำระ", "awaiting_verification": "รอตรวจสอบการชำระเงิน",
            "confirmed": "ยืนยันการชำระเงินแล้ว", "rejected": "สลิปถูกปฏิเสธ",
            "refund_pending": "รอดำเนินการคืนเงิน", "refunded": "คืนเงินแล้ว",
        }.get(value, value)

    return app
