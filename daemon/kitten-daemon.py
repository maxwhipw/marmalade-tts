#!/usr/bin/env python3
"""
marmalade-tts-kitten-daemon
Persistent Kitten TTS daemon — loads model once into RAM, serves synthesis
requests over a Unix domain socket.

Protocol (newline-delimited JSON):
  Request:  {"text": "...", "voice": "Hugo", "speed": 1.0, "out": "/tmp/x.wav"}
  Response: {"ok": true, "out": "/tmp/x.wav"}
         or {"ok": false, "error": "..."}

The model repo is resolved from KITTEN_MODEL env var (default: nano).
HF_HUB_OFFLINE=1 is set so it never re-downloads after the first cache fill.
"""

import json
import logging
import os
import signal
import socket
import sys
import threading

# ── paths ──────────────────────────────────────────────────────────────────────
BASE        = os.path.expanduser("~/.local/share/marmalade-tts")
SOCKET_PATH = os.path.join(BASE, "kitten.sock")
PID_PATH    = os.path.join(BASE, "kitten.pid")
LOG_PATH    = os.path.join(BASE, "kitten.log")

os.makedirs(BASE, exist_ok=True)

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("kitten-daemon")

# ── model size → HF repo ───────────────────────────────────────────────────────
MODEL_REPOS = {
    "nano":  "KittenML/kitten-tts-nano-0.8",
    "micro": "KittenML/kitten-tts-micro-0.8",
    "mini":  "KittenML/kitten-tts-mini-0.8",
}

raw_model = os.environ.get("KITTEN_MODEL", "nano")
MODEL_REPO = MODEL_REPOS.get(raw_model, raw_model)   # accept size name or full repo

# ── env ────────────────────────────────────────────────────────────────────────
os.environ["CUDA_VISIBLE_DEVICES"] = ""   # force CPU — Pascal sm_61 not supported
os.environ["HF_HUB_OFFLINE"]       = "1"  # never re-download after cache fill

# ── load model ─────────────────────────────────────────────────────────────────
log.info("Loading KittenTTS model: %s", MODEL_REPO)
print(f"[kitten-daemon] loading {MODEL_REPO} ...", flush=True)
try:
    from kittentts import KittenTTS
    MODEL = KittenTTS(MODEL_REPO)
    log.info("Model loaded OK")
    print("[kitten-daemon] model loaded", flush=True)
except Exception as e:
    log.error("Failed to load model: %s", e)
    print(f"[kitten-daemon] FATAL: {e}", file=sys.stderr)
    sys.exit(1)

_lock = threading.Lock()

# ── client handler ─────────────────────────────────────────────────────────────
def handle_client(conn):
    try:
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
        req   = json.loads(buf.split(b"\n")[0])
        text  = req["text"]
        voice = req.get("voice", "Hugo")
        speed = float(req.get("speed", 1.0))
        out   = req["out"]

        with _lock:
            MODEL.generate_to_file(text, out, voice=voice, speed=speed)

        conn.sendall((json.dumps({"ok": True, "out": out}) + "\n").encode())
        log.info("synthesized voice=%s chars=%d -> %s", voice, len(text), out)
    except Exception as exc:
        log.error("handle_client: %s", exc)
        try:
            conn.sendall((json.dumps({"ok": False, "error": str(exc)}) + "\n").encode())
        except Exception:
            pass
    finally:
        conn.close()

# ── main ───────────────────────────────────────────────────────────────────────
def main():
    with open(PID_PATH, "w") as f:
        f.write(str(os.getpid()))

    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o600)
    server.listen(16)
    log.info("listening on %s", SOCKET_PATH)
    print(f"[kitten-daemon] ready — socket: {SOCKET_PATH}", flush=True)

    def _shutdown(sig, _frame):
        log.info("shutting down (signal %s)", sig)
        server.close()
        for p in (SOCKET_PATH, PID_PATH):
            try: os.unlink(p)
            except FileNotFoundError: pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    while True:
        try:
            conn, _ = server.accept()
        except OSError:
            break
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

if __name__ == "__main__":
    main()
