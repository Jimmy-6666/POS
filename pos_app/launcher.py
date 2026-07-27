import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from waitress import serve

from . import create_app
from .runtime_paths import load_runtime_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_CONFIG = load_runtime_config(PROJECT_ROOT)
PORT = RUNTIME_CONFIG.port


def active_release_command():
    """Return a trusted versioned release command, if one is active."""
    if os.environ.get("POS_ACTIVE_RELEASE_CHILD") == "1":
        return None
    active_file = RUNTIME_CONFIG.paths.releases / "active-release.json"
    try:
        import json
        data = json.loads(active_file.read_text(encoding="utf-8"))
        version = str(data.get("version", ""))
        release = (RUNTIME_CONFIG.paths.releases / version).resolve()
        release.relative_to(RUNTIME_CONFIG.paths.releases.resolve())
        if not version or not (release / "pos_app" / "launcher.py").is_file():
            return None
        environment = os.environ.copy()
        environment["POS_ACTIVE_RELEASE_CHILD"] = "1"
        environment["PYTHONPATH"] = os.pathsep.join((str(release), environment.get("PYTHONPATH", "")))
        return environment, release
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def listener_pids():
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, check=False
    )
    pids = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[1].endswith(f":{PORT}") and parts[3] == "LISTENING":
            pids.add(int(parts[4]))
    return pids


def process_name(process_id):
    process = ctypes.windll.kernel32.OpenProcess(0x1000, False, process_id)
    if not process:
        return ""
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
            return Path(buffer.value).name.lower()
        return ""
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


def stop_old_instances():
    current_pid = os.getpid()
    old_pids = listener_pids() - {current_pid}
    for process_id in old_pids:
        name = process_name(process_id)
        if name not in {"python.exe", "pythonw.exe"}:
            raise RuntimeError(
                f"Port {PORT} is used by {name or 'another program'} (PID {process_id})."
            )
        print(f"Stopping old POS instance (PID {process_id})...")
        try:
            os.kill(process_id, signal.SIGTERM)
        except PermissionError:
            result = subprocess.run(
                ["taskkill", "/PID", str(process_id), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Cannot stop old POS process {process_id}. Close its command window once, then run start-pos.bat again."
                )
    deadline = time.monotonic() + 8
    while listener_pids():
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Port {PORT} did not become available.")
        time.sleep(0.25)


def main():
    active = active_release_command()
    if active:
        environment, release = active
        os.chdir(release)
        os.execve(sys.executable, [sys.executable, "-m", "pos_app.launcher"], environment)
    try:
        stop_old_instances()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    print("Starting Thai Minimart POS...")
    print(f"Local URL: http://127.0.0.1:{PORT}")
    print(f"LAN URL:   http://THIS-COMPUTER-IP:{PORT}")
    print("Only one POS server instance is running.")
    print("Press Ctrl+C to stop the server.")
    serve(create_app(), host=RUNTIME_CONFIG.host, port=PORT, threads=8)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
