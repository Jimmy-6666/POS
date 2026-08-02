# Hands-on Prompt — Deploy LINE Product Bot to Production

คัดลอกข้อความตั้งแต่หัวข้อ **เริ่ม Prompt** ถึง **จบ Prompt** ไปเปิดเป็น task
ใหม่ใน Codex พร้อมแนบ ZIP ของโครงการนี้

---

## เริ่ม Prompt

แพ็กเกจนี้ใช้ฐาน source GitHub `v3.1.5` (commit `e36ebe7465bc6b17f82d75a08326b7811ab0e62a`)
ร่วมกับ LINE Bot candidate ที่ผ่าน UAT แล้ว ต้องรักษาความสามารถและ production repair
ทั้งหมดของ 3.1.5 ไว้ ห้ามแทนที่ไฟล์ด้วยฐาน 3.1.2 หรือ downgrade Production ระหว่าง deploy

คุณคือ Codex ที่รับผิดชอบ deploy LINE Product-Maintenance Bot และ signed POS
integration ขึ้น Production จริงแบบ hands-on ตั้งแต่ต้นจนจบ ผู้ใช้เป็น
Non-IT จึงห้ามมอบหมายขั้นตอนทางเทคนิคให้ผู้ใช้ทำเอง

### คำถามแรกที่ต้องถาม

ก่อนดำเนินการใด ๆ ให้ถามผู้ใช้และรอรับข้อมูลสามรายการนี้ก่อน:

1. `VPS IP`
2. `Temporary Username` — ต้องเป็น `root` หรือมีสิทธิ์ `sudo`
3. `Temporary Password`

ใช้ข้อความสั้น ๆ ว่า:

> กรุณาส่งข้อมูลสำหรับ Production VPS ให้ผม 3 รายการครับ: VPS IP,
> Temporary Username และ Temporary Password จากนั้นผมจะตรวจสอบและดำเนินการ
> setup ให้ทั้งหมดครับ

ห้ามทวน password/token/secret กลับในแชต ห้ามเขียนลง source, commit, ZIP,
command output หรือ log และต้องลบไฟล์ช่วย deploy ชั่วคราวเมื่อเสร็จ

หาก Cloudflare, LINE Developers หรือเครื่อง POS Production ต้อง login/MFA
ผู้ใช้อาจช่วยได้เฉพาะการกรอก credential หรือยืนยัน MFA/consent ที่ระบบบังคับ
เท่านั้น หลัง login สำเร็จ Codex ต้องเป็นผู้คลิก ตั้งค่า ตรวจสอบ และแก้ปัญหา
ทั้งหมดเอง

### ข้อกำหนดการทำงานกับผู้ใช้

- ผู้ใช้เป็น Non-IT ห้ามบอกให้ผู้ใช้รัน command, แก้ config, ตั้ง DNS, ตั้ง
  Cloudflare Tunnel/VPN, WAF, firewall, systemd, Windows service หรือ copy file
  เอง
- ห้ามขอให้ผู้ใช้ “ไปตั้ง tunnel/VPN แล้วกลับมาแจ้ง” Codex ต้อง setup เองจาก
  credential/session ที่ได้รับ
- ขอข้อมูลเพิ่มได้เฉพาะ credential, MFA หรือ business choice ที่ค้นจากระบบ
  ไม่ได้จริง ๆ เช่น Production LINE account ที่จะใช้ หรือกลุ่มผู้จัดการที่
  ต้อง allowlist โดยถามครั้งละสั้น ๆ
- ผู้ใช้อาจช่วยเฉพาะ business acceptance ที่ต้องใช้ LINE จริง เช่น เชิญ bot
  เข้ากลุ่ม ส่งรูป barcode และกดยืนยันรายการที่ผู้ใช้อนุมัติ ไม่ถือเป็นงาน
  infrastructure
- ส่ง progress update ที่อ่านง่ายอย่างน้อยทุก 60 วินาทีระหว่างทำงาน
- ทำงานต่อเนื่องจน Production ผ่าน verification หรือพบ blocker ที่ต้องใช้
  credential/authority ใหม่จริง ๆ

### แหล่งอ้างอิงและขอบเขต

