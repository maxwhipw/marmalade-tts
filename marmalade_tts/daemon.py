"""Kitten daemon management (start/stop/status) and client."""

import json
import os
import signal
import socket
import subprocess
import sys
import time

BASE_DIR    = os.path.expanduser("~/.local/share/marmalade-tts")
SOCKET_PATH = os.path.join(BASE_DIR, "kitten.sock")
PID_PATH    = os.path.join(BASE_DIR, "kitten.pid")
SERVICE     = "marmalade-kitten.service"


def is_running() -> bool:
    """Check if kitten daemon is alive."""
    if not os.path.exists(PID_PATH):
        return False
    try:
        pid = int(open(PID_PATH).read().strip())
        os.kill(pid, 0)  # signal 0 = check existence
        return True
    except (ValueError, OSError):
        return False


def start(timeout: float = 15.0) -> bool:
    """Start the kitten daemon via systemd. Returns True if ready."""
    if is_running() and os.path.exists(SOCKET_PATH):
        return True
    subprocess.run(["systemctl", "--user", "start", SERVICE], check=False)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(SOCKET_PATH) and is_running():
            return True
        time.sleep(0.5)
    return False


def stop():
    """Stop the kitten daemon via systemd."""
    subprocess.run(["systemctl", "--user", "stop", SERVICE], check=False)


def status() -> dict:
    """Return daemon status info."""
    running = is_running()
    pid = None
    if os.path.exists(PID_PATH):
        try:
            pid = int(open(PID_PATH).read().strip())
        except (ValueError, OSError):
            pass
    return {
        "running": running,
        "pid": pid,
        "socket": SOCKET_PATH if os.path.exists(SOCKET_PATH) else None,
    }


def synthesize(text: str, voice: str, speed: float, out_path: str,
               auto_start: bool = True, timeout: float = 60.0) -> str:
    """Send synthesis request to daemon. Returns output path.

    If daemon is not running and auto_start=True, tries to start it first.
    """
    if not os.path.exists(SOCKET_PATH):
        if auto_start:
            ok = start()
            if not ok:
                raise RuntimeError(
                    "Kitten daemon failed to start. Run: marmalade-tts daemon start"
                )
        else:
            raise RuntimeError("Kitten daemon not running.")

    request = {
        "text": text,
        "voice": voice,
        "speed": speed,
        "out": out_path,
    }

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(SOCKET_PATH)
        client.sendall((json.dumps(request) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = client.recv(4096)
            if not chunk:
                break
            buf += chunk
        resp = json.loads(buf.strip())
    finally:
        client.close()

    if not resp.get("ok"):
        raise RuntimeError(f"Daemon error: {resp.get('error', 'unknown')}")
    return resp["out"]
