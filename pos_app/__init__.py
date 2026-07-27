import json
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
from .routes.maintenance import bp as maintenance_bp
from .services.print_jobs import init_app as init_print_jobs
from .runtime_paths import RuntimePathError, RuntimePaths, load_runtime_config, validate_runtime


def _effective_app_version(runtime_config):
    """Use the validated active release version when one is selected."""
    active_file = runtime_config.paths.releases / "active-release.json"
    try:
        active = json.loads(active_file.read_text(encoding="utf-8"))
        version = str(active.get("version", ""))
        manifest = json.loads((runtime_config.paths.releases / version / "manifest.json").read_text(encoding="utf-8"))
        return str(manifest.get("application_version") or runtime_config.app_version)
    except (OSError, ValueError, json.JSONDecodeError):
        return runtime_config.app_version


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
        )
    runtime_paths.create_directories()
    runtime_paths.ensure_secret_key()
    app = Flask(__name__, instance_relative_config=False)
    effective_app_version = _effective_app_version(runtime_config)
    app.config.from_mapping(
        DATABASE=str(runtime_paths.database),
        PROJECT_ROOT=str(runtime_paths.root),
        RUNTIME_PATHS=runtime_paths,
        RUNTIME_CONFIG=runtime_config,
        SECRET_KEY=runtime_paths.secret_key.read_text(encoding="ascii").strip(),
        POS_BIND_HOST=runtime_config.host,
        POS_PORT=runtime_config.port,
        POS_APP_VERSION=effective_app_version,
        POS_BACKUP_RETENTION=int(os.environ.get("POS_BACKUP_RETENTION", "7")),
        SESSION_TIMEOUT_MINUTES=30,
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        CUSTOMER_SESSION_DAYS=14,
        PRINT_AGENT_TOKEN=os.environ.get("POS_PRINT_AGENT_TOKEN", ""),
        POS_STARTED_AT=datetime.now(timezone.utc).isoformat(),
    )
    if test_config:
        app.config.update(test_config)

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
