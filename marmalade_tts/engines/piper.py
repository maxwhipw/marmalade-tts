"""Piper TTS engine — daemon client with subprocess fallback."""

import os
import subprocess
import sys

from . import Engine
from .. import daemon as dmgr

PIPER_VOICES_DIR = os.path.expanduser("~/.local/share/piper/voices")

# marmalade-tts owns the install: piper lives in its own venv and is
# invoked by explicit path, never via $PATH. An explicit venv path makes
# a working install unambiguous and lets the hands-off installer
# self-test the engine exactly the way the CLI runs it.
PIPER_VENV = os.path.expanduser("~/.local/share/piper-venv")
PIPER_BIN = os.path.join(PIPER_VENV, "bin", "piper")


class PiperEngine(Engine):
    name = "piper"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = cfg.get("model")
        self.use_daemon = cfg.get("daemon", False)
        # Expressivity knobs (config-only, no CLI flag — same precedent as
        # matcha's steps/temperature). None means "use Piper's default".
        #   noise_scale   — timbre variation per utterance (default 0.667).
        #                   Lower = more monotone but consistent; higher =
        #                   more lively but more variable.
        #   noise_w_scale — per-phoneme duration variation (default 0.8).
        #                   Lower = more robotic pacing; higher = more
        #                   natural cadence variation.
        self.noise_scale = cfg.get("noise_scale")
        self.noise_w_scale = cfg.get("noise_w_scale")

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
                   speaker: str = None, voice: str = None,
                   model: str = None, **kwargs):
        # The CLI passes voice=; older callers pass model=. Treat them as
        # synonyms — both point at a .onnx voice model. Matches matcha/coqui.
        model = model or voice
        if self.use_daemon:
            request = {"text": text, "speed": speed, "out": out_path}
            if speaker is not None:
                request["speaker"] = speaker
            if self.noise_scale is not None:
                request["noise_scale"] = float(self.noise_scale)
            if self.noise_w_scale is not None:
                request["noise_w_scale"] = float(self.noise_w_scale)
            dmgr.synthesize("piper", request, auto_start=True)
            return

        # Subprocess fallback
        if not os.path.exists(PIPER_BIN):
            sys.exit(
                f"[piper] piper venv not found at {PIPER_VENV}\n"
                f"  Run: marmalade-tts install piper"
            )

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

        cmd = [PIPER_BIN, "--model", m, "--output-file", out_path]
        if speed and speed != 1.0:
            cmd += ["--length-scale", str(1.0 / speed)]
        if speaker is not None:
            cmd += ["--speaker", str(speaker)]
        if self.noise_scale is not None:
            cmd += ["--noise-scale", str(float(self.noise_scale))]
        if self.noise_w_scale is not None:
            cmd += ["--noise-w-scale", str(float(self.noise_w_scale))]

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
