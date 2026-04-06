"""Pocket TTS engine — kyutai-labs/pocket-tts.

100M parameter CPU-only TTS. Very fast (~6x realtime), low latency (~200ms),
voice cloning via wav files. English only.

Built-in voices: alba, marius, javert, jean, fantine, cosette, eponine, azelma

Install:
  pip install pocket-tts
"""

import os

VOICES = ["alba", "marius", "javert", "jean", "fantine", "cosette", "eponine", "azelma"]

# Cache the model and voice states to avoid reloading on every call.
_model = None
_voice_states = {}


def _get_model():
    global _model
    if _model is None:
        from pocket_tts import TTSModel
        _model = TTSModel.load_model()
    return _model


def _get_voice_state(model, voice: str):
    """Get or cache a voice state. Supports built-in names, .wav paths, and .safetensors."""
    if voice not in _voice_states:
        _voice_states[voice] = model.get_state_for_audio_prompt(voice)
    return _voice_states[voice]


class PocketEngine:
    """Pocket TTS engine for marmalade-tts."""

    def __init__(self, cfg: dict):
        self.voice = cfg.get("voice", "alba")
        self.device = cfg.get("device", "cpu")  # always CPU for pocket

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, **kwargs):
        import scipy.io.wavfile

        model = _get_model()
        v = voice or self.voice
        state = _get_voice_state(model, v)

        audio = model.generate_audio(state, text)
        scipy.io.wavfile.write(out_path, model.sample_rate, audio.numpy())

    def list_voices(self):
        print("Pocket TTS voices (built-in):")
        for v in VOICES:
            marker = " (default)" if v == self.voice else ""
            print(f"  {v}{marker}")
        print("\nVoice cloning: pass any .wav file path as the voice.")
        print("For faster loading, export to .safetensors with pocket-tts export-voice.")