1. แตก ZIP ลงโฟลเดอร์ชั่วคราวที่ตรวจสอบ path แล้ว
2. อ่าน `AGENTS.md` และไฟล์บังคับหกไฟล์ก่อน:
   `AI_CONTEXT.md`, `PROJECT_MAP.md`, `FEATURE_STATUS.md`, `DECISIONS.md`,
   `CODING_RULES.md`, `DESIGN_RULES.md`
3. อ่าน scope packet ของ LINE Bot อย่างน้อย:
   `docs/LINE_BOT_SETUP.md`, `line_bot/`, `deploy/line-bot/`,
   `pos_app/routes/line_bot_integration.py`,
   `pos_app/services/line_bot_products.py`, `tests/test_line_bot_workflow.py`,
   `tests/test_line_bot_integration.py`
4. ถือ Production data/config ปัจจุบันเป็นของจริง ห้ามแทนที่ด้วย `runtime`,
   `uat_runtime`, database, group ID หรือ secret จาก UAT
5. ห้ามเปลี่ยน behavior ธุรกิจอื่น ห้ามเปิด port 8000/8010 สู่ Internet โดยตรง
   และห้ามทำ router port-forwarding

### Target architecture

ใช้โครงสร้างแยก Production ชัดเจน โดยตรวจชื่อว่าชนกับของเดิมหรือไม่ก่อนสร้าง:

```text
LINE Messaging API
  -> https://linebot.raisanngam.com/webhook
  -> Cloudflare Tunnel ใหม่บน Production VPS
  -> http://127.0.0.1:8010
  -> raisanngam-line-bot.service

Production VPS bot
  -> https://posbot.raisanngam.com/_internal/line-bot/*
  -> Cloudflare route ของเครื่อง POS Production
  -> http://127.0.0.1:8000
  -> timestamped HMAC + idempotency + revision check + audit
```

ชื่อ default:

- Public webhook: `linebot.raisanngam.com`
- Private POS integration hostname: `posbot.raisanngam.com`
- Tunnel ใหม่บน VPS: `raisanngam-linebot-prd`

ห้ามนำ `linebot-uat.raisanngam.com`, `dev.raisanngam.com`, UAT tunnel/token หรือ
UAT database มาใช้ใน Production ห้ามเปลี่ยน route ของ
`admin.raisanngam.com`/`online.raisanngam.com` และห้าม reuse UAT tunnel ถ้าไม่
มีหลักฐานว่าได้รับการออกแบบให้รองรับ Production โดยเฉพาะ

ถ้าชื่อ default ถูกใช้งานอยู่ ให้ตรวจ ownership/route ก่อน ห้าม overwrite
เงียบ ๆ เลือกชื่อ single-level Production hostname ที่ชัดเจนและรายงานเหตุผล

### Phase 1 — Read-only discovery และ baseline

ดำเนินการเองทั้งหมด:

1. ตรวจ SHA-256/package manifest และยืนยันว่า ZIP ไม่มี `.git`, `.venv`,
   `runtime`, `uat_runtime`, database, uploads, backups, browser profile,
   credentials หรือ private key
2. ตรวจ git/source status และยืนยันว่า LINE Bot hotfix ล่าสุดอยู่ใน package:
   exact-satang cost, one-minute flow, no product-image edit, linear barcode
   only, legacy/current POS response compatibility และ 24-hour image-reference
   retention
3. รัน focused tests และ full test suite จาก environment แยกก่อนแตะ Production
4. ตรวจ Production POS แบบ read-only: install root, runtime root, port 8000,
   service/task, current source version, database path, health, SQLite
   `quick_check`, foreign keys, migration history, product/sale counts และ
   existing Cloudflare routes
5. ตรวจ VPS แบบ read-onlyผ่าน SSH: OS, disk, time sync, Python, active services,
   firewall, cloudflared/tunnel ที่มีอยู่ และ port collision
6. ตรวจ Cloudflare และ LINE console จาก authenticated session; ถ้าต้อง login
   ให้ผู้ใช้ทำเฉพาะ authentication/MFA แล้ว Codex ทำขั้นตอนที่เหลือ
7. ตรวจว่า Production LINE Messaging API channel แยกจาก UAT หรือเป็น channel
   ที่เจ้าของอนุมัติให้ promote ห้ามเปลี่ยน webhook ของ UAT channel โดยไม่ถาม
   business choice นี้ก่อน

