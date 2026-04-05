#!/usr/bin/env python3
"""
marmalade-tts piper daemon — keeps Piper voice loaded in RAM.
Protocol: same as kitten daemon (JSON over Unix socket).
Request:  {"text": "...", "speed": 1.0, "speaker": null, "out": "/tmp/x.wav"}
Response: {"ok": true, "out": "/tmp/x.wav"} or {"ok": false, "error": "..."}
"""

import json
import logging
import os
import signal
import socket
import sys
import threading
import wave
import io

BASE        = os.path.expanduser("~/.local/share/marmalade-tts")
SOCKET_PATH = os.path.join(BASE, "piper.sock")
PID_PATH    = os.path.join(BASE, "piper.pid")
LOG_PATH    = os.path.join(BASE, "piper.log")

os.makedirs(BASE, exist_ok=True)

logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("piper-daemon")

DEFAULT_MODEL = os.environ.get("PIPER_MODEL",
    os.path.expanduser("~/.local/share/piper/voices/en_US-lessac-medium.onnx"))

log.info("Loading Piper voice: %s", DEFAULT_MODEL)
print(f"[piper-daemon] loading {DEFAULT_MODEL} ...", flush=True)
try:
    from piper import PiperVoice
    VOICE = PiperVoice.load(DEFAULT_MODEL)
    log.info("Voice loaded OK")
    print("[piper-daemon] voice loaded", flush=True)
except Exception as e:
    log.error("Failed to load: %s", e)
    print(f"[piper-daemon] FATAL: {e}", file=sys.stderr)
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
        req     = json.loads(buf.split(b"\n")[0])
        text    = req["text"]
        speed   = float(req.get("speed", 1.0))
        speaker = req.get("speaker")
        out     = req["out"]

        length_scale = 1.0 / speed if speed else 1.0

        with _lock:
            from piper.config import SynthesisConfig
            syn_cfg = SynthesisConfig()
            syn_cfg.length_scale = length_scale
            if speaker is not None:
                syn_cfg.speaker_id = int(speaker)
            with open(out, "wb") as raw_file:
                wav_file = wave.open(raw_file, "wb")
                VOICE.synthesize_wav(text, wav_file, syn_config=syn_cfg)
                wav_file.close()

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
    print(f"[piper-daemon] ready — socket: {SOCKET_PATH}", flush=True)

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
