#!/usr/bin/env python3
"""
marmalade-tts coqui daemon — keeps Coqui TTS model in RAM.
Protocol: same as kitten daemon (JSON over Unix socket).
Request:  {"text": "...", "out": "/tmp/x.wav"}
Response: {"ok": true, "out": "/tmp/x.wav"} or {"ok": false, "error": "..."}
"""

import json
import logging
import os
import signal
import socket
import sys
import threading

BASE        = os.path.expanduser("~/.local/share/marmalade-tts")
SOCKET_PATH = os.path.join(BASE, "coqui.sock")
PID_PATH    = os.path.join(BASE, "coqui.pid")
LOG_PATH    = os.path.join(BASE, "coqui.log")

os.makedirs(BASE, exist_ok=True)

logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("coqui-daemon")

os.environ["CUDA_VISIBLE_DEVICES"] = ""

DEFAULT_MODEL = os.environ.get("COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC")

log.info("Loading Coqui TTS model: %s", DEFAULT_MODEL)
print(f"[coqui-daemon] loading {DEFAULT_MODEL} ...", flush=True)
try:
    from TTS.api import TTS
    MODEL = TTS(DEFAULT_MODEL, gpu=False)
    log.info("Model loaded OK")
    print("[coqui-daemon] model loaded", flush=True)
except Exception as e:
    log.error("Failed to load: %s", e)
    print(f"[coqui-daemon] FATAL: {e}", file=sys.stderr)
    sys.exit(1)

_lock = threading.Lock()

def handle_client(conn):
    try:
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
        req  = json.loads(buf.split(b"\n")[0])
        text = req["text"]
        out  = req["out"]

        with _lock:
            MODEL.tts_to_file(text, file_path=out)

        conn.sendall((json.dumps({"ok": True, "out": out}) + "\n").encode())
        log.info("synthesized chars=%d -> %s", len(text), out)
    except Exception as exc:
        log.error("handle_client: %s", exc)
        try:
            conn.sendall((json.dumps({"ok": False, "error": str(exc)}) + "\n").encode())
        except Exception:
            pass
    finally:
        conn.close()

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
    print(f"[coqui-daemon] ready — socket: {SOCKET_PATH}", flush=True)

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