### Phase 2 — Backup และ rollback ก่อนเขียน Production

ก่อนแก้ source/config/database/tunnel ต้อง:

1. สร้าง verified Production database backup และ full recovery bundle ตาม
   script/คู่มือของ project
2. เก็บ source rollback snapshot ของ Production ที่กำลังรัน
3. สำรองเฉพาะ config ที่ต้องแก้ โดย redacted secret ในรายงาน
4. บันทึก current Cloudflare tunnel route, DNS และ WAF rule IDs/expressions เพื่อ
   rollback ได้
5. ถ้า VPS มี bot เก่า ให้สำรอง application/config/database ของ bot โดยรักษา
   permission เดิม
6. เขียน rollback plan ที่ระบุ exact target แล้วตรวจว่า rollback artifact อ่าน
   ได้จริง ห้ามใช้คำสั่งลบแบบกว้างหรือ `git reset --hard`

หาก backup/integrity/foreign-key gate ไม่ผ่าน ให้หยุดการเปลี่ยนแปลง แก้หรือ
รายงาน blocker ห้าม deploy ทับ

### Phase 3 — เตรียม POS Production integration

1. ตรวจว่ารหัส Migration 31 และ LINE Bot integration source อยู่ใน Production
   candidate ครบ
2. สร้าง shared secret ใหม่แบบ cryptographically secure อย่างน้อย 32 bytes
   สำหรับ Production เท่านั้น ห้ามใช้ secret ของ UAT
3. จัดเก็บ secret ใน ignored Production runtime config ที่ ACL อนุญาตเฉพาะ
   `SYSTEM`/Administrators และห้ามพิมพ์ค่าออก terminal/report
4. ทำให้ Production startup task โหลดค่าต่อไปนี้อย่างถาวรหลัง reboot:

   ```ini
   POS_LINE_BOT_ENABLED=1
   POS_LINE_BOT_SHARED_SECRET=<Production-only secret>
   POS_LINE_BOT_ALLOWED_SOURCE_IPS=<verified VPS public IP เมื่อ origin เห็น IP นี้จริง>
   POS_LINE_BOT_MAX_CLOCK_SKEW_SECONDS=300
   POS_TRUSTED_HOSTS=<retain existing hosts และเพิ่ม posbot.raisanngam.com>
   POS_TRUST_PROXY=1
   ```

5. ปัจจุบันต้องตรวจ `start-production.ps1`/`production-common.ps1` ว่ามีกลไก
   persistent secret config หรือยัง ถ้ายังไม่มี ให้ทำ minimal source change
   เพื่อโหลดไฟล์ `runtime/config/line-bot-integration.env` อย่างปลอดภัย เพิ่ม
   regression test และรัน full suiteก่อน deploy ห้ามตั้ง environment เฉพาะ
   current shell เพราะจะหายเมื่อ scheduled task/reboot
6. ใช้ deployment/upgrade script ของ project; รักษา Production database,
   uploads, runtime, service identity, port 8000 และ startup tasks
7. restart เฉพาะ service ที่จำเป็น แล้วตรวจ single listener, health, database,
   migration 31, SQLite integrity, foreign keys และ baseline counts เทียบก่อน
   deploy

### Phase 4 — Setup Production VPS bot

Codex ต้อง SSH และทำเอง:

1. ตรวจ host key/fingerprint และยืนยัน target IP ก่อนเขียน
2. สร้าง dedicated system user `raisanngam-line-bot`, venv, application root
   `/opt/raisanngam-line-bot/app`, state root
   `/var/lib/raisanngam-line-bot` และ secret file
   `/etc/raisanngam-line-bot/line-bot.env`
3. deploy source จาก package และใช้ `deploy/line-bot/install-vps.sh` หลัง review;
   แก้ bug ใน script ก่อนใช้ถ้า path/template ไม่ตรง package
4. ตั้ง owner/mode อย่างน้อย:
   - application source: root-owned, non-writable by bot user
   - environment file: `root:raisanngam-line-bot`, mode `0640` หรือตึงกว่า
   - bot state: bot user เท่านั้น, mode `0700`
5. ใส่ Production LINE secret/token/user ID, Production group allowlist,
   Production POS URL และ shared HMAC secret โดยไม่แสดงค่า
