# ความปลอดภัยของการบำรุงรักษาระยะไกล

การเชื่อมต่อดูแล POS เป็น outbound และ allow-listed เท่านั้น เครื่อง POS ไม่เปิด port สำหรับ remote shell และหน้า maintenance อยู่ใน Flask blueprint ที่ต้องเป็น staff role `admin` พร้อม permission `backup.manage`

มาตรการสำคัญ:

- งาน backup, sync, update, support และ restart ถูกเขียนเป็น job type คงที่ใน `pos_app/services/maintenance_jobs.py`
- web UI รับเพียง action ที่กำหนดไว้ ไม่รับ command/path/URL/file name จากผู้ใช้
- POST ทุกตัวตรวจ CSRF และ action สำคัญต้อง re-authenticate ด้วย PIN ภายใน 5 นาที
- signed remote requests ใช้ HMAC, store id, nonce replay protection และช่วงเวลาไม่เกิน 1 ชั่วโมง
- support bundle redacts secrets, credentials, PIN hashes และหมายเลขโทรศัพท์
- update manifest และทุกไฟล์ใน release ตรวจ HMAC/SHA-256 ก่อน staging
- active release สลับด้วย atomic JSON replace และ failure คืน release เดิม
- secrets/key files อยู่ใน runtime/config หรือ Windows secret store และอยู่ใน `.gitignore` ไม่ commit เข้า repository

การเปิดให้ลูกค้าเข้าถึงเว็บสั่งซื้อไม่ทำให้ `/maintenance` หรือ remote inbox เข้าถึงได้ เพราะ route ใช้ staff session และ admin authorization แยกจาก customer authentication

