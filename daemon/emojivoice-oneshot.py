#!/usr/bin/env python3
"""marmalade-tts emojivoice one-shot — load model, synth one phrase, exit.

Invoked by `marmalade_tts.engines.emojivoice` (the cold path: no daemon
running). The engine wrapper has already resolved the emoji → speaker id
and stripped the emoji from the text — this script just synthesises the
cleaned text against the given speaker checkpoint.

Bypasses the upstream `matcha-tts` CLI so we don't get a stray
mel-spectrogram .png written next to every WAV.

Wire shape (argparse):
  --text TEXT          required (already emoji-stripped by the caller)
  --out PATH           required, destination WAV
  --checkpoint PATH    required, path to a speaker .ckpt
  --vocoder NAME       default: hifigan_univ_v1
  --spk INT            required, speaker id resolved from the original emoji
  --length-scale FLOAT default: 0.8 (EmojiVoice's expressive scale)
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
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--vocoder", default=_matcha_synth.DEFAULT_VOCODER)
    ap.add_argument("--spk", type=int, required=True)
    ap.add_argument("--length-scale", type=float, default=0.8)
    ap.add_argument("--steps", type=int, default=_matcha_synth.DEFAULT_STEPS)
    ap.add_argument("--temperature", type=float,
                    default=_matcha_synth.DEFAULT_TEMPERATURE)
    args = ap.parse_args()

    state = _matcha_synth.load(args.checkpoint, vocoder_name=args.vocoder)
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
