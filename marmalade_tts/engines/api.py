"""API TTS engine — OpenAI-compatible ``/audio/speech`` providers.

One engine covers every provider that speaks the OpenAI audio API shape
(Venice, OpenAI, Groq, DeepInfra, …): point ``engines.api.base_url`` at the
provider, name a model + voice, and supply a key. Defaults target Venice,
whose TTS lineup (Kokoro, Qwen3-TTS, xAI, Inworld) is served at
``https://api.venice.ai/api/v1``.

No venv, no install step, no daemon — there is nothing to keep warm, so
time-to-first-audio is just the network round trip plus server-side
synthesis.

Key resolution order:
  1. ``engines.api.api_key`` in config.yaml (discouraged — config files
     get pasted into issues; prefer the env var)
  2. the environment variable named by ``engines.api.api_key_env``
     (default ``VENICE_API_KEY``)
"""

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

from . import Engine, EngineError

DEFAULT_BASE_URL = "https://api.venice.ai/api/v1"
DEFAULT_MODEL = "tts-kokoro"
DEFAULT_VOICE = "af_heart"
DEFAULT_KEY_ENV = "VENICE_API_KEY"

# Venice's tts-kokoro voices (canonical kokoro IDs). Used for shell
# completion only — the authoritative list comes from ``list_voices``,
# which queries the provider live.
VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sky", "af_sarah",
    "am_adam", "am_michael", "am_onyx", "am_puck",
    "bf_emma", "bf_lily", "bm_george", "bm_daniel", "bm_fable", "bm_lewis",
]


class ApiEngine(Engine):
    name = "api"
    MAX_CHARS = 4000  # OpenAI-compatible endpoints cap input at 4096 chars

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.base_url = cfg.get("base_url", DEFAULT_BASE_URL).rstrip("/")
        self.model = cfg.get("model", DEFAULT_MODEL)
        self.voice = cfg.get("voice", DEFAULT_VOICE)
        self.timeout = cfg.get("timeout", 120)
        # Provider-specific payload extras (e.g. OpenAI's ``instructions``)
        # pass through verbatim — see config-default.yaml.
        self.extra = cfg.get("extra") or {}

    def _api_key(self) -> str:
        key = self.cfg.get("api_key")
        if key:
            return key
        env_name = self.cfg.get("api_key_env", DEFAULT_KEY_ENV)
        key = os.environ.get(env_name)
        if key:
            return key
        raise EngineError(
            f"[api] No API key found.\n"
            f"  Set the {env_name} environment variable, or put the key in\n"
            f"  config.yaml under engines.api.api_key (env var preferred)."
        )

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, **kwargs):
        payload = {
            "model": self.model,
            "input": text,
            "voice": voice or self.voice,
            # The rest of the pipeline (chunk concat, sox effects) assumes
            # WAV on disk, so we always ask the provider for wav.
            "response_format": "wav",
            "speed": speed,
            # Venice streams audio as it generates (first byte ~0.6s instead
            # of after full synthesis). We still read to completion — the
            # file is identical — but leaving this on keeps the door open
            # for progressive playback and costs nothing. Providers that
            # don't know the field ignore it; override via ``extra`` if one
            # ever rejects it.
            "streaming": True,
            **self.extra,
        }
        req = urllib.request.Request(
            f"{self.base_url}/audio/speech",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self._api_key()}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                audio = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                body = json.loads(body).get("error", body)
            except (json.JSONDecodeError, AttributeError):
                pass
            raise EngineError(
                f"[api] {self.base_url} returned HTTP {e.code}: {body}"
            ) from None
        except urllib.error.URLError as e:
            raise EngineError(
                f"[api] Could not reach {self.base_url}: {e.reason}"
            ) from None
        except OSError as e:
            # Read-phase failures (socket timeout mid-response, connection
            # reset) surface as bare OSError/TimeoutError, not URLError.
            raise EngineError(
                f"[api] Request to {self.base_url} failed: "
                f"{e or type(e).__name__}"
            ) from None

        if audio[:4] == b"RIFF":
            with open(out_path, "wb") as f:
                f.write(audio)
        else:
            # Some Venice models (tts-qwen3-*) ignore response_format and
            # return MP3 no matter what. The pipeline needs WAV on disk, so
            # transcode via ffmpeg.
            self._transcode_to_wav(audio, out_path)

    def _transcode_to_wav(self, audio: bytes, out_path: str):
        if not shutil.which("ffmpeg"):
            raise EngineError(
                "[api] Provider returned non-WAV audio and ffmpeg is not "
                "installed to convert it.\n"
                "  Install ffmpeg, or pick a model that honors "
                "response_format=wav (e.g. tts-kokoro)."
            )
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
            tmp.write(audio)
            tmp_path = tmp.name
        try:
            proc = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp_path, out_path],
                capture_output=True)
            if proc.returncode != 0:
                raise EngineError(
                    f"[api] ffmpeg failed to convert the provider's audio:\n"
                    f"{proc.stderr.decode(errors='replace')}")
        finally:
            os.unlink(tmp_path)

    def list_voices(self):
        """Query the provider's model list and print models + voices.

        Venice's ``/models?type=tts`` is public and includes per-model voice
        lists. Providers without that endpoint get a graceful fallback.
        """
        req = urllib.request.Request(f"{self.base_url}/models?type=tts")
        try:
            key = self._api_key()
            req.add_header("Authorization", f"Bearer {key}")
        except EngineError:
            pass  # Venice's model list works unauthenticated
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            print(f"[api] Could not list models from {self.base_url}: {e}")
            print(f"[api] Configured model: {self.model}  voice: {self.voice}")
            return

        models = data.get("data") or []
        if not models:
            print(f"[api] {self.base_url} listed no TTS models.")
            return
        print(f"API TTS models at {self.base_url}:")
        for m in models:
            mid = m.get("id", "?")
            spec = m.get("model_spec") or {}
            marker = "  ← configured" if mid == self.model else ""
            print(f"\n  {mid} — {spec.get('name', '')}{marker}")
            voices = spec.get("voices") or []
            if voices:
                print("    voices: " + ", ".join(voices))
