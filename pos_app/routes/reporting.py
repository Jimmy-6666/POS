import csv
import io
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, Response, flash, g, redirect, render_template, request, url_for

from ..auth import permission_required, valid_csrf
from ..database import get_db
from ..services.money import baht_to_satang


bp=Blueprint("reporting",__name__)


def utc_bounds(day_text):
    local_tz=timezone(timedelta(hours=7));day=date.fromisoformat(day_text)
    start=datetime.combine(day,datetime.min.time(),local_tz).astimezone(timezone.utc)
    return start.isoformat(timespec="seconds"),(start+timedelta(days=1)).isoformat(timespec="seconds")


@bp.route("/reconciliations",methods=("GET","POST"))
@permission_required("reconciliation.manage")
def reconciliations():
    db=get_db();business_date=request.values.get("business_date") or date.today().isoformat()
    cashier_id=request.values.get("cashier_id",type=int) or g.staff["id"]
    if g.staff["role_code"]=="cashier":
        cashier_id=g.staff["id"]
        login_at=datetime.fromisoformat(g.session_row["created_at"].replace("Z","+00:00"))
        if login_at.tzinfo is None:login_at=login_at.replace(tzinfo=timezone.utc)
        business_date=login_at.astimezone(timezone(timedelta(hours=7))).date().isoformat()
        day_start,_=utc_bounds(business_date);end=datetime.now(timezone.utc).isoformat(timespec="seconds")
    else:
        day_start,day_end=utc_bounds(business_date)
        today_local=datetime.now(timezone(timedelta(hours=7))).date().isoformat()
        end=datetime.now(timezone.utc).isoformat(timespec="seconds") if business_date==today_local else day_end
    last_close=db.execute("SELECT created_at FROM reconciliations WHERE cashier_id=? AND business_date=? ORDER BY created_at DESC,id DESC LIMIT 1",(cashier_id,business_date)).fetchone()
    start=last_close["created_at"] if last_close and last_close["created_at"]>day_start else day_start
    unsettled_sales=db.execute("""SELECT id,payment_method_code,total_satang FROM sales
        WHERE cashier_id=? AND status='completed' AND settled_reconciliation_id IS NULL AND created_at<=?
        ORDER BY created_at,id""",(cashier_id,end)).fetchall()
    totals={}
    for sale in unsettled_sales:totals[sale["payment_method_code"]]=totals.get(sale["payment_method_code"],0)+sale["total_satang"]
    cash=totals.get("cash",0) or 0;scan=totals.get("scan",0) or 0;transfer=totals.get("transfer",0) or 0;billing=totals.get("billing",0) or 0
    if request.method=="POST":
        if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
        opening=baht_to_satang(request.form.get("opening_float"));actual=baht_to_satang(request.form.get("actual_cash"));removals=baht_to_satang(request.form.get("cash_removals"));additions=baht_to_satang(request.form.get("cash_additions"));expected=opening+cash-removals+additions;difference=actual-expected
        try:
            db.execute("BEGIN IMMEDIATE")
            unsettled_sales=db.execute("""SELECT id,payment_method_code,total_satang FROM sales
                WHERE cashier_id=? AND status='completed' AND settled_reconciliation_id IS NULL AND created_at<=?
                ORDER BY created_at,id""",(cashier_id,end)).fetchall()
            locked_totals={}
            for sale in unsettled_sales:locked_totals[sale["payment_method_code"]]=locked_totals.get(sale["payment_method_code"],0)+sale["total_satang"]
            cash=locked_totals.get("cash",0) or 0;scan=locked_totals.get("scan",0) or 0;transfer=locked_totals.get("transfer",0) or 0;billing=locked_totals.get("billing",0) or 0
            expected=opening+cash-removals+additions;difference=actual-expected
            cursor=db.execute("""INSERT INTO reconciliations (cashier_id,business_date,opening_float_satang,cash_sales_satang,scan_sales_satang,
                transfer_sales_satang,billed_sales_satang,cash_removals_satang,cash_additions_satang,expected_cash_satang,actual_cash_satang,difference_satang,note,closed_by,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(cashier_id,business_date,opening,cash,scan,transfer,billing,removals,additions,expected,actual,difference,request.form.get("note"),g.staff["id"],datetime.now(timezone.utc).isoformat(timespec="seconds")))
            sale_ids=[sale["id"] for sale in unsettled_sales]
            if sale_ids:
                placeholders=",".join("?" for _ in sale_ids)
                settled_at=datetime.now(timezone.utc).isoformat(timespec="seconds")
                db.execute(f"UPDATE sales SET settled_reconciliation_id=?,settled_at=? WHERE id IN ({placeholders}) AND settled_reconciliation_id IS NULL",(cursor.lastrowid,settled_at,*sale_ids))
            db.commit();flash("ปิดรอบแล้ว ยอดช่วงนี้ถูกตัดออกจากรอบถัดไปเรียบร้อย","success")
        except Exception:db.rollback();flash("บันทึกปิดยอดไม่สำเร็จ","error")
        return redirect(url_for("reporting.reconciliations",business_date=business_date,cashier_id=cashier_id))
    cashiers=db.execute("SELECT id,display_name FROM staff WHERE is_active=1 ORDER BY display_name").fetchall()
    summary_mode=g.staff["role_code"]!="cashier"
    if summary_mode:
        history=db.execute("""SELECT MIN(r.id) id,r.cashier_id,r.business_date,s.display_name,
            SUM(r.cash_sales_satang) cash_sales_satang,SUM(r.scan_sales_satang) scan_sales_satang,
            SUM(r.transfer_sales_satang) transfer_sales_satang,SUM(r.billed_sales_satang) billed_sales_satang,
            SUM(r.expected_cash_satang) expected_cash_satang,SUM(r.actual_cash_satang) actual_cash_satang,
            SUM(r.difference_satang) difference_satang,COUNT(*) close_count,
            SUM(CASE WHEN r.verified_by IS NOT NULL THEN 1 ELSE 0 END) verified_count,
            MAX(r.created_at) created_at FROM reconciliations r JOIN staff s ON s.id=r.cashier_id
            GROUP BY r.cashier_id,r.business_date ORDER BY r.business_date DESC,MAX(r.created_at) DESC LIMIT 100""").fetchall()
    else:
        history=db.execute("""SELECT r.*,s.display_name,v.display_name verifier_name,1 close_count,
            CASE WHEN r.verified_by IS NULL THEN 0 ELSE 1 END verified_count FROM reconciliations r
            JOIN staff s ON s.id=r.cashier_id LEFT JOIN staff v ON v.id=r.verified_by
            WHERE r.cashier_id=? ORDER BY r.business_date DESC,r.id DESC LIMIT 100""",(g.staff["id"],)).fetchall()
    bill_count=len(unsettled_sales)
    return render_template("reconciliation.html",business_date=business_date,cashier_id=cashier_id,cashiers=cashiers,cash=cash,scan=scan,transfer=transfer,billing=billing,bill_count=bill_count,history=history,summary_mode=summary_mode)


@bp.get("/billing")
@permission_required("settings.manage")
def billing_report():
    db=get_db();status=request.args.get("status","");customer_id=request.args.get("customer_id",type=int)
    where=["1=1"];params=[]
    if status in {"outstanding","partial","paid"}:where.append("b.status=?");params.append(status)
    if customer_id:where.append("b.customer_id=?");params.append(customer_id)
    rows=db.execute(f"""SELECT b.*,c.name customer_name,s.receipt_number,s.created_at sale_created_at,
        st.display_name cashier_name,(b.original_satang-b.paid_satang) balance_satang
        FROM billed_sales b JOIN billing_customers c ON c.id=b.customer_id JOIN sales s ON s.id=b.sale_id
        JOIN staff st ON st.id=s.cashier_id WHERE {' AND '.join(where)} ORDER BY b.created_at DESC""",params).fetchall()
    customers=db.execute("SELECT id,name FROM billing_customers ORDER BY name").fetchall()
    totals=db.execute(f"""SELECT COALESCE(SUM(b.original_satang),0) original,COALESCE(SUM(b.paid_satang),0) paid,
        COALESCE(SUM(CASE WHEN b.status IN ('outstanding','partial') THEN b.original_satang-b.paid_satang ELSE 0 END),0) balance
        FROM billed_sales b WHERE {' AND '.join(where)}""",params).fetchone()
    return render_template("billing_report.html",rows=rows,customers=customers,totals=totals,status=status,customer_id=customer_id,print_view=request.args.get("print")=="1")


@bp.post("/billing/<int:billed_id>/payments")
@permission_required("settings.manage")
def receive_billing_payment(billed_id):
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    db=get_db();bill=db.execute("SELECT * FROM billed_sales WHERE id=?",(billed_id,)).fetchone()
    if not bill or bill["status"] not in ("outstanding","partial"):flash("รายการนี้ไม่มียอดคงค้าง","error");return redirect(url_for("reporting.billing_report"))
    try:amount=baht_to_satang(request.form.get("amount"));balance=bill["original_satang"]-bill["paid_satang"]
    except Exception:amount=0;balance=0
    method=request.form.get("payment_method")
    if amount<=0 or amount>balance or method not in {"cash","scan","transfer"}:flash("จำนวนเงินหรือวิธีชำระไม่ถูกต้อง","error");return redirect(url_for("reporting.billing_report"))
    now=datetime.now(timezone.utc).isoformat(timespec="seconds");new_paid=bill["paid_satang"]+amount;new_status="paid" if new_paid==bill["original_satang"] else "partial"
    db.execute("INSERT INTO billed_sale_payments(billed_sale_id,amount_satang,payment_method_code,reference,note,received_by,created_at) VALUES(?,?,?,?,?,?,?)",(billed_id,amount,method,request.form.get("reference","").strip(),request.form.get("note","").strip(),g.staff["id"],now))
    db.execute("UPDATE billed_sales SET paid_satang=?,status=?,updated_at=? WHERE id=?",(new_paid,new_status,now,billed_id))
    db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,new_value,created_at) VALUES(?,'receive_billing_payment','billed_sale',?,?,?)",(g.staff["id"],billed_id,str(amount),now));db.commit();flash("บันทึกรับชำระแล้ว","success")
    return redirect(url_for("reporting.billing_report"))


@bp.post("/billing/payments/bulk")
@permission_required("settings.manage")
def receive_bulk_billing_payment():
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    try:ids=sorted({int(value) for value in request.form.getlist("billed_id")})
    except ValueError:ids=[]
    method=request.form.get("payment_method")
    if not ids or method not in {"cash","scan","transfer"}:
        flash("กรุณาเลือกรายการและวิธีรับชำระ","error");return redirect(url_for("reporting.billing_report"))
    db=get_db();placeholders=",".join("?" for _ in ids)
    bills=db.execute(f"SELECT * FROM billed_sales WHERE id IN ({placeholders}) AND status IN ('outstanding','partial')",ids).fetchall()
    if not bills:flash("รายการที่เลือกไม่มียอดคงค้าง","error");return redirect(url_for("reporting.billing_report"))
    now=datetime.now(timezone.utc).isoformat(timespec="seconds");total=0
    try:
        db.execute("BEGIN IMMEDIATE")
        for bill in bills:
            amount=bill["original_satang"]-bill["paid_satang"]
            if amount<=0:continue
            db.execute("INSERT INTO billed_sale_payments(billed_sale_id,amount_satang,payment_method_code,note,received_by,created_at) VALUES(?,?,?,?,?,?)",(bill["id"],amount,method,"รับชำระรวมรายการที่เลือก",g.staff["id"],now))
            db.execute("UPDATE billed_sales SET paid_satang=original_satang,status='paid',updated_at=? WHERE id=?",(now,bill["id"]))
            total+=amount
        db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,new_value,created_at) VALUES(?,'receive_bulk_billing_payment','billed_sale',?,?,?)",(g.staff["id"],",".join(str(b["id"]) for b in bills),str(total),now))
        db.commit();flash(f"รับชำระรายการที่เลือกครบแล้ว รวม {total/100:,.2f} บาท","success")
    except Exception:
        db.rollback();flash("รับชำระรวมไม่สำเร็จ","error")
    return redirect(url_for("reporting.billing_report"))


@bp.get("/billing/export.csv")
@permission_required("settings.manage")
def export_billing_csv():
    rows=get_db().execute("""SELECT c.name,s.receipt_number,b.created_at,b.due_date,b.original_satang,b.paid_satang,
        b.original_satang-b.paid_satang,b.status FROM billed_sales b JOIN billing_customers c ON c.id=b.customer_id JOIN sales s ON s.id=b.sale_id ORDER BY b.created_at""").fetchall()
    output=io.StringIO();writer=csv.writer(output);writer.writerow(["customer","receipt_number","created_at","due_date","original_baht","paid_baht","balance_baht","status"])
    for r in rows:writer.writerow([r[0],r[1],r[2],r[3] or "",r[4]/100,r[5]/100,r[6]/100,r[7]])
    return Response("\ufeff"+output.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=billed-sales.csv"})


@bp.post("/reconciliations/<int:reconciliation_id>/verify")
@permission_required("reports.view")
def verify_reconciliation(reconciliation_id):
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    db=get_db();row=db.execute("SELECT verified_by FROM reconciliations WHERE id=?",(reconciliation_id,)).fetchone()
    if not row:return ("ไม่พบรายการปิดยอด",404)
    if row["verified_by"]:return ("รายการนี้ยืนยันแล้ว",400)
    db.execute("UPDATE reconciliations SET verified_by=?,verified_at=?,verification_note=? WHERE id=?",(g.staff["id"],datetime.now(timezone.utc).isoformat(timespec="seconds"),request.form.get("verification_note","").strip(),reconciliation_id))
    db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,created_at) VALUES(?,'verify_reconciliation','reconciliation',?,?)",(g.staff["id"],reconciliation_id,datetime.now(timezone.utc).isoformat(timespec="seconds")))
    db.commit();flash("ยืนยันยอดที่พนักงานแจ้งแล้ว","success")
    return redirect(url_for("reporting.reconciliations"))


@bp.post("/reconciliations/verify-day")
@permission_required("reports.view")
def verify_reconciliation_day():
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    cashier_id=request.form.get("cashier_id",type=int);business_date=request.form.get("business_date","")
    if not cashier_id or not business_date:return ("ข้อมูลไม่ถูกต้อง",400)
    db=get_db();now=datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows=db.execute("SELECT id FROM reconciliations WHERE cashier_id=? AND business_date=? AND verified_by IS NULL",(cashier_id,business_date)).fetchall()
    if not rows:flash("Summary นี้ได้รับการยืนยันครบแล้ว","error");return redirect(url_for("reporting.reconciliations"))
    db.execute("UPDATE reconciliations SET verified_by=?,verified_at=?,verification_note=? WHERE cashier_id=? AND business_date=? AND verified_by IS NULL",(g.staff["id"],now,request.form.get("verification_note","").strip(),cashier_id,business_date))
    db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,new_value,created_at) VALUES(?,'verify_reconciliation_day','reconciliation',?,?,?)",(g.staff["id"],f"{cashier_id}:{business_date}",str(len(rows)),now));db.commit();flash(f"ยืนยัน Summary ครบ {len(rows)} รอบแล้ว","success")
    return redirect(url_for("reporting.reconciliations",business_date=business_date,cashier_id=cashier_id))


@bp.get("/reports")
@permission_required("reports.view")
def reports():
    db=get_db();period=request.args.get("period","daily");day=request.args.get("date") or date.today().isoformat();month=request.args.get("month") or date.today().strftime("%Y-%m")
    if period=="monthly":
        month_start=date.fromisoformat(month+"-01");next_month=(month_start.replace(day=28)+timedelta(days=4)).replace(day=1);start,_=utc_bounds(month_start.isoformat());end,_=utc_bounds(next_month.isoformat())
    else:start,end=utc_bounds(day)
    sales=db.execute("""SELECT s.*,st.display_name FROM sales s JOIN staff st ON st.id=s.cashier_id
        WHERE s.created_at>=? AND s.created_at<? ORDER BY s.created_at DESC""",(start,end)).fetchall()
    summary=db.execute("""SELECT COALESCE(SUM(total_satang),0),COALESCE(SUM(gross_profit_satang),0),COUNT(*) FROM sales
        WHERE status='completed' AND created_at>=? AND created_at<?""",(start,end)).fetchone()
    payment_totals={row["payment_method_code"]:row["total"] for row in db.execute("""SELECT payment_method_code,COALESCE(SUM(total_satang),0) total FROM sales
        WHERE status='completed' AND created_at>=? AND created_at<? GROUP BY payment_method_code""",(start,end)).fetchall()}
    top=db.execute("""SELECT product_name,SUM(quantity) qty,SUM(line_total_satang) total FROM sale_items i JOIN sales s ON s.id=i.sale_id
        WHERE s.status='completed' AND s.created_at>=? AND s.created_at<? GROUP BY product_id ORDER BY qty DESC LIMIT 10""",(start,end)).fetchall()
    low=db.execute("SELECT name_th,stock_quantity,minimum_stock FROM products WHERE is_active=1 AND stock_quantity<=minimum_stock ORDER BY stock_quantity").fetchall()
    daily=[]
    if period=="monthly":
        for row in db.execute("""SELECT substr(datetime(created_at,'+7 hours'),1,10) label,SUM(total_satang) total FROM sales WHERE status='completed' AND created_at>=? AND created_at<? GROUP BY label ORDER BY label""",(start,end)).fetchall():daily.append(row)
    return render_template("reports.html",day=day,month=month,period=period,sales=sales,summary=summary,payment_totals=payment_totals,top=top,low=low,daily=daily)


@bp.get("/reports/export.csv")
@permission_required("reports.view")
def export_csv():
    day=request.args.get("date") or date.today().isoformat();start,end=utc_bounds(day)
    rows=get_db().execute("""SELECT receipt_number,created_at,total_satang,gross_profit_satang,payment_method_code,status
        FROM sales WHERE created_at>=? AND created_at<? ORDER BY created_at""",(start,end)).fetchall()
    output=io.StringIO();writer=csv.writer(output);writer.writerow(["receipt_number","created_at","total_baht","gross_profit_baht","payment_method","status"])
    for r in rows:writer.writerow([r[0],r[1],r[2]/100,r[3]/100,r[4],r[5]])
    return Response("\ufeff"+output.getvalue(),mimetype="text/csv",headers={"Content-Disposition":f"attachment; filename=sales-{day}.csv"})
