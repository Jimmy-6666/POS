import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pos_app import create_app
from pos_app.database import get_db
from pos_app.services.sales import complete_sale
from werkzeug.security import generate_password_hash


class Phase6To10Tests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();root=Path(self.folder.name);(root/"backups").mkdir();(root/"uploads"/"products").mkdir(parents=True)
        self.app=create_app({"TESTING":True,"DATABASE":str(root/"pos.db"),"PROJECT_ROOT":str(root)})
        with self.app.app_context():
            db=get_db();db.execute("UPDATE staff SET must_change_pin=0 WHERE id=1");cat=db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0];unit=db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute("INSERT INTO products(barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity) VALUES('20001','สินค้าครบระบบ',?,?,1000,2000,10)",(cat,unit));db.commit()
        self.client=self.app.test_client();self.client.post('/login',data={'staff_id':1,'pin':'1234'})
        with self.app.app_context():self.csrf=get_db().execute("SELECT csrf_token FROM staff_sessions").fetchone()[0]
    def tearDown(self):self.folder.cleanup()
    def test_adjustment_and_stock_count_finalization(self):
        reason=None
        with self.app.app_context():reason=get_db().execute("SELECT id FROM adjustment_reasons LIMIT 1").fetchone()[0]
        self.assertEqual(self.client.post('/inventory/adjust',data={'csrf_token':self.csrf,'product_id':1,'adjustment_type':'increase','quantity':'2','reason_id':reason}).status_code,302)
        response=self.client.post('/stock-counts',data={'csrf_token':self.csrf,'name':'รอบทดสอบ'});session_id=int(response.headers['Location'].rstrip('/').split('/')[-1])
        self.client.post(f'/stock-counts/{session_id}',data={'csrf_token':self.csrf,'product_id':1,'counted_quantity':'9'})
        self.client.post(f'/stock-counts/{session_id}',data={'csrf_token':self.csrf,'product_id':1,'counted_quantity':'10'})
        active_page=self.client.get(f'/stock-counts/{session_id}').get_data(as_text=True)
        self.assertNotIn('name="system_quantity"',active_page)
        self.client.post(f'/stock-counts/{session_id}/finalize',data={'csrf_token':self.csrf})
        with self.app.app_context():
            db=get_db();self.assertEqual(db.execute("SELECT stock_quantity FROM products WHERE id=1").fetchone()[0],12);self.assertEqual(db.execute("SELECT status FROM stock_count_sessions").fetchone()[0],'finalized');self.assertEqual(db.execute("SELECT COUNT(*) FROM stock_count_attempts WHERE session_id=?",(session_id,)).fetchone()[0],2)
        self.assertEqual(self.client.post(f'/stock-counts/{session_id}/apply',data={'csrf_token':self.csrf,'quantity_1':'9'}).status_code,302)
        with self.app.app_context():
            db=get_db();self.assertEqual(db.execute("SELECT stock_quantity FROM products WHERE id=1").fetchone()[0],9);self.assertEqual(db.execute("SELECT COUNT(*) FROM stock_count_applications WHERE session_id=?",(session_id,)).fetchone()[0],1)
    def test_reconciliation_reports_and_backup(self):
        business_date=datetime.now(timezone(timedelta(hours=7))).date().isoformat()
        with self.app.app_context():sale_id=complete_sale({'items':[{'product_id':1,'quantity':1}],'payment_method':'cash','amount_received_satang':2000},1)[0]
        response=self.client.post('/reconciliations',data={'csrf_token':self.csrf,'business_date':business_date,'cashier_id':1,'opening_float':'500','actual_cash':'520'})
        self.assertEqual(response.status_code,302)
        response=self.client.post('/reconciliations',data={'csrf_token':self.csrf,'business_date':business_date,'cashier_id':1,'opening_float':'500','actual_cash':'500'})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():self.assertEqual(get_db().execute("SELECT COUNT(*) FROM reconciliations WHERE cashier_id=1 AND business_date=?",(business_date,)).fetchone()[0],2)
        with self.app.app_context():
            db=get_db();self.assertIsNotNone(db.execute("SELECT settled_reconciliation_id FROM sales WHERE id=?",(sale_id,)).fetchone()[0]);self.assertEqual(db.execute("SELECT cash_sales_satang FROM reconciliations ORDER BY id DESC LIMIT 1").fetchone()[0],0)
        with self.app.app_context():self.assertEqual(get_db().execute("SELECT difference_satang FROM reconciliations").fetchone()[0],0)
        with self.app.app_context():reconciliation_id=get_db().execute("SELECT id FROM reconciliations").fetchone()[0]
        self.assertEqual(self.client.post(f'/reconciliations/{reconciliation_id}/verify',data={'csrf_token':self.csrf,'verification_note':'ตรวจเงินจริงแล้ว'}).status_code,302)
        with self.app.app_context():self.assertIsNotNone(get_db().execute("SELECT verified_by FROM reconciliations WHERE id=?",(reconciliation_id,)).fetchone()[0])
        reconciliation_page=self.client.get('/reconciliations').get_data(as_text=True);self.assertIn('Summary ปิดยอดรายวัน',reconciliation_page)
        reports_page=self.client.get('/reports');self.assertEqual(reports_page.status_code,200);self.assertIn('เงินโอนรวม',reports_page.get_data(as_text=True));self.assertEqual(self.client.get('/reports?period=monthly&month=2026-07').status_code,200);self.assertEqual(self.client.get('/reports/export.csv').status_code,200)
        self.assertEqual(self.client.post('/backups',data={'csrf_token':self.csrf}).status_code,302)
        archives=list((Path(self.folder.name)/'backups').glob('*.zip'));self.assertEqual(len(archives),1)
        with zipfile.ZipFile(archives[0]) as archive:self.assertIn('data/pos.db',archive.namelist())

    def test_scan_lookup_manual_sheet_and_direct_price_save(self):
        lookup=self.client.get('/stock-counts/product-lookup?barcode=20001');self.assertEqual(lookup.status_code,200);self.assertIn('name',lookup.get_json())
        manual_page=self.client.get('/stock-counts/manual-sheet');self.assertEqual(manual_page.status_code,200)
        manual_html=manual_page.get_data(as_text=True)
        self.assertIn('class="manual-sheet-print"',manual_html)
        self.assertIn('class="manual-category-row"',manual_html)
        self.assertIn('หมวดหมู่:',manual_html)
        print_css=(Path(__file__).parent.parent/'pos_app'/'static'/'css'/'app.css').read_text(encoding='utf-8').split('@media print',1)[1]
        self.assertIn('.mobile-bottom-nav',print_css)
        price_page=self.client.get('/products/prices?q=20001').get_data(as_text=True)
        self.assertIn('ค้นหา / สแกนบาร์โค้ด',price_page)
        self.assertIn('name="price_1"',price_page)
        self.assertIn('autofocus onfocus="this.select()"',price_page)
        save=self.client.post('/products/prices',data={'csrf_token':self.csrf,'action':'confirm','product_id':'1','price_1':'25','return_q':'20001'});self.assertEqual(save.status_code,302)
        self.assertIn('q=20001',save.headers['Location'])
        with self.app.app_context():self.assertEqual(get_db().execute("SELECT price_satang FROM products WHERE id=1").fetchone()[0],2500)

    def test_product_edit_can_change_price_without_price_shortcut(self):
        edit_page=self.client.get('/products/1/edit').get_data(as_text=True)
        self.assertIn('name="price"',edit_page)
        edit_content=edit_page.split('<main id="mainContent"',1)[1].split('</main>',1)[0]
        self.assertNotIn('href="/products/prices"',edit_content)
        with self.app.app_context():
            db=get_db();product=db.execute("SELECT category_id,unit_id FROM products WHERE id=1").fetchone()
        response=self.client.post('/products/1/edit',data={
            'csrf_token':self.csrf,'barcode':'20001','name_th':'สินค้าครบระบบ',
            'category_id':product['category_id'],'unit_id':product['unit_id'],'cost':'10',
            'price':'30','minimum_stock':'0','is_active':'on','is_online_available':'on',
        })
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            db=get_db()
            self.assertEqual(db.execute("SELECT price_satang FROM products WHERE id=1").fetchone()[0],3000)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_logs WHERE action='change_price'").fetchone()[0],1)

    def test_inventory_pages_search_and_select_exact_barcode(self):
        receive=self.client.get('/inventory/receive?q=20001').get_data(as_text=True)
        self.assertIn('ค้นหา / สแกนบาร์โค้ด',receive)
        self.assertIn('value="1" selected',receive)
        self.assertIn('name="quantity" type="number" min="0.001" step="0.001" required autofocus',receive)
        adjust=self.client.get('/inventory/adjust?q=20001').get_data(as_text=True)
        self.assertIn('ค้นหา / สแกนบาร์โค้ด',adjust)
        self.assertIn('value="1" selected',adjust)
        self.assertIn('name="quantity" type="number" min="0" step="0.001" required autofocus',adjust)

    def test_cashier_can_join_and_delete_only_own_attempt(self):
        response=self.client.post('/stock-counts',data={'csrf_token':self.csrf,'name':'รอบหลายคน'});session_id=int(response.headers['Location'].rstrip('/').split('/')[-1])
        self.client.post(f'/stock-counts/{session_id}',data={'csrf_token':self.csrf,'product_id':1,'counted_quantity':'8'})
        with self.app.app_context():
            db=get_db();cashier_role=db.execute("SELECT id FROM roles WHERE code='cashier'").fetchone()[0];db.execute("INSERT INTO staff(display_name,pin_hash,role_id,must_change_pin) VALUES(?,?,?,0)",('Cashier Test',generate_password_hash('2468'),cashier_role));cashier_id=db.execute("SELECT last_insert_rowid()").fetchone()[0];admin_attempt=db.execute("SELECT id FROM stock_count_attempts WHERE session_id=?",(session_id,)).fetchone()[0];db.commit()
        cashier=self.app.test_client();self.assertEqual(cashier.post('/login',data={'staff_id':cashier_id,'pin':'2468'}).status_code,302)
        with self.app.app_context():cashier_csrf=get_db().execute("SELECT csrf_token FROM staff_sessions WHERE staff_id=?",(cashier_id,)).fetchone()[0]
        with self.app.app_context():get_db().execute("UPDATE staff_sessions SET created_at='2026-07-21T15:00:00+00:00' WHERE staff_id=?",(cashier_id,));get_db().commit()
        self.assertEqual(cashier.post('/reconciliations',data={'csrf_token':cashier_csrf,'business_date':'2026-07-22','opening_float':'0','actual_cash':'0'}).status_code,302)
        with self.app.app_context():self.assertEqual(get_db().execute("SELECT business_date FROM reconciliations WHERE cashier_id=?",(cashier_id,)).fetchone()[0],'2026-07-21')
        self.assertEqual(cashier.get('/stock-counts').status_code,200)
        self.assertEqual(cashier.post('/stock-counts',data={'csrf_token':cashier_csrf,'name':'ห้ามสร้าง'}).status_code,403)
        cashier.post(f'/stock-counts/{session_id}',data={'csrf_token':cashier_csrf,'product_id':1,'counted_quantity':'7'})
        with self.app.app_context():own_attempt=get_db().execute("SELECT id FROM stock_count_attempts WHERE session_id=? AND counter_id=?",(session_id,cashier_id)).fetchone()[0]
        self.assertEqual(cashier.post(f'/stock-counts/{session_id}/attempts/{admin_attempt}/delete',data={'csrf_token':cashier_csrf}).status_code,403)
        self.assertEqual(cashier.post(f'/stock-counts/{session_id}/attempts/{own_attempt}/delete',data={'csrf_token':cashier_csrf}).status_code,302)
        self.assertEqual(cashier.post(f'/stock-counts/{session_id}/finalize',data={'csrf_token':cashier_csrf}).status_code,403)


if __name__=='__main__':unittest.main()
