"""Daemon management for all engines — start/stop/status.

Start priority:
  1. systemd --user (if systemctl is available and a service file exists)
  2. Direct subprocess.Popen of the daemon script (non-systemd systems,
     Docker, WSL, etc.)

The fallback writes a PID file and leaves the daemon running in the background.
On stop, it sends SIGTERM via the PID file.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time

BASE_DIR = os.path.expanduser("~/.local/share/marmalade-tts")

# Engine → (socket filename, pid filename, systemd service name, daemon script)
ENGINE_DAEMONS = {
    "kitten": ("kitten.sock", "kitten.pid", "marmalade-kitten.service", "kitten-daemon.py"),
    "kokoro": ("kokoro.sock", "kokoro.pid", "marmalade-kokoro.service", "kokoro-daemon.py"),
    "piper":  ("piper.sock",  "piper.pid",  "marmalade-piper.service",  "piper-daemon.py"),
    "coqui":  ("coqui.sock",  "coqui.pid",  "marmalade-coqui.service",  "coqui-daemon.py"),
}

# Engine → Python interpreter to use for the daemon script (in order of preference)
ENGINE_PYTHON = {
    "kitten": [
        os.path.expanduser("~/.local/share/kittentts-venv/bin/python"),
    ],
    "kokoro": [
        os.path.expanduser("~/.local/share/pipx/venvs/kokoro/bin/python"),
    ],
    "piper": [
        os.path.expanduser("~/.local/share/pipx/venvs/piper-tts/bin/python"),
    ],
    "coqui": [
        os.path.expanduser("~/.local/share/pipx/venvs/coqui-tts/bin/python"),
    ],
}


def _paths(engine: str):
    """Return (socket_path, pid_path, service_name, daemon_script_path)."""
    sock_f, pid_f, svc, script_f = ENGINE_DAEMONS[engine]
    return (
        os.path.join(BASE_DIR, sock_f),
        os.path.join(BASE_DIR, pid_f),
        svc,
        os.path.join(BASE_DIR, script_f),
    )


def _systemd_available() -> bool:
    """Check if systemctl --user is usable."""
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-system-running"],
            capture_output=True, timeout=3,
        )
        # "running", "degraded", or "starting" are all functional enough
        return r.returncode in (0, 1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _service_file_exists(service_name: str) -> bool:
    """Check if the systemd user service file is installed."""
    search_dirs = [
        os.path.expanduser("~/.config/systemd/user"),
        "/etc/systemd/user",
        "/usr/lib/systemd/user",
    ]
    return any(
        os.path.exists(os.path.join(d, service_name))
        for d in search_dirs
    )


def _find_python(engine: str) -> str | None:
    """Find the Python interpreter for a daemon's venv."""
    for p in ENGINE_PYTHON.get(engine, []):
        if os.path.exists(p):
            return p
    # Last resort: system python3
    import shutil
    return shutil.which("python3")


def is_running(engine: str) -> bool:
    """Check if a daemon is alive (by PID file)."""
    _, pid_path, _, _ = _paths(engine)
    if not os.path.exists(pid_path):
        return False
    try:
        pid = int(open(pid_path).read().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False


def _start_via_systemd(engine: str) -> bool:
    """Start daemon via systemctl --user. Returns True if command succeeded."""
    _, _, svc, _ = _paths(engine)
    r = subprocess.run(["systemctl", "--user", "start", svc], capture_output=True)
    return r.returncode == 0


def _start_direct(engine: str) -> bool:
    """Start daemon directly as a background subprocess. Returns True if launched."""
    _, pid_path, _, script = _paths(engine)

    if not os.path.exists(script):
        print(f"[daemon] Daemon script not found: {script}", file=sys.stderr)
        return False

    python = _find_python(engine)
    if not python:
        print(f"[daemon] No Python interpreter found for {engine}", file=sys.stderr)
        return False

    # Env tweaks (mirrors what the systemd services do)
    env = os.environ.copy()
    env_overrides = {
        "kitten": {"KITTEN_MODEL": "nano"},
        "kokoro": {"KOKORO_LANG":  "a"},
        "piper":  {"PIPER_MODEL":  os.path.expanduser(
                       "~/.local/share/piper/voices/en_US-lessac-medium.onnx")},
        "coqui":  {"COQUI_MODEL":  "tts_models/en/ljspeech/tacotron2-DDC"},
    }
    env.update(env_overrides.get(engine, {}))

    log_path = os.path.join(BASE_DIR, f"{engine}.log")

    with open(log_path, "a") as logf:
        proc = subprocess.Popen(
            [python, script],
            env=env,
            stdout=logf,
            stderr=logf,
            start_new_session=True,  # detach from current process group
        )

    # Give it a moment to write its PID file
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if os.path.exists(pid_path):
            return True
        time.sleep(0.2)

    # Fallback: trust the Popen PID (daemon may write its own PID file later)
    return proc.poll() is None  # still running = good sign


def start(engine: str, timeout: float = 30.0) -> bool:
    """Start a daemon. Returns True when the socket is ready."""
    sock_path, _, svc, _ = _paths(engine)

    if is_running(engine) and os.path.exists(sock_path):
        return True

    # Try systemd first, fall back to direct subprocess
    use_systemd = _systemd_available() and _service_file_exists(svc)
    if use_systemd:
        _start_via_systemd(engine)
    else:
        ok = _start_direct(engine)
        if not ok:
            return False

    # Wait for socket to appear
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(sock_path) and is_running(engine):
            return True
        time.sleep(0.5)
    return False


def stop(engine: str):
    """Stop a daemon — via systemd if available, otherwise SIGTERM via PID file."""
    _, pid_path, svc, _ = _paths(engine)
    use_systemd = _systemd_available() and _service_file_exists(svc)
    if use_systemd:
        subprocess.run(["systemctl", "--user", "stop", svc], check=False)
    else:
        if os.path.exists(pid_path):
            try:
                pid = int(open(pid_path).read().strip())
                os.kill(pid, signal.SIGTERM)
            except (ValueError, OSError):
                pass


def status(engine: str = None) -> dict:
    """Return status for one or all engines."""
    engines = [engine] if engine else list(ENGINE_DAEMONS.keys())
    result = {}
    for eng in engines:
        sock_path, pid_path, svc, _ = _paths(eng)
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
    """Send a synthesis request to a daemon. Returns output path."""
    sock_path, _, _, _ = _paths(engine)

    if not os.path.exists(sock_path):
        if auto_start:
            ok = start(engine, timeout=30.0)
            if not ok:
                raise RuntimeError(
                    f"{engine} daemon failed to start.\n"
                    f"Run: marmalade-tts daemon start --engine {engine}\n"
                    f"Log: {os.path.join(BASE_DIR, engine + '.log')}"
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
