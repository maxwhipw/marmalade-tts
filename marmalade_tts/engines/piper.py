"""Piper TTS engine — daemon client with subprocess fallback."""

import os
import subprocess
import sys

from . import Engine
from .. import daemon as dmgr

PIPER_VOICES_DIR = os.path.expanduser("~/.local/share/piper/voices")


class PiperEngine(Engine):
    name = "piper"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = cfg.get("model")
        self.use_daemon = cfg.get("daemon", False)

    def _find_model(self) -> str:
        if self.model:
            return os.path.expanduser(self.model)
        if os.path.isdir(PIPER_VOICES_DIR):
            for root, _, files in os.walk(PIPER_VOICES_DIR):
                for f in files:
                    if f.endswith(".onnx"):
                        return os.path.join(root, f)
        return None

    def synthesize(self, text: str, out_path: str, speed: float = 1.0,
                   speaker: str = None, model: str = None, **kwargs):
        if self.use_daemon:
            request = {"text": text, "speed": speed, "out": out_path}
            if speaker is not None:
                request["speaker"] = speaker
            dmgr.synthesize("piper", request, auto_start=True)
            return

        # Subprocess fallback
        m = model or self._find_model()
        if not m:
            sys.exit(
                "[piper] No model found. Download one:\n"
                "  mkdir -p ~/.local/share/piper/voices && cd ~/.local/share/piper/voices\n"
                "  wget https://huggingface.co/rhasspy/piper-voices/resolve/main/"
                "en/en_US/lessac/medium/en_US-lessac-medium.onnx\n"
                "  wget https://huggingface.co/rhasspy/piper-voices/resolve/main/"
                "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
            )

        cmd = ["piper", "--model", m, "--output-file", out_path]
        if speed and speed != 1.0:
            cmd += ["--length-scale", str(1.0 / speed)]
        if speaker is not None:
            cmd += ["--speaker", str(speaker)]

        proc = subprocess.run(cmd, input=text.encode(), capture_output=True)
        if proc.returncode != 0:
            sys.exit(f"[piper] synthesis failed:\n{proc.stderr.decode(errors='replace')}")

    def list_voices(self):
        print(f"Piper voices dir: {PIPER_VOICES_DIR}")
        found = False
        if os.path.isdir(PIPER_VOICES_DIR):
            for root, _, files in os.walk(PIPER_VOICES_DIR):
                for f in files:
                    if f.endswith(".onnx"):
                        print(f"  {os.path.join(root, f)}")
                        found = True
        if not found:
            print("  (no voices downloaded)")
        print("\nBrowse: https://rhasspy.github.io/piper-samples/")
