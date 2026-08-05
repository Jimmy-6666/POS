import base64
import gzip
import json
import os
import secrets
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    receipt_items = []
    items = db.execute(
        "SELECT *,quantity-voided_quantity AS remaining_quantity FROM sale_items WHERE sale_id=?",
        (sale_id,),
    ).fetchall()
    for item in items:
        quantity = item["remaining_quantity"]
        if quantity <= 0:
            continue
        line_total = item["line_total_satang"] * quantity // item["quantity"]
        receipt_items.append({
            "name": item["product_name"],
            "detail": f"{quantity:g} × {_money(item['unit_price_satang'])} บาท",
            "amount": _money(line_total),
            "manual_price_reference": item["manual_price_reference"] or "",
            "void_note": (
                f"Void แล้ว {item['voided_quantity']:g}"
                if item["voided_quantity"]
                else ""
            ),
        })
    store_name = settings.get("store_name") or "แสนงาม มินิมาร์ท"
    return {
        "layout": "sale_receipt_80mm",
        "printer_name": printer_name,
        "document_name": f"POS {sale['receipt_number']}",
        "store_name": store_name,
        "store_phone": settings.get("store_phone") or "",
        "logo_path": str(Path(current_app.root_path) / "static" / "img" / "receipt-logo.png"),
        "title": "ใบวางบิล" if sale["payment_method_code"] == "billing" else "ใบเสร็จรับเงิน",
        "status": sale["status"],
        "receipt_number": sale["receipt_number"],
        "receipt_datetime": _bangkok_datetime(sale["created_at"]),
        "cashier": sale["display_name"],
        "items": receipt_items,
        # Delivery is not enabled for POS receipts yet. Keep the structured
        # field for the Windows renderer, but leave it blank so no delivery
        # row is emitted; the persisted sale total remains unchanged.
        "delivery_fee": "",
        "total": _money(sale["total_satang"]),
        "payment_label": payment_label,
        "amount_received": (
            _money(sale["amount_received_satang"])
            if sale["payment_method_code"] == "cash"
            else ""
        ),
        "change": (
            _money(sale["change_satang"])
            if sale["payment_method_code"] == "cash"
            else ""
        ),
        "footer_store_name": store_name,
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
$payloadJson = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload_b64}'))
$payload = $payloadJson | ConvertFrom-Json
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Printing;
using System.Web.Script.Serialization;
public static class SaengngamReceiptPrinter {{
    public class ReceiptItem {{
        public string name {{ get; set; }}
        public string detail {{ get; set; }}
        public string amount {{ get; set; }}
        public string manual_price_reference {{ get; set; }}
        public string void_note {{ get; set; }}
    }}

    public class ReceiptPayload {{
        public string layout {{ get; set; }}
        public string printer_name {{ get; set; }}
        public string document_name {{ get; set; }}
        public string header {{ get; set; }}
        public string body {{ get; set; }}
        public string store_name {{ get; set; }}
        public string store_phone {{ get; set; }}
        public string logo_path {{ get; set; }}
        public string title {{ get; set; }}
        public string status {{ get; set; }}
        public string receipt_number {{ get; set; }}
        public string receipt_datetime {{ get; set; }}
        public string cashier {{ get; set; }}
        public List<ReceiptItem> items {{ get; set; }}
        public string delivery_fee {{ get; set; }}
        public string total {{ get; set; }}
        public string payment_label {{ get; set; }}
        public string amount_received {{ get; set; }}
        public string change {{ get; set; }}
        public string footer_store_name {{ get; set; }}
    }}

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

    private static float DrawWrapped(Graphics graphics, string text, Font font, Brush brush, RectangleF bounds) {{
        string value = text ?? "";
        SizeF measured = graphics.MeasureString(value, font, Math.Max(1, (int)bounds.Width));
        graphics.DrawString(value, font, brush, bounds);
        return measured.Height;
    }}

    private static float DrawCentered(Graphics graphics, string text, Font font, Brush brush, float x, float y, float width) {{
        using (var centered = new StringFormat() {{ Alignment = StringAlignment.Center }}) {{
            SizeF measured = graphics.MeasureString(text ?? "", font, Math.Max(1, (int)width), centered);
            graphics.DrawString(text ?? "", font, brush, new RectangleF(x, y, width, measured.Height), centered);
            return measured.Height;
        }}
    }}

