import sqlite3
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash


CATEGORIES = [
    "เครื่องดื่ม", "ขนมขบเคี้ยว", "บะหมี่กึ่งสำเร็จรูป", "อาหารแห้ง",
    "อาหารกระป๋อง", "นมและผลิตภัณฑ์นม", "ของแช่เย็น", "ของแช่แข็ง",
    "เบเกอรี่", "เครื่องปรุงรส", "ของใช้ส่วนตัว", "ของใช้ในบ้าน",
    "ผลิตภัณฑ์ซักล้าง", "เครื่องเขียน", "ยาและเวชภัณฑ์ทั่วไป", "บุหรี่", "อื่น ๆ",
]
UNITS = [
    "ชิ้น", "ขวด", "กระป๋อง", "ถุง", "ซอง", "กล่อง", "แพ็ก", "ลัง",
    "กิโลกรัม", "กรัม", "ลิตร", "มิลลิลิตร",
]
ADJUSTMENT_REASONS = [
    "สินค้าเสียหาย", "สินค้าหมดอายุ", "สินค้าสูญหาย", "ใช้ภายในร้าน",
    "จำนวนไม่ตรง", "แก้ไขยอดยกมา", "อื่น ๆ",
]
PAYMENT_METHODS = ["เงินสด", "สแกนจ่าย", "โอนเงิน"]

