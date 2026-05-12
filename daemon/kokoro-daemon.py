#!/usr/bin/env python3
"""marmalade-tts kokoro daemon — keeps the Kokoro pipeline loaded in RAM.

Request: {"text": "...", "voice": "af_heart", "speed": 1.0, "lang": "a", "out": "/tmp/x.wav"}
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import serve

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"

DEFAULT_LANG = os.environ.get("KOKORO_LANG", "a")


def load_model():
    from kokoro import KPipeline
    import soundfile as sf  # noqa: F401  — fail fast if missing
    return KPipeline(lang_code=DEFAULT_LANG, device="cpu")


def synth(pipeline, req):
    import numpy as np
    import soundfile as sf

    audio_chunks = []
    for result in pipeline(req["text"],
                           voice=req.get("voice", "af_heart"),
                           speed=float(req.get("speed", 1.0))):
        if result.audio is not None:
            audio_chunks.append(result.audio.numpy())

    if not audio_chunks:
        raise RuntimeError("No audio generated")

    audio = np.concatenate(audio_chunks)
    sf.write(req["out"], audio, 24000)


if __name__ == "__main__":
    serve("kokoro", load_model, synth)
