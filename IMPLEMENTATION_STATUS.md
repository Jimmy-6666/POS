# สถานะการพัฒนา

> เอกสารนี้เป็นรายละเอียดการส่งมอบ Release 1.0 เดิมและเก็บไว้เพื่อ
> traceability สถานะปัจจุบันและผลทดสอบล่าสุดอยู่ที่ `FEATURE_STATUS.md`
> ข้อกำหนดเดิมทั้งหมดคงเดิมและสถานะ verification ล่าสุดเป็นสีเขียว

อัปเดต: 22 กรกฎาคม 2026

| ระยะ | สถานะ | รายละเอียด |
|---|---|---|
| 1 พื้นฐาน | เสร็จ | Flask factory, SQLite init, Thai seed, assets ในเครื่อง, Waitress launcher, README, health page, tests |
| 2 Login/roles | เสร็จ | PIN hash, SQLite server-side session, timeout 30 นาที, CSRF, role permissions, login/logout log, บังคับเปลี่ยน PIN เริ่มต้น |
| 3 สินค้า | เสร็จ | CRUD สินค้า, barcode/SKU unique, รูปสินค้า, หมวด/หน่วยจาก DB, กำไร, opening-stock movement |
| 4 POS เงินสด | เสร็จ | scanner Enter, ค้นหา/หมวด/tile, ตะกร้า, ส่วนลด, พักบิล, เงินสด/ปุ่มพอดี/ธนบัตร/เหรียญ/keypad/เงินทอน |
| 5 การจ่าย/ใบเสร็จ | เสร็จ | เงินสด/สแกน/โอน, ยืนยันรับเงิน, หลักฐานโอน, atomic sale, เลขใบเสร็จ, stock reduction, ประวัติและใบเสร็จ 80 มม. |
| 6 สต็อก | เสร็จ | รับเข้า, weighted-average cost, ปรับเพิ่ม/ลด/set, ledger, ผู้จำหน่าย, movement/audit |
| 7 นับสต็อก | เสร็จ | รอบนับหลายผู้ใช้, scanner/manual/camera เมื่อรองรับ, draft แยกผู้ตรวจ, finalization transaction |
| 8 ปิดยอด | เสร็จ | เงินสด/สแกน/โอน, เงินตั้งต้น/เติม/นำออก, expected/actual, เกิน/ขาด, สิทธิ์ตามบทบาท |
| 9 Dashboard/รายงาน | เสร็จ | KPI วันนี้, 7 วัน, ขายดี, low stock, กำไร, รายการขาย และ CSV |
| 10 Audit/backup/security | เสร็จ | staff/roles, settings, audit viewer, SQLite online backup + uploads ZIP, manual restore instructions |

## ตรวจสอบระยะที่ 1

- [x] สร้างฐานข้อมูลอัตโนมัติและเริ่มซ้ำได้
- [x] ข้อมูลเริ่มต้นภาษาไทยอยู่ใน SQLite ไม่ hard-code ในหน้าเว็บ
- [x] หน้า Thai UTF-8 responsive และไม่ใช้ CDN
- [x] bind LAN ที่ `0.0.0.0:8000`
- [x] โฟลเดอร์ข้อมูล รูปสินค้า และ backup อยู่ในโครงการ
- [x] automated tests ตรวจหน้าเว็บ health และ idempotent seed

คุณลักษณะที่ยังไม่เสร็จจะไม่ถูกนำเสนอว่าใช้งานได้ หน้าแรกจะแสดงระยะล่าสุดที่พร้อมใช้งานอย่างชัดเจน

## ตรวจสอบระยะที่ 2

- [x] หน้า protected redirect ไปหน้าเข้าสู่ระบบ
- [x] PIN รองรับตัวเลข 4 หรือ 6 หลักและเก็บด้วย Werkzeug password hash
- [x] session เก็บฝั่ง SQLite, cookie เป็น HttpOnly/SameSite และ timeout แบบเลื่อน 30 นาที
- [x] บังคับผู้ดูแลเปลี่ยน PIN เริ่มต้น; มี CSRF สำหรับเปลี่ยน PIN/ออกจากระบบ
- [x] seed บทบาท 3 แบบและ permission mapping ในฐานข้อมูล
- [x] บันทึก login สำเร็จ/ล้มเหลว/logout/หมดอายุ และจำกัดการเดา PIN
- [x] smoke test ผ่านด้วย temporary database; ไม่แตะข้อมูลจริงระหว่างทดสอบ

## ตรวจสอบระยะที่ 3–5

- [x] backend คำนวณราคาและส่วนลดจากฐานข้อมูล ไม่เชื่อยอดจาก browser
- [x] transaction เดียวบันทึก sale/items, ลดสต็อก, movement และ audit; rollback เมื่อสต็อกไม่พอ
- [x] เลขใบเสร็จรายวันไม่ซ้ำรูปแบบ `POS-YYYYMMDD-0001`
- [x] เงินสดต่ำกว่ายอดชำระถูกปฏิเสธ; scan/transfer ต้องยืนยันรับเงินจริง
- [x] change breakdown และปุ่มชำระพอดีรองรับธนบัตร/เหรียญไทย
- [x] 14 automated tests ผ่าน รวม regression ระยะ 1–2
