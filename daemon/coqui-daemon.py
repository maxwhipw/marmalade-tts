#!/usr/bin/env python3
"""marmalade-tts coqui daemon — keeps the Coqui TTS model loaded in RAM.

Request:
  {
    "text": "...",
    "out": "/tmp/x.wav",
    "speed": 1.0,            # optional, default 1.0
    "speaker": "p225",       # optional, multi-speaker models
    "speaker_idx": 0,        # optional, integer speaker id
    "language": "en",        # optional, multilingual models
    "speaker_wav": "/path/to/ref.wav",  # optional, XTTS voice cloning
    "emotion": "Happy"       # optional, emotion-aware models
  }

Unknown fields are ignored. The model decides which of speaker /
speaker_idx / language / speaker_wav / emotion it actually honors; we
pass them through if set.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import serve, check_loaded

os.environ["CUDA_VISIBLE_DEVICES"] = ""

DEFAULT_MODEL = os.environ.get("COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC")


def load_model():
    from TTS.api import TTS
    return TTS(DEFAULT_MODEL, gpu=False)


# Knobs we pass straight through to tts_to_file if present in the request.
# Coqui itself decides which it honors per-model; unknown ones it ignores.
_PASSTHROUGH = ("speaker", "speaker_idx", "language", "speaker_wav", "emotion")


def synth(model, req):
    check_loaded("coqui", req.get("model"), DEFAULT_MODEL)
    kwargs = {"file_path": req["out"]}
    speed = req.get("speed")
    if speed is not None and float(speed) != 1.0:
        kwargs["speed"] = float(speed)
    for k in _PASSTHROUGH:
        if k in req and req[k] is not None:
            kwargs[k] = req[k]
    model.tts_to_file(req["text"], **kwargs)


if __name__ == "__main__":
    serve("coqui", load_model, synth)