    private static float DrawReceiptLogo(Graphics graphics, string logoPath, float x, float y, float width) {{
        if (String.IsNullOrWhiteSpace(logoPath) || !System.IO.File.Exists(logoPath)) return 0f;
        try {{
            using (var logo = Image.FromFile(logoPath)) {{
                const float maxLogoWidth = 180f;
                const float maxLogoHeight = 180f;
                float scale = Math.Min(
                    Math.Min(maxLogoWidth, width) / logo.Width,
                    maxLogoHeight / logo.Height
                );
                float logoWidth = logo.Width * scale;
                float logoHeight = logo.Height * scale;
                var previousInterpolation = graphics.InterpolationMode;
                graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
                graphics.DrawImage(logo, new RectangleF(x + (width - logoWidth) / 2f, y, logoWidth, logoHeight));
                graphics.InterpolationMode = previousInterpolation;
                return logoHeight;
            }}
        }} catch {{
            return 0f;
        }}
    }}

    private static float DrawLeftRight(
        Graphics graphics, string label, string value, Font leftFont, Font rightFont,
        Brush brush, float x, float y, float width
    ) {{
        const float amountWidth = 83f;
        const float columnGap = 6f;
        float leftWidth = Math.Max(1f, width - amountWidth - columnGap);
        float leftHeight = graphics.MeasureString(label ?? "", leftFont, Math.Max(1, (int)leftWidth)).Height;
        using (var right = new StringFormat() {{ Alignment = StringAlignment.Far }}) {{
            float rightHeight = graphics.MeasureString(value ?? "", rightFont, Math.Max(1, (int)amountWidth), right).Height;
            graphics.DrawString(label ?? "", leftFont, brush, new RectangleF(x, y, leftWidth, leftHeight));
            graphics.DrawString(
                value ?? "", rightFont, brush,
                new RectangleF(x + width - amountWidth, y, amountWidth, rightHeight), right
            );
            return Math.Max(leftHeight, rightHeight);
        }}
    }}

    private static void DrawLine(Graphics graphics, float x, float y, float width, DashStyle dashStyle) {{
        using (var pen = new Pen(Color.Black, 0.8f) {{ DashStyle = dashStyle }}) {{
            graphics.DrawLine(pen, x, y, x + width, y);
        }}
    }}

