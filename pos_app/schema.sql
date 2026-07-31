CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_th TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_th TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS adjustment_reasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_th TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payment_methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_th TEXT NOT NULL UNIQUE,
    code TEXT UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT,
    application_version TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 1 CHECK(success IN (0,1))
);

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name_th TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name_th TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    pin_hash TEXT NOT NULL,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    must_change_pin INTEGER NOT NULL DEFAULT 1 CHECK (must_change_pin IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staff_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    two_factor_verified_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_staff_sessions_token ON staff_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_staff_sessions_expiry ON staff_sessions(expires_at);

CREATE TABLE IF NOT EXISTS staff_two_factor (
    staff_id INTEGER PRIMARY KEY REFERENCES staff(id) ON DELETE CASCADE,
    secret_encrypted TEXT,
    pending_secret_encrypted TEXT,
    is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0,1)),
    last_totp_counter INTEGER,
    enabled_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((is_enabled=0) OR secret_encrypted IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS staff_two_factor_recovery_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    used_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_staff_two_factor_recovery_codes_staff
ON staff_two_factor_recovery_codes(staff_id,used_at);

CREATE TABLE IF NOT EXISTS staff_two_factor_challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    next_url TEXT,
    ip_address TEXT,
    user_agent TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_staff_two_factor_challenges_expiry
ON staff_two_factor_challenges(expires_at);

CREATE TABLE IF NOT EXISTS login_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('login_success', 'login_failed', 'logout', 'session_expired')),
    ip_address TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    old_value TEXT,
    new_value TEXT,
    ip_address TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_uuid TEXT NOT NULL UNIQUE DEFAULT (
        lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' ||
        substr(lower(hex(randomblob(2))), 2, 3) || '-' ||
        substr('89ab', abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))), 2, 3) || '-' ||
        lower(hex(randomblob(6)))
    ),
    barcode TEXT NOT NULL UNIQUE,
    sku TEXT UNIQUE,
    name_th TEXT NOT NULL,
    name_en TEXT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE RESTRICT,
    cost_satang INTEGER NOT NULL DEFAULT 0 CHECK (cost_satang >= 0),
    price_satang INTEGER NOT NULL DEFAULT 0 CHECK (price_satang >= 0),
    stock_quantity REAL NOT NULL DEFAULT 0,
    minimum_stock REAL NOT NULL DEFAULT 0 CHECK (minimum_stock >= 0),
    image_path TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    is_favorite INTEGER NOT NULL DEFAULT 0 CHECK (is_favorite IN (0, 1)),
    allow_decimal_quantity INTEGER NOT NULL DEFAULT 0 CHECK (allow_decimal_quantity IN (0, 1)),
    is_online_available INTEGER NOT NULL DEFAULT 1 CHECK (is_online_available IN (0, 1)),
    online_sort_order INTEGER NOT NULL DEFAULT 0,
    online_max_quantity REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_products_name_th ON products(name_th);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);

