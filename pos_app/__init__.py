import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .database import init_app
from .auth import init_app as init_auth
from .customer_auth import init_app as init_customer_auth
from .public_host_access import init_app as init_public_host_access, normalize_public_host
from .web_security import init_app as init_web_security
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
from .routes.line_auth import bp as line_auth_bp
from .routes.maintenance import bp as maintenance_bp
from .services.print_jobs import init_app as init_print_jobs
from .services.backup_scheduler import init_app as init_backup_scheduler
from .runtime_paths import RuntimePathError, RuntimePaths, load_runtime_config, validate_runtime


def create_app(test_config=None):
    project_root = Path(__file__).resolve().parent.parent
    runtime_config = load_runtime_config(project_root)
    runtime_paths = runtime_config.paths
    if test_config and "POS_RUNTIME_ROOT" not in os.environ:
        configured_root = test_config.get("PROJECT_ROOT")
        configured_database = test_config.get("DATABASE")
        if configured_root:
            runtime_paths = RuntimePaths.from_root(configured_root)
        elif configured_database:
            runtime_paths = RuntimePaths.from_root(Path(configured_database).parent)
        if configured_database:
            runtime_paths = runtime_paths.with_database(configured_database)
        runtime_config = runtime_config.__class__(
            paths=runtime_paths,
            host=runtime_config.host,
            port=runtime_config.port,
            min_free_space_mb=runtime_config.min_free_space_mb,
            store_id=runtime_config.store_id,
            app_version=runtime_config.app_version,
            production=runtime_config.production,
            config_file=runtime_config.config_file,
            update_signer_thumbprint=runtime_config.update_signer_thumbprint,
        )
    runtime_paths.create_directories()
    runtime_paths.ensure_secret_key()
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_mapping(
        DATABASE=str(runtime_paths.database),
        PROJECT_ROOT=str(runtime_paths.root),
        RUNTIME_PATHS=runtime_paths,
        RUNTIME_CONFIG=runtime_config,
        SECRET_KEY=runtime_paths.secret_key.read_text(encoding="ascii").strip(),
        POS_BIND_HOST=runtime_config.host,
        POS_PORT=runtime_config.port,
        POS_APP_VERSION=runtime_config.app_version,
        POS_INSTALL_ROOT=str(project_root),
        POS_BACKUP_RETENTION=int(os.environ.get("POS_BACKUP_RETENTION", "7")),
        BACKUP_SCHEDULER_ENABLED=os.environ.get("POS_BACKUP_SCHEDULER_ENABLED", "1").lower() not in {"0", "false", "no"},
        SESSION_TIMEOUT_MINUTES=30,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        CUSTOMER_SESSION_DAYS=14,
        PRINT_AGENT_TOKEN=os.environ.get("POS_PRINT_AGENT_TOKEN", ""),
        POS_TRUST_PROXY=os.environ.get("POS_TRUST_PROXY", "").lower() in {"1", "true", "yes"},
        POS_PUBLIC_ORDER_HOST=normalize_public_host(os.environ.get("POS_PUBLIC_ORDER_HOST")),
        POS_ADMIN_HOST=normalize_public_host(os.environ.get("POS_ADMIN_HOST")),
        POS_TRUSTED_HOSTS=os.environ.get("POS_TRUSTED_HOSTS", ""),
        LINE_LIFF_ID=os.environ.get("LINE_LIFF_ID", "").strip(),
        LINE_LOGIN_CHANNEL_ID=os.environ.get("LINE_LOGIN_CHANNEL_ID", "").strip(),
        LINE_LOGIN_CHANNEL_SECRET=os.environ.get("LINE_LOGIN_CHANNEL_SECRET", ""),
        LINE_LOGIN_FAILURE_LIMIT=int(os.environ.get("LINE_LOGIN_FAILURE_LIMIT", "12")),
        LINE_LOGIN_FAILURE_WINDOW_MINUTES=int(os.environ.get("LINE_LOGIN_FAILURE_WINDOW_MINUTES", "5")),
        APP_BASE_URL=os.environ.get("APP_BASE_URL", "").rstrip("/"),
        POS_UPDATE_SIGNER_THUMBPRINT=os.environ.get("POS_UPDATE_SIGNER_THUMBPRINT", runtime_config.update_signer_thumbprint).strip(),
        POS_UPDATE_POWERSHELL=os.environ.get("POS_UPDATE_POWERSHELL", "powershell.exe").strip(),
    )
    if test_config:
        app.config.update(test_config)
    app.config["POS_PUBLIC_ORDER_HOST"] = normalize_public_host(app.config["POS_PUBLIC_ORDER_HOST"])
    app.config["POS_ADMIN_HOST"] = normalize_public_host(app.config["POS_ADMIN_HOST"])
    if app.config["POS_PUBLIC_ORDER_HOST"] and app.config["POS_PUBLIC_ORDER_HOST"] == app.config["POS_ADMIN_HOST"]:
        raise RuntimeError("POS_PUBLIC_ORDER_HOST and POS_ADMIN_HOST must be different hostnames.")
    trusted_hosts = [host.strip().lower().rstrip(".") for host in str(app.config["POS_TRUSTED_HOSTS"] or "").split(",") if host.strip()]
    public_hosts = {host for host in (app.config["POS_PUBLIC_ORDER_HOST"], app.config["POS_ADMIN_HOST"]) if host}
    if not app.config.get("TESTING") and public_hosts:
        if not trusted_hosts:
            raise RuntimeError("POS_TRUSTED_HOSTS must be configured before public host isolation is enabled.")
        if not public_hosts.issubset(set(trusted_hosts)):
            raise RuntimeError("POS_TRUSTED_HOSTS must include every configured public hostname.")
    if trusted_hosts:
        app.config["TRUSTED_HOSTS"] = trusted_hosts
    if app.config["POS_TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    init_app(app)
    try:
        validation = validate_runtime(runtime_config, database_required=True)
    except RuntimePathError as exc:
        raise RuntimeError(f"Invalid POS runtime configuration: {exc}") from exc
    if not validation["ok"]:
        raise RuntimeError("POS runtime validation failed: " + "; ".join(validation["fatal"]))
    app.config["RUNTIME_VALIDATION"] = validation
    init_auth(app)
    init_customer_auth(app)
    init_public_host_access(app)
    init_web_security(app)
    init_print_jobs(app)
    if not app.config.get("TESTING"):
        init_backup_scheduler(app)
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
    app.register_blueprint(line_auth_bp)
    app.register_blueprint(maintenance_bp)

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
