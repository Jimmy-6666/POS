# Prompt สำหรับ Codex Agent — Deploy รูปแบบใบเสร็จ 80 มม.

คัดลอกข้อความระหว่าง **เริ่ม Prompt** และ **จบ Prompt** ไปเปิด task ใหม่ใน Codex
แล้วแนบ ZIP `receipt-format-80mm-20260802.zip` กับไฟล์ `.sha256`.

---

## เริ่ม Prompt

คุณคือ Codex Agent ที่รับผิดชอบ deploy hotfix รูปแบบใบเสร็จ 80 มม. ขึ้น
Saengngam POS Production แบบ hands-on จน verification เสร็จ ผู้ใช้ไม่ต้องรัน
คำสั่งเอง ยกเว้นช่วย login/UAC/MFA หรือทำ business acceptance ที่ต้องสังเกต
เครื่องพิมพ์และลิ้นชักจริง

เป้าหมายนี้เป็น **format-only hotfix** ห้ามนำ source, dependency, migration,
database, runtime, LINE Bot candidate หรือ feature อื่นจาก working tree ไป deploy
ร่วมกัน

### กฎที่ห้ามละเมิด

1. ต้องรักษาฟังก์ชันเด้ง cash drawer เดิมให้ทำงานหนึ่งครั้งก่อนโลโก้และใบเสร็จ:

   ```powershell
   $drawer = [byte[]](0x1B,0x40,0x1B,0x70,0,25,250)
   [SaengngamReceiptPrinter]::SendRaw([string]$payload.printer_name, $drawer)
   ```

   normalized source block SHA-256 ต้องเป็น
   `e48cff050317e5c8476b83a338f1e3bdd5deaf004c2f8550fb562793a5dd8e49`.
2. ต้องรักษาคำสั่ง printer-stored logo
   `0x1B,0x40,0x1B,0x74,20,0x1C,0x70,1,0,0x0A` และลำดับ
   drawer → logo → GDI receipt.
3. ห้าม force-copy `print_jobs.py`. ใช้ `apply-receipt-format.ps1` ซึ่งแทนที่
   เฉพาะ `_sale_receipt_payload` กับ `_windows_gdi_command` และ abort เมื่อ
   target มี diff นอก scope.
4. ห้ามแก้ `pos_desktop.py`, routes, receipt popup JS, startup environment,
   printer driver, database, migration, sales/stock/payment logic หรือ UAT.
5. ถ้า package hash, baseline, backup, integrity, drawer invariant หรือ target
   identity ไม่ผ่าน ให้หยุดก่อน write และรายงานหลักฐาน ห้าม bypass guard.

### รูปแบบที่ต้องได้

- กระดาษ 80×297 มม.; ขอบข้าง 4 มม.; พื้นที่เนื้อหา 72 มม.
- คอลัมน์รายการ 51 มม. และจำนวนเงิน 21 มม. จัดยอดชิดขวาโดยไม่พึ่ง space.
- ส่วนหัวมีโลโก้ ชื่อร้าน และเฉพาะ `store_phone` จาก Settings.
- ไม่พิมพ์ store address, Tax ID หรือ customer note.
- เนื่องจากยังไม่เปิด delivery ให้ซ่อนแถวค่าจัดส่งใน POS receipt เท่านั้น ห้ามแก้
  `sale.total_satang` หรือเปิด/เปลี่ยนการคำนวณ delivery; checked-order/online
  delivery workflow นอก scope นี้ต้องคงเดิม.
- manual-price item ยังพิมพ์ `manual_price_reference` ตาม D-045.
- browser receipt และ direct Windows GDI receipt ใช้ข้อมูล/ลำดับเดียวกัน.
- วันเวลา receipt ต้องแสดงเป็นเวลาไทย UTC+7 จาก timestamp ต้นทาง.

แบบที่เจ้าของอนุมัติ:
`https://docs.google.com/document/d/1zyf1tXiM0bMRbkZDkhk62IwFHzgYPKzEaRv31w1Da9k`

### วิธีทำงาน

1. ตรวจ SHA-256 ของ ZIP/manifest ก่อนแตกไฟล์ และยืนยันว่า package ไม่มี runtime,
   database, uploads, secret, browser profile หรือ source นอก whitelist.
2. อ่าน `DEPLOY_INSTRUCTIONS_TH.md`, `AGENTS.md` และ compact context 6 ไฟล์ของ
   Production source. ส่ง progress update อย่างน้อยทุก 60 วินาที.
3. ทำ read-only discovery หา install root/runtime root จาก scheduled task,
   port-8000 listener และ command line จริง; ยืนยันว่าไม่ใช่ UAT port 8001.
4. รัน elevated Production verification และเก็บ baseline: health, listener,
   tasks/security context, runtime/database path, migration, SQLite quick/integrity,
   foreign keys, row counts, `POS_DIRECT_WINDOWS_PRINTING=1` และ printer
   `POSPrinter POS-80`.
5. รัน package installer ด้วย `-PreflightOnly`. ถ้ามี mismatch ให้ inspect diff
   และหยุดขอคำยืนยันเมื่อจำเป็น ห้าม force.
6. ก่อน downtime สร้างและตรวจ database backup, full recovery bundle, source
   rollback กับ SHA-256 ตาม project workflow.
7. หยุดเฉพาะ Production port 8000 ด้วย task/port-scoped method; ยืนยัน port
   8000 ไม่มี listener และ port 8001 UAT ไม่ถูกหยุด.
8. รัน installer จริง โดยระบุ verified `InstallRoot` และ `BackupRoot`. ตรวจ
   output manifest และ hash ทุกไฟล์.
9. **restart Production server จำเป็น** เพราะ `print_jobs.py` เป็น Python module
   ที่โหลดอยู่ใน memory. ไม่ต้อง reboot Windows และไม่ต้องเปลี่ยน driver.
10. ตรวจ single listener, health, tasks, DB integrity/foreign keys/row counts,
    UAT health, focused test `tests.test_receipt_format`, full suite และ
    `pip check`. คอมไพล์ GDI Add-Type แบบ compile-only ห้ามส่ง test print โดยพลการ.
11. ตรวจ browser receipt หรือ sample ว่าหน้ากระดาษ 227.04×841.92 pt
    (80×297 มม.) หนึ่งหน้า และข้อมูล/คอลัมน์ตรงแบบ.
12. ขออนุญาตก่อนทำ Production cash-sale smoke test. เมื่อได้รับอนุญาต ให้
    ผู้ใช้ช่วยสังเกต hardware เท่านั้น: ต้องพิมพ์หนึ่งใบและลิ้นชักเด้งหนึ่งครั้ง.
    หากยังไม่อนุญาต ให้ระบุว่า physical drawer acceptance รอรายการจริงถัดไป
    โดยไม่สร้าง/void ข้อมูลเอง.
13. ถ้า gate ใดล้มเหลว ให้ rollback เฉพาะไฟล์จาก installer backup, restart
    port 8000 และ verify ซ้ำ; ห้าม rollback database เพราะ hotfix ไม่แก้ข้อมูล.

รายงานสุดท้ายต้องมี: Production/UAT health, exact files changed, before/after
SHA-256, backup/rollback path, test counts, DB counts unchanged, drawer source
hash/order, receipt page size, restart result และสถานะ physical acceptance.

## จบ Prompt
