#!/usr/bin/env python3
"""marmalade-tts piper daemon — keeps the Piper voice model loaded in RAM.

Request: {"text": "...", "speed": 1.0, "speaker": null, "out": "/tmp/x.wav"}
"""

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import serve

DEFAULT_MODEL = os.environ.get(
    "PIPER_MODEL",
    os.path.expanduser("~/.local/share/piper/voices/en_US-lessac-medium.onnx"),
)


def load_model():
    from piper import PiperVoice
    return PiperVoice.load(DEFAULT_MODEL)


def synth(voice, req):
    from piper.config import SynthesisConfig

    speed = float(req.get("speed", 1.0))
    syn_cfg = SynthesisConfig()
    syn_cfg.length_scale = 1.0 / speed if speed else 1.0
    speaker = req.get("speaker")
    if speaker is not None:
        syn_cfg.speaker_id = int(speaker)

    with open(req["out"], "wb") as raw_file:
        wav_file = wave.open(raw_file, "wb")
        voice.synthesize_wav(req["text"], wav_file, syn_config=syn_cfg)
        wav_file.close()


if __name__ == "__main__":
    serve("piper", load_model, synth)