    private static void DrawSaleReceipt(PrintPageEventArgs args, ReceiptPayload payload) {{
        Graphics graphics = args.Graphics;
        float x = args.MarginBounds.Left;
        float width = args.MarginBounds.Width;
        float y = args.MarginBounds.Top;
        const float rowGap = 4f;

        using (var storeFont = new Font("Tahoma", 11, FontStyle.Bold))
        using (var titleFont = new Font("Tahoma", 10, FontStyle.Bold))
        using (var normalFont = new Font("Tahoma", 8, FontStyle.Regular))
        using (var labelFont = new Font("Tahoma", 8, FontStyle.Bold))
        using (var itemFont = new Font("Tahoma", 8, FontStyle.Bold))
        using (var smallFont = new Font("Tahoma", 7, FontStyle.Regular))
        using (var totalFont = new Font("Tahoma", 10, FontStyle.Bold))
        using (var footerFont = new Font("Tahoma", 9, FontStyle.Bold)) {{
            if (String.Equals(payload.status, "voided", StringComparison.OrdinalIgnoreCase)) {{
                float bannerHeight = 25f;
                graphics.DrawRectangle(Pens.Black, x, y, width, bannerHeight);
                y += DrawCentered(graphics, "VOID ทั้งบิล", titleFont, Brushes.Black, x, y + 4f, width) + 10f;
            }}

            y += DrawReceiptLogo(graphics, payload.logo_path, x, y, width) + rowGap;
            y += DrawCentered(graphics, payload.store_name, storeFont, Brushes.Black, x, y, width) + 2f;
            if (!String.IsNullOrWhiteSpace(payload.store_phone)) {{
                y += DrawCentered(graphics, "โทร. " + payload.store_phone, normalFont, Brushes.Black, x, y, width) + 1f;
            }}
            y += DrawCentered(graphics, payload.title, titleFont, Brushes.Black, x, y, width) + rowGap;

            DrawLine(graphics, x, y, width, DashStyle.Dash);
            y += rowGap;
            y += DrawWrapped(graphics, "เลขที่: " + payload.receipt_number, normalFont, Brushes.Black, new RectangleF(x, y, width, 30f));
            y += 1f;
            y += DrawWrapped(graphics, "วันที่/เวลา: " + payload.receipt_datetime, normalFont, Brushes.Black, new RectangleF(x, y, width, 30f));
            y += 1f;
            y += DrawWrapped(graphics, "แคชเชียร์: " + payload.cashier, normalFont, Brushes.Black, new RectangleF(x, y, width, 30f));
            y += rowGap;
            DrawLine(graphics, x, y, width, DashStyle.Dash);
            y += rowGap;

            y += DrawLeftRight(graphics, "รายการ", "จำนวนเงิน", labelFont, labelFont, Brushes.Black, x, y, width) + 2f;
            DrawLine(graphics, x, y, width, DashStyle.Solid);
            y += rowGap;

            foreach (ReceiptItem item in payload.items ?? new List<ReceiptItem>()) {{
                float itemStart = y;
                const float amountWidth = 83f;
                const float columnGap = 6f;
                float nameWidth = Math.Max(1f, width - amountWidth - columnGap);
                float nameHeight = DrawWrapped(
                    graphics, item.name, itemFont, Brushes.Black,
                    new RectangleF(x, itemStart, nameWidth, 80f)
                );
                using (var right = new StringFormat() {{ Alignment = StringAlignment.Far }}) {{
                    graphics.DrawString(
                        item.amount ?? "", normalFont, Brushes.Black,
                        new RectangleF(x + width - amountWidth, itemStart, amountWidth, 30f), right
                    );
                }}
                y = itemStart + nameHeight + 1f;
                y += DrawWrapped(graphics, item.detail, smallFont, Brushes.Black, new RectangleF(x, y, nameWidth, 30f));
                if (!String.IsNullOrWhiteSpace(item.manual_price_reference)) {{
                    y += DrawWrapped(
                        graphics, "อ้างอิงราคา: " + item.manual_price_reference,
                        smallFont, Brushes.Black, new RectangleF(x, y, nameWidth, 30f)
                    );
                }}
                if (!String.IsNullOrWhiteSpace(item.void_note)) {{
                    y += DrawWrapped(graphics, item.void_note, labelFont, Brushes.Black, new RectangleF(x, y, nameWidth, 30f));
                }}
                y += 2f;
                DrawLine(graphics, x, y, width, DashStyle.Dot);
                y += rowGap;
            }}

            DrawLine(graphics, x, y, width, DashStyle.Solid);
            y += rowGap;
            if (!String.IsNullOrWhiteSpace(payload.delivery_fee)) {{
                y += DrawLeftRight(
                    graphics, "ค่าจัดส่ง", payload.delivery_fee + " บาท",
                    normalFont, normalFont, Brushes.Black, x, y, width
                ) + rowGap;
                DrawLine(graphics, x, y, width, DashStyle.Solid);
                y += rowGap;
            }}
            y += DrawLeftRight(
                graphics, "รวม", payload.total + " บาท",
                totalFont, totalFont, Brushes.Black, x, y, width
            ) + rowGap;
            DrawLine(graphics, x, y, width, DashStyle.Solid);
            y += rowGap;
            y += DrawLeftRight(
                graphics, "ชำระโดย", payload.payment_label,
                normalFont, normalFont, Brushes.Black, x, y, width
            ) + rowGap;
            if (!String.IsNullOrWhiteSpace(payload.amount_received)) {{
                y += DrawLeftRight(
                    graphics, "รับเงิน", payload.amount_received,
                    normalFont, normalFont, Brushes.Black, x, y, width
                ) + rowGap;
                y += DrawLeftRight(
                    graphics, "เงินทอน", payload.change,
                    normalFont, normalFont, Brushes.Black, x, y, width
                ) + rowGap;
            }}

            y += rowGap;
            y += DrawCentered(graphics, "ขอบคุณที่ใช้บริการ", footerFont, Brushes.Black, x, y, width);
            DrawCentered(graphics, payload.footer_store_name, normalFont, Brushes.Black, x, y, width);
        }}
    }}

