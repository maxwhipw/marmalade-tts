"""Daemon management for all engines — start/stop/status via systemd + socket client."""

import json
import os
import socket
import subprocess
import sys
import time

BASE_DIR = os.path.expanduser("~/.local/share/marmalade-tts")

# Engine → (socket filename, pid filename, systemd service name)
ENGINE_DAEMONS = {
    "kitten": ("kitten.sock", "kitten.pid", "marmalade-kitten.service"),
    "kokoro": ("kokoro.sock", "kokoro.pid", "marmalade-kokoro.service"),
    "piper":  ("piper.sock",  "piper.pid",  "marmalade-piper.service"),
    "coqui":  ("coqui.sock",  "coqui.pid",  "marmalade-coqui.service"),
}


def _paths(engine: str):
    """Return (socket_path, pid_path, service_name) for an engine."""
    sock_f, pid_f, svc = ENGINE_DAEMONS[engine]
    return os.path.join(BASE_DIR, sock_f), os.path.join(BASE_DIR, pid_f), svc


def is_running(engine: str) -> bool:
    """Check if a daemon is alive."""
    _, pid_path, _ = _paths(engine)
    if not os.path.exists(pid_path):
        return False
    try:
        pid = int(open(pid_path).read().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False


def start(engine: str, timeout: float = 30.0) -> bool:
    """Start a daemon via systemd. Returns True if ready."""
    sock_path, _, svc = _paths(engine)
    if is_running(engine) and os.path.exists(sock_path):
        return True
    subprocess.run(["systemctl", "--user", "start", svc], check=False)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(sock_path) and is_running(engine):
            return True
        time.sleep(0.5)
    return False


def stop(engine: str):
    """Stop a daemon via systemd."""
    _, _, svc = _paths(engine)
    subprocess.run(["systemctl", "--user", "stop", svc], check=False)


def status(engine: str = None) -> dict:
    """Return status for one or all engines."""
    engines = [engine] if engine else list(ENGINE_DAEMONS.keys())
    result = {}
    for eng in engines:
        sock_path, pid_path, svc = _paths(eng)
        running = is_running(eng)
        pid = None
        if os.path.exists(pid_path):
            try:
                pid = int(open(pid_path).read().strip())
            except (ValueError, OSError):
                pass
        result[eng] = {
            "running": running,
            "pid": pid,
            "socket": sock_path if os.path.exists(sock_path) else None,
            "service": svc,
        }
    return result


def synthesize(engine: str, request: dict, auto_start: bool = True,
               timeout: float = 60.0) -> str:
    """Send a synthesis request to a daemon. Returns output path.

    Request dict should contain at minimum: {"text": "...", "out": "/path/to.wav"}
    Additional keys depend on the engine (voice, speed, lang, speaker, etc.)
    """
    sock_path, _, _ = _paths(engine)

    if not os.path.exists(sock_path):
        if auto_start:
            ok = start(engine, timeout=30.0)
            if not ok:
                raise RuntimeError(
                    f"{engine} daemon failed to start. "
                    f"Run: marmalade-tts daemon start --engine {engine}"
                )
        else:
            raise RuntimeError(f"{engine} daemon not running.")

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(sock_path)
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
