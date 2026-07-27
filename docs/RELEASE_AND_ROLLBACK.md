# Release และ rollback

Sprint 3 เพิ่มตัวตรวจสอบ release แบบ pull-based ในเครื่อง POS โดยไม่ใช้ `git pull` ในโฟลเดอร์ production

## การกำหนดค่า

กำหนดใน `runtime/config/production.json` หรือ environment ของ service เท่านั้น:

```json
{
  "updates": {
    "release_manifest_source": "https://updates.example.invalid/pos/manifest.json",
    "release_package_source": "https://updates.example.invalid/pos/pos-2.2.0.zip",
    "release_trusted_key_file": "C:/ProgramData/SaengngamPOS/runtime/config/release-trusted.key"
  }
}
```

Manifest ต้องมีเวอร์ชัน, ช่วง schema ที่รองรับ, checksum SHA-256 ของทุกไฟล์และ package และลายเซ็น HMAC ที่สร้างด้วยกุญแจซึ่งอยู่นอก Git การดาวน์โหลดเครือข่ายต้องใช้ HTTPS; งานขายยังทำงานได้ถ้าแหล่ง release ใช้งานไม่ได้

## ขั้นตอน

```powershell
& .\.venv\Scripts\python.exe -m pos_app.update_cli check
& .\.venv\Scripts\python.exe -m pos_app.update_cli download
& .\.venv\Scripts\python.exe -m pos_app.update_cli install
& .\.venv\Scripts\python.exe -m pos_app.update_cli rollback
```

หน้า `การบำรุงรักษาระบบ` เรียกงานเหล่านี้ผ่านคิวงานที่บันทึกใน `runtime/support/jobs/` การติดตั้งจะสร้าง safety backup, วาง maintenance marker, คัดลอกไปยัง `runtime/releases/<version>`, ตรวจสอบ package และสลับ `active-release.json` แบบ atomic หาก smoke check ของ release ล้มเหลว ระบบคืน active release เดิมทันที

Rollback ถูกปฏิเสธหาก schema ปัจจุบันอยู่นอกช่วงที่ release เป้าหมายรองรับ หาก migration เปลี่ยนแปลงแบบย้อนกลับไม่ได้ ให้ใช้ขั้นตอนกู้คืนจาก backup ใน `docs/DISASTER_RECOVERY.md` แทน

