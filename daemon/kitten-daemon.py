#!/usr/bin/env python3
"""marmalade-tts kitten daemon — keeps the KittenTTS model loaded in RAM.

Request: {"text": "...", "voice": "Hugo", "speed": 1.0, "out": "/tmp/x.wav"}
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import serve

# Force CPU and offline mode — Pascal sm_61 isn't supported by current torch wheels,
# and we don't want re-downloads after the first cache fill.
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"

MODEL_REPOS = {
    "nano":  "KittenML/kitten-tts-nano-0.8",
    "micro": "KittenML/kitten-tts-micro-0.8",
    "mini":  "KittenML/kitten-tts-mini-0.8",
}

_raw_model = os.environ.get("KITTEN_MODEL", "nano")
MODEL_REPO = MODEL_REPOS.get(_raw_model, _raw_model)  # accept size name or full repo


def load_model():
    from kittentts import KittenTTS
    return KittenTTS(MODEL_REPO)


def synth(model, req):
    model.generate_to_file(
        req["text"],
        req["out"],
        voice=req.get("voice", "Hugo"),
        speed=float(req.get("speed", 1.0)),
    )


if __name__ == "__main__":
    serve("kitten", load_model, synth)
