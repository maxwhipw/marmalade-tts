#!/usr/bin/env python3
"""marmalade-tts matcha daemon — keeps the Matcha-TTS model + vocoder in RAM.

Request: {"text": "...", "speed": 1.0, "spk": null, "out": "/tmp/x.wav"}

Model loading + synthesis live in `_matcha_synth.py` so the warm (daemon)
path and the cold (one-shot) path go through the same code.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import serve
import _matcha_synth

os.environ["CUDA_VISIBLE_DEVICES"] = ""

DEFAULT_MODEL = os.environ.get("MATCHA_MODEL", "matcha_ljspeech")
VOCODER = os.environ.get("MATCHA_VOCODER", "hifigan_univ_v1")


def load_model():
    return _matcha_synth.load(DEFAULT_MODEL, vocoder_name=VOCODER)


def synth(state, req):
    spk = req.get("spk")
    speed = float(req.get("speed", 1.0))
    length_scale = 1.0 / speed if speed else 1.0
    _matcha_synth.synth(
        state,
        text=req["text"],
        out_path=req["out"],
        spk=int(spk) if spk is not None else None,
        length_scale=length_scale,
    )


if __name__ == "__main__":
    serve("matcha", load_model, synth)
