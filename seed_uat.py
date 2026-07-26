"""Create deterministic demonstration data for the UAT package only."""
from datetime import datetime, timedelta, timezone
from random import Random

from werkzeug.security import generate_password_hash

from pos_app import create_app
from pos_app.database import get_db


PRODUCTS = [
    ("8850001000011", "น้ำดื่ม 600 มล.", "เครื่องดื่ม", "ขวด", 500, 700, 80),
    ("8850001000028", "น้ำอัดลมกระป๋อง", "เครื่องดื่ม", "กระป๋อง", 1200, 1500, 55),
    ("8850001000035", "กาแฟกระป๋อง", "เครื่องดื่ม", "กระป๋อง", 1300, 1800, 40),
    ("8850001000042", "มันฝรั่งทอด", "ขนมขบเคี้ยว", "ถุง", 1200, 2000, 35),
    ("8850001000059", "บะหมี่กึ่งสำเร็จรูป", "บะหมี่กึ่งสำเร็จรูป", "ซอง", 550, 700, 90),
    ("8850001000066", "ปลากระป๋อง", "อาหารกระป๋อง", "กระป๋อง", 1600, 2200, 28),
    ("8850001000073", "นม UHT", "นมและผลิตภัณฑ์นม", "กล่อง", 1000, 1400, 45),
    ("8850001000080", "กระดาษทิชชู", "ของใช้ในบ้าน", "แพ็ก", 2200, 2900, 22),
    ("8850001000097", "สบู่ก้อน", "ของใช้ส่วนตัว", "ชิ้น", 1300, 1800, 25),
    ("8850001000103", "น้ำยาล้างจาน", "ผลิตภัณฑ์ซักล้าง", "ขวด", 2400, 3200, 18),
    ("8850001000110", "ปากกาลูกลื่น", "เครื่องเขียน", "ชิ้น", 500, 1000, 30),
    ("8850001000127", "ขนมปังแผ่น", "เบเกอรี่", "ถุง", 2400, 3200, 15),
]


def main():
    app=create_app()
    with app.app_context():
        db=get_db()
        if db.execute("SELECT 1 FROM settings WHERE key='uat_seeded'").fetchone():
            print("UAT data already exists.");return
        db.execute("UPDATE settings SET value='แสนงาม มินิมาร์ท (UAT)',updated_at=CURRENT_TIMESTAMP WHERE key='store_name'")
        roles={r["code"]:r["id"] for r in db.execute("SELECT id,code FROM roles")}
        db.execute("UPDATE staff SET display_name='ผู้ดูแลระบบ UAT',pin_hash=?,must_change_pin=0 WHERE id=1",(generate_password_hash("1234"),))
        db.execute("INSERT INTO staff(display_name,pin_hash,role_id,must_change_pin) VALUES(?,?,?,0)",("ผู้จัดการสาธิต",generate_password_hash("2222"),roles["manager"]));manager_id=db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO staff(display_name,pin_hash,role_id,must_change_pin) VALUES(?,?,?,0)",("แคชเชียร์สาธิต",generate_password_hash("3333"),roles["cashier"]));cashier_id=db.execute("SELECT last_insert_rowid()").fetchone()[0]
        categories={r["name_th"]:r["id"] for r in db.execute("SELECT id,name_th FROM categories")};units={r["name_th"]:r["id"] for r in db.execute("SELECT id,name_th FROM units")}
        product_ids=[];now=datetime.now(timezone.utc).isoformat(timespec="seconds")
        for barcode,name,category,unit,cost,price,stock in PRODUCTS:
            cur=db.execute("""INSERT INTO products(barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity,minimum_stock,is_active,is_favorite)
                VALUES(?,?,?,?,?,?,?,?,1,?)""",(barcode,name,categories[category],units[unit],cost,price,stock,10,1 if len(product_ids)<4 else 0));product_ids.append(cur.lastrowid)
            db.execute("""INSERT INTO stock_movements(product_id,movement_type,previous_quantity,changed_quantity,new_quantity,unit_cost_satang,reference_type,reference_number,staff_id,note,created_at)
                VALUES(?,'opening_balance',0,?,?,?,'uat','DEMO',?,'ข้อมูลสาธิต',?)""",(cur.lastrowid,stock,stock,cost,manager_id,now))
        rng=Random(100);local_now=datetime.now(timezone(timedelta(hours=7)))
        for number in range(1,31):
            product_index=rng.randrange(len(PRODUCTS));quantity=rng.choice((1,1,1,2,3));product=PRODUCTS[product_index];total=product[5]*quantity;cost=product[4]*quantity
            created=(local_now-timedelta(days=rng.randrange(0,25),hours=rng.randrange(0,10))).astimezone(timezone.utc).isoformat(timespec="seconds")
            receipt=f"UAT-{local_now:%Y%m}-{number:04d}";method=rng.choice(("cash","cash","scan"));received=total if method!="cash" else ((total+9900)//10000)*10000
            cur=db.execute("""INSERT INTO sales(receipt_number,cashier_id,subtotal_satang,total_satang,total_cost_satang,gross_profit_satang,payment_method_code,amount_received_satang,change_satang,status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,'completed',?)""",(receipt,cashier_id,total,total,cost,total-cost,method,received,received-total,created))
            db.execute("""INSERT INTO sale_items(sale_id,product_id,product_name,quantity,unit_price_satang,cost_satang,line_total_satang)
                VALUES(?,?,?,?,?,?,?)""",(cur.lastrowid,product_ids[product_index],product[1],quantity,product[5],product[4],total))
        db.execute("INSERT INTO settings(key,value) VALUES('uat_seeded','1')");db.commit()
        print("UAT demo data created. Admin 1234, Manager 2222, Cashier 3333.")


if __name__=="__main__":main()
