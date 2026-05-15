"""Matcha-TTS engine — daemon client with subprocess fallback.

Matcha-TTS is a fast flow-matching neural TTS by Shivam Mehta et al.
https://github.com/shivammehta25/Matcha-TTS  (MIT)

It lives in its own venv. The CLI writes auto-numbered WAVs into an
output folder rather than to an exact path, so the subprocess path
synthesises into a temp dir and moves the result to `out_path`.

Install:  marmalade-tts install matcha
  (creates the Python 3.11 venv, installs matcha-tts + espeak-ng, and
  self-tests — matcha-tts does NOT build on Python 3.12, so the installer
  provisions 3.11 via uv. See marmalade_tts/installer.py.)
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile

from . import Engine
from .. import daemon as dmgr

MATCHA_VENV = os.path.expanduser("~/.local/share/matcha-tts-venv")
MATCHA_BIN = os.path.join(MATCHA_VENV, "bin", "matcha-tts")

# Built-in model names that matcha-tts auto-downloads on first use.
MODELS = ["matcha_ljspeech", "matcha_vctk"]
DEFAULT_MODEL = "matcha_ljspeech"

# Universal vocoder — works with every Matcha checkpoint, auto-downloads.
VOCODER = "hifigan_univ_v1"
STEPS = 10
TEMPERATURE = 0.667


def _is_checkpoint_path(model: str) -> bool:
    """A model spec is a checkpoint file path if it looks like one."""
    return model.endswith(".ckpt") or os.sep in model or model.startswith("~")


class MatchaEngine(Engine):
    name = "matcha"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = cfg.get("model", DEFAULT_MODEL)
        self.device = cfg.get("device", "cpu")
        self.use_daemon = cfg.get("daemon", False)
        # Optional speaker id for multi-speaker models (matcha_vctk: 0-107).
        self.spk = cfg.get("spk")

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, speaker: str = None, **kwargs):
        # Matcha-TTS (via espeak) chokes on parentheses — strip them.
        text = text.replace("(", "").replace(")", "")
        # `voice` overrides the model spec; `speaker` overrides the speaker id.
        model = voice or self.model
        spk = speaker if speaker is not None else self.spk

        if self.use_daemon:
            request = {"text": text, "speed": speed, "out": out_path}
            if spk is not None:
                request["spk"] = int(spk)
            dmgr.synthesize("matcha", request, auto_start=True, timeout=120.0)
            return

        # ── Subprocess fallback ──
        if not os.path.exists(MATCHA_BIN):
            sys.exit(
                f"[matcha] matcha-tts venv not found at {MATCHA_VENV}\n"
                f"  Run: marmalade-tts install matcha"
            )

        env = os.environ.copy()
        if self.device == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""

        # The CLI writes <output_folder>/utterance_NNN.wav (plus a .png
        # spectrogram), not an exact path — synthesise into a fresh temp dir
        # and move the single .wav result to out_path.
        tmpdir = tempfile.mkdtemp(prefix="marmalade-matcha-")
        try:
            cmd = [
                MATCHA_BIN,
                "--text", text,
                "--output_folder", tmpdir,
                "--vocoder", VOCODER,
                "--steps", str(STEPS),
                "--temperature", str(TEMPERATURE),
            ]
            if _is_checkpoint_path(model):
                cmd += ["--checkpoint_path", os.path.expanduser(model)]
            else:
                cmd += ["--model", model]
            if self.device == "cpu":
                cmd += ["--cpu"]
            # marmalade `speed` is a rate multiplier (1.4 = faster). Matcha's
            # --speaking_rate is a *length scale* — higher means SLOWER — so
            # invert. Only pass when non-default; otherwise Matcha uses the
            # model's own default rate.
            if speed and speed != 1.0:
                cmd += ["--speaking_rate", str(1.0 / speed)]
            if spk is not None:
                cmd += ["--spk", str(int(spk))]

            proc = subprocess.run(cmd, capture_output=True, env=env)
            if proc.returncode != 0:
                sys.exit(f"[matcha] synthesis failed:\n"
                         f"{proc.stderr.decode(errors='replace')}")

            wavs = glob.glob(os.path.join(tmpdir, "*.wav"))
            if not wavs:
                sys.exit(f"[matcha] no output produced\n"
                         f"{proc.stderr.decode(errors='replace')}")
            shutil.move(wavs[0], out_path)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def list_voices(self):
        print("Matcha-TTS models (auto-download on first use):")
        for m in MODELS:
            marker = " (default)" if m == self.model else ""
            print(f"  {m}{marker}")
        print()
        print("  matcha_ljspeech — single female speaker (LJSpeech)")
        print("  matcha_vctk     — multi-speaker; pick a speaker with --speaker N (0-107)")
        print()
        print("Custom checkpoint: set engines.matcha.model to a .ckpt path,")
        print("or pass --voice /path/to/model.ckpt")
