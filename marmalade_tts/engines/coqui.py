"""Coqui TTS engine — daemon client with subprocess fallback."""

import os
import subprocess
import sys

from . import Engine
from .. import daemon as dmgr

# marmalade-tts owns the install: coqui lives in its own venv and the `tts`
# CLI is invoked by explicit path, never via $PATH. An explicit venv path
# makes a working install unambiguous and lets the hands-off installer
# self-test the engine exactly the way the CLI runs it.
COQUI_VENV = os.path.expanduser("~/.local/share/coqui-venv")
COQUI_BIN = os.path.join(COQUI_VENV, "bin", "tts")


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
        if not os.path.exists(COQUI_BIN):
            sys.exit(
                f"[coqui] coqui venv not found at {COQUI_VENV}\n"
                f"  Run: marmalade-tts install coqui"
            )

        env = os.environ.copy()
        if self.device == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""

        cmd = [COQUI_BIN, "--model_name", self.model, "--text", text, "--out_path", out_path]
        proc = subprocess.run(cmd, capture_output=True, env=env)
        if proc.returncode != 0:
            sys.exit(f"[coqui] synthesis failed:\n{proc.stderr.decode(errors='replace')}")

    def list_voices(self):
        if os.path.exists(COQUI_BIN):
            subprocess.run([COQUI_BIN, "--list_models"])
        else:
            print(f"[coqui] coqui venv not found at {COQUI_VENV}\n"
                  f"  Run: marmalade-tts install coqui")