6. `POS_LINE_BOT_BASE_URL` ต้องเป็น
   `https://posbot.raisanngam.com` ไม่ใช่ UAT/admin/customer hostname
7. เปิด systemd hardening ตาม service file, enable at boot, restart และตรวจ
   `systemctl is-active`, localhost health, port 8010 single listener และ logs
8. ห้ามเปิด inbound 8010 ต่อ Internet; อนุญาตเฉพาะ localhost ผ่าน cloudflared

### Phase 5 — Codex setup Cloudflare Tunnel/DNS เอง

ห้ามให้ผู้ใช้ทำขั้นตอนนี้:

1. สร้าง named tunnel ใหม่ `raisanngam-linebot-prd` สำหรับ VPS Production
2. install/configure cloudflared บน VPS และผูกเป็น systemd service ที่ restart
   หลัง reboot
3. route `linebot.raisanngam.com` ไป `http://127.0.0.1:8010`
4. เพิ่ม Production POS route `posbot.raisanngam.com` ไป
   `http://127.0.0.1:8000` บน tunnel/connector ของเครื่อง POS Production โดย
   ไม่เปลี่ยน route เดิมของ admin/online
5. จำกัด ingress route/path เท่าที่ provider รองรับ และตรวจ certificate/HTTPS
6. export/จด tunnel ID, connector status, hostname route และ service state แบบ
   ไม่เปิดเผย token
7. ตรวจว่า tunnel ทั้ง VPS และ POS มี connector online หลัง reboot/restart

Cloudflare Tunnel ไม่ใช่เหตุผลให้เปิด firewall inbound 8010/8000 และห้ามใช้
Cloudflare quick tunnel สำหรับ Production

### Phase 6 — Allowlist VPS IP แบบแคบที่สุด

Codex ต้องตั้งเองทั้ง edge และ origin เท่าที่พิสูจน์ได้:

1. ใช้ Production VPS public egress IP ที่ตรวจจาก VPS จริง ห้ามเดาจากค่า input
   เพียงอย่างเดียว
2. สร้าง Cloudflare WAF/custom rule เฉพาะ:
   - hostname เท่ากับ `posbot.raisanngam.com`
   - path เริ่มด้วย `/_internal/line-bot/`
   - source IP เท่ากับ verified VPS egress IP
3. block request อื่นทั้งหมดที่ hostname `posbot.raisanngam.com` รวมถึง path
   อื่นหรือ source IP อื่น ห้ามสร้าง account/zone-wide IP allow rule
4. ถ้า managed WAF/Bot protection ขวาง signed request ให้ skip เฉพาะ rule/path/
   IP ข้างต้นเท่านั้น ห้ามปิด WAF ทั้ง zone
5. ส่ง signed read-only lookup จาก VPS แล้วพิสูจน์ว่า origin เห็น client IP เป็น
   ค่าใดก่อนตั้ง `POS_LINE_BOT_ALLOWED_SOURCE_IPS`
6. ถ้า proxy chain รักษา VPS IP ถึง `request.remote_addr` ได้ ให้ตั้ง application
   allowlist เป็น VPS IP และทดสอบ non-allowed source ได้ 403
7. ถ้า origin เห็นเพียง shared Cloudflare IP ห้าม allowlist Cloudflare CIDR
   กว้าง ๆ แทน ให้ใช้ Cloudflare edge IP allowlist + HMAC เป็น boundary และ
   บันทึกข้อจำกัดนี้อย่างตรงไปตรงมา จนกว่าจะเพิ่ม authenticated transport ที่
   พิสูจน์ source ได้
8. HMAC timestamp/signature, command idempotency, revision check และ audit ต้อง
   คงอยู่ แม้มี IP allowlist แล้ว

### Phase 7 — LINE Production setup โดย Codex

1. ใช้ Messaging API channel ที่ได้รับอนุมัติสำหรับ Production
2. ตั้ง webhook เป็น `https://linebot.raisanngam.com/webhook` และกด Verify เอง
3. เปิด Use webhook และ Allow bot to join group chats
4. ปิด greeting/auto response ที่ชนกับ bot flow และใช้ Manual chat ตามคู่มือ
5. ตรวจ long-lived channel access token และ bot user ID ด้วย API โดยไม่แสดง token
6. ถ้ายังไม่รู้ group ID ให้เปิด enrollment mode ชั่วคราว ซึ่งต้องบันทึก group
   ID เท่านั้นและไม่ประมวลผลคำสั่ง จากนั้นขอผู้ใช้ทำเพียงเชิญ bot/ส่งข้อความ
   หนึ่งครั้ง
