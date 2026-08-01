import base64
import json
import os
import secrets
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import current_app, url_for

from ..database import get_db
from .print_diagnostics import record_print_event


# Thailand uses a fixed UTC+7 offset (no DST).  Use a fixed offset here rather
# than ZoneInfo so the bundled/runtime Python does not require an external
# tzdata package just to render a receipt.
BANGKOK = timezone(timedelta(hours=7), "Asia/Bangkok")


class PrintJobQueue:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def enqueue(self, document_type, entity_id):
        job_id = secrets.token_urlsafe(18)
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "document_type": document_type,
                "entity_id": int(entity_id),
                "status": "pending",
                "claimed_at": None,
            }
        return job_id

    def claim(self):
        now = time.monotonic()
        with self._lock:
            for job in self._jobs.values():
                if job["status"] == "pending" or (
                    job["status"] == "claimed" and now - job["claimed_at"] > 30
                ):
                    job["status"] = "claimed"
                    job["claimed_at"] = now
                    return dict(job)
        return None

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def acknowledge(self, job_id):
        with self._lock:
            return self._jobs.pop(job_id, None) is not None


def init_app(app):
    app.extensions["print_jobs"] = PrintJobQueue()


def enqueue_print(document_type, entity_id):
    if current_app.config.get("DIRECT_WINDOWS_PRINTING"):
        return enqueue_direct_windows_print(document_type, entity_id)
    if not current_app.config.get("PRINT_AGENT_TOKEN"):
        record_print_event(
            "queue_unavailable",
            source="server",
            details={"document_type": document_type, "entity_id": entity_id, "reason": "print-agent-token-missing"},
        )
        return None
    job_id = current_app.extensions["print_jobs"].enqueue(document_type, entity_id)
    record_print_event(
        "queue_created",
        source="server",
        details={"job_id": job_id, "document_type": document_type, "entity_id": entity_id},
    )
    return job_id


def _money(satang):
    return f"{int(satang or 0) / 100:,.2f}"