    private static void DrawLegacyDocument(PrintPageEventArgs args, ReceiptPayload payload) {{
        float x = args.MarginBounds.Left;
        float width = args.MarginBounds.Width;
        float y = args.MarginBounds.Top;
        using (var title = new Font("Tahoma", 11, FontStyle.Bold))
        using (var content = new Font("Tahoma", 8, FontStyle.Regular))
        using (var centered = new StringFormat() {{ Alignment = StringAlignment.Center }}) {{
            var headerBox = new RectangleF(x, y, width, args.MarginBounds.Height);
            args.Graphics.DrawString(payload.header, title, Brushes.Black, headerBox, centered);
            y += args.Graphics.MeasureString(payload.header, title, (int)width).Height + 4;
            var bodyBox = new RectangleF(x, y, width, args.MarginBounds.Bottom - y);
            args.Graphics.DrawString(payload.body, content, Brushes.Black, bodyBox);
        }}
    }}

    public static void Print(string payloadJson) {{
        var payload = new JavaScriptSerializer().Deserialize<ReceiptPayload>(payloadJson);
        var document = new PrintDocument();
        document.PrinterSettings.PrinterName = payload.printer_name;
        if (!document.PrinterSettings.IsValid) throw new InvalidOperationException("Printer unavailable");
        document.DocumentName = payload.document_name;
        document.PrintController = new StandardPrintController();
        bool isSaleReceipt = String.Equals(payload.layout, "sale_receipt_80mm", StringComparison.Ordinal);
        if (isSaleReceipt) {{
            // POS-80 drivers expose an 80 mm roll as a 72 mm printable form:
            // the remaining 4 mm at each side is the roll's hardware margin.
            // Asking this driver for an 80 mm printable canvas clips the right
            // edge after the software applies its own side margins.
            PaperSize receiptPaper = new PaperSize("80(72)mm x 297mm", 283, 1169);
            foreach (PaperSize available in document.PrinterSettings.PaperSizes) {{
                if (available.Width == 283 && available.Height == 1169) {{
                    receiptPaper = available;
                    break;
                }}
            }}
            document.DefaultPageSettings.Landscape = false;
            document.DefaultPageSettings.PaperSize = receiptPaper;
            document.DefaultPageSettings.Margins = new Margins(0, 0, 16, 16);
        }} else {{
            document.DefaultPageSettings.Margins = new Margins(3, 3, 3, 3);
        }}
        document.PrintPage += (sender, args) => {{
            if (isSaleReceipt) DrawSaleReceipt(args, payload);
            else DrawLegacyDocument(args, payload);
            args.HasMorePages = false;
        }};
        document.Print();
    }}
}}
'@ -ReferencedAssemblies System.Drawing,System.Web.Extensions
try {{
    # Keep the original single drawer pulse before the receipt job.
    $drawer = [byte[]](0x1B,0x40,0x1B,0x70,0,25,250)
    [SaengngamReceiptPrinter]::SendRaw([string]$payload.printer_name, $drawer)
}} catch {{
    # Optional RAW drawer support must never suppress the receipt.
}}
# The approved logo is embedded in the GDI receipt above.  The POS-80 stored
# logo RAW command is not reliable from the SYSTEM production service, and a
# separate RAW fallback can duplicate the logo for interactive printer users.
[SaengngamReceiptPrinter]::Print($payloadJson)
"""
    compressed_script = base64.b64encode(gzip.compress(script.encode("utf-16le"), compresslevel=9)).decode("ascii")
    bootstrap = f"""
$compressed = [Convert]::FromBase64String('{compressed_script}')
$compressedStream = [IO.MemoryStream]::new($compressed)
$gzipStream = [IO.Compression.GzipStream]::new($compressedStream, [IO.Compression.CompressionMode]::Decompress)
$reader = [IO.StreamReader]::new($gzipStream, [Text.Encoding]::Unicode)
Invoke-Expression $reader.ReadToEnd()
"""
    encoded = base64.b64encode(bootstrap.encode("utf-16le")).decode("ascii")
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
