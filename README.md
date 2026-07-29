# แสนงาม มินิมาร์ท POS 1.0

> เอกสารนี้เก็บคู่มือฐานของ Release 1.0 ไว้ตามข้อกำหนดเดิม ปัจจุบันโครงการมี
> Release 3.0.1 และ Desktop Launcher/LINE/Backup ล่าสุด โปรดดู `VERSION_3.0.1.md`
> สำหรับการเปิดรุ่นปัจจุบัน และดู `AI_CONTEXT.md` สำหรับสถานะการพัฒนาล่าสุด
> โดยข้อกำหนดเดิมใน `REQUIREMENTS_V1.0.md` ยังมีผลครบถ้วน

Production Release 1.0 สำหรับ Windows/LAN: POS, สินค้าและราคา, สต็อก, blind stock count หลายคน, ใบนับ Code 128, ปิดยอดและตรวจรับ, Dashboard, รายงานรายวัน/รายเดือน, พนักงาน, Audit และ Backup

- การติดตั้งเครื่องใหม่: `FIRST_INSTALLATION.md`
- Requirements ที่รับรองใน Release: `REQUIREMENTS_V1.0.md`

## 1. ติดตั้ง Python

ดาวน์โหลด Python 3.11 ขึ้นไปจาก python.org บน Windows ระหว่างติดตั้งให้เลือก **Add Python to PATH** แล้วเปิด Command Prompt ใหม่ ตรวจด้วย `python --version`

## 2. ติดตั้งส่วนประกอบ

เปิด Command Prompt ในโฟลเดอร์นี้แล้วรัน:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

ไม่จำเป็นต้อง activate virtual environment วิธีนี้ใช้ได้ทั้ง Command Prompt และ PowerShell และไม่ติดข้อจำกัด PowerShell Execution Policy

## 3. เริ่มระบบ

หลังติดตั้งส่วนประกอบแล้ว ดับเบิลคลิก `start-pos.bat` ได้ทันที หรือรันใน PowerShell:

```bat
.venv\Scripts\python -m waitress --host=0.0.0.0 --port=8000 app:app
```

ครั้งแรกระบบจะสร้าง `data\pos.db` อัตโนมัติ กด Ctrl+C ในหน้าต่างเซิร์ฟเวอร์เพื่อหยุด

หากเปิด `start-pos.bat` ขณะที่ POS รุ่นเดิมยังทำงานอยู่ launcher จะหยุด Python instance เดิมที่ฟังพอร์ต 8000 ก่อน แล้วเริ่มรุ่นปัจจุบันเพียงหนึ่ง instance อัตโนมัติ หากพอร์ต 8000 เป็นโปรแกรมชนิดอื่น ระบบจะไม่ปิดโปรแกรมนั้นและจะแจ้งข้อผิดพลาดแทน

## 4. เปิดบนเครื่องแคชเชียร์

เปิดเบราว์เซอร์ไปที่ `http://127.0.0.1:8000` หน้า `/health` ควรแสดง `status: ok`

## 5. IP คงที่ของเครื่อง Server

Release 3.0.1 กำหนดเครื่อง Server เป็น `192.168.0.200/24`, gateway
`192.168.0.1` แบบ static ใช้ `configure-production-network.ps1` จาก PowerShell
ที่เปิดแบบ Run as administrator เมื่อต้องติดตั้งหรือซ่อมค่า network

## 6. เปิดจากมือถือใน Wi‑Fi เดียวกัน

Desktop Launcher ใช้ `http://192.168.0.200:8002`; scheduled Production service
ค่าเริ่มต้นใช้ `http://192.168.0.200:8000` เครื่องหลักต้องเปิดโปรแกรมอยู่ และ
อุปกรณ์ต้องอยู่ใน `192.168.0.0/24` ห้าม forward พอร์ตนี้ออกอินเทอร์เน็ต

## 7. สำรองและคืนฐานข้อมูล

ระยะที่ 1 ใช้วิธี manual: หยุดเซิร์ฟเวอร์ก่อน แล้วคัดลอก `data\pos.db` และโฟลเดอร์ `uploads\products` ไปเก็บใน `backups\ชื่อวันที่เวลา\` การคืนข้อมูลให้หยุดเซิร์ฟเวอร์ เปลี่ยนชื่อฐานเดิมเพื่อเก็บไว้ แล้วคัดลอกไฟล์สำรองกลับเป็น `data\pos.db` จากนั้นเริ่มระบบและเปิด `/health` ห้ามแทนไฟล์ขณะระบบทำงาน

## 8. ย้ายไประบบอื่น

หยุดระบบ คัดลอกทั้งโฟลเดอร์ไปเครื่องใหม่ ติดตั้ง Python/requirements แล้วเปิดด้วย launcher ฐานข้อมูลและรูปสินค้าจะตามไปด้วย ไม่ต้องมี cloud

## 9. ผู้ดูแลเริ่มต้นและการเปลี่ยน PIN

ครั้งแรกเลือก **ผู้ดูแลระบบ** และใช้ PIN ชั่วคราว `1234` ระบบจะบังคับให้เปลี่ยนเป็น PIN ตัวเลข 4 หรือ 6 หลักทันที PIN เก็บเป็น password hash และไม่เก็บ plain text หลังเปลี่ยนแล้ว เมื่อต้องการเปลี่ยนอีกให้กด **เปลี่ยน PIN** ด้านบน ห้ามใช้ `1234` ต่อในงานจริง

## 10. แก้ปัญหา Windows Firewall

ถ้าเครื่องหลักเปิดได้แต่มือถือเปิดไม่ได้ ตรวจว่าอยู่ Wi‑Fi เดียวกันและ network profile เป็น Private จากนั้นอนุญาต Python/พอร์ต TCP 8000 เฉพาะ Private networks ใน Windows Defender Firewall อย่าอนุญาต Public networks หากไม่จำเป็น ตรวจ IP ใหม่หลังเปลี่ยน Wi‑Fi และปิด VPN/AP isolation ชั่วคราวเพื่อวิเคราะห์

## ทดสอบ

รันทดสอบด้วย Python ได้ทันที ไม่ต้องติดตั้งแพ็กเกจทดสอบเพิ่ม:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

ทดสอบด้วยตนเอง: เปิด `/`, `/health`, ตรวจ `data\pos.db`, หยุด/เริ่มซ้ำ และลองเปิดจากมือถือ การทดสอบ business logic ใน brief จะเพิ่มพร้อม phase ที่เกี่ยวข้อง

## สำหรับนักพัฒนา

- UI และข้อความผู้ใช้เป็นภาษาไทย; identifier และ comment เป็นอังกฤษ
- ไม่มี frontend build หรือ asset ภายนอก
- ตั้งค่าเวลาเป้าหมาย `Asia/Bangkok`; timestamps เชิงธุรกิจในระยะถัดไปจะเก็บ ISO UTC และแปลงเมื่อแสดง
- ระบบสร้าง secret key สุ่มไว้ใน `data\.secret_key` อัตโนมัติ ต้องย้ายไฟล์นี้พร้อมโฟลเดอร์โครงการ และไม่ควรเผยแพร่
