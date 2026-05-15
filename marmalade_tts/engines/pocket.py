"""Pocket TTS engine — kyutai-labs/pocket-tts.

100M parameter CPU-only TTS. Very fast (~6x realtime), low latency (~200ms),
voice cloning via wav files. English only.

Built-in voices: alba, marius, javert, jean, fantine, cosette, eponine, azelma

marmalade-tts owns the install: pocket-tts lives in its own venv and is
invoked as a subprocess by explicit path. pocket-tts has no CLI entrypoint,
so the venv's python runs a short inline script. Calling into the venv
explicitly — rather than importing pocket_tts in-process — keeps pocket's
heavy torch dependency out of marmalade-tts's own environment and lets the
hands-off installer self-test the engine exactly the way the CLI runs it.

Install:
  marmalade-tts install pocket
"""

import os
import subprocess
import sys

from . import Engine

VOICES = ["alba", "marius", "javert", "jean", "fantine", "cosette", "eponine", "azelma"]

POCKET_VENV = os.path.expanduser("~/.local/share/pocket-tts-venv")
POCKET_PYTHON = os.path.join(POCKET_VENV, "bin", "python")

# Inline script run inside the pocket-tts venv. Loads the model, resolves the
# voice (built-in name, .wav path, or .safetensors export), synthesizes, and
# writes a WAV. Args: <text> <out_path> <voice>.
_SYNTH_SCRIPT = """\
import sys
import scipy.io.wavfile
from pocket_tts import TTSModel

text, out_path, voice = sys.argv[1], sys.argv[2], sys.argv[3]
model = TTSModel.load_model()
state = model.get_state_for_audio_prompt(voice)
audio = model.generate_audio(state, text)
scipy.io.wavfile.write(out_path, model.sample_rate, audio.numpy())
"""


class PocketEngine(Engine):
    """Pocket TTS engine for marmalade-tts."""

    name = "pocket"

    def __init__(self, cfg: dict):
        self.voice = cfg.get("voice", "alba")
        self.device = cfg.get("device", "cpu")  # always CPU for pocket

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, **kwargs):
        if not os.path.exists(POCKET_PYTHON):
            sys.exit(
                f"[pocket] pocket-tts venv not found at {POCKET_VENV}\n"
                f"  Run: marmalade-tts install pocket"
            )
        # Built-in voice names pass through unchanged; ~ in a cloning path
        # (.wav / .safetensors) is expanded.
        v = os.path.expanduser(voice or self.voice)

        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = ""

        cmd = [POCKET_PYTHON, "-c", _SYNTH_SCRIPT, text, out_path, v]
        proc = subprocess.run(cmd, capture_output=True, env=env)
        if proc.returncode != 0:
            sys.exit(f"[pocket] synthesis failed:\n{proc.stderr.decode(errors='replace')}")

    def list_voices(self):
        print("Pocket TTS voices (built-in):")
        for v in VOICES:
            marker = " (default)" if v == self.voice else ""
            print(f"  {v}{marker}")
        print("\nVoice cloning: pass any .wav file path as the voice.")
        print("For faster loading, export to .safetensors with pocket-tts export-voice.")