CREATE TABLE IF NOT EXISTS pos_button_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_th TEXT NOT NULL CHECK(length(trim(name_th)) BETWEEN 1 AND 80),
    position INTEGER NOT NULL UNIQUE CHECK(position >= 1),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_by INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    updated_by INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pos_button_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES pos_button_groups(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL CHECK(position >= 1),
    created_by INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    updated_by INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, position),
    UNIQUE(group_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_pos_button_groups_active_position
ON pos_button_groups(is_active, position);
CREATE INDEX IF NOT EXISTS idx_pos_button_items_group_position
ON pos_button_items(group_id, position);
CREATE INDEX IF NOT EXISTS idx_pos_button_items_product
ON pos_button_items(product_id);

CREATE TABLE IF NOT EXISTS receipt_sequences (
    sale_date TEXT PRIMARY KEY,
    last_number INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_number TEXT NOT NULL UNIQUE,
    cashier_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    subtotal_satang INTEGER NOT NULL,
    item_discount_satang INTEGER NOT NULL DEFAULT 0,
    bill_discount_satang INTEGER NOT NULL DEFAULT 0,
    delivery_fee_satang INTEGER NOT NULL DEFAULT 0,
    total_satang INTEGER NOT NULL,
    total_cost_satang INTEGER NOT NULL,
    gross_profit_satang INTEGER NOT NULL,
    payment_method_code TEXT NOT NULL,
    amount_received_satang INTEGER NOT NULL DEFAULT 0,
    change_satang INTEGER NOT NULL DEFAULT 0,
    bank_name TEXT,
    payment_reference TEXT,
    evidence_image_path TEXT,
    customer_note TEXT,
    settled_reconciliation_id INTEGER REFERENCES reconciliations(id) ON DELETE RESTRICT,
    settled_at TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS billing_customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    contact_name TEXT,
    phone TEXT,
    address TEXT,
    tax_id TEXT,
    credit_limit_satang INTEGER NOT NULL DEFAULT 0 CHECK(credit_limit_satang >= 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS billed_sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL UNIQUE REFERENCES sales(id) ON DELETE RESTRICT,
    customer_id INTEGER NOT NULL REFERENCES billing_customers(id) ON DELETE RESTRICT,
    original_satang INTEGER NOT NULL CHECK(original_satang > 0),
    paid_satang INTEGER NOT NULL DEFAULT 0 CHECK(paid_satang >= 0),
    due_date TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'outstanding' CHECK(status IN ('outstanding','partial','paid','voided')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_billed_sales_customer_status ON billed_sales(customer_id,status);

CREATE TABLE IF NOT EXISTS billed_sale_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    billed_sale_id INTEGER NOT NULL REFERENCES billed_sales(id) ON DELETE RESTRICT,
    amount_satang INTEGER NOT NULL CHECK(amount_satang > 0),
    payment_method_code TEXT NOT NULL CHECK(payment_method_code IN ('cash','scan','transfer')),
    reference TEXT,
    note TEXT,
    received_by INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE RESTRICT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    product_name TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity > 0),
    unit_price_satang INTEGER NOT NULL,
    discount_satang INTEGER NOT NULL DEFAULT 0,
    cost_satang INTEGER NOT NULL,
    line_total_satang INTEGER NOT NULL,
    voided_quantity REAL NOT NULL DEFAULT 0,
    manual_price_reference TEXT
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    movement_type TEXT NOT NULL,
    previous_quantity REAL NOT NULL,
    changed_quantity REAL NOT NULL,
    new_quantity REAL NOT NULL,
    unit_cost_satang INTEGER NOT NULL DEFAULT 0,
    reference_type TEXT,
    reference_number TEXT,
    staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sale_voids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE RESTRICT,
    void_type TEXT NOT NULL CHECK(void_type IN ('partial','full')),
    reason TEXT NOT NULL,
    voided_by INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sale_void_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    void_id INTEGER NOT NULL REFERENCES sale_voids(id) ON DELETE RESTRICT,
    sale_item_id INTEGER NOT NULL REFERENCES sale_items(id) ON DELETE RESTRICT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK(quantity > 0),
    refund_satang INTEGER NOT NULL,
    cost_satang INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS held_bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    cart_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT,
    invoice_number TEXT,
    lot_number TEXT,
    expiry_date TEXT,
    note TEXT,
    staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    total_cost_satang INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_receipt_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL REFERENCES stock_receipts(id) ON DELETE RESTRICT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK(quantity > 0),
    unit_cost_satang INTEGER NOT NULL CHECK(unit_cost_satang >= 0),
    total_cost_satang INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    contact_name TEXT, phone TEXT, line_id TEXT, address TEXT, tax_id TEXT, note TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_count_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','finalized')),
    created_by INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    finalized_by INTEGER REFERENCES staff(id) ON DELETE RESTRICT,
    finalized_at TEXT
);

CREATE TABLE IF NOT EXISTS stock_count_participants (
    session_id INTEGER NOT NULL REFERENCES stock_count_sessions(id) ON DELETE CASCADE,
    staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    joined_at TEXT NOT NULL,
    PRIMARY KEY(session_id,staff_id)
);

CREATE TABLE IF NOT EXISTS stock_count_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES stock_count_sessions(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    counter_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    system_quantity REAL NOT NULL,
    counted_quantity REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(session_id,product_id,counter_id)
);

CREATE TABLE IF NOT EXISTS reconciliations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cashier_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    business_date TEXT NOT NULL,
    opening_float_satang INTEGER NOT NULL DEFAULT 0,
    cash_sales_satang INTEGER NOT NULL DEFAULT 0,
    scan_sales_satang INTEGER NOT NULL DEFAULT 0,
    transfer_sales_satang INTEGER NOT NULL DEFAULT 0,
    billed_sales_satang INTEGER NOT NULL DEFAULT 0,
    void_total_satang INTEGER NOT NULL DEFAULT 0,
    cash_refunds_satang INTEGER NOT NULL DEFAULT 0,
    cash_removals_satang INTEGER NOT NULL DEFAULT 0,
    cash_additions_satang INTEGER NOT NULL DEFAULT 0,
    expected_cash_satang INTEGER NOT NULL,
    actual_cash_satang INTEGER NOT NULL,
    difference_satang INTEGER NOT NULL,
    note TEXT,
    closed_by INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    verified_by INTEGER REFERENCES staff(id) ON DELETE RESTRICT,
    verified_at TEXT,
    verification_note TEXT,
    created_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS stock_count_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES stock_count_sessions(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    counter_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    counted_quantity REAL NOT NULL CHECK(counted_quantity >= 0),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_count_attempts_session_product ON stock_count_attempts(session_id,product_id);

CREATE TABLE IF NOT EXISTS stock_count_results (
    session_id INTEGER NOT NULL REFERENCES stock_count_sessions(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    system_quantity REAL NOT NULL,
    suggested_quantity REAL NOT NULL,
    selected_quantity REAL,
    applied INTEGER NOT NULL DEFAULT 0 CHECK(applied IN (0,1)),
    PRIMARY KEY(session_id,product_id)
);

CREATE TABLE IF NOT EXISTS stock_count_applications (
    session_id INTEGER PRIMARY KEY REFERENCES stock_count_sessions(id) ON DELETE RESTRICT,
    applied_by INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    phone_normalized TEXT NOT NULL UNIQUE,
    display_name TEXT,
    pin_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    must_change_pin INTEGER NOT NULL DEFAULT 0 CHECK(must_change_pin IN (0,1)),
    is_guest INTEGER NOT NULL DEFAULT 0 CHECK(is_guest IN (0,1)),
    line_user_id TEXT UNIQUE,
    line_display_name TEXT,
    line_picture_url TEXT,
    line_created_at TEXT,
    line_last_login_at TEXT,
    registered_name TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
    deleted_at TEXT,
    deleted_by_staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    default_delivery_location_id INTEGER REFERENCES delivery_locations(id) ON DELETE SET NULL,
    default_room_reference TEXT,
    profile_completed INTEGER NOT NULL DEFAULT 0 CHECK(profile_completed IN (0,1)),
    staff_notes TEXT,
    created_at TEXT NOT NULL,
    last_login_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customer_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_customer_sessions_token ON customer_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_customer_sessions_expiry ON customer_sessions(expires_at);

CREATE TABLE IF NOT EXISTS customer_login_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    phone_fingerprint TEXT,
    event_type TEXT NOT NULL CHECK(event_type IN ('registration','login_success','login_failed','logout','session_expired','pin_changed','pin_reset')),
    ip_address TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_customer_login_rate ON customer_login_events(phone_fingerprint,ip_address,event_type,created_at);

CREATE TABLE IF NOT EXISTS delivery_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    is_available INTEGER NOT NULL DEFAULT 1 CHECK(is_available IN (0,1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    delivery_fee_satang INTEGER NOT NULL DEFAULT 0 CHECK(delivery_fee_satang >= 0),
    minimum_order_satang INTEGER NOT NULL DEFAULT 0 CHECK(minimum_order_satang >= 0),
    room_required INTEGER NOT NULL DEFAULT 1 CHECK(room_required IN (0,1)),
    estimated_note TEXT,
    instructions TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS online_bank_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    account_name TEXT NOT NULL,
    account_number TEXT NOT NULL,
    instructions TEXT,
    qr_path TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS online_order_sequences (
    order_date TEXT PRIMARY KEY,
    last_number INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS online_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    order_number TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    contact_phone TEXT,
    contact_name TEXT,
    delivery_location_id INTEGER REFERENCES delivery_locations(id) ON DELETE RESTRICT,
    location_name_snapshot TEXT NOT NULL,
    delivery_fee_satang INTEGER NOT NULL DEFAULT 0,
    room_reference TEXT,
    payment_method_code TEXT NOT NULL CHECK(payment_method_code IN ('cash','transfer')),
    payment_status TEXT NOT NULL DEFAULT 'unpaid' CHECK(payment_status IN ('unpaid','awaiting_verification','confirmed','rejected','refund_pending','refunded')),
    status TEXT NOT NULL DEFAULT 'submitted' CHECK(status IN ('submitted','accepted','preparing','reconciling','ready','delivering','completed','customer_cancelled','staff_cancelled','rejected','expired')),
    subtotal_satang INTEGER NOT NULL,
    total_satang INTEGER NOT NULL,
    customer_note TEXT,
    internal_note TEXT,
    customer_visible_note TEXT,
    idempotency_key TEXT NOT NULL,
    expires_at TEXT,
    accepted_by INTEGER REFERENCES staff(id) ON DELETE RESTRICT,
    prepared_by INTEGER REFERENCES staff(id) ON DELETE RESTRICT,
    reconciled_by INTEGER REFERENCES staff(id) ON DELETE RESTRICT,
    assigned_staff_id INTEGER REFERENCES staff(id) ON DELETE RESTRICT,
    sale_id INTEGER UNIQUE REFERENCES sales(id) ON DELETE RESTRICT,
    cash_expected_satang INTEGER,
    cash_received_satang INTEGER,
    change_satang INTEGER,
    cash_received_by INTEGER REFERENCES staff(id) ON DELETE RESTRICT,
    delivery_result TEXT,
    delivery_note TEXT,
    cancellation_reason TEXT,
    accepted_at TEXT,
    preparation_started_at TEXT,
    reconciliation_started_at TEXT,
    reconciliation_completed_at TEXT,
    assigned_at TEXT,
    delivery_started_at TEXT,
    completed_at TEXT,
    cancelled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(customer_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_online_orders_customer ON online_orders(customer_id,created_at);
CREATE INDEX IF NOT EXISTS idx_online_orders_staff_queue ON online_orders(status,created_at);

CREATE TABLE IF NOT EXISTS online_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES online_orders(id) ON DELETE RESTRICT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    product_name_snapshot TEXT NOT NULL,
    barcode_snapshot TEXT,
    unit_price_satang INTEGER NOT NULL,
    customer_confirmed_unit_price_satang INTEGER CHECK(customer_confirmed_unit_price_satang >= 0),
    original_quantity REAL NOT NULL CHECK(original_quantity > 0),
    ordered_quantity REAL NOT NULL CHECK(ordered_quantity > 0),
    prepared_quantity REAL NOT NULL DEFAULT 0 CHECK(prepared_quantity >= 0),
    reconciled_quantity REAL NOT NULL DEFAULT 0 CHECK(reconciled_quantity >= 0),
    delivered_quantity REAL NOT NULL DEFAULT 0 CHECK(delivered_quantity >= 0),
    line_total_satang INTEGER NOT NULL,
    missing_flag INTEGER NOT NULL DEFAULT 0 CHECK(missing_flag IN (0,1)),
    preparation_note TEXT,
    is_removed INTEGER NOT NULL DEFAULT 0 CHECK(is_removed IN (0,1)),
    UNIQUE(order_id,product_id)
);

CREATE TABLE IF NOT EXISTS online_order_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES online_orders(id) ON DELETE RESTRICT,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK(actor_type IN ('customer','staff','system')),
    actor_customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    actor_staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    reason TEXT,
    customer_visible INTEGER NOT NULL DEFAULT 1 CHECK(customer_visible IN (0,1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS online_order_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES online_orders(id) ON DELETE RESTRICT,
    method_code TEXT NOT NULL CHECK(method_code IN ('cash','transfer')),
    amount_satang INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('unpaid','awaiting_verification','confirmed','rejected','refund_pending','refunded')),
    slip_path TEXT,
    content_type TEXT,
    uploaded_by_customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    verified_by INTEGER REFERENCES staff(id) ON DELETE RESTRICT,
    verified_at TEXT,
    rejection_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES online_orders(id) ON DELETE RESTRICT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK(quantity > 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','released','converted')),
    created_at TEXT NOT NULL,
    released_at TEXT,
    release_reason TEXT,
    UNIQUE(order_id,product_id)
);
CREATE INDEX IF NOT EXISTS idx_stock_reservations_available ON stock_reservations(product_id,status);

CREATE TABLE IF NOT EXISTS order_reconciliation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES online_orders(id) ON DELETE RESTRICT,
    order_item_id INTEGER NOT NULL REFERENCES online_order_items(id) ON DELETE RESTRICT,
    method TEXT NOT NULL CHECK(method IN ('barcode','manual','reset','discrepancy')),
    quantity REAL NOT NULL,
    barcode_scanned TEXT,
    reason TEXT,
    staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL
);
