"""Kokoro TTS engine — daemon client with subprocess fallback."""

import os
import subprocess
import sys

from . import Engine
from .. import daemon as dmgr

VOICES_BY_LANG = {
    "a": ["af_heart", "af_bella", "af_nicole", "am_adam", "am_michael"],
    "b": ["bf_emma", "bf_isabella", "bm_george", "bm_lewis"],
    "j": ["jf_alpha", "jf_gongitsune", "jm_kumo"],
    "z": ["zf_xiaobei", "zm_yunjian"],
}

LANG_NAMES = {
    "a": "American English", "b": "British English", "h": "Hindi",
    "e": "Spanish", "f": "French", "i": "Italian", "p": "Portuguese",
    "j": "Japanese", "z": "Mandarin",
}


class KokoroEngine(Engine):
    name = "kokoro"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.voice = cfg.get("voice", "af_heart")
        self.lang = cfg.get("lang", "a")
        self.device = cfg.get("device", "cpu")
        self.use_daemon = cfg.get("daemon", False)

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, lang: str = None, **kwargs):
        v = voice or self.voice
        la = lang or self.lang

        if self.use_daemon:
            request = {"text": text, "voice": v, "speed": speed, "lang": la, "out": out_path}
            dmgr.synthesize("kokoro", request, auto_start=True)
            return

        # Subprocess fallback
        env = os.environ.copy()
        if self.device == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""
        env["HF_HUB_OFFLINE"] = "1"

        cmd = ["kokoro", "--voice", v, "--output-file", out_path, "--text", text]
        if la:
            cmd += ["--language", la]
        if speed and speed != 1.0:
            cmd += ["--speed", str(speed)]

        proc = subprocess.run(cmd, capture_output=True, env=env)
        if proc.returncode != 0:
            sys.exit(f"[kokoro] synthesis failed:\n{proc.stderr.decode()}")

    def list_voices(self):
        for lang_code, voices in VOICES_BY_LANG.items():
            name = LANG_NAMES.get(lang_code, lang_code)
            print(f"  {name} ({lang_code}): {', '.join(voices)}")
        print(f"\nLanguage codes: {', '.join(f'{k}={v}' for k, v in LANG_NAMES.items())}")
