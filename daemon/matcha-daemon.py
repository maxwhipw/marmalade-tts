#!/usr/bin/env python3
"""marmalade-tts matcha daemon — keeps the Matcha-TTS model + vocoder in RAM.

Request: {"text": "...", "speed": 1.0, "spk": null, "out": "/tmp/x.wav",
          "steps": 10, "temperature": 0.667}
  steps and temperature are optional; if omitted the daemon falls back to
  the defaults in _matcha_synth.

Model loading + synthesis live in `_matcha_synth.py` so the warm (daemon)
path and the cold (one-shot) path go through the same code.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import serve, check_loaded
import _matcha_synth

os.environ["CUDA_VISIBLE_DEVICES"] = ""

DEFAULT_MODEL = os.environ.get("MATCHA_MODEL", "matcha_ljspeech")
VOCODER = os.environ.get("MATCHA_VOCODER", "hifigan_univ_v1")


def load_model():
    return _matcha_synth.load(DEFAULT_MODEL, vocoder_name=VOCODER)


def synth(state, req):
    check_loaded("matcha", req.get("model"), DEFAULT_MODEL)
    spk = req.get("spk")
    speed = float(req.get("speed", 1.0))
    length_scale = 1.0 / speed if speed else 1.0
    kwargs = {
        "text": req["text"],
        "out_path": req["out"],
        "spk": int(spk) if spk is not None else None,
        "length_scale": length_scale,
    }
    # Pass quality knobs through only when the caller set them, so the
    # _matcha_synth defaults stay authoritative when nobody overrides.
    if "steps" in req:
        kwargs["steps"] = int(req["steps"])
    if "temperature" in req:
        kwargs["temperature"] = float(req["temperature"])
    _matcha_synth.synth(state, **kwargs)


if __name__ == "__main__":
    serve("matcha", load_model, synth)
