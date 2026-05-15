#!/usr/bin/env python3
"""marmalade-tts matcha daemon — keeps the Matcha-TTS model + vocoder in RAM.

Request: {"text": "...", "speed": 1.0, "spk": null, "out": "/tmp/x.wav"}

Note: the resident-model path uses Matcha-TTS's Python API
(load_matcha / load_vocoder / process_text / to_waveform). The subprocess
path in marmalade_tts/engines/matcha.py uses the verified `matcha-tts`
CLI and is the reliable fallback if this API path needs adjustment.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import serve

os.environ["CUDA_VISIBLE_DEVICES"] = ""

DEFAULT_MODEL = os.environ.get("MATCHA_MODEL", "matcha_ljspeech")
VOCODER = os.environ.get("MATCHA_VOCODER", "hifigan_univ_v1")
STEPS = 10
TEMPERATURE = 0.667
DENOISER_STRENGTH = 0.00025


def load_model():
    import torch
    from matcha.cli import MATCHA_URLS, VOCODER_URLS, load_matcha, load_vocoder
    from matcha.utils.utils import assert_model_downloaded, get_user_data_dir

    device = torch.device("cpu")
    # Resolve (and download on first run) the model + vocoder checkpoint
    # paths — load_matcha / load_vocoder need real file paths, not names.
    save_dir = get_user_data_dir()
    model_path = save_dir / f"{DEFAULT_MODEL}.ckpt"
    assert_model_downloaded(model_path, MATCHA_URLS[DEFAULT_MODEL])
    vocoder_path = save_dir / VOCODER
    assert_model_downloaded(vocoder_path, VOCODER_URLS[VOCODER])

    model = load_matcha(DEFAULT_MODEL, model_path, device)
    vocoder, denoiser = load_vocoder(VOCODER, vocoder_path, device)
    return {"device": device, "model": model,
            "vocoder": vocoder, "denoiser": denoiser}


def synth(state, req):
    import torch
    import soundfile as sf
    from matcha.cli import process_text, to_waveform

    device = state["device"]
    spk = req.get("spk")
    spks = (torch.tensor([int(spk)], device=device, dtype=torch.long)
            if spk is not None else None)

    speed = float(req.get("speed", 1.0))
    length_scale = 1.0 / speed if speed else 1.0

    text_input = process_text(0, req["text"], device)
    output = state["model"].synthesise(
        text_input["x"], text_input["x_lengths"],
        n_timesteps=STEPS, temperature=TEMPERATURE,
        spks=spks, length_scale=length_scale,
    )
    waveform = to_waveform(output["mel"], state["vocoder"],
                           state["denoiser"], DENOISER_STRENGTH)
    sf.write(req["out"], waveform.cpu().numpy(), 22050)


if __name__ == "__main__":
    serve("matcha", load_model, synth)
