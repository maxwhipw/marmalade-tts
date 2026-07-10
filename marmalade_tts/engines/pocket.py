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

from . import Engine, run_in_venv, sox_tempo

VOICES = ["alba", "marius", "javert", "jean", "fantine", "cosette", "eponine", "azelma"]

# Smart-punctuation → ASCII, applied before pocket-tts tokenizes. The bundled
# SentencePiece vocab has only a straight apostrophe piece (U+0027) — no curly
# apostrophe and no contraction pieces — and pocket's NFKC normalization does
# not fold curly quotes. So a curly apostrophe (e.g. from a copy-paste) in a
# contraction like "that's" byte-falls-back and the model renders the OOV bytes
# as a stumble/pause. Folding to ASCII first makes contractions tokenize via the
# real `'` piece. Mirrors the Android engine's normalizeSmartPunctuation().
_SMART_PUNCT = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "ʼ": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "–": "-", "—": "-", "‒": "-", "―": "-",
    " ": " ", " ": " ", " ": " ",
    "…": ".",
}
_SMART_PUNCT_TABLE = {ord(k): v for k, v in _SMART_PUNCT.items()}


def normalize_smart_punctuation(text: str) -> str:
    """Fold curly quotes/apostrophes, dashes, NBSPs and ellipsis to ASCII."""
    return text.translate(_SMART_PUNCT_TABLE)

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
    MAX_CHARS = 500

    def __init__(self, cfg: dict):
        self.voice = cfg.get("voice", "alba")
        self.device = cfg.get("device", "cpu")  # always CPU for pocket

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, **kwargs):
        # Fold smart punctuation to ASCII before pocket-tts tokenizes — see
        # normalize_smart_punctuation for why (curly apostrophes break
        # contractions). Android parity (P-AG).
        text = normalize_smart_punctuation(text)

        # Built-in voice names pass through unchanged; ~ in a cloning path
        # (.wav / .safetensors) is expanded.
        v = os.path.expanduser(voice or self.voice)

        cmd = [POCKET_PYTHON, "-c", _SYNTH_SCRIPT, text, out_path, v]
        run_in_venv(POCKET_PYTHON, cmd,
                    env_extra={"CUDA_VISIBLE_DEVICES": ""},
                    engine_name="pocket")

        # Pocket-TTS has no native speed knob — honor --speed via sox.
        # See ENGINE-GUIDE.md "Honoring --speed".
        sox_tempo(out_path, speed)

    def list_voices(self):
        print("Pocket TTS voices (built-in):")
        for v in VOICES:
            marker = " (default)" if v == self.voice else ""
            print(f"  {v}{marker}")
        print("\nVoice cloning: pass any .wav file path as the voice.")
        print("For faster loading, export to .safetensors with pocket-tts export-voice.")
