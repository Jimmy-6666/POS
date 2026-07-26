# แสนงาม มินิมาร์ท POS — Requirements Release 1.0

วันที่ออก Release: 22 กรกฎาคม 2026

## เป้าหมายและสถาปัตยกรรม

- ระบบ POS ภาษาไทยสำหรับร้านมินิมาร์ท ทำงานบน Windows เครื่องหลักและเปิดจากอุปกรณ์ใน LAN/Wi‑Fi
- Flask + Waitress + SQLite, HTML/CSS/Vanilla JavaScript ไม่มี frontend build, Docker, cloud database หรือ CDN
- ข้อมูลอยู่ในโฟลเดอร์เดียว: `data/pos.db`, รูปใน `uploads/products`, สำรองใน `backups`
- Production ใช้ TCP 8000; UAT ใช้ TCP 8001; launcher ป้องกัน server ซ้ำบน port เดียวกัน
- เงินเก็บเป็นสตางค์และ UI แสดงเงินบาทจำนวนเต็มในหน้าขาย/ชำระตามการใช้งานร้าน
- เวลาเก็บแบบ ISO UTC และแสดงตาม Asia/Bangkok

## ผู้ใช้ ความปลอดภัย และสิทธิ์

- บทบาท: ผู้ดูแลระบบ, ผู้จัดการ, แคชเชียร์
- Login เลือกพนักงาน + PIN 4/6 หลัก; PIN hash, session ฝั่ง SQLite, timeout 30 นาที, CSRF
- Audit log, login/logout/หมดอายุ, จำกัดสิทธิ์ทุก route ฝั่ง server
- ผู้ดูแลจัดการพนักงาน การตั้งค่า Audit และ Backup; ผู้จัดการดูแลสินค้า/สต็อก/รายงาน; Cashier ขายสินค้า ปิดยอดของตน และร่วมรอบนับ

## สินค้าและราคา

- เพิ่ม/แก้ไขสินค้า: barcode/SKU, ชื่อไทย/อังกฤษ, หมวด, หน่วย, ต้นทุน, stock ขั้นต่ำ, รูป, favorite, active และจำนวนทศนิยม
- Barcode และ SKU ไม่ซ้ำ; หมวด/หน่วย/เหตุผลปรับ stock มาจากฐานข้อมูลและแก้ไขได้
- ราคาขายแยกจากต้นทุนรับเข้าล็อต
- หน้าควบคุมราคากรองหมวด แก้หลายรายการ และแสดง Summary เฉพาะรายการเปลี่ยนก่อนยืนยันครั้งที่สอง

## POS และการรับชำระ

- สแกน USB/Bluetooth, กรอก barcode, ค้นชื่อ, category box, product tile, favorite และรูปสินค้า
- ตะกร้าเพิ่ม/ลด/กรอกจำนวน ลบสินค้า ส่วนลดระดับสินค้า/บิล พักและเรียกบิล พร้อมหมายเหตุ
- Backend คำนวณราคาจากฐานข้อมูล ตรวจ stock และบันทึก sale/items/stock movement/audit ใน transaction เดียว
- เงินสดและสแกนจ่าย; เงินสดมีช่องกรอกเงินรับ ปุ่มพอดี ปุ่มธนบัตร/เหรียญ เงินทอน และคำแนะนำทอน โดยไม่มี numpad บนหน้าจอ
- หน้าขายแสดงรูปสินค้าแบบขยาย พร้อมเฉพาะชื่อและราคา ไม่แสดง stock คงเหลือบน product tile
- หน้าขายและหน้าชำระเงินรองรับหน้าจอ iPad/tablet โดยคงตะกร้า ยอดรวม และปุ่มชำระเงินไว้ในพื้นที่มองเห็นโดยไม่ต้องเลื่อนทั้งหน้า
- หน้าชำระแบ่ง panel 70/30 แสดงยอด/เงินทอนตัวใหญ่; popup สำเร็จทบทวนสินค้า ราคา เงินทอน พิมพ์หรือปิดได้โดยไม่เปิด tab ใหม่
- ใบเสร็จภาษาไทยสำหรับเครื่องพิมพ์ความร้อนผ่าน browser print; ประวัติการขายและใบเสร็จย้อนหลัง

## สต็อก

- รับสินค้าเข้า: supplier/invoice/lot/expiry/note/จำนวน/ต้นทุนจริงของล็อต; weighted-average cost โดยไม่แก้ราคาขาย
- ปรับ stock แบบเพิ่ม/ลด/set พร้อมเหตุผล ledger และ audit
- รายการ supplier และประวัติ movement
- รับเข้าและหน้าราคามีตัวกรองหมวด

## การนับสต็อก

- Blind count ไม่แสดงยอดระบบระหว่างนับ; หลายคนและหลาย attempt ต่อสินค้าได้พร้อมกัน
- Cashier เพิ่ม/ลบได้เฉพาะ attempt ของตน; Manager/Admin จัดการทั้งหมดและเป็นผู้ปิดรอบ
- หลังปิดรอบแสดง Summary พร้อมยอดระบบและค่าล่าสุด แต่ยังไม่ปรับ stock จน Manager/Admin ยืนยันอีกขั้น
- สแกนสดเมื่อ browser/HTTPS รองรับ, ถ่ายรูปอ่านด้วย ZXing fallback, manual/USB/Bluetooth; lookup แสดงชื่อสินค้าหลังอ่าน barcode
- ใบนับ Manual กรองหมวดและพิมพ์ชื่อสินค้า, Code 128 จริง, เลข barcode และช่องจดจำนวน

## ปิดยอด Dashboard และรายงาน

- Cashier แจ้งเงินตั้งต้น/นำออก/เติม/เงินจริง; ระบบเทียบ expected/actual และเก็บประวัติ
- Manager/Admin ตรวจเงินจริงและกดยืนยันรายการปิดยอดพร้อมหมายเหตุได้
- Dashboard: ยอดขาย บิล กำไรวันนี้, stock ใกล้หมด, กราฟ 7 วัน, KPI เดือนปัจจุบัน
- รายงานรายวัน/รายเดือน: ยอดขาย กำไร จำนวนบิล สินค้าขายดี stock ใกล้หมด รายการขาย และ CSV รายวัน

## การดูแลระบบและข้อจำกัด Release 1.0

- สำรอง SQLite แบบ online พร้อม uploads เป็น ZIP; restore ทำเมื่อ server หยุด
- ทำงาน offline หลังติดตั้ง dependency ครั้งแรก; asset barcode ทั้งหมดเก็บในโครงการ
- กล้องสดบนมือถือผ่าน LAN ต้องใช้ HTTPS; การถ่ายรูป, USB/Bluetooth และกรอกเองเป็น fallback บน HTTP
- ไม่รวม PromptPay dynamic QR, banking API, ESC/POS direct driver, cloud sync หรือการติดตามจำนวนธนบัตรในลิ้นชัก

## Acceptance

- Automated regression suite 19 tests ครอบคลุม auth/permissions, POS transaction, stock, blind count, Cashier ownership, reconciliation verification, monthly report, barcode lookup, manual sheet, price two-step และ backup
- `/health` ต้องตอบ `{"status":"ok","database":"ready"}` และมี listener เดียวต่อ port
