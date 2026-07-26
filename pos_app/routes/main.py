from datetime import datetime, timedelta, timezone
from flask import Blueprint, g, jsonify, render_template

from ..database import get_db
from ..auth import login_required


bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def index():
    db = get_db()
    store_name = db.execute(
        "SELECT value FROM settings WHERE key = ?", ("store_name",)
    ).fetchone()[0]
    permissions = db.execute(
        """SELECT p.code, p.name_th FROM role_permissions rp
           JOIN roles r ON r.id = rp.role_id
           JOIN permissions p ON p.id = rp.permission_id
           WHERE r.code = ? ORDER BY p.name_th""",
        (g.staff["role_code"],),
    ).fetchall()
    local_now=datetime.now(timezone(timedelta(hours=7)));local_start=local_now.replace(hour=0,minute=0,second=0,microsecond=0)
    start=local_start.astimezone(timezone.utc).isoformat(timespec="seconds");end=(local_start+timedelta(days=1)).astimezone(timezone.utc).isoformat(timespec="seconds")
    today=db.execute("""SELECT COALESCE(SUM(total_satang),0) sales,COALESCE(SUM(gross_profit_satang),0) profit,COUNT(*) bills
        FROM sales WHERE status='completed' AND created_at>=? AND created_at<?""",(start,end)).fetchone()
    payments={r["payment_method_code"]:r["total"] for r in db.execute("""SELECT payment_method_code,SUM(total_satang) total FROM sales
        WHERE status='completed' AND created_at>=? AND created_at<? GROUP BY payment_method_code""",(start,end)).fetchall()}
    low_count=db.execute("SELECT COUNT(*) FROM products WHERE is_active=1 AND stock_quantity<=minimum_stock").fetchone()[0]
    seven_days=[]
    for offset in range(6,-1,-1):
        day_start=local_start-timedelta(days=offset);day_end=day_start+timedelta(days=1)
        value=db.execute("SELECT COALESCE(SUM(total_satang),0) FROM sales WHERE status='completed' AND created_at>=? AND created_at<?",(day_start.astimezone(timezone.utc).isoformat(timespec="seconds"),day_end.astimezone(timezone.utc).isoformat(timespec="seconds"))).fetchone()[0]
        seven_days.append({"label":day_start.strftime("%d/%m"),"value":value})
    max_sales=max((d["value"] for d in seven_days),default=0) or 1
    month_start=local_start.replace(day=1);next_month=(month_start.replace(day=28)+timedelta(days=4)).replace(day=1)
    month=db.execute("""SELECT COALESCE(SUM(total_satang),0) sales,COALESCE(SUM(gross_profit_satang),0) profit,COUNT(*) bills FROM sales
        WHERE status='completed' AND created_at>=? AND created_at<?""",(month_start.astimezone(timezone.utc).isoformat(timespec="seconds"),next_month.astimezone(timezone.utc).isoformat(timespec="seconds"))).fetchone()
    return render_template("index.html", store_name=store_name, permissions=permissions,today=today,month=month,payment_totals=payments,low_count=low_count,seven_days=seven_days,max_sales=max_sales)


@bp.get("/health")
def health():
    get_db().execute("SELECT 1").fetchone()
    return jsonify(status="ok", database="ready")
