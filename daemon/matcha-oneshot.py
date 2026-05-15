#!/usr/bin/env python3
"""marmalade-tts matcha one-shot — load model, synth one phrase, exit.

Invoked by `marmalade_tts.engines.matcha` (the cold path: no daemon
running). Bypasses the upstream `matcha-tts` CLI so we don't get a stray
mel-spectrogram .png written next to every WAV.

Wire shape (argparse):
  --text TEXT          required
  --out PATH           required, destination WAV
  --model NAME|CKPT    built-in name (matcha_ljspeech / matcha_vctk) or
                       a .ckpt path. Default: matcha_ljspeech
  --vocoder NAME       default: hifigan_univ_v1
  --spk INT            optional speaker id (matcha_vctk: 0-107)
  --length-scale FLOAT default: 1.0 (higher = slower)
  --steps INT          default: 10
  --temperature FLOAT  default: 0.667
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _matcha_synth

os.environ["CUDA_VISIBLE_DEVICES"] = ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="matcha_ljspeech")
    ap.add_argument("--vocoder", default=_matcha_synth.DEFAULT_VOCODER)
    ap.add_argument("--spk", type=int, default=None)
    ap.add_argument("--length-scale", type=float, default=1.0)
    ap.add_argument("--steps", type=int, default=_matcha_synth.DEFAULT_STEPS)
    ap.add_argument("--temperature", type=float,
                    default=_matcha_synth.DEFAULT_TEMPERATURE)
    args = ap.parse_args()

    state = _matcha_synth.load(args.model, vocoder_name=args.vocoder)
    _matcha_synth.synth(
        state,
        text=args.text,
        out_path=args.out,
        spk=args.spk,
        length_scale=args.length_scale,
        steps=args.steps,
        temperature=args.temperature,
    )


if __name__ == "__main__":
    main()
