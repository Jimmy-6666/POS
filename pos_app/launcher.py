import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from waitress import serve

from . import create_app


PORT = int(os.environ.get("POS_PORT", "8000"))


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
    serve(create_app(), host="0.0.0.0", port=PORT, threads=8)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
