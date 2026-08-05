# Deploy รูปแบบใบเสร็จ 80 มม.

เอกสารนี้ใช้กับแพ็กเกจ `receipt-format-80mm-20260802` เท่านั้น แบบอ้างอิงที่
เจ้าของร้านอนุมัติคือ Google Docs:

`https://docs.google.com/document/d/1zyf1tXiM0bMRbkZDkhk62IwFHzgYPKzEaRv31w1Da9k`

## ขอบเขตที่อนุมัติ

- กระดาษกว้าง 80 มม. สูง 297 มม. ขอบซ้าย/ขวา 4 มม. และพื้นที่เนื้อหา
  72 มม.
- ตารางรายการแบ่งชื่อ/รายละเอียดสินค้า 51 มม. และยอดเงิน 21 มม.
- ส่วนหัวแสดงโลโก้ ชื่อร้าน และเฉพาะเบอร์โทรศัพท์จาก `store_phone` ใน Settings
  ไม่พิมพ์ที่อยู่หรือเลขประจำตัวผู้เสียภาษี
- ไม่พิมพ์หมายเหตุลูกค้า
- ตอนนี้ยังไม่เปิด delivery จึงไม่พิมพ์แถวค่าจัดส่งใน POS receipt; ยอดรวมยังอ่านจาก
  `sale.total_satang` เดิมและไม่แก้ข้อมูลหรือสูตรคำนวณ
- สินค้าที่ตั้งราคาด้วยมือยังพิมพ์ `manual_price_reference` ตามกฎ D-045
- ใช้แบบเดียวกันกับใบเสร็จย้อนหลังผ่าน browser และงานพิมพ์ตรง Windows GDI
- วันเวลาในทั้งสองเส้นทางแปลงจาก timestamp ที่มี timezone เป็นเวลาไทย UTC+7

ไม่มี schema change, migration, dependency, business-data rewrite หรือการแก้
วิธีคำนวณยอด/ตัด stock/รับชำระ

## สิ่งที่ห้ามเปลี่ยน

คำสั่ง ESC/POS เด้งลิ้นชักต้องคงอยู่หนึ่งครั้งและอยู่ก่อนโลโก้กับใบเสร็จ:

```powershell
$drawer = [byte[]](0x1B,0x40,0x1B,0x70,0,25,250)
[SaengngamReceiptPrinter]::SendRaw([string]$payload.printer_name, $drawer)
```

source block นี้มี SHA-256 แบบ normalized LF เท่ากับ
`e48cff050317e5c8476b83a338f1e3bdd5deaf004c2f8550fb562793a5dd8e49`.
คำสั่งโลโก้ที่เก็บในเครื่องพิมพ์
`0x1B,0x40,0x1B,0x74,20,0x1C,0x70,1,0,0x0A` ต้องคงอยู่หลัง drawer pulse
และก่อน GDI receipt เหมือนเดิม

ห้าม deploy ไฟล์อื่นจาก working tree, ZIP เต็มโครงการ หรือ LINE Bot candidate
ร่วมกับ hotfix นี้

## ไฟล์ที่แพ็กเกจเปลี่ยน

1. `pos_app/services/print_jobs.py` — เปลี่ยนเฉพาะ
   `_sale_receipt_payload` และ `_windows_gdi_command`; ตัวติดตั้งตรวจและแทนที่
   สองฟังก์ชันนี้โดยไม่เขียนทับส่วนอื่นของไฟล์
2. `pos_app/templates/receipt.html` — layout ใบเสร็จ browser
3. `pos_app/static/css/receipt.css` — page size และคอลัมน์คงที่
4. `pos_app/static/img/receipt-logo.png` — โลโก้หน้า browser

`tests/test_receipt_format.py` และ PDF ตัวอย่างอยู่ในแพ็กเกจเพื่อ verification
เท่านั้น ไม่จำเป็นต้องติดตั้งลง Production

## ขั้นตอน Deploy

### 1. Read-only preflight

1. แตก ZIP ไปยังโฟลเดอร์ชั่วคราวที่ตรวจ path แล้ว และตรวจ SHA-256 ของ ZIP กับ
   ไฟล์ `.sha256` รวมทั้งทุก entry ใน `manifest.json`.
