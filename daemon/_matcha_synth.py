"""Shared model-loading + synthesis helpers for Matcha-TTS-based engines.

Both the long-running daemons (matcha-daemon.py, emojivoice-daemon.py) and
the one-shot scripts (matcha-oneshot.py, emojivoice-oneshot.py) import
from here. Anything that touches the Matcha-TTS Python API lives in this
one module so warm-path and cold-path always go through the same code.

The helpers run on CPU by default (matcha checkpoints embedded an
omegaconf.DictConfig that breaks under torch>=2.6's stricter weights_only
default — the installer pins torch<2.6 to avoid that).
"""

import os

DEFAULT_VOCODER = "hifigan_univ_v1"
DEFAULT_STEPS = 10
DEFAULT_TEMPERATURE = 0.667
DEFAULT_DENOISER_STRENGTH = 0.00025


def _looks_like_checkpoint_path(spec: str) -> bool:
    """A model spec is a checkpoint file path if it looks like one."""
    return spec.endswith(".ckpt") or os.sep in spec or spec.startswith("~")


def load(model_or_checkpoint: str, device=None,
         vocoder_name: str = DEFAULT_VOCODER):
    """Load a Matcha-TTS model + vocoder.

    `model_or_checkpoint` is either a built-in name (``matcha_ljspeech``,
    ``matcha_vctk``) that matcha-tts will auto-download, or a path to a
    custom ``.ckpt`` file (EmojiVoice speaker checkpoints, etc).

    Returns a dict with the loaded model, vocoder, denoiser, device, and
    vocoder name (the shape both daemons used previously).
    """
    import torch
    from matcha.cli import MATCHA_URLS, VOCODER_URLS, load_matcha, load_vocoder
    from matcha.utils.utils import assert_model_downloaded, get_user_data_dir

    if device is None:
        device = torch.device("cpu")

    save_dir = get_user_data_dir()

    if _looks_like_checkpoint_path(model_or_checkpoint):
        # Custom checkpoint (e.g. EmojiVoice paige). load_matcha restores
        # the architecture from the checkpoint's saved hparams; the
        # model-name arg is just a label in this case.
        ckpt_path = os.path.expanduser(model_or_checkpoint)
        model = load_matcha("custom_model", ckpt_path, device)
    else:
        # Built-in name: resolve to the auto-downloaded path under the
        # matcha user-data directory.
        if model_or_checkpoint not in MATCHA_URLS:
            raise ValueError(
                f"unknown matcha model {model_or_checkpoint!r} "
                f"(known: {', '.join(MATCHA_URLS)})")
        model_path = save_dir / f"{model_or_checkpoint}.ckpt"
        assert_model_downloaded(model_path, MATCHA_URLS[model_or_checkpoint])
        model = load_matcha(model_or_checkpoint, model_path, device)

    vocoder_path = save_dir / vocoder_name
    assert_model_downloaded(vocoder_path, VOCODER_URLS[vocoder_name])
    vocoder, denoiser = load_vocoder(vocoder_name, vocoder_path, device)

    return {
        "device": device,
        "model": model,
        "vocoder": vocoder,
        "denoiser": denoiser,
        "vocoder_name": vocoder_name,
    }


def synth(state: dict, *, text: str, out_path: str, spk=None,
          length_scale: float = 1.0,
          steps: int = DEFAULT_STEPS,
          temperature: float = DEFAULT_TEMPERATURE,
          denoiser_strength: float = DEFAULT_DENOISER_STRENGTH):
    """Synthesize `text` to a WAV at `out_path` using a pre-loaded state.

    `state` is the dict returned by `load()`. `spk` is an optional speaker
    id (int) for multi-speaker checkpoints. `length_scale` is matcha's
    duration scale (higher = slower); callers convert from marmalade's
    speed-rate semantics before calling.
    """
    import torch
    import soundfile as sf
    from matcha.cli import process_text, to_waveform

    device = state["device"]
    # `MatchaTTS.synthesise` is wrapped in `torch.inference_mode()` upstream,
    # so its outputs are inference tensors. On newer torch those can't flow
    # into a graph-tracked module (the vocoder), so we wrap the whole
    # synthesise + vocoder call in inference_mode too — matching what
    # matcha-tts's own CLI does (`@torch.inference_mode()` on `cli()`).
    with torch.inference_mode():
        spks = (torch.tensor([int(spk)], device=device, dtype=torch.long)
                if spk is not None else None)
        text_input = process_text(0, text, device)
        output = state["model"].synthesise(
            text_input["x"], text_input["x_lengths"],
            n_timesteps=steps, temperature=temperature,
            spks=spks, length_scale=length_scale,
        )
        waveform = to_waveform(output["mel"], state["vocoder"],
                               state["denoiser"], denoiser_strength)
    sf.write(out_path, waveform.cpu().numpy(), 22050)
