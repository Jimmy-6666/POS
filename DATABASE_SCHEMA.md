# แบบฐานข้อมูล

> เอกสารนี้เก็บประวัติการออกแบบฐานข้อมูลระยะแรก บางส่วนที่เขียนว่า
> “ระยะถัดไป” ถูกพัฒนาแล้วหรือเปลี่ยนรูปแบบในภายหลัง ห้ามใช้เป็น live schema
> เพียงแหล่งเดียว ให้ใช้ `DATABASE_OVERVIEW.md`, `pos_app/schema.sql` และ
> migration ใน `pos_app/database.py` เป็นสถานะปัจจุบัน

SQLite เปิด `foreign_keys`, WAL และใช้ timestamp แบบ ISO-8601 UTC; UI แปลงเป็น `Asia/Bangkok` ตารางรายการตั้งค่าทั้งหมดแก้ไขได้และใช้ soft-active แทนการลบข้อมูลที่ถูกอ้างอิง

## ตารางระยะที่ 1 (สร้างแล้ว)

- `categories(id, name_th, is_active, sort_order, created_at, updated_at)`
- `units(id, name_th, is_active, sort_order, created_at, updated_at)`
- `adjustment_reasons(id, name_th, is_active, created_at, updated_at)`
- `payment_methods(id, name_th, code, is_active, created_at, updated_at)`
- `settings(key, value, updated_at)`

Schema ใช้ `CREATE TABLE IF NOT EXISTS` และ seed ใช้ unique constraint + `INSERT OR IGNORE` จึงเริ่มซ้ำได้โดยไม่ลบข้อมูล

## ตารางระยะที่ 2 (สร้างแล้ว)

- `roles`, `permissions`, `role_permissions`: บทบาทและสิทธิ์แบบ many-to-many
- `staff`: ชื่อพนักงาน, PIN hash, บทบาท, สถานะ และ flag บังคับเปลี่ยน PIN
- `staff_sessions`: session token hash, CSRF token, IP, เวลาล่าสุดและวันหมดอายุ
- `login_events`: สำเร็จ, ล้มเหลว, ออกจากระบบ และ session หมดอายุ
- `audit_logs`: โครงสร้าง audit กลาง; ระยะนี้บันทึกการเปลี่ยน PIN

cookie เก็บเพียง token สุ่ม ส่วน token hash และสถานะ session อยู่ใน SQLite จึงยกเลิกจากฝั่งเซิร์ฟเวอร์ได้

## ตารางที่ออกแบบสำหรับระยะถัดไป

| กลุ่ม | ตารางและความสัมพันธ์หลัก |
|---|---|
| บุคลากร | ตารางหลักสร้างแล้ว; หน้าจัดการพนักงานจะเพิ่มในระยะที่เกี่ยวข้อง |
| สินค้า | `products *—1 categories`, `products *—1 units`, `product_images` |
| ผู้จำหน่าย | `suppliers`, `stock_receipts 1—* stock_receipt_items`; item อ้างสินค้า |
| การขาย | `sales 1—* sale_items`, `sales 1—* payments`, `held_sales`; sale อ้าง cashier |
| สต็อก | `products 1—* stock_movements`; movement อ้างเอกสารต้นทางและ staff |
| นับสต็อก | `stock_count_sessions 1—* stock_count_participants`, `stock_count_sessions 1—* stock_count_items`; unique `(session_id, product_id, counter_id)` ป้องกันงานร่างชนกัน |
| ปิดยอด | `reconciliations`, `cash_adjustments`; อ้าง staff/shift/date |
| ระบบ | `audit_logs`, `receipt_sequences`, `schema_migrations` |

## ตารางระยะที่ 3–5 (สร้างแล้ว)

- `products`: บาร์โค้ด/SKU unique, หมวด, หน่วย, ต้นทุน/ราคาเป็นสตางค์, สต็อก, รูป และ flags
- `sales 1—* sale_items`: snapshot ชื่อ ราคา ต้นทุน ส่วนลด และกำไร ณ เวลาขาย
- `receipt_sequences`: ลำดับใบเสร็จแยกตามวัน
- `stock_movements`: opening balance และ sale movement; ขยายชนิด movement ในระยะ 6
- `held_bills`: ตะกร้า JSON แยกตามพนักงาน ไม่ทับกัน

## ข้อกำหนดข้อมูลสำคัญ

- เงินเก็บเป็น integer satang เพื่อเลี่ยง floating point; จำนวนสินค้าใช้ decimal string/NUMERIC ที่ตรวจใน service
- `products.barcode` unique และ required; `sku` unique เมื่อไม่ว่าง
- `sales.receipt_number` unique; sale item เก็บชื่อ ราคา ต้นทุน และส่วนลด snapshot
- `stock_movements` เก็บ previous/change/new และห้ามแก้ย้อนหลังโดย route ปกติ
- foreign keys ใช้ `RESTRICT` สำหรับประวัติ และ `CASCADE` เฉพาะรายละเอียดที่ไม่มีตัวตนอิสระ
- ทุกการขายและการเปลี่ยนสต็อกใช้ transaction; migration เพิ่ม schema เท่านั้นและไม่ลบข้อมูลผู้ใช้

## แผน migration

เพิ่ม `schema_migrations(version, applied_at)` ในระยะ 2 ก่อนตารางยืนยันตัวตน การอัปเกรดแต่ละ version ทำใน transaction และสำรองฐานข้อมูลก่อน migration ที่ซับซ้อน
