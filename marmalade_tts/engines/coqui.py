"""Coqui TTS engine — daemon client with subprocess fallback.

Coqui's ``TTS.tts_to_file`` exposes a richer surface than the other engines:

  - ``speed``        — speed multiplier (honored by many but not all models)
  - ``speaker``      — speaker name (multi-speaker models like VITS-VCTK)
  - ``speaker_idx``  — speaker integer id (alternative to name)
  - ``language``     — IETF language code (multilingual models like XTTS)
  - ``speaker_wav``  — reference WAV file for XTTS voice cloning
  - ``emotion``      — emotion string (Tortoise + some VITS variants)

Which of these are honored depends on the model. We pass through any that
are set; Coqui itself decides whether to use them or ignore them.
``--list`` (``tts --list_models``) shows the available models; the model
card on the HuggingFace mirror documents which knobs each one supports.

marmalade-tts owns the install: coqui lives in its own venv and the `tts`
CLI is invoked by explicit path, never via $PATH.
"""

import os
import subprocess
import sys

from . import Engine
from .. import daemon as dmgr

COQUI_VENV = os.path.expanduser("~/.local/share/coqui-venv")
COQUI_BIN = os.path.join(COQUI_VENV, "bin", "tts")


class CoquiEngine(Engine):
    name = "coqui"
    MAX_CHARS = 500  # varies by model; conservative default

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = cfg.get("model", "tts_models/en/ljspeech/tacotron2-DDC")
        self.device = cfg.get("device", "cpu")
        self.use_daemon = cfg.get("daemon", False)
        # Optional model-specific knobs. None means "don't pass — let the
        # model use its own default". Configurable via:
        #   engines.coqui.speaker / speaker_idx / language / speaker_wav / emotion
        self.speaker = cfg.get("speaker")
        self.speaker_idx = cfg.get("speaker_idx")
        self.language = cfg.get("language")
        self.speaker_wav = cfg.get("speaker_wav")
        self.emotion = cfg.get("emotion")

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, speaker: str = None,
                   lang: str = None, speaker_wav: str = None,
                   emotion: str = None, **kwargs):
        # --voice overrides the model; per-call kwargs override config.
        model = voice or self.model
        speaker_val = speaker if speaker is not None else self.speaker
        language_val = lang if lang is not None else self.language
        speaker_wav_val = (speaker_wav if speaker_wav is not None
                           else self.speaker_wav)
        emotion_val = emotion if emotion is not None else self.emotion
        speaker_wav_val = (os.path.expanduser(speaker_wav_val)
                           if speaker_wav_val else None)

        if self.use_daemon:
            request = {"text": text, "out": out_path, "speed": float(speed)}
            if speaker_val is not None:
                request["speaker"] = speaker_val
            if self.speaker_idx is not None:
                request["speaker_idx"] = int(self.speaker_idx)
            if language_val is not None:
                request["language"] = language_val
            if speaker_wav_val is not None:
                request["speaker_wav"] = speaker_wav_val
            if emotion_val is not None:
                request["emotion"] = emotion_val
            dmgr.synthesize("coqui", request, auto_start=True, timeout=120.0)
            return

        # ── Subprocess fallback ──
        if not os.path.exists(COQUI_BIN):
            sys.exit(
                f"[coqui] coqui venv not found at {COQUI_VENV}\n"
                f"  Run: marmalade-tts install coqui"
            )

        env = os.environ.copy()
        if self.device == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""

        cmd = [COQUI_BIN, "--model_name", model, "--text", text,
               "--out_path", out_path]
        if speed and speed != 1.0:
            # Coqui's CLI takes --speed (honored by models that support it;
            # silently ignored otherwise — matches the Python API behavior).
            cmd += ["--speed", str(float(speed))]
        # speaker (name) wins over speaker_idx (integer) when both are set,
        # since the named form is more explicit and is what the CLI flag
        # passes. The `tts` CLI uses --speaker_idx for both shapes.
        if speaker_val is not None:
            cmd += ["--speaker_idx", str(speaker_val)]
        elif self.speaker_idx is not None:
            cmd += ["--speaker_idx", str(int(self.speaker_idx))]
        if language_val is not None:
            cmd += ["--language_idx", str(language_val)]
        if speaker_wav_val is not None:
            cmd += ["--speaker_wav", speaker_wav_val]
        # Note: the `tts` CLI doesn't expose --emotion as a top-level flag
        # (it's a per-model concept). For emotion-aware models, prefer
        # daemon mode where we route to the Python API.

        proc = subprocess.run(cmd, capture_output=True, env=env)
        if proc.returncode != 0:
            sys.exit(f"[coqui] synthesis failed:\n{proc.stderr.decode(errors='replace')}")

    def list_voices(self):
        if os.path.exists(COQUI_BIN):
            subprocess.run([COQUI_BIN, "--list_models"])
        else:
            print(f"[coqui] coqui venv not found at {COQUI_VENV}\n"
                  f"  Run: marmalade-tts install coqui")
