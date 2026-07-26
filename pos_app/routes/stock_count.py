from datetime import datetime, timezone

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from ..auth import permission_required, valid_csrf
from ..database import get_db


bp=Blueprint("stock_count",__name__,url_prefix="/stock-counts")


def now_iso(): return datetime.now(timezone.utc).isoformat(timespec="seconds")


@bp.get("/product-lookup")
@permission_required("stock_count.participate")
def product_lookup():
    barcode=request.args.get("barcode","").strip()
    product=get_db().execute("SELECT id,barcode,name_th FROM products WHERE barcode=? AND is_active=1",(barcode,)).fetchone()
    if not product:return jsonify(error="ไม่พบสินค้าจากบาร์โค้ดนี้"),404
    return jsonify(id=product["id"],barcode=product["barcode"],name=product["name_th"])


@bp.get("/manual-sheet")
@permission_required("stock_count.participate")
def manual_sheet():
    db=get_db();category_id=request.args.get("category_id",type=int);params=[];where=""
    if category_id:where=" AND p.category_id=?";params.append(category_id)
    products=db.execute(f"""SELECT p.barcode,p.name_th,c.name_th category_name FROM products p JOIN categories c ON c.id=p.category_id
        WHERE p.is_active=1 {where} ORDER BY c.sort_order,c.name_th,p.name_th""",params).fetchall()
    categories=db.execute("SELECT id,name_th FROM categories WHERE is_active=1 ORDER BY sort_order,name_th").fetchall()
    return render_template("stock_count_manual.html",products=products,categories=categories,selected_category=category_id)


@bp.route("",methods=("GET","POST"))
@permission_required("stock_count.participate")
def index():
    db=get_db()
    if request.method=="POST":
        if g.staff["role_code"] not in ("admin","manager"):return ("เฉพาะผู้ดูแลระบบหรือผู้จัดการเท่านั้นที่สร้างรอบนับได้",403)
        if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
        name=request.form.get("name","").strip()
        if name:
            now=now_iso();cur=db.execute("INSERT INTO stock_count_sessions(name,created_by,created_at) VALUES(?,?,?)",(name,g.staff["id"],now));db.execute("INSERT INTO stock_count_participants VALUES(?,?,?)",(cur.lastrowid,g.staff["id"],now));db.commit();return redirect(url_for("stock_count.session",session_id=cur.lastrowid))
    rows=db.execute("""SELECT s.*,st.display_name,(SELECT COUNT(*) FROM stock_count_attempts a WHERE a.session_id=s.id) attempt_count,
        EXISTS(SELECT 1 FROM stock_count_applications x WHERE x.session_id=s.id) applied FROM stock_count_sessions s JOIN staff st ON st.id=s.created_by ORDER BY s.created_at DESC""").fetchall()
    return render_template("stock_counts.html",sessions=rows,can_manage=g.staff["role_code"] in ("admin","manager"))


@bp.route("/<int:session_id>",methods=("GET","POST"))
@permission_required("stock_count.participate")
def session(session_id):
    db=get_db();session_row=db.execute("SELECT * FROM stock_count_sessions WHERE id=?",(session_id,)).fetchone()
    if not session_row:return ("ไม่พบรอบนับ",404)
    db.execute("INSERT OR IGNORE INTO stock_count_participants VALUES(?,?,?)",(session_id,g.staff["id"],now_iso()));db.commit()
    if request.method=="POST":
        if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
        product=db.execute("SELECT * FROM products WHERE barcode=? OR id=?",(request.form.get("barcode","").strip(),request.form.get("product_id",type=int) or 0)).fetchone()
        try:counted=float(request.form.get("counted_quantity",""))
        except ValueError:counted=-1
        if not product or counted<0:flash("สินค้า หรือจำนวนไม่ถูกต้อง","error")
        else:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT status FROM stock_count_sessions WHERE id=?",(session_id,)).fetchone()[0]!="open":db.rollback();return ("รอบนับปิดแล้ว",400)
            db.execute("INSERT INTO stock_count_attempts(session_id,product_id,counter_id,counted_quantity,created_at) VALUES(?,?,?,?,?)",(session_id,product["id"],g.staff["id"],counted,now_iso()));db.commit();flash("เพิ่มการนับแล้ว สามารถนับสินค้าเดิมซ้ำได้","success")
        return redirect(url_for("stock_count.session",session_id=session_id))
    products=db.execute("SELECT id,barcode,name_th FROM products WHERE is_active=1 ORDER BY name_th").fetchall()
    attempts=db.execute("""SELECT a.id,a.product_id,a.counter_id,a.counted_quantity,a.created_at,p.barcode,p.name_th,st.display_name FROM stock_count_attempts a
        JOIN products p ON p.id=a.product_id JOIN staff st ON st.id=a.counter_id WHERE a.session_id=? ORDER BY a.created_at DESC,a.id DESC""",(session_id,)).fetchall()
    results=[]
    if session_row["status"]=="finalized":
        for result in db.execute("""SELECT r.*,p.barcode,p.name_th FROM stock_count_results r JOIN products p ON p.id=r.product_id
            WHERE r.session_id=? ORDER BY p.name_th""",(session_id,)).fetchall():
            values=db.execute("SELECT counted_quantity FROM stock_count_attempts WHERE session_id=? AND product_id=? ORDER BY created_at,id",(session_id,result["product_id"])).fetchall()
            item=dict(result);item["attempts"]=[v[0] for v in values];results.append(item)
    applied=db.execute("SELECT * FROM stock_count_applications WHERE session_id=?",(session_id,)).fetchone()
    return render_template("stock_count_session.html",session=session_row,attempts=attempts,products=products,results=results,applied=applied,can_manage=g.staff["role_code"] in ("admin","manager"))