7. อ่าน group ID จาก VPS ด้วย Codex, ใส่ allowlist, ปิด enrollment mode และ
   restart service ห้ามปล่อย enrollment mode เปิดค้าง
8. ยืนยันว่า event จากกลุ่มอื่นถูก ignore

### Phase 8 — Production verification

ต้องทดสอบและเก็บหลักฐานแบบไม่เปิดเผยข้อมูลลูกค้า/secret:

1. Local VPS bot health และ public `linebot` health
2. Local POS health, public signed POS lookup จาก VPS และ response contract
   `cost_satang`
3. unsigned/wrong-signature request ถูกปฏิเสธ
4. non-VPS source และ path อื่นบน `posbot` ถูก block
5. LINE webhook Verify ผ่านและ event เข้า worker/database
6. ส่งรูป linear barcode แล้ว Quote + `บอท` และ actual `@bot`
7. QR Code ถูกปฏิเสธ, barcode อ่านไม่ได้ตอบภายใน 10 วินาที
8. สินค้าเดิมแสดงชื่อ/ทุน/ขาย; ทุนรับสตางค์; ราคาขายต้องเกิน 0 และมากกว่าทุน
9. สินค้าใหม่/placeholder ใช้ `อื่น ๆ`/`ชิ้น`, ไม่มี flow รูปสินค้า
10. ปุ่มเป็น visible message action และเจ้าของ flow เท่านั้นที่ตอบได้
11. session หมดอายุหนึ่งนาทีพร้อมข้อความแจ้ง
12. source image bytes ไม่ถูกเขียนดิสก์; reference ใช้ไม่ได้เมื่อครบ 24 ชั่วโมง
13. ทดสอบ cancel/read-only flow ก่อน การทดสอบ write บน Production ต้องใช้
    สินค้าทดสอบหรือค่าที่เจ้าของอนุมัติเท่านั้น ห้ามแก้สินค้าจริงโดยเดา
14. ห้ามจำลอง POS outage ด้วยการหยุด Production service; ใช้ automated tests
    ยืนยัน retry และตรวจ durable queue configuration แทน
15. restart/reboot-safe checks: bot service, cloudflared, POS task และ tunnel
    connectors กลับมา active, listener ไม่ซ้ำ
16. monitor service/tunnel/application logs อย่างน้อย 5 นาทีหลัง smoke test

### Phase 9 — Completion, rollback และ credential hygiene

ก่อนจบต้อง:

1. ถ้า gate ใดล้ม ให้ rollback เฉพาะ change ที่ทำตาม snapshot/backup และพิสูจน์
   Production health/data preservation หลัง rollback
2. ลบ upload/temp scripts และ temporary archives ที่มี secret
3. ตรวจ ZIP/source/VPS app/config permissions และ logs ว่าไม่มี credential หลุด
4. รายงานเป็นภาษาไทย: architecture ที่ติดตั้ง, hostname/tunnel/rule IDs,
   source/config ที่แก้, backup/rollback location, migration, health, tests,
   allowlist proof, LINE verification, data counts และ remaining risks
5. ห้ามพิมพ์ password, channel token, channel secret, HMAC secret, group/user ID
   แบบเต็มในรายงาน
6. แจ้งผู้ใช้ให้เปลี่ยน Temporary Password หลังส่งมอบ หรือเสนอเปลี่ยนเป็น SSH
   key แล้วปิด password login โดยต้องไม่ทำให้ผู้ใช้ถูก lock out
7. ห้ามประกาศว่าสำเร็จเพียงเพราะ health 200; ต้องผ่าน signed POS lookup,
   Cloudflare restriction, LINE webhook และ end-to-end group flow

เป้าหมายสุดท้ายคือ Production ที่ใช้งานได้จริง ปลอดภัย rollback ได้ และผู้ใช้
ไม่ต้องทำงาน tunnel/VPN/DNS/WAF/server setup ด้วยตนเอง

## จบ Prompt
