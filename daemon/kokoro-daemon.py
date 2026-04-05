#!/usr/bin/env python3
"""
marmalade-tts kokoro daemon — keeps Kokoro model in RAM.
Protocol: same as kitten daemon (JSON over Unix socket).
Request:  {"text": "...", "voice": "af_heart", "speed": 1.0, "lang": "a", "out": "/tmp/x.wav"}
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
SOCKET_PATH = os.path.join(BASE, "kokoro.sock")
PID_PATH    = os.path.join(BASE, "kokoro.pid")
LOG_PATH    = os.path.join(BASE, "kokoro.log")

os.makedirs(BASE, exist_ok=True)

logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kokoro-daemon")

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"

DEFAULT_LANG = os.environ.get("KOKORO_LANG", "a")

log.info("Loading Kokoro pipeline (lang=%s)", DEFAULT_LANG)
print(f"[kokoro-daemon] loading pipeline (lang={DEFAULT_LANG}) ...", flush=True)
try:
    from kokoro import KPipeline
    import soundfile as sf
    PIPELINE = KPipeline(lang_code=DEFAULT_LANG, device="cpu")
    log.info("Pipeline loaded OK")
    print("[kokoro-daemon] model loaded", flush=True)
except Exception as e:
    log.error("Failed to load: %s", e)
    print(f"[kokoro-daemon] FATAL: {e}", file=sys.stderr)
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
        req   = json.loads(buf.split(b"\n")[0])
        text  = req["text"]
        voice = req.get("voice", "af_heart")
        speed = float(req.get("speed", 1.0))
        out   = req["out"]

        with _lock:
            # KPipeline.__call__ returns a generator of Result objects
            audio_chunks = []
            for result in PIPELINE(text, voice=voice, speed=speed):
                if result.audio is not None:
                    audio_chunks.append(result.audio.numpy())

            if not audio_chunks:
                raise RuntimeError("No audio generated")

            import numpy as np
            audio = np.concatenate(audio_chunks)
            sf.write(out, audio, 24000)

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
    print(f"[kokoro-daemon] ready — socket: {SOCKET_PATH}", flush=True)

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
