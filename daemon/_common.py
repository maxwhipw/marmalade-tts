"""Shared scaffolding for marmalade-tts engine daemons.

Each daemon script lives next to this module and provides:
  - the engine name (used for socket/pid/log paths and log prefix)
  - a zero-arg `model_loader` callable that returns the loaded model
  - a `synth_handler(model, request_dict)` callable that writes the output WAV

The boilerplate (socket setup, logging, signal handling, per-request
recv/JSON/respond, threadpool, shutdown) is handled here.

Wire protocol (newline-delimited JSON over a Unix domain socket):
  Request:  {"text": "...", "out": "/tmp/x.wav", ...engine fields}
  Response: {"ok": true, "out": "/tmp/x.wav"}
         or {"ok": false, "error": "..."}
"""

import json
import logging
import os
import signal
import socket
import sys
import threading

BASE = os.path.expanduser("~/.local/share/marmalade-tts")
os.makedirs(BASE, exist_ok=True)


def paths(engine: str):
    """Return (socket_path, pid_path, log_path) for an engine name."""
    return (
        os.path.join(BASE, f"{engine}.sock"),
        os.path.join(BASE, f"{engine}.pid"),
        os.path.join(BASE, f"{engine}.log"),
    )


def _setup_logging(engine: str, log_path: str) -> logging.Logger:
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return logging.getLogger(f"{engine}-daemon")


def check_loaded(engine: str, requested, loaded, what: str = "model"):
    """Refuse a request whose model identity doesn't match what's loaded.

    A daemon loads ONE model at startup; the client sends the identity its
    config resolved to, and a mismatch means the daemon predates a config
    change (or the caller overrode --voice/--lang past what's loaded).
    Raising here surfaces as {"ok": false, ...} to the client instead of
    silently synthesizing with the wrong model.
    """
    if requested and str(requested) != str(loaded):
        raise RuntimeError(
            f"daemon has {what} {loaded!r} loaded but the request wants "
            f"{requested!r}. Restart it to pick up config "
            f"(marmalade-tts daemon stop --engine {engine}; it auto-starts "
            f"on next use) or set engines.{engine}.daemon: false."
        )


def _read_request(conn):
    buf = b""
    while b"\n" not in buf:
        chunk = conn.recv(65536)
        if not chunk:
            return None
        buf += chunk
    return json.loads(buf.split(b"\n")[0])


def _send_response(conn, obj):
    conn.sendall((json.dumps(obj) + "\n").encode())


def serve(engine: str, model_loader, synth_handler):
    """Run the daemon main loop for `engine`.

    `model_loader`: zero-arg callable returning the loaded model object.
    `synth_handler`: callable taking (model, request_dict). Must write the
                     output file at `request["out"]`. Raise on failure.
    """
    socket_path, pid_path, log_path = paths(engine)
    log = _setup_logging(engine, log_path)
    prefix = f"[{engine}-daemon]"

    log.info("Loading model")
    print(f"{prefix} loading model ...", flush=True)
    try:
        model = model_loader()
    except Exception as e:
        log.error("Failed to load model: %s", e)
        print(f"{prefix} FATAL: {e}", file=sys.stderr)
        sys.exit(1)
    log.info("Model loaded OK")
    print(f"{prefix} model loaded", flush=True)

    lock = threading.Lock()

    def handle_client(conn):
        try:
            req = _read_request(conn)
            if req is None:
                return
            with lock:
                synth_handler(model, req)
            out = req.get("out")
            _send_response(conn, {"ok": True, "out": out})
            voice_str = f"voice={req['voice']} " if req.get("voice") else ""
            log.info("synthesized %schars=%d -> %s",
                     voice_str, len(req.get("text", "")), out)
        except Exception as exc:
            log.error("handle_client: %s", exc)
            try:
                _send_response(conn, {"ok": False, "error": str(exc)})
            except Exception:
                pass
        finally:
            conn.close()

    with open(pid_path, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    if os.path.exists(socket_path):
        os.unlink(socket_path)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    os.chmod(socket_path, 0o600)
    server.listen(16)
    log.info("listening on %s", socket_path)
    print(f"{prefix} ready — socket: {socket_path}", flush=True)

    def _shutdown(sig, _frame):
        log.info("shutting down (signal %s)", sig)
        server.close()
        for p in (socket_path, pid_path):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while True:
        try:
            conn, _ = server.accept()
        except OSError:
            break
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