def _bangkok_datetime(value):
    text = str(value or "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(BANGKOK).strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError, ValueError):
        return text


def _sale_receipt_payload(sale_id, printer_name):
    db = get_db()
    settings = dict(db.execute("SELECT key,value FROM settings").fetchall())
    sale = db.execute(
        "SELECT s.*,st.display_name FROM sales s JOIN staff st ON st.id=s.cashier_id WHERE s.id=?",
        (sale_id,),
    ).fetchone()
    if not sale:
        raise ValueError("sale not found")
    payment_label = {
        "cash": "เงินสด",
        "scan": "สแกนจ่าย",
        "transfer": "โอนเงิน",
        "billing": "วางบิล",
    }.get(sale["payment_method_code"], sale["payment_method_code"])
    lines = ["-" * 32]
    items = db.execute(
        "SELECT *,quantity-voided_quantity AS remaining_quantity FROM sale_items WHERE sale_id=?",
        (sale_id,),
    ).fetchall()
    for item in items:
        quantity = item["remaining_quantity"]
        if quantity <= 0:
            continue
        line_total = item["line_total_satang"] * quantity // item["quantity"]
        lines.extend((
            item["product_name"],
            f" {quantity:g} x {_money(item['unit_price_satang'])} = {_money(line_total)}",
        ))
    lines.extend((
        "-" * 32,
        f"รวม              {_money(sale['total_satang'])} บาท",
        f"ชำระโดย          {payment_label}",
    ))
    if sale["payment_method_code"] == "cash":
        lines.extend((
            f"รับเงิน           {_money(sale['amount_received_satang'])}",
            f"เงินทอน          {_money(sale['change_satang'])}",
        ))
    lines.extend(("-" * 32, "ขอบคุณที่ใช้บริการ"))
    return {
        "printer_name": printer_name,
        "document_name": f"POS {sale['receipt_number']}",
        "header": "\n".join((
            settings.get("store_name") or "แสนงาม มินิมาร์ท",
            "ใบเสร็จรับเงิน",
            sale["receipt_number"],
            _bangkok_datetime(sale["created_at"]),
            f"แคชเชียร์: {sale['display_name']}",
        )),
        "body": "\n".join(lines),
    }


def _checked_order_payload(order_id, printer_name):
    db = get_db()
    settings = dict(db.execute("SELECT key,value FROM settings").fetchall())
    order = db.execute(
        """SELECT o.*,c.phone_normalized,c.display_name FROM online_orders o
           JOIN customers c ON c.id=o.customer_id WHERE o.id=?""",
        (order_id,),
    ).fetchone()
    if not order:
        raise ValueError("online order not found")
    lines = ["-" * 32]
    items = db.execute(
        "SELECT * FROM online_order_items WHERE order_id=? AND is_removed=0 ORDER BY id",
        (order_id,),
    ).fetchall()
    for item in items:
        lines.extend((
            item["product_name_snapshot"],
            f" {item['ordered_quantity']:g} x {_money(item['unit_price_satang'])} = {_money(item['line_total_satang'])}",
        ))
    lines.extend((
        "-" * 32,
        f"สินค้า            {_money(order['subtotal_satang'])} บาท",
        f"ค่าจัดส่ง         {_money(order['delivery_fee_satang'])} บาท",
        f"รวม              {_money(order['total_satang'])} บาท",
        "-" * 32,
        "ตรวจสินค้าครบแล้ว",
    ))
    return {
        "printer_name": printer_name,
        "document_name": f"POS {order['order_number']}",
        "header": "\n".join((
            settings.get("store_name") or "แสนงาม มินิมาร์ท",
            "ใบสรุปออเดอร์",
            order["order_number"],
            _bangkok_datetime(order["reconciliation_completed_at"] or order["created_at"]),
        )),
        "body": "\n".join(lines),
    }


def _windows_gdi_command(payload):
    payload_b64 = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    script = f"""
$payload = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload_b64}')) | ConvertFrom-Json
Add-Type -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Printing;
public static class SaengngamReceiptPrinter {{
    private class DocInfo {{
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.LPWStr)] public string pDocName = null;
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.LPWStr)] public string pOutputFile = null;
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.LPWStr)] public string pDataType = null;
    }}
    [System.Runtime.InteropServices.DllImport("winspool.drv", EntryPoint="OpenPrinterW", CharSet=System.Runtime.InteropServices.CharSet.Unicode, SetLastError=true)]
    private static extern bool OpenPrinter(string name, out IntPtr handle, IntPtr defaults);
    [System.Runtime.InteropServices.DllImport("winspool.drv", SetLastError=true)] private static extern bool ClosePrinter(IntPtr handle);
    [System.Runtime.InteropServices.DllImport("winspool.drv", EntryPoint="StartDocPrinterW", CharSet=System.Runtime.InteropServices.CharSet.Unicode, SetLastError=true)]
    private static extern int StartDocPrinter(IntPtr handle, int level, [System.Runtime.InteropServices.In] DocInfo info);
    [System.Runtime.InteropServices.DllImport("winspool.drv", SetLastError=true)] private static extern bool EndDocPrinter(IntPtr handle);
    [System.Runtime.InteropServices.DllImport("winspool.drv", SetLastError=true)] private static extern bool StartPagePrinter(IntPtr handle);
    [System.Runtime.InteropServices.DllImport("winspool.drv", SetLastError=true)] private static extern bool EndPagePrinter(IntPtr handle);
    [System.Runtime.InteropServices.DllImport("winspool.drv", SetLastError=true)] private static extern bool WritePrinter(IntPtr handle, byte[] bytes, int count, out int written);

    public static void SendRaw(string printerName, byte[] payload) {{
        IntPtr handle;
        if (!OpenPrinter(printerName, out handle, IntPtr.Zero)) throw new InvalidOperationException("Printer unavailable");
        try {{
            var info = new DocInfo {{ pDocName = "Saengngam POS drawer and logo", pDataType = "RAW" }};
            if (StartDocPrinter(handle, 1, info) == 0) throw new InvalidOperationException("RAW print job unavailable");
            try {{
                if (!StartPagePrinter(handle)) throw new InvalidOperationException("RAW print page unavailable");
                try {{ int written; if (!WritePrinter(handle, payload, payload.Length, out written)) throw new InvalidOperationException("RAW print write failed"); }}
                finally {{ EndPagePrinter(handle); }}
            }} finally {{ EndDocPrinter(handle); }}
        }} finally {{ ClosePrinter(handle); }}
    }}

    public static void Print(string printerName, string documentName, string header, string body) {{
        var document = new PrintDocument();
        document.PrinterSettings.PrinterName = printerName;
        if (!document.PrinterSettings.IsValid) throw new InvalidOperationException("Printer unavailable");
        document.DocumentName = documentName;
        document.PrintController = new StandardPrintController();
        document.DefaultPageSettings.Margins = new Margins(3, 3, 3, 3);
        document.PrintPage += (sender, args) => {{
            float x = args.MarginBounds.Left;
            float width = args.MarginBounds.Width;
            float y = args.MarginBounds.Top;
            using (var title = new Font("Tahoma", 11, FontStyle.Bold))
            using (var content = new Font("Tahoma", 8, FontStyle.Regular))
            using (var centered = new StringFormat() {{ Alignment = StringAlignment.Center }}) {{
                var headerBox = new RectangleF(x, y, width, args.MarginBounds.Height);
                args.Graphics.DrawString(header, title, Brushes.Black, headerBox, centered);
                y += args.Graphics.MeasureString(header, title, (int)width).Height + 4;
                var bodyBox = new RectangleF(x, y, width, args.MarginBounds.Bottom - y);
                args.Graphics.DrawString(body, content, Brushes.Black, bodyBox);
            }}
            args.HasMorePages = false;
        }};
        document.Print();
    }}
}}
'@ -ReferencedAssemblies System.Drawing
try {{
    # Keep the original single drawer pulse before the receipt job.
    $drawer = [byte[]](0x1B,0x40,0x1B,0x70,0,25,250)
    [SaengngamReceiptPrinter]::SendRaw([string]$payload.printer_name, $drawer)
}} catch {{
    # Optional RAW drawer support must never suppress the receipt.
}}
try {{
    # Print the printer-stored logo before the GDI receipt.  This is a
    # separate RAW job so a driver that accepts GDI but rejects one combined
    # job cannot prevent the receipt from printing.
    $logo = [byte[]](0x1B,0x40,0x1B,0x74,20,0x1C,0x70,1,0,0x0A)
    [SaengngamReceiptPrinter]::SendRaw([string]$payload.printer_name, $logo)
}} catch {{
    # Logo support is optional; receipt output remains authoritative.
}}
[SaengngamReceiptPrinter]::Print([string]$payload.printer_name, [string]$payload.document_name, [string]$payload.header, [string]$payload.body)
"""
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-EncodedCommand", encoded,
    ]


