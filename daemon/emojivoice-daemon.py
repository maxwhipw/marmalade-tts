#!/usr/bin/env python3
"""marmalade-tts emojivoice daemon — Matcha-TTS + EmojiVoice checkpoint in RAM.

Request: {"text": "...", "spk": 103, "length_scale": 0.8, "out": "/tmp/x.wav",
          "steps": 10, "temperature": 0.667}
  steps and temperature are optional; if omitted, _matcha_synth defaults
  apply.

The engine wrapper (marmalade_tts/engines/emojivoice.py) has already parsed
the emoji -> speaker id and stripped the emoji from the text, so this daemon
just synthesises the cleaned text at the given speaker id.

Model loading + synthesis live in `_matcha_synth.py` so the warm (daemon)
path and the cold (one-shot) path go through the same code.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import serve
import _matcha_synth

os.environ["CUDA_VISIBLE_DEVICES"] = ""

CKPT = os.environ.get(
    "EMOJIVOICE_CKPT",
    os.path.expanduser(
        "~/.local/share/emojivoice/models/emoji-hri-paige-inference.ckpt"),
)
VOCODER = os.environ.get("EMOJIVOICE_VOCODER", "hifigan_univ_v1")


def load_model():
    return _matcha_synth.load(CKPT, vocoder_name=VOCODER)


def synth(state, req):
    # The engine wrapper already computed the length scale (higher = slower);
    # the daemon uses it directly.
    kwargs = {
        "text": req["text"],
        "out_path": req["out"],
        "spk": int(req.get("spk", 0)),
        "length_scale": float(req.get("length_scale", 0.8)),
    }
    if "steps" in req:
        kwargs["steps"] = int(req["steps"])
    if "temperature" in req:
        kwargs["temperature"] = float(req["temperature"])
    _matcha_synth.synth(state, **kwargs)


if __name__ == "__main__":
    serve("emojivoice", load_model, synth)