2. อ่าน `AGENTS.md` และ compact context 6 ไฟล์ของ source Production ก่อนทำงาน.
3. หา install root/runtime root/port จาก scheduled task และ process ที่กำลัง
   ฟัง port 8000 ห้ามเดา path และห้ามเลือก UAT port 8001.
4. รัน `verify-production.ps1` แบบ elevated และบันทึก health, task identity,
   database path, migration, SQLite integrity/foreign keys และ row counts.
5. ยืนยันว่า `POS_DIRECT_WINDOWS_PRINTING=1`, printer คือ
   `POSPrinter POS-80`, drawer pulse และ printer-stored logo command ตรงค่าด้านบน.
6. รันตัวติดตั้งแบบ preflight โดยยังไม่เปลี่ยนไฟล์:

   ```powershell
   .\apply-receipt-format.ps1 `
     -InstallRoot '<verified-production-install-root>' `
     -BackupRoot '<verified-backup-root>' `
     -PreflightOnly
   ```

ถ้า preflight แจ้งว่า target ต่างจาก baseline/package ให้หยุดและตรวจ diff
ห้ามใช้วิธี force-copy `print_jobs.py`.

### 2. Backup และ apply

1. ทำ database backup, full recovery bundle และ source rollback ตาม workflow
   ของ Production ก่อน downtime.
2. ยืนยันว่า backup อ่านกลับได้และบันทึก SHA-256.
3. หยุดเฉพาะ Production port 8000 ตาม task/port-scoped workflow และตรวจว่า
   port 8001 UAT ยังทำงาน.
4. รันคำสั่งเดิมโดยเอา `-PreflightOnly` ออก. Script จะสำรองไฟล์เป้าหมาย 4
   รายการเพิ่มอีกชั้นและรายงาน `backup_directory` สำหรับ rollback.
5. ตรวจ output ว่า `server_restart_required=true`,
   `database_migration_required=false` และ drawer hash ตรงค่าที่อนุมัติ.

### 3. Restart และ verify

ต้อง restart server เพราะ Python โหลด `print_jobs.py` เข้า process memory แล้ว;
การเปลี่ยนไฟล์บน disk อย่างเดียวไม่พอ ไม่ต้อง reboot Windows และไม่ต้อง restart
เครื่องพิมพ์/desktop launcher ถ้า lifecycle ที่ใช้อยู่ไม่ได้หยุดมันไปด้วย

หลัง start:

1. ตรวจ port 8000 มี listener เดียว, `/health` เป็น `ok/ready`, scheduled task,
   runtime version, SQLite integrity/foreign keys และ row counts เท่ากับ baseline.
2. ตรวจ port 8001 UAT ยัง healthy.
3. รัน focused test:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest tests.test_receipt_format -v
   ```

4. รัน full suite และ `pip check` ตาม release policy. ใช้ exit code เป็นหลัก
   เพราะ PowerShell 5.1 อาจแสดง unittest progress จาก stderr เป็น error record.
5. เปิดใบเสร็จย้อนหลังและยืนยันโลโก้/ชื่อร้าน/เบอร์โทร, 51/21 มม., ยอดรวม,
   เงินรับ/เงินทอน และไม่มีที่อยู่/Tax ID/หมายเหตุ.
6. Physical acceptance ต้องได้รับอนุญาตให้ทำรายการเงินสดทดสอบ หรือให้เจ้าของ
   สังเกตรายการเงินจริงถัดไป: ใบเสร็จต้องออกหนึ่งใบและลิ้นชักต้องเด้งหนึ่งครั้ง.
   อย่าสร้างหรือ void รายการ Production เองโดยไม่ได้รับอนุญาต.

## Rollback

ถ้า health, print หรือ drawer acceptance ไม่ผ่าน ให้หยุด Production port 8000,
คืนเฉพาะไฟล์จาก `backup_directory` ของตัวติดตั้ง, ลบโลโก้เฉพาะเมื่อ manifest
ระบุว่าเดิมไม่มีไฟล์นี้, restart server และรัน verification ซ้ำ ไม่ต้อง rollback
ฐานข้อมูลเพราะแพ็กเกจนี้ไม่แก้ schema หรือข้อมูลธุรกิจ
