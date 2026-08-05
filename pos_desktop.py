"""Friendly Windows launcher for Saengngam Minimart POS 3.1.8."""
import ctypes
import importlib.util
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from pathlib import Path
from ctypes import wintypes
from tkinter import messagebox
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent


def _load_runtime_paths():
    """Load the standalone runtime helper without bootstrapping Flask."""
    module_name = "_saengngam_runtime_paths"
    module_path = ROOT / "pos_app" / "runtime_paths.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load runtime helper: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_runtime_paths = _load_runtime_paths()
DEFAULT_LAN_NETWORKS = _runtime_paths.DEFAULT_LAN_NETWORKS
DEFAULT_SERVER_IP = _runtime_paths.DEFAULT_SERVER_IP
RuntimePaths = _runtime_paths.RuntimePaths
load_runtime_config = _runtime_paths.load_runtime_config

RUNTIME_PATHS = RuntimePaths.from_root(os.environ.get("POS_RUNTIME_ROOT", ROOT / "runtime"))
RUNTIME = RUNTIME_PATHS.root
PROFILE_ROOT = Path(os.environ.get("POS_DESKTOP_PROFILE_ROOT", RUNTIME)).expanduser().resolve()
BROWSER_PROFILE = PROFILE_ROOT / "browser-profile"
PRINT_BROWSER_PROFILE = PROFILE_ROOT / "print-browser-profile"
PRINT_DIAGNOSTICS_LOG = PROFILE_ROOT / "print-diagnostics.log"
RECEIPT_PRINTER_NAME = os.environ.get("POS_RECEIPT_PRINTER", "POSPrinter POS-80").strip()
RUNTIME_CONFIG = load_runtime_config(ROOT, {**os.environ, "POS_RUNTIME_ROOT": str(RUNTIME)})
STATE_FILE = Path(
    os.environ.get("POS_DISPLAY_STATE_FILE", RUNTIME_PATHS.display_state)
).expanduser().resolve()
LOG_FILE = RUNTIME_PATHS.launcher_log
PORT = int(os.environ.get("POS_PORT", "8002"))
ATTACH_ONLY = str(os.environ.get("POS_DESKTOP_ATTACH_ONLY", "")).lower() in {"1", "true", "yes"}
EXTERNAL_PRINT_AGENT = str(os.environ.get("POS_EXTERNAL_PRINT_AGENT", "")).lower() in {"1", "true", "yes"}
DIRECT_WINDOWS_PRINTING = str(os.environ.get("POS_DIRECT_WINDOWS_PRINTING", "")).lower() in {"1", "true", "yes"}
URL = f"http://127.0.0.1:{PORT}"
SERVER_IP = os.environ.get("POS_SERVER_IP", RUNTIME_CONFIG.server_ip or DEFAULT_SERVER_IP)
LAN_NETWORKS = os.environ.get("POS_LAN_NETWORKS", RUNTIME_CONFIG.lan_networks or DEFAULT_LAN_NETWORKS)
LAN_URL = f"http://{SERVER_IP}:{PORT}"
LAUNCHER_TITLE = os.environ.get("POS_LAUNCHER_TITLE", "Saengngam POS 3.1.8")
MUTEX_NAME = os.environ.get("POS_LAUNCHER_MUTEX", "SaengngamPOS306DesktopLauncher")
CREATE_NO_WINDOW = 0x08000000
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
SW_MAXIMIZE = 3
VK_F11 = 0x7A
KEYEVENTF_KEYUP = 0x0002
GWL_STYLE = -16
WS_CAPTION = 0x00C00000


def load_print_agent_token():
    configured = os.environ.get("POS_PRINT_AGENT_TOKEN", "").strip()
    if configured:
        return configured
    try:
        saved = RUNTIME_PATHS.print_agent_token.read_text(encoding="ascii").strip()
    except OSError:
        saved = ""
    if saved:
        return saved
    return "" if ATTACH_ONLY else secrets.token_urlsafe(32)


def main_browser_args(browser_exe, profile):
    return [
        str(browser_exe), f"--app={URL}", "--new-window", "--window-size=1100,760",
        "--window-position=80,60", f"--user-data-dir={profile}", "--no-first-run",
        "--no-default-browser-check", "--disable-session-crashed-bubble",
        "--disable-save-password-bubble", "--disable-background-mode", "--disable-sync",
        "--disable-signin-promo",
        "--disable-features=PasswordManagerOnboarding,PasswordLeakDetection,AutofillEnableAccountWalletStorage",
    ]


