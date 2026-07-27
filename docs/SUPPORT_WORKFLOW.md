# ขั้นตอน remote support

POS ไม่เปิด remote shell และไม่รับคำสั่ง, URL, path หรือ SQL จากระยะไกล

ผู้ให้บริการสร้าง JSON request ที่ลงลายเซ็น HMAC ด้วยกุญแจ support ของ store และวางไว้ใน `runtime/support/remote-inbox/` ผ่านช่องทางที่องค์กรอนุมัติ request ต้องมี `request_id`, store/device id, action ที่ allow-list, nonce, เวลาสร้าง/หมดอายุ และ signature

Action ที่รับได้คือ `health_report`, `support_bundle`, `backup`, `sync_retry`, `update_check`, `schedule_update`, `controlled_restart` เท่านั้น คำขอหมดอายุ, ใช้ซ้ำ หรือชี้ไปยัง store อื่นจะถูกปฏิเสธ

ผู้ดูแลระบบต้องเปิดหน้า `การบำรุงรักษาระบบ`, ยืนยัน PIN สำหรับงานเสี่ยงสูง แล้วกดอนุมัติ คำขอจะถูกบันทึกใน audit log และถูกเปลี่ยนชื่อเป็น `.approved.json` หลังตรวจสอบ

ชุดข้อมูลช่วยเหลือมีเฉพาะเวอร์ชัน, schema/migration history, สถานะระบบ, พื้นที่ดิสก์, health check และ log ที่ถูกลบ secret/token/PIN hash/เบอร์โทร ไม่รวมฐานข้อมูล, ยอดขาย, ข้อมูลลูกค้า, สลิป หรือ private key โดยค่าเริ่มต้น

