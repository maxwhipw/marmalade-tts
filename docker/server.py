#!/usr/bin/env python3
"""
marmalade-tts HTTP API server.

A local TTS API server compatible with OpenAI and ElevenLabs TTS endpoints.
Designed to run in Docker or standalone as a drop-in replacement for cloud TTS.

Security:
  - API key auth (Bearer token)
  - Request size limits (10KB max body)
  - Rate limiting (token bucket, per-IP)
  - Input sanitization (strip control chars)
  - Path validation (no directory traversal)
  - Non-root execution
  - No eval/exec of user input
  - Requests logged without bodies (no sensitive text in logs)

Endpoints:
  GET  /health                    → {"status": "ok", "version": "<package-version>"}
  GET  /v1/voices                 → voice list (ElevenLabs-style)
  POST /v1/audio/speech           → OpenAI TTS-compatible
  POST /v1/text-to-speech/{voice} → ElevenLabs-compatible
"""

import json
import logging
import os
import re
import secrets
import sys
import tempfile
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

# ── Version ────────────────────────────────────────────────────────────────────
# Import from the package so we have a single source of truth (no drift).
try:
    from marmalade_tts import __version__ as VERSION
except ImportError:
    VERSION = "unknown"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("marmalade-tts-server")

# ── Configuration from environment ────────────────────────────────────────────
MAX_BODY_BYTES = 10 * 1024  # 10KB
MAX_TEXT_LENGTH = int(os.environ.get("MARMALADE_MAX_TEXT_LENGTH", "5000"))
RATE_LIMIT_RPS = float(os.environ.get("MARMALADE_RATE_LIMIT", "10"))
CORS_ORIGIN = os.environ.get("MARMALADE_CORS_ORIGIN", "")
PORT = int(os.environ.get("MARMALADE_PORT", "8880"))

# Allowed voice/model directories (no path traversal outside these)
ALLOWED_VOICE_DIRS = [
    Path("/voices"),
    Path(os.path.expanduser("~/.local/share/piper/voices")),
]


# ── API key setup ─────────────────────────────────────────────────────────────
def _init_api_key() -> str:
    key = os.environ.get("MARMALADE_API_KEY", "").strip()
    if not key:
        key = secrets.token_urlsafe(32)
        # Print clearly so the operator can capture it from docker logs
        print(f"\n{'='*60}", flush=True)
        print(f"  MARMALADE API KEY (auto-generated — save this!)", flush=True)
        print(f"  {key}", flush=True)
        print(f"{'='*60}\n", flush=True)
    return key


API_KEY: str = _init_api_key()


