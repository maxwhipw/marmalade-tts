#!/usr/bin/env python3
"""marmalade-tts coqui daemon — keeps the Coqui TTS model loaded in RAM.

Request: {"text": "...", "out": "/tmp/x.wav"}
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import serve

os.environ["CUDA_VISIBLE_DEVICES"] = ""

DEFAULT_MODEL = os.environ.get("COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC")


def load_model():
    from TTS.api import TTS
    return TTS(DEFAULT_MODEL, gpu=False)


def synth(model, req):
    model.tts_to_file(req["text"], file_path=req["out"])


if __name__ == "__main__":
    serve("coqui", load_model, synth)