ROLES = {
    "admin": "ผู้ดูแลระบบ",
    "manager": "ผู้จัดการ",
    "cashier": "แคชเชียร์",
}
PERMISSIONS = {
    "pos.use": "ขายสินค้า",
    "inventory.manage": "จัดการสต็อก",
    "stock_count.manage": "จัดการรอบนับสต็อก",
    "stock_count.participate": "เข้าร่วมการนับสต็อก",
    "reports.view": "ดูรายงาน",
    "reconciliation.manage": "ปิดยอด",
    "sales.approve": "อนุมัติยกเลิกและคืนสินค้า",
    "products.manage": "จัดการสินค้า",
    "staff.manage": "จัดการพนักงาน",
    "settings.manage": "ตั้งค่าระบบ",
    "audit.view": "ดูประวัติการใช้งาน",
    "backup.manage": "สำรองข้อมูล",
    "online_orders.view": "ดูออเดอร์ออนไลน์",
    "online_orders.accept": "รับหรือปฏิเสธออเดอร์ออนไลน์",
    "online_orders.prepare": "จัดสินค้าออเดอร์ออนไลน์",
    "online_orders.reconcile": "ตรวจสอบสินค้าออเดอร์ออนไลน์",
    "online_orders.verify_payment": "ตรวจสอบการโอนเงินออนไลน์",
    "online_orders.assign": "มอบหมายผู้จัดส่ง",
    "online_orders.deliver": "จัดส่งและรับเงินสด",
    "online_orders.cancel": "ยกเลิกออเดอร์ออนไลน์",
    "online_customers.manage": "จัดการบัญชีลูกค้าออนไลน์",
    "online_settings.manage": "จัดการการสั่งซื้อและสถานที่จัดส่ง",
}
ROLE_PERMISSIONS = {
    "admin": set(PERMISSIONS),
    "manager": {"pos.use", "inventory.manage", "stock_count.manage", "stock_count.participate", "reports.view", "reconciliation.manage", "sales.approve", "products.manage",
                "online_orders.view", "online_orders.accept", "online_orders.prepare", "online_orders.reconcile", "online_orders.verify_payment",
                "online_orders.assign", "online_orders.deliver", "online_orders.cancel", "online_customers.manage", "online_settings.manage"},
    "cashier": {"pos.use", "stock_count.participate", "reconciliation.manage", "online_orders.view", "online_orders.accept",
                "online_orders.prepare", "online_orders.reconcile", "online_orders.assign", "online_orders.deliver"},
}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def initialize_database():
    db = get_db()
    schema_path = Path(__file__).with_name("schema.sql")
    db.executescript(schema_path.read_text(encoding="utf-8"))
    for table, values in (
        ("categories", CATEGORIES),
        ("units", UNITS),
        ("adjustment_reasons", ADJUSTMENT_REASONS),
        ("payment_methods", PAYMENT_METHODS),
    ):
        db.executemany(
            f"INSERT OR IGNORE INTO {table} (name_th) VALUES (?)",
            ((value,) for value in values),
        )
    defaults = {
        "store_name": "แสนงาม มินิมาร์ท",
        "timezone": "Asia/Bangkok",
        "currency": "THB",
        "allow_negative_stock": "0",
        "receipt_prefix": "POS",
        "schema_version": "1",
        "online_ordering_enabled": "0",
        "online_closed_message": "ขณะนี้ร้านปิดรับออเดอร์ออนไลน์ กรุณาติดต่อร้าน",
        "online_minimum_order_satang": "0",
        "online_order_expiry_minutes": "60",
        "online_auto_expiry": "1",
        "online_max_order_quantity": "50",
        "online_ordering_start": "",
        "online_ordering_end": "",
        "online_contact": "",
        "online_contact_line": "@114rbvoi",
        "online_contact_phone": "09X-XXX-XXXX",
        "online_bank_name": "",
        "online_bank_account_name": "",
        "online_bank_account_number": "",
        "online_bank_instructions": "",
        "online_bank_qr_path": "",
        "online_bank_account_id": "",
        "online_transfer_enabled": "0",
        "all_products_online_migrated": "0",
    }
    db.executemany(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        defaults.items(),
    )
    current_schema = int(db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0])
    product_columns={row[1] for row in db.execute("PRAGMA table_info(products)").fetchall()}
    if "is_online_available" not in product_columns:
        db.execute("ALTER TABLE products ADD COLUMN is_online_available INTEGER NOT NULL DEFAULT 1 CHECK(is_online_available IN (0,1))")
    if "online_sort_order" not in product_columns:
        db.execute("ALTER TABLE products ADD COLUMN online_sort_order INTEGER NOT NULL DEFAULT 0")
    if "online_max_quantity" not in product_columns:
        db.execute("ALTER TABLE products ADD COLUMN online_max_quantity REAL")
    if db.execute("SELECT value FROM settings WHERE key='all_products_online_migrated'").fetchone()[0] != "1":
        db.execute("UPDATE products SET is_online_available=1,updated_at=CURRENT_TIMESTAMP")
        db.execute("UPDATE settings SET value='1',updated_at=CURRENT_TIMESTAMP WHERE key='all_products_online_migrated'")
    if db.execute("SELECT COUNT(*) FROM online_bank_accounts").fetchone()[0] == 0:
        legacy = dict(db.execute(
            """SELECT key,value FROM settings WHERE key IN
               ('online_bank_name','online_bank_account_name','online_bank_account_number',
                'online_bank_instructions','online_bank_qr_path')"""
        ).fetchall())
        if legacy.get("online_bank_name") or legacy.get("online_bank_account_number"):
            cursor = db.execute(
                """INSERT INTO online_bank_accounts
                   (label,bank_name,account_name,account_number,instructions,qr_path)
                   VALUES(?,?,?,?,?,?)""",
                (
                    legacy.get("online_bank_name") or "บัญชีเดิม",
                    legacy.get("online_bank_name") or "",
                    legacy.get("online_bank_account_name") or "",
                    legacy.get("online_bank_account_number") or "",
                    legacy.get("online_bank_instructions") or None,
                    legacy.get("online_bank_qr_path") or None,
                ),
            )
            db.execute(
                "UPDATE settings SET value=?,updated_at=CURRENT_TIMESTAMP WHERE key='online_bank_account_id'",
                (str(cursor.lastrowid),),
            )
    online_item_columns={row[1] for row in db.execute("PRAGMA table_info(online_order_items)").fetchall()}
    if online_item_columns and "is_removed" not in online_item_columns:
        db.execute("ALTER TABLE online_order_items ADD COLUMN is_removed INTEGER NOT NULL DEFAULT 0 CHECK(is_removed IN (0,1))")
    if online_item_columns and "customer_confirmed_unit_price_satang" not in online_item_columns:
        db.execute("ALTER TABLE online_order_items ADD COLUMN customer_confirmed_unit_price_satang INTEGER")
        db.execute(
            """UPDATE online_order_items SET customer_confirmed_unit_price_satang=unit_price_satang
               WHERE customer_confirmed_unit_price_satang IS NULL"""
        )
    customer_columns={row[1] for row in db.execute("PRAGMA table_info(customers)").fetchall()}
    if "is_guest" not in customer_columns:
        db.execute("ALTER TABLE customers ADD COLUMN is_guest INTEGER NOT NULL DEFAULT 0 CHECK(is_guest IN (0,1))")
    online_order_columns={row[1] for row in db.execute("PRAGMA table_info(online_orders)").fetchall()}
    if online_order_columns and "contact_phone" not in online_order_columns:
        db.execute("ALTER TABLE online_orders ADD COLUMN contact_phone TEXT")
    if online_order_columns and "contact_name" not in online_order_columns:
        db.execute("ALTER TABLE online_orders ADD COLUMN contact_name TEXT")
    reconciliation_columns={row[1] for row in db.execute("PRAGMA table_info(reconciliations)").fetchall()}
    if "billed_sales_satang" not in reconciliation_columns:
        db.execute("ALTER TABLE reconciliations ADD COLUMN billed_sales_satang INTEGER NOT NULL DEFAULT 0")
    if "verified_by" not in reconciliation_columns:
        db.execute("ALTER TABLE reconciliations ADD COLUMN verified_by INTEGER REFERENCES staff(id) ON DELETE RESTRICT")
        db.execute("ALTER TABLE reconciliations ADD COLUMN verified_at TEXT")
        db.execute("ALTER TABLE reconciliations ADD COLUMN verification_note TEXT")
    reconciliation_sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='reconciliations'").fetchone()[0]
    if "UNIQUE(cashier_id,business_date)" in reconciliation_sql.replace(" ", ""):
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("ALTER TABLE reconciliations RENAME TO reconciliations_legacy")
        db.execute("""CREATE TABLE reconciliations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cashier_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
            business_date TEXT NOT NULL, opening_float_satang INTEGER NOT NULL DEFAULT 0,
            cash_sales_satang INTEGER NOT NULL DEFAULT 0, scan_sales_satang INTEGER NOT NULL DEFAULT 0,
            transfer_sales_satang INTEGER NOT NULL DEFAULT 0, billed_sales_satang INTEGER NOT NULL DEFAULT 0,
            cash_refunds_satang INTEGER NOT NULL DEFAULT 0, cash_removals_satang INTEGER NOT NULL DEFAULT 0,
            cash_additions_satang INTEGER NOT NULL DEFAULT 0, expected_cash_satang INTEGER NOT NULL,
            actual_cash_satang INTEGER NOT NULL, difference_satang INTEGER NOT NULL, note TEXT,
            closed_by INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
            verified_by INTEGER REFERENCES staff(id) ON DELETE RESTRICT, verified_at TEXT,
            verification_note TEXT, created_at TEXT NOT NULL)""")
        legacy_columns={row[1] for row in db.execute("PRAGMA table_info(reconciliations_legacy)").fetchall()}
        billed_expr="billed_sales_satang" if "billed_sales_satang" in legacy_columns else "0"
        db.execute(f"""INSERT INTO reconciliations(id,cashier_id,business_date,opening_float_satang,cash_sales_satang,
            scan_sales_satang,transfer_sales_satang,billed_sales_satang,cash_refunds_satang,cash_removals_satang,
            cash_additions_satang,expected_cash_satang,actual_cash_satang,difference_satang,note,closed_by,
            verified_by,verified_at,verification_note,created_at)
            SELECT id,cashier_id,business_date,opening_float_satang,cash_sales_satang,scan_sales_satang,
            transfer_sales_satang,{billed_expr},cash_refunds_satang,cash_removals_satang,cash_additions_satang,
            expected_cash_satang,actual_cash_satang,difference_satang,note,closed_by,verified_by,verified_at,
            verification_note,created_at FROM reconciliations_legacy""")
        db.execute("DROP TABLE reconciliations_legacy")
        db.execute("PRAGMA foreign_keys=ON")
    sale_item_columns={row[1] for row in db.execute("PRAGMA table_info(sale_items)").fetchall()}
    if "voided_quantity" not in sale_item_columns:
        db.execute("ALTER TABLE sale_items ADD COLUMN voided_quantity REAL NOT NULL DEFAULT 0")
    sale_columns={row[1] for row in db.execute("PRAGMA table_info(sales)").fetchall()}
    if "delivery_fee_satang" not in sale_columns:
        db.execute("ALTER TABLE sales ADD COLUMN delivery_fee_satang INTEGER NOT NULL DEFAULT 0")
        sale_columns.add("delivery_fee_satang")
    added_settlement_flag=False
    if "settled_reconciliation_id" not in sale_columns:
        db.execute("ALTER TABLE sales ADD COLUMN settled_reconciliation_id INTEGER REFERENCES reconciliations(id) ON DELETE RESTRICT")
        added_settlement_flag=True
    if "settled_at" not in sale_columns:
        db.execute("ALTER TABLE sales ADD COLUMN settled_at TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS idx_sales_unsettled_cashier ON sales(cashier_id,settled_reconciliation_id,created_at)")
    if added_settlement_flag:
        db.execute("""UPDATE sales SET
            settled_reconciliation_id=(SELECT r.id FROM reconciliations r WHERE r.cashier_id=sales.cashier_id AND r.created_at>=sales.created_at ORDER BY r.created_at,r.id LIMIT 1),
            settled_at=(SELECT r.created_at FROM reconciliations r WHERE r.cashier_id=sales.cashier_id AND r.created_at>=sales.created_at ORDER BY r.created_at,r.id LIMIT 1)
            WHERE status='completed' AND EXISTS(SELECT 1 FROM reconciliations r WHERE r.cashier_id=sales.cashier_id AND r.created_at>=sales.created_at)""")
    if current_schema < 7:
        db.execute(
            "UPDATE settings SET value='แสนงาม มินิมาร์ท', updated_at=CURRENT_TIMESTAMP WHERE key='store_name'"
        )
    db.executemany(
        "INSERT OR IGNORE INTO roles (code, name_th) VALUES (?, ?)",
        ROLES.items(),
    )
    db.executemany(
        "INSERT OR IGNORE INTO permissions (code, name_th) VALUES (?, ?)",
        PERMISSIONS.items(),
    )
    for code, name in (("cash", "เงินสด"), ("scan", "สแกนจ่าย"), ("transfer", "โอนเงิน")):
        db.execute("UPDATE payment_methods SET code = ? WHERE name_th = ?", (code, name))
    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        role_id = db.execute("SELECT id FROM roles WHERE code = ?", (role_code,)).fetchone()[0]
        db.executemany(
            """INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
               SELECT ?, id FROM permissions WHERE code = ?""",
            ((role_id, code) for code in permission_codes),
        )
    admin_role_id = db.execute("SELECT id FROM roles WHERE code = 'admin'").fetchone()[0]
    if db.execute("SELECT COUNT(*) FROM staff").fetchone()[0] == 0:
        db.execute(
            """INSERT INTO staff (display_name, pin_hash, role_id, must_change_pin)
               VALUES (?, ?, ?, 1)""",
            ("ผู้ดูแลระบบ", generate_password_hash("1234"), admin_role_id),
        )
    db.execute(
        "UPDATE settings SET value = '19', updated_at = CURRENT_TIMESTAMP WHERE key = 'schema_version'"
    )
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        initialize_database()