def print_browser_args(browser_exe, profile, token, desktop_user):
    return [
        str(browser_exe), f"--app={URL}/print-agent?token={quote(token)}&desktop_user={quote(desktop_user)}", "--new-window",
        "--window-size=320,240", "--window-position=-32000,-32000",
        f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
        "--disable-session-crashed-bubble", "--kiosk-printing",
        "--disable-save-password-bubble", "--disable-background-mode", "--disable-sync",
        "--disable-signin-promo",
    ]


def record_launcher_print_event(event, **details):
    """Best-effort local diagnostics for per-user Windows printer setup."""
    try:
        safe_details = {
            str(key): str(value).replace("\r", " ").replace("\n", " ").replace("|", "/")[:180]
            for key, value in details.items()
        }
        parts = [
            time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source=desktop-launcher",
            f"event={event}",
        ]
        parts.extend(f"{key}={value}" for key, value in safe_details.items())
        PRINT_DIAGNOSTICS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with PRINT_DIAGNOSTICS_LOG.open("a", encoding="utf-8") as stream:
            stream.write(" | ".join(parts) + "\n")
    except OSError:
        # Printer setup must never prevent POS from opening or recording a sale.
        pass


def configure_attach_only_default_printer(desktop_user):
    """Set the driver-backed receipt printer in the standard POS profile only."""
    if not ATTACH_ONLY or not RECEIPT_PRINTER_NAME:
        return
    try:
        legacy_mode = subprocess.run(
            [
                "reg.exe", "add", r"HKCU\Software\Microsoft\Windows NT\CurrentVersion\Windows",
                "/v", "LegacyDefaultPrinterMode", "/t", "REG_DWORD", "/d", "1", "/f",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
        printer_mode = subprocess.run(
            ["rundll32.exe", "printui.dll,PrintUIEntry", "/y", "/n", RECEIPT_PRINTER_NAME],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
        record_launcher_print_event(
            "default_printer_configured",
            desktop_user=desktop_user,
            printer=RECEIPT_PRINTER_NAME,
            registry_exit=legacy_mode.returncode,
            printer_exit=printer_mode.returncode,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        record_launcher_print_event(
            "default_printer_configuration_failed",
            desktop_user=desktop_user,
            printer=RECEIPT_PRINTER_NAME,
            error=type(exc).__name__,
        )


class PosDesktop:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(LAUNCHER_TITLE)
        self.root.geometry("560x340")
        self.root.minsize(520, 320)
        self.root.configure(bg="#eef4ef")
        self.server = None
        self.browser_process = None
        self.print_browser_process = None
        self.browser_hwnd = None
        self.print_browser_hwnd = None
        self.browser_exe = self.find_browser()
        self.attach_only = ATTACH_ONLY
        self.print_agent_token = load_print_agent_token() if self.browser_exe else ""
        self.desktop_user = os.environ.get("USERNAME", "unknown")
        self.known_chrome_windows = set(self.chrome_windows())
        self.fullscreen = False
        self.last_state_stamp = None
        self.closing = False
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        RUNTIME.mkdir(parents=True, exist_ok=True)
        self.write_state("normal")
        threading.Thread(target=self.start_server, daemon=True).start()
        self.root.after(500, self.poll_display_state)

    def build_ui(self):
        header = tk.Frame(self.root, bg="#0b3d2a", height=82)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="แสนงาม มินิมาร์ท", fg="white", bg="#0b3d2a", font=("Tahoma", 20, "bold")).pack(anchor="w", padx=24, pady=(15, 0))
        tk.Label(header, text="POS Desktop Launcher · Version 3.1.8", fg="#cce6d5", bg="#0b3d2a", font=("Tahoma", 9)).pack(anchor="w", padx=25)

        content = tk.Frame(self.root, bg="#eef4ef")
        content.pack(fill="both", expand=True, padx=24, pady=20)
        self.status_dot = tk.Label(content, text="●", fg="#b57612", bg="#eef4ef", font=("Tahoma", 16))
        self.status_dot.grid(row=0, column=0, sticky="w")
        self.status = tk.Label(content, text="กำลังเริ่มระบบ…", fg="#24372c", bg="#eef4ef", font=("Tahoma", 12, "bold"))
        self.status.grid(row=0, column=1, sticky="w", padx=(5, 0))
        tk.Label(content, text=f"เครื่องหลัก: {URL} · เครื่องอื่น/iPad: {LAN_URL}", fg="#617067", bg="#eef4ef", font=("Tahoma", 10)).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 18))

        self.open_button = tk.Button(content, text="เปิดหน้าร้าน", command=self.open_browser, state="disabled", bg="#176b46", fg="white", activebackground="#0d4b30", activeforeground="white", relief="flat", font=("Tahoma", 11, "bold"), padx=20, pady=11, cursor="hand2")
        self.open_button.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.normal_button = tk.Button(content, text="หน้าต่างปกติ", command=lambda: self.apply_display("normal"), bg="white", fg="#164a35", relief="solid", bd=1, font=("Tahoma", 10, "bold"), pady=9, cursor="hand2")
        self.normal_button.grid(row=3, column=0, sticky="ew", pady=(10, 0), padx=(0, 5))
        self.full_button = tk.Button(content, text="เต็มหน้าจอ", command=lambda: self.apply_display("fullscreen"), bg="white", fg="#164a35", relief="solid", bd=1, font=("Tahoma", 10, "bold"), pady=9, cursor="hand2")
        self.full_button.grid(row=3, column=1, sticky="ew", pady=(10, 0), padx=5)
        stop_label = "ปิด Launcher" if self.attach_only else "ปิดระบบ"
        self.stop_button = tk.Button(content, text=stop_label, command=self.close, bg="#f9e7e7", fg="#8b2020", relief="solid", bd=1, font=("Tahoma", 10, "bold"), pady=9, cursor="hand2")
        self.stop_button.grid(row=3, column=2, sticky="ew", pady=(10, 0), padx=(5, 0))
        self.print_log_button = tk.Button(content, text="เปิด Log การพิมพ์", command=self.open_print_diagnostics, bg="white", fg="#164a35", relief="solid", bd=1, font=("Tahoma", 10, "bold"), pady=8, cursor="hand2")
        self.print_log_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        for column in range(3):
            content.grid_columnconfigure(column, weight=1)
        tk.Label(content, text="Login จะเปิดเป็นหน้าต่างปกติ · Login สำเร็จจะเต็มจอ · Logout จะกลับเป็นหน้าต่างปกติ", fg="#65746b", bg="#eef4ef", wraplength=500, justify="left", font=("Tahoma", 9)).grid(row=5, column=0, columnspan=3, sticky="w", pady=(16, 0))

    def find_browser(self):
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        return next((path for path in candidates if path.is_file()), None)

    def start_server(self):
        if self.attach_only:
            try:
                if not self.print_agent_token:
                    raise RuntimeError("print-agent token is unavailable")
                for _ in range(40):
                    try:
                        with urllib.request.urlopen(f"{URL}/health", timeout=1) as response:
                            if response.status == 200:
                                self.root.after(0, self.server_ready)
                                return
                    except Exception:
                        time.sleep(0.3)
                raise RuntimeError("Production server is not ready")
            except Exception as exc:
                self.root.after(0, lambda: self.server_failed(str(exc)))
            return
        env = os.environ.copy()
        env.update(
            POS_PORT=str(PORT), POS_RUNTIME_ROOT=str(RUNTIME),
            POS_DISPLAY_STATE_FILE=str(STATE_FILE), POS_PRINT_AGENT_TOKEN=self.print_agent_token,
            POS_BIND_HOST="0.0.0.0", POS_SERVER_IP=SERVER_IP,
            POS_LAN_ACCESS_ENABLED="1", POS_LAN_NETWORKS=LAN_NETWORKS,
            POS_APP_VERSION="3.1.8",
        )
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            log = LOG_FILE.open("a", encoding="utf-8")
            self.server = subprocess.Popen(
                [sys.executable, "-m", "pos_app.launcher"], cwd=ROOT, env=env,
                stdout=log, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW,
            )
            for _ in range(40):
                if self.server.poll() is not None:
                    raise RuntimeError("server process stopped")
                try:
                    with urllib.request.urlopen(f"{URL}/health", timeout=1) as response:
                        if response.status == 200:
                            self.root.after(0, self.server_ready)
                            return
                except Exception:
                    time.sleep(0.3)
            raise RuntimeError("server startup timed out")
        except Exception as exc:
            self.root.after(0, lambda: self.server_failed(str(exc)))

    def server_ready(self):
        self.status.config(text="ระบบพร้อมใช้งาน")
        self.status_dot.config(fg="#218455")
        self.open_button.config(state="normal")
        self.open_browser()

    def server_failed(self, detail):
        self.status.config(text="ไม่สามารถเริ่มระบบได้")
        self.status_dot.config(fg="#ad2929")
        messagebox.showerror("POS 3.1.8", f"เริ่มเซิร์ฟเวอร์ไม่สำเร็จ\n\n{detail}\n\nดูรายละเอียดที่ runtime\\launcher.log")

    def open_browser(self):
        if not self.browser_exe:
            os.startfile(URL)
            self.status.config(text="เปิด Default browser แล้ว")
            return
        if self.browser_hwnd and ctypes.windll.user32.IsWindow(self.browser_hwnd):
            ctypes.windll.user32.ShowWindow(self.browser_hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(self.browser_hwnd)
            return
        self.known_chrome_windows = set(self.chrome_windows())
        profile = BROWSER_PROFILE
        self.configure_browser_profile(profile)
        self.browser_process = subprocess.Popen(main_browser_args(self.browser_exe, profile), creationflags=CREATE_NO_WINDOW)
        self.status.config(text="เปิดหน้าร้านแล้ว — กรุณา Login")
        threading.Thread(target=self.capture_browser_window, daemon=True).start()
        self.root.after(600, self.root.iconify)

    def configure_browser_profile(self, profile):
        """Disable credential prompts that can cover and intercept the POS window."""
        preferences = profile / "Default" / "Preferences"
        try:
            preferences.parent.mkdir(parents=True, exist_ok=True)
            data = json.loads(preferences.read_text(encoding="utf-8")) if preferences.exists() else {}
            data["credentials_enable_service"] = False
            data.setdefault("profile", {})["password_manager_enabled"] = False
            data.setdefault("autofill", {})["profile_enabled"] = False
            data.setdefault("signin", {})["allowed"] = False
            data["signin"]["allowed_on_next_startup"] = False
            preferences.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    def chrome_windows(self):
        handles = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def callback(hwnd, _):
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return True
            class_name = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, class_name, 256)
            if class_name.value.startswith("Chrome_WidgetWin"):
                handles.append(int(hwnd))
            return True
        ctypes.windll.user32.EnumWindows(callback_type(callback), 0)
        return handles

    def capture_browser_window(self):
        for _ in range(50):
            new_windows = [item for item in self.chrome_windows() if item not in self.known_chrome_windows]
            if new_windows:
                self.browser_hwnd = max(new_windows, key=self.window_area)
                self.root.after(0, lambda: self.apply_display("normal"))
                self.root.after(0, self.open_print_agent)
                return
            time.sleep(0.2)

    def open_print_agent(self):
        if not self.browser_exe or not self.print_agent_token or (
            self.print_browser_process and self.print_browser_process.poll() is None
        ):
            return
        configure_attach_only_default_printer(self.desktop_user)
        if DIRECT_WINDOWS_PRINTING:
            record_launcher_print_event(
                "direct_windows_printing_enabled",
                desktop_user=self.desktop_user,
                printer=RECEIPT_PRINTER_NAME,
            )
            return
        if EXTERNAL_PRINT_AGENT:
            record_launcher_print_event(
                "external_print_agent_in_use",
                desktop_user=self.desktop_user,
                printer=RECEIPT_PRINTER_NAME,
            )
            return
        known_windows = set(self.chrome_windows())
        profile = PRINT_BROWSER_PROFILE
        self.configure_browser_profile(profile)
        self.print_browser_process = subprocess.Popen(
            print_browser_args(self.browser_exe, profile, self.print_agent_token, self.desktop_user),
            creationflags=CREATE_NO_WINDOW,
        )
        threading.Thread(target=self.capture_print_window, args=(known_windows,), daemon=True).start()

    def open_print_diagnostics(self):
        try:
            PRINT_DIAGNOSTICS_LOG.parent.mkdir(parents=True, exist_ok=True)
            if not PRINT_DIAGNOSTICS_LOG.exists():
                PRINT_DIAGNOSTICS_LOG.write_text("ยังไม่มีรายการพิมพ์\n", encoding="utf-8")
            subprocess.Popen(["notepad.exe", str(PRINT_DIAGNOSTICS_LOG)])
        except OSError as exc:
            messagebox.showerror(LAUNCHER_TITLE, f"ไม่สามารถเปิด Log การพิมพ์ได้\n\n{exc}")

    def capture_print_window(self, known_windows):
        for _ in range(50):
            new_windows = [item for item in self.chrome_windows() if item not in known_windows and item != self.browser_hwnd]
            if new_windows:
                self.print_browser_hwnd = min(new_windows, key=self.window_area)
                return
            time.sleep(0.2)

    def window_area(self, hwnd):
        rectangle = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rectangle)):
            return 0
        return max(0, rectangle.right - rectangle.left) * max(0, rectangle.bottom - rectangle.top)

    def send_f11(self):
        if not self.browser_hwnd:
            return
        ctypes.windll.user32.SetForegroundWindow(self.browser_hwnd)
        ctypes.windll.user32.keybd_event(VK_F11, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)

    def is_browser_fullscreen(self):
        """Read Chrome's real state so launcher restarts cannot desync it."""
        if not self.browser_hwnd or not ctypes.windll.user32.IsWindow(self.browser_hwnd):
            return False
        style = ctypes.windll.user32.GetWindowLongW(self.browser_hwnd, GWL_STYLE)
        return not bool(style & WS_CAPTION)

    def apply_display(self, mode):
        if not self.browser_hwnd or not ctypes.windll.user32.IsWindow(self.browser_hwnd):
            return
        actual_fullscreen = self.is_browser_fullscreen()
        if mode == "fullscreen" and not actual_fullscreen:
            ctypes.windll.user32.ShowWindow(self.browser_hwnd, SW_MAXIMIZE)
            self.send_f11()
            self.fullscreen = True
            self.status.config(text="หน้าร้านอยู่ในโหมดเต็มจอ")
        elif mode == "normal":
            if actual_fullscreen:
                self.send_f11()
                time.sleep(0.15)
            self.fullscreen = False
            ctypes.windll.user32.ShowWindow(self.browser_hwnd, SW_RESTORE)
            screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            screen_h = ctypes.windll.user32.GetSystemMetrics(1)
            width, height = min(1100, screen_w - 80), min(760, screen_h - 80)
            ctypes.windll.user32.SetWindowPos(self.browser_hwnd, 0, (screen_w-width)//2, (screen_h-height)//2, width, height, 0x0040)
            self.status.config(text="หน้าร้านอยู่ในโหมดหน้าต่างปกติ")

    def write_state(self, mode):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({"mode": mode, "updated_at": time.time()}), encoding="utf-8")

    def poll_display_state(self):
        if self.closing:
            return
        try:
            stamp = STATE_FILE.stat().st_mtime_ns
            if stamp != self.last_state_stamp:
                self.last_state_stamp = stamp
                mode = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("mode")
                if mode in {"normal", "fullscreen"}:
                    self.apply_display(mode)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        self.root.after(500, self.poll_display_state)

    def close(self):
        title = "ปิด Launcher" if self.attach_only else "ปิดระบบ"
        question = (
            "ต้องการปิดหน้าต่าง POS ใช่หรือไม่?\n\nเซิร์ฟเวอร์จะยังทำงานต่อ"
            if self.attach_only
            else "ต้องการปิด POS Server ใช่หรือไม่?"
        )
        if not messagebox.askyesno(title, question):
            return
        self.closing = True
        if self.fullscreen:
            self.apply_display("normal")
        if self.server and self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.server.kill()
        if self.print_browser_process and self.print_browser_process.poll() is None:
            self.print_browser_process.terminate()
        if self.browser_process and self.browser_process.poll() is None:
            self.browser_process.terminate()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(0, f"{LAUNCHER_TITLE} is already running.", LAUNCHER_TITLE, 0x40)
        raise SystemExit(0)
    try:
        PosDesktop().run()
    except Exception:
        import traceback
        error_log = PROFILE_ROOT / "desktop-error.log"
        error_log.parent.mkdir(parents=True, exist_ok=True)
        error_log.write_text(traceback.format_exc(), encoding="utf-8")
        ctypes.windll.user32.MessageBoxW(0, f"POS Desktop Launcher encountered an error.\n\nSee: {error_log}", LAUNCHER_TITLE, 0x10)
        raise
    finally:
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)
