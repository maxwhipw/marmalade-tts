#!/usr/bin/env python3
"""marmalade-tts emojivoice daemon — Matcha-TTS + EmojiVoice checkpoint in RAM.

Request: {"text": "...", "spk": 103, "length_scale": 0.8, "out": "/tmp/x.wav"}

The engine wrapper (marmalade_tts/engines/emojivoice.py) has already parsed
the emoji -> speaker id and stripped the emoji from the text, so this daemon
just synthesises the cleaned text at the given speaker id.

Note: the resident-model path uses Matcha-TTS's Python API. The subprocess
path in the engine wrapper uses the verified `matcha-tts` CLI and is the
reliable fallback if this API path needs adjustment.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import serve

os.environ["CUDA_VISIBLE_DEVICES"] = ""

CKPT = os.environ.get(
    "EMOJIVOICE_CKPT",
    os.path.expanduser(
        "~/.local/share/emojivoice/models/emoji-hri-paige-inference.ckpt"),
)
VOCODER = os.environ.get("EMOJIVOICE_VOCODER", "hifigan_univ_v1")
STEPS = 10
TEMPERATURE = 0.667
DENOISER_STRENGTH = 0.00025


def load_model():
    import torch
    from matcha.cli import VOCODER_URLS, load_matcha, load_vocoder
    from matcha.utils.utils import assert_model_downloaded, get_user_data_dir

    device = torch.device("cpu")
    # The model is the EmojiVoice speaker checkpoint itself (already a real
    # file path). load_matcha restores the architecture from the checkpoint's
    # saved hparams, so the model-name arg is just a label.
    model = load_matcha("custom_model", CKPT, device)
    # Resolve (and download on first run) the universal vocoder checkpoint —
    # load_vocoder needs a real file path, not a name.
    vocoder_path = get_user_data_dir() / VOCODER
    assert_model_downloaded(vocoder_path, VOCODER_URLS[VOCODER])
    vocoder, denoiser = load_vocoder(VOCODER, vocoder_path, device)
    return {"device": device, "model": model,
            "vocoder": vocoder, "denoiser": denoiser}


def synth(state, req):
    import torch
    import soundfile as sf
    from matcha.cli import process_text, to_waveform

    device = state["device"]
    spk = int(req.get("spk", 0))
    spks = torch.tensor([spk], device=device, dtype=torch.long)

    # The engine wrapper already computed the length scale (higher = slower);
    # the daemon uses it directly.
    length_scale = float(req.get("length_scale", 0.8))

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
    serve("emojivoice", load_model, synth)
