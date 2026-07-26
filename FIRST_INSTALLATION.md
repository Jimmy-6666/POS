# First Installation — แสนงาม มินิมาร์ท POS 2.0

## Online ordering setup

The application creates `uploads/online-payments` automatically. Backups include
this folder together with product images and payment slips.

Before sharing `/order`, an Admin or Manager must open the online settings,
add delivery locations, configure transfer details if used, explicitly enable
selected products in each product form, and only then enable online ordering.
Safe defaults are closed ordering, disabled transfer, and no online products.

Automatic expiry is access-triggered: pending orders are checked when relevant
customer or staff pages are opened. Keep the staff order queue available during
service hours for the 15-second local polling alert.

## สิ่งที่ต้องมี

- Windows 10/11 64-bit
- Python 3.11 ขึ้นไปจาก python.org โดยเลือก **Add Python to PATH**
- อินเทอร์เน็ตเฉพาะตอนติดตั้ง Flask และ Waitress ครั้งแรก

## Production — ฐานข้อมูลใหม่

1. แตก `Saengngam-POS-2.0-Production.zip` ไปยังโฟลเดอร์ถาวร เช่น `C:\SaengngamPOS` ห้ามเปิดใช้งานจากใน ZIP
2. ดับเบิลคลิก `install-pos.bat` และรอข้อความ `Installation complete`
3. ดับเบิลคลิก `start-pos.bat`
4. เปิด `http://127.0.0.1:8000`
5. เลือกผู้ดูแลระบบ ใช้ PIN เริ่มต้น `1234` แล้วตั้ง PIN ใหม่เมื่อระบบแจ้ง
6. ตั้งค่าร้าน เพิ่มพนักงาน สินค้า ราคาขาย และยอดสต็อกเริ่มต้น

Production จะสร้างฐานข้อมูลใหม่อัตโนมัติ และไม่มีสินค้า ยอดขาย หรือข้อมูลสาธิต

## UAT — ข้อมูลสาธิต

1. แตก `Saengngam-POS-2.0-UAT.zip` ไปยังอีกโฟลเดอร์ ห้ามใช้โฟลเดอร์เดียวกับ Production
2. ดับเบิลคลิก `install-uat.bat`
3. ดับเบิลคลิก `start-uat.bat`
4. เปิด `http://127.0.0.1:8001`

บัญชีสาธิต:

- ผู้ดูแลระบบ: `1234`
- ผู้จัดการ: `2222`
- แคชเชียร์: `3333`

UAT มีสินค้า สต็อก และยอดขายตัวอย่าง ห้ามนำฐานข้อมูล UAT ไปใช้จริง

## เปิดจาก iPad หรือมือถือ

ใช้คำสั่ง `ipconfig` หา IPv4 ของเครื่องหลัก แล้วเปิด `http://IP-เครื่องหลัก:8000` สำหรับ Production หรือ `:8001` สำหรับ UAT จาก Wi-Fi เดียวกัน อนุญาต Python บน Private network ใน Windows Firewall

## การใช้งานทั่วไป

- หยุดระบบด้วย `Ctrl+C` ในหน้าต่างเซิร์ฟเวอร์
- เปิดไฟล์ start ซ้ำ ระบบจะพยายามปิด instance เดิมบนพอร์ตเดียวกัน
- สำรองข้อมูลจากเมนูสำรองข้อมูลก่อนอัปเดตทุกครั้ง
- ไม่ต้อง activate PowerShell virtual environment เพราะไฟล์ติดตั้งเรียก Python ให้โดยตรง
- ตรวจสถานะระบบที่ `/health`; ควรแสดง `status: ok`