def _direct_windows_print_worker(app, job_id, document_type, entity_id):
    with app.app_context():
        try:
            printer_name = app.config.get("DIRECT_WINDOWS_PRINTER") or "POSPrinter POS-80"
            if document_type == "sale_receipt":
                payload = _sale_receipt_payload(entity_id, printer_name)
            elif document_type == "checked_order":
                payload = _checked_order_payload(entity_id, printer_name)
            else:
                raise ValueError("unsupported print document")
            completed = subprocess.run(
                _windows_gdi_command(payload),
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"PowerShell exit {completed.returncode}")
            record_print_event(
                "direct_driver_submitted",
                source="windows-gdi",
                details={"job_id": job_id, "document_type": document_type, "entity_id": entity_id, "printer": printer_name},
            )
        except Exception as exc:
            record_print_event(
                "direct_driver_failed",
                source="windows-gdi",
                details={"job_id": job_id, "document_type": document_type, "entity_id": entity_id, "error": type(exc).__name__},
            )


def enqueue_direct_windows_print(document_type, entity_id):
    if os.name != "nt":
        return None
    job_id = secrets.token_urlsafe(18)
    app = current_app._get_current_object()
    record_print_event(
        "direct_driver_queued",
        source="server",
        details={"job_id": job_id, "document_type": document_type, "entity_id": entity_id},
    )
    worker = threading.Thread(
        target=_direct_windows_print_worker,
        args=(app, job_id, document_type, int(entity_id)),
        name=f"pos-print-{job_id[:8]}",
        daemon=True,
    )
    worker.start()
    return job_id


def claim_print():
    job = current_app.extensions["print_jobs"].claim()
    if not job:
        return None
    record_print_event(
        "queue_claimed",
        source="server",
        details={"job_id": job["id"], "document_type": job["document_type"], "entity_id": job["entity_id"]},
    )
    job["render_url"] = url_for("print_agent.render_job", job_id=job["id"])
    return job


def get_print_job(job_id):
    return current_app.extensions["print_jobs"].get(job_id)


def acknowledge_print(job_id):
    acknowledged = current_app.extensions["print_jobs"].acknowledge(job_id)
    record_print_event(
        "queue_acknowledged" if acknowledged else "queue_acknowledge_missing",
        source="server",
        details={"job_id": job_id},
    )
    return acknowledged
