"""Coqui TTS engine — daemon client with subprocess fallback."""

import os
import shutil
import subprocess
import sys

from . import Engine
from .. import daemon as dmgr


class CoquiEngine(Engine):
    name = "coqui"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = cfg.get("model", "tts_models/en/ljspeech/tacotron2-DDC")
        self.device = cfg.get("device", "cpu")
        self.use_daemon = cfg.get("daemon", False)

    def synthesize(self, text: str, out_path: str, speed: float = 1.0, **kwargs):
        if self.use_daemon:
            request = {"text": text, "out": out_path}
            dmgr.synthesize("coqui", request, auto_start=True, timeout=120.0)
            return

        # Subprocess fallback
        if not shutil.which("tts"):
            sys.exit("[coqui] `tts` CLI not found. Run: pipx install coqui-tts")

        env = os.environ.copy()
        if self.device == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""

        cmd = ["tts", "--model_name", self.model, "--text", text, "--out_path", out_path]
        proc = subprocess.run(cmd, capture_output=True, env=env)
        if proc.returncode != 0:
            sys.exit(f"[coqui] synthesis failed:\n{proc.stderr.decode(errors='replace')}")

    def list_voices(self):
        if shutil.which("tts"):
            subprocess.run(["tts", "--list_models"])
        else:
            print("[coqui] `tts` CLI not found. Run: pipx install coqui-tts")