# ── Rate limiter (token bucket, per-IP) ───────────────────────────────────────
class TokenBucket:
    """Thread-safe per-IP token bucket rate limiter."""

    def __init__(self, rate: float):
        self.rate = rate          # tokens per second
        self._buckets: dict[str, dict] = {}
        self._lock = threading.Lock()
        # Periodic cleanup: remove stale buckets every 5 minutes
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True
        )
        self._cleanup_thread.start()

    def allow(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(ip)
            if bucket is None:
                self._buckets[ip] = {"tokens": self.rate, "last": now}
                return True
            elapsed = now - bucket["last"]
            bucket["tokens"] = min(self.rate, bucket["tokens"] + elapsed * self.rate)
            bucket["last"] = now
            if bucket["tokens"] >= 1.0:
                bucket["tokens"] -= 1.0
                return True
            return False

    def _cleanup_loop(self):
        while True:
            time.sleep(300)
            cutoff = time.monotonic() - 300
            with self._lock:
                stale = [ip for ip, b in self._buckets.items() if b["last"] < cutoff]
                for ip in stale:
                    del self._buckets[ip]
            if stale:
                log.debug("Rate limiter: evicted %d stale buckets", len(stale))


RATE_LIMITER = TokenBucket(RATE_LIMIT_RPS)


# ── Input sanitization ────────────────────────────────────────────────────────
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(text: str) -> str:
    """Strip ASCII control characters (keep \t \n \r) and normalize unicode."""
    text = _CONTROL_RE.sub("", text)
    # Normalize to NFC — prevents homoglyph tricks
    text = unicodedata.normalize("NFC", text)
    return text.strip()


# ── Path validation ────────────────────────────────────────────────────────────
def validate_voice_path(path_str: str) -> Path:
    """
    Resolve and validate a voice/model file path.
    Must resolve to one of ALLOWED_VOICE_DIRS. Raises ValueError on traversal.
    """
    p = Path(path_str).resolve()
    for allowed in ALLOWED_VOICE_DIRS:
        try:
            p.relative_to(allowed.resolve())
            return p
        except ValueError:
            continue
    raise ValueError(f"Voice path escapes allowed directories: {path_str!r}")


def validate_voice_name(name: str) -> str:
    """Allow only safe voice name chars (alphanum, dash, underscore, dot)."""
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", name):
        raise ValueError(f"Invalid voice name: {name!r}")
    return name


# ── Voice discovery ────────────────────────────────────────────────────────────
def discover_voices() -> list[dict]:
    """Scan ALLOWED_VOICE_DIRS for .onnx files and return voice metadata."""
    voices = []
    seen = set()
    for voice_dir in ALLOWED_VOICE_DIRS:
        if not voice_dir.is_dir():
            continue
        for onnx in sorted(voice_dir.rglob("*.onnx")):
            stem = onnx.stem  # e.g. "en_US-lessac-medium"
            if stem in seen:
                continue
            seen.add(stem)
            voices.append(
                {
                    "voice_id": stem,
                    "name": stem,
                    "category": "premade",
                    "labels": {"engine": "piper"},
                    "description": f"Piper voice: {stem}",
                    "preview_url": None,
                    "available_for_tiers": [],
                    "settings": None,
                    "sharing": None,
                    "high_quality_base_model_ids": [],
                    "model_path": str(onnx),
                }
            )
    return voices


# ── Engine loader ─────────────────────────────────────────────────────────────
def _load_engine(engine_name: str, cfg: dict):
    """Import and instantiate the named engine class."""
    engine_name = engine_name.lower()
    if engine_name == "piper":
        from marmalade_tts.engines.piper import PiperEngine
        return PiperEngine(cfg)
    if engine_name == "kokoro":
        from marmalade_tts.engines.kokoro import KokoroEngine
        return KokoroEngine(cfg)
    if engine_name == "kitten":
        from marmalade_tts.engines.kitten import KittenEngine
        return KittenEngine(cfg)
    if engine_name == "coqui":
        from marmalade_tts.engines.coqui import CoquiEngine
        return CoquiEngine(cfg)
    if engine_name == "pocket":
        from marmalade_tts.engines.pocket import PocketEngine
        return PocketEngine(cfg)
    raise ValueError(f"Unknown engine: {engine_name!r}")


VALID_ENGINES = frozenset({"piper", "kokoro", "kitten", "coqui", "pocket"})


# ── Server config ─────────────────────────────────────────────────────────────
try:
    from marmalade_tts import config as _cfg_mod
    APP_CONFIG = _cfg_mod.load()
except Exception as e:
    log.warning("Could not load marmalade-tts config (%s), using defaults", e)
    APP_CONFIG = {}

VOICE_LIST: list[dict] = discover_voices()
log.info("Discovered %d voice(s)", len(VOICE_LIST))
for v in VOICE_LIST:
    log.info("  • %s", v["voice_id"])


# ── HTTP helpers ──────────────────────────────────────────────────────────────
def _json_error(code: str, message: str, http_status: int = 400) -> tuple[int, bytes]:
    body = json.dumps({"error": {"message": message, "code": code}}).encode()
    return http_status, body


# ── Request handler ───────────────────────────────────────────────────────────
class TTSHandler(BaseHTTPRequestHandler):
    server_version = f"marmalade-tts/{VERSION}"
    # Silence default request logging — we do our own
    def log_message(self, fmt, *args):
        pass

    # ── Authentication ─────────────────────────────────────────────────────
    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token = auth[len("Bearer "):]
        return secrets.compare_digest(token.encode(), API_KEY.encode())

    # ── Rate limiting ──────────────────────────────────────────────────────
    def _get_client_ip(self) -> str:
        # Trust X-Forwarded-For only if you put a trusted proxy in front;
        # for direct Docker use, client_address is fine.
        return self.client_address[0]

    # ── CORS ───────────────────────────────────────────────────────────────
    def _add_cors_headers(self):
        if CORS_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    # ── Response helpers ───────────────────────────────────────────────────
    def _send_json(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, code: str, message: str, http_status: int = 400):
        self._send_json(http_status, {"error": {"message": message, "code": code}})

    def _send_audio(self, wav_path: str, content_type: str = "audio/wav"):
        try:
            with open(wav_path, "rb") as f:
                data = f.read()
        except OSError as e:
            self._send_error_json("synthesis_failed", str(e), 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    # ── Body reading ───────────────────────────────────────────────────────
    def _read_body(self) -> tuple[bytes | None, tuple[int, str] | None]:
        """Read and size-limit the request body. Returns (body, None) or (None, (status, msg))."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, (400, "invalid_request")
        if length > MAX_BODY_BYTES:
            return None, (413, "request_too_large")
        return self.rfile.read(length), None

    def _parse_json_body(self) -> tuple[dict | None, tuple[int, str, str] | None]:
        """Parse JSON body. Returns (data, None) or (None, (http_status, code, msg))."""
        body, err = self._read_body()
        if err:
            return None, (err[0], "request_too_large", f"Request body exceeds {MAX_BODY_BYTES} bytes")
        try:
            return json.loads(body or b"{}"), None
        except json.JSONDecodeError as e:
            return None, (400, "invalid_json", f"Invalid JSON: {e}")

    # ── Synthesize helper ──────────────────────────────────────────────────
    def _synthesize(
        self,
        engine_name: str,
        text: str,
        voice_id: str,
        speed: float = 1.0,
    ) -> tuple[str | None, tuple[int, str, str] | None]:
        """
        Run synthesis. Returns (tmp_wav_path, None) on success,
        or (None, (http_status, code, message)) on error.
        Never pass user input to subprocess or eval.
        """
        # Validate engine
        if engine_name not in VALID_ENGINES:
            return None, (400, "invalid_engine", f"Unknown engine: {engine_name!r}")

        # Validate speed
        try:
            speed = float(speed)
            if not (0.1 <= speed <= 4.0):
                raise ValueError
        except (ValueError, TypeError):
            return None, (400, "invalid_speed", "speed must be a float between 0.1 and 4.0")

        # Resolve voice to a model path (piper-specific; other engines use voice name)
        model_path = None
        if engine_name == "piper":
            if voice_id:
                # Look up voice_id in discovered voices
                matched = next(
                    (v for v in VOICE_LIST if v["voice_id"] == voice_id), None
                )
                if matched:
                    model_path = matched["model_path"]
                else:
                    # Try to find by filename stem in allowed dirs
                    try:
                        safe_name = validate_voice_name(voice_id)
                    except ValueError as e:
                        return None, (400, "invalid_voice", str(e))
                    for vdir in ALLOWED_VOICE_DIRS:
                        candidate = vdir / f"{safe_name}.onnx"
                        if candidate.exists():
                            try:
                                validate_voice_path(str(candidate))
                                model_path = str(candidate)
                                break
                            except ValueError:
                                pass
                    if not model_path:
                        return None, (404, "voice_not_found", f"Voice {voice_id!r} not found")

        # Build engine config
        from marmalade_tts.config import engine_cfg
        ecfg = engine_cfg(APP_CONFIG, engine_name)
        if model_path:
            ecfg = dict(ecfg)
            ecfg["model"] = model_path
        ecfg["daemon"] = False  # never use daemon mode in server context

        # Load engine
        try:
            engine = _load_engine(engine_name, ecfg)
        except Exception as e:
            log.error("Engine load failed: %s", e)
            return None, (500, "engine_unavailable", f"Engine {engine_name!r} unavailable: {e}")

        # Create temp file for output
        fd, tmp_path = tempfile.mkstemp(suffix=".wav", dir="/tmp")
        os.close(fd)

        try:
            engine.synthesize(
                text=text,
                out_path=tmp_path,
                speed=speed,
            )
        except Exception as e:
            log.error("Synthesis error: %s", e)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return None, (500, "synthesis_failed", f"Synthesis failed: {e}")

        return tmp_path, None

    # ── Main dispatcher ────────────────────────────────────────────────────
    def _handle(self):
        start = time.monotonic()
        method = self.command
        path = self.path.split("?")[0].rstrip("/") or "/"
        status = 200

        try:
            # OPTIONS pre-flight
            if method == "OPTIONS":
                self.send_response(204)
                self._add_cors_headers()
                self.end_headers()
                return

            # Health check — no auth required
            if method == "GET" and path == "/health":
                self._send_json(200, {"status": "ok", "version": VERSION})
                return

            # Auth check for all other routes
            if not self._check_auth():
                status = 401
                self._send_error_json("unauthorized", "Invalid or missing API key", 401)
                return

            # Rate limiting
            ip = self._get_client_ip()
            if not RATE_LIMITER.allow(ip):
                status = 429
                self._send_error_json("rate_limit_exceeded", "Too many requests", 429)
                return

            # Route dispatch
            if method == "GET" and path == "/v1/voices":
                self._handle_list_voices()
            elif method == "POST" and path == "/v1/audio/speech":
                self._handle_openai_speech()
            elif method == "POST" and path.startswith("/v1/text-to-speech/"):
                voice_id = path[len("/v1/text-to-speech/"):]
                self._handle_elevenlabs_speech(voice_id)
            else:
                status = 404
                self._send_error_json("not_found", f"No route: {method} {path}", 404)

        except BrokenPipeError:
            pass  # client disconnected
        except Exception as e:
            log.exception("Unhandled error: %s", e)
            status = 500
            try:
                self._send_error_json("internal_error", "Internal server error", 500)
            except Exception:
                pass
        finally:
            latency_ms = (time.monotonic() - start) * 1000
            log.info("%s %s %d %.1fms %s", method, path, status, latency_ms, self._get_client_ip())

    do_GET = _handle
    do_POST = _handle
    do_OPTIONS = _handle

    # ── Route handlers ─────────────────────────────────────────────────────
    def _handle_list_voices(self):
        self._send_json(200, {"voices": VOICE_LIST})

    def _handle_openai_speech(self):
        data, err = self._parse_json_body()
        if err:
            self._send_error_json(err[1], err[2], err[0])
            return

        # Extract and validate fields
        engine_name = str(data.get("model", "piper")).lower()
        raw_text = data.get("input", "")
        voice_id = str(data.get("voice", "en_US-lessac-medium"))
        speed = data.get("speed", 1.0)
        # response_format: only wav is supported
        fmt = str(data.get("response_format", "wav")).lower()
        if fmt not in ("wav", "pcm"):
            # Gracefully accept but warn — we always return wav
            log.debug("response_format=%r requested, returning wav", fmt)

        if not isinstance(raw_text, str) or not raw_text.strip():
            self._send_error_json("invalid_input", "'input' must be a non-empty string")
            return

        text = sanitize_text(raw_text)
        if len(text) > MAX_TEXT_LENGTH:
            self._send_error_json(
                "text_too_long",
                f"Text exceeds {MAX_TEXT_LENGTH} character limit",
                400,
            )
            return

        tmp_path, err = self._synthesize(engine_name, text, voice_id, speed)
        if err:
            self._send_error_json(err[1], err[2], err[0])
            return

        try:
            self._send_audio(tmp_path, "audio/wav")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _handle_elevenlabs_speech(self, raw_voice_id: str):
        # Validate voice_id from URL path
        try:
            voice_id = validate_voice_name(raw_voice_id)
        except ValueError as e:
            self._send_error_json("invalid_voice", str(e))
            return

        data, err = self._parse_json_body()
        if err:
            self._send_error_json(err[1], err[2], err[0])
            return

        raw_text = data.get("text", "")
        engine_name = str(data.get("model_id", "piper")).lower()
        voice_settings = data.get("voice_settings") or {}
        speed = voice_settings.get("speed", 1.0) if isinstance(voice_settings, dict) else 1.0

        if not isinstance(raw_text, str) or not raw_text.strip():
            self._send_error_json("invalid_input", "'text' must be a non-empty string")
            return

        text = sanitize_text(raw_text)
        if len(text) > MAX_TEXT_LENGTH:
            self._send_error_json(
                "text_too_long",
                f"Text exceeds {MAX_TEXT_LENGTH} character limit",
                400,
            )
            return

        tmp_path, err = self._synthesize(engine_name, text, voice_id, speed)
        if err:
            self._send_error_json(err[1], err[2], err[0])
            return

        try:
            # ElevenLabs returns audio/mpeg by default, but we return wav
            self._send_audio(tmp_path, "audio/wav")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ── Threaded HTTP server ───────────────────────────────────────────────────────
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle each request in a separate thread."""
    daemon_threads = True
    allow_reuse_address = True


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    server = ThreadedHTTPServer(("", PORT), TTSHandler)
    log.info("marmalade-tts HTTP server v%s listening on :%d", VERSION, PORT)
    log.info("Auth: API key configured (%d chars)", len(API_KEY))
    log.info("Rate limit: %.0f req/s per IP", RATE_LIMIT_RPS)
    log.info("Max text length: %d chars", MAX_TEXT_LENGTH)
    if CORS_ORIGIN:
        log.info("CORS: %s", CORS_ORIGIN)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