@bp.post("/<int:session_id>/attempts/<int:attempt_id>/delete")
@permission_required("stock_count.participate")
def delete_attempt(session_id,attempt_id):
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    db=get_db();db.execute("BEGIN IMMEDIATE")
    session_row=db.execute("SELECT status FROM stock_count_sessions WHERE id=?",(session_id,)).fetchone()
    attempt=db.execute("SELECT * FROM stock_count_attempts WHERE id=? AND session_id=?",(attempt_id,session_id)).fetchone()
    if not session_row or session_row["status"]!="open":db.rollback();return ("ลบได้เฉพาะรอบที่กำลังนับ",400)
    if not attempt:db.rollback();return ("ไม่พบรายการนับ",404)
    if g.staff["role_code"]=="cashier" and attempt["counter_id"]!=g.staff["id"]:db.rollback();return ("Cashier ลบได้เฉพาะรายการนับของตัวเอง",403)
    db.execute("DELETE FROM stock_count_attempts WHERE id=?",(attempt_id,))
    db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,created_at) VALUES(?,'delete_stock_count_attempt','stock_count_attempt',?,?)",(g.staff["id"],attempt_id,now_iso()))
    db.commit();flash("ยกเลิกรายการนับแล้ว","success")
    return redirect(url_for("stock_count.session",session_id=session_id))


@bp.post("/<int:session_id>/finalize")
@permission_required("stock_count.manage")
def finalize(session_id):
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    db=get_db();db.execute("BEGIN IMMEDIATE");session_row=db.execute("SELECT * FROM stock_count_sessions WHERE id=?",(session_id,)).fetchone()
    if not session_row or session_row["status"]!="open":db.rollback();return ("รอบนับไม่ถูกต้อง",400)
    latest={}
    for row in db.execute("SELECT * FROM stock_count_attempts WHERE session_id=? ORDER BY created_at DESC,id DESC",(session_id,)).fetchall():latest.setdefault(row["product_id"],row)
    if not latest:db.rollback();flash("ยังไม่มีรายการนับ","error");return redirect(url_for("stock_count.session",session_id=session_id))
    now=now_iso()
    for product_id,attempt in latest.items():
        current=db.execute("SELECT stock_quantity FROM products WHERE id=?",(product_id,)).fetchone()[0]
        db.execute("INSERT INTO stock_count_results(session_id,product_id,system_quantity,suggested_quantity) VALUES(?,?,?,?)",(session_id,product_id,current,attempt["counted_quantity"]))
    db.execute("UPDATE stock_count_sessions SET status='finalized',finalized_by=?,finalized_at=? WHERE id=?",(g.staff["id"],now,session_id))
    db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,created_at) VALUES(?,'close_stock_count','stock_count',?,?)",(g.staff["id"],session_id,now));db.commit();flash("ปิดรอบแล้ว กรุณาตรวจ Summary ก่อนเลือกปรับสต็อก","success")
    return redirect(url_for("stock_count.session",session_id=session_id))


@bp.post("/<int:session_id>/apply")
@permission_required("stock_count.manage")
def apply_results(session_id):
    if not valid_csrf(request.form.get("csrf_token")):return ("คำขอไม่ถูกต้อง",400)
    db=get_db()
    if db.execute("SELECT 1 FROM stock_count_applications WHERE session_id=?",(session_id,)).fetchone():return ("รอบนี้ปรับสต็อกแล้ว",400)
    results=db.execute("SELECT * FROM stock_count_results WHERE session_id=?",(session_id,)).fetchall();now=now_iso()
    try:
        db.execute("BEGIN IMMEDIATE")
        for result in results:
            selected=float(request.form.get(f"quantity_{result['product_id']}",result["suggested_quantity"]))
            if selected<0:raise ValueError("จำนวนต้องไม่ติดลบ")
            product=db.execute("SELECT * FROM products WHERE id=?",(result["product_id"],)).fetchone();changed=selected-product["stock_quantity"]
            if changed:
                db.execute("UPDATE products SET stock_quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(selected,product["id"]))
                db.execute("""INSERT INTO stock_movements(product_id,movement_type,previous_quantity,changed_quantity,new_quantity,unit_cost_satang,reference_type,reference_number,staff_id,note,created_at)
                    VALUES(?,'stock_count',?,?,?,?, 'stock_count',?,?,?,?)""",(product["id"],product["stock_quantity"],changed,selected,product["cost_satang"],session_id,g.staff["id"],"อนุมัติผลนับสต็อก",now))
            db.execute("UPDATE stock_count_results SET selected_quantity=?,applied=1 WHERE session_id=? AND product_id=?",(selected,session_id,product["id"]))
        db.execute("INSERT INTO stock_count_applications VALUES(?,?,?)",(session_id,g.staff["id"],now));db.execute("INSERT INTO audit_logs(staff_id,action,entity_type,entity_id,created_at) VALUES(?,'apply_stock_count','stock_count',?,?)",(g.staff["id"],session_id,now));db.commit();flash("ปรับสต็อกตามผลที่อนุมัติแล้ว","success")
    except Exception as exc:db.rollback();flash(str(exc),"error")
    return redirect(url_for("stock_count.session",session_id=session_id))
