"""EmojiVoice engine — emoji-controlled expressive TTS.

EmojiVoice (Tuttosi et al., SFU Rosie Lab) fine-tunes Matcha-TTS so that
an emoji in the text selects an emotional speaking style. Each speaker
checkpoint bakes the 11 emoji "styles" in as speaker ids; an emoji
anywhere in the text is mapped to its id and then stripped before
synthesis (the emoji sets the tone, it is not spoken).

https://github.com/rosielab/emojivoice  (MIT code)
Paper: https://arxiv.org/abs/2506.15085

It runs on Matcha-TTS, installed in its own venv (duplicated from the
`matcha` engine on purpose — keeping the venvs separate is simpler and
less fragile than sharing one).

The cold path runs `daemon/emojivoice-oneshot.py` inside the venv via the
venv's Python directly — calling matcha-tts's Python API rather than its
CLI. That avoids the upstream CLI's leak: it always writes a `.png`
mel-spectrogram next to each `.wav` (no flag disables it). The one-shot
writes only the WAV.

Install:  marmalade-tts install emojivoice
  (creates the Python 3.11 venv, installs matcha-tts + espeak-ng, fetches
  the paige speaker checkpoint, and self-tests. See
  marmalade_tts/installer.py.)
"""

import os
import subprocess
import sys

from . import Engine
from .. import daemon as dmgr

EMOJIVOICE_VENV = os.path.expanduser("~/.local/share/emojivoice-venv")
VENV_PYTHON = os.path.join(EMOJIVOICE_VENV, "bin", "python")
ONESHOT_SCRIPT = "emojivoice-oneshot.py"
MODELS_DIR = os.path.expanduser("~/.local/share/emojivoice/models")

# Matcha's length scale runs higher = slower; EmojiVoice tunes a shorter
# scale for more expressive delivery — matches upstream feel_me.py's
# SPEAKING_RATE = 0.8.
DEFAULT_LENGTH_SCALE = 0.8

# Speaker checkpoints. Only "paige" ships: its emoji -> speaker-id map is
# verified from EmojiVoice's feel_me.py. The olivia/zach checkpoints exist
# upstream but their per-emoji id maps are unverified, so they are left out
# until someone can confirm them (adding one is just a CHECKPOINTS +
# EMOJI_SPK + VOICES entry).
VOICES = ["paige"]

CHECKPOINTS = {
    "paige": "emoji-hri-paige-inference.ckpt",
}

# emoji -> speaker id, per speaker checkpoint. Verified for paige.
EMOJI_SPK = {
    "paige": {
        "😍": 107, "😡": 58, "😎": 79, "😭": 103, "🙄": 66, "😁": 18,
        "🙂": 12, "🤣": 15, "😮": 54, "😅": 22, "🤔": 17,
    },
}

# Speaker id used when the text has no recognized emoji.
NEUTRAL_SPK = 0


def parse_emoji(text: str, voice: str):
    """Resolve the emotional style from any emoji in `text`.

    Returns (speaker_id, cleaned_text). The first recognized emoji sets
    the speaker id; all recognized emojis are then stripped from the text
    (they set the tone, they are not spoken). With no recognized emoji,
    returns the neutral speaker id and the text unchanged.
    """
    emoji_map = EMOJI_SPK.get(voice, {})
    spk = NEUTRAL_SPK
    matched = False
    for ch in text:
        if ch in emoji_map:
            spk = emoji_map[ch]
            matched = True
            break
    if not matched:
        return spk, text
    cleaned = "".join(c for c in text if c not in emoji_map)
    # Collapse whitespace left behind by stripped emojis.
    cleaned = " ".join(cleaned.split())
    return spk, cleaned


class EmojiVoiceEngine(Engine):
    name = "emojivoice"
    MAX_CHARS = 500  # emojis are load-bearing — chunking may split emotion context

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.voice = cfg.get("voice", "paige")
        self.device = cfg.get("device", "cpu")
        self.use_daemon = cfg.get("daemon", False)
        # Quality knobs (see engines/matcha.py for the full explanation).
        # None means "let the engine venv default decide".
        self.steps = cfg.get("steps")
        self.temperature = cfg.get("temperature")

    def _checkpoint(self, voice: str) -> str:
        fname = CHECKPOINTS.get(voice)
        if not fname:
            sys.exit(f"[emojivoice] unknown speaker {voice!r}. "
                     f"Available: {', '.join(VOICES)}")
        return os.path.join(MODELS_DIR, fname)

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, **kwargs):
        v = voice or self.voice
        # parse_emoji must run here (in marmalade-tts's process), not in
        # the engine venv — EMOJI_SPK lives in this package, not the venv.
        spk, clean_text = parse_emoji(text, v)
        # Matcha-TTS (via espeak) chokes on parentheses — strip them.
        clean_text = clean_text.replace("(", "").replace(")", "")
        if not clean_text.strip():
            sys.exit("[emojivoice] nothing to speak after removing emoji(s)")
        # marmalade `speed` is a rate multiplier (1.4 = faster); Matcha's
        # length scale runs the other way (higher = slower), so invert an
        # explicit --speed. With no override, use EmojiVoice's expressive
        # default length scale.
        length_scale = (1.0 / speed) if (speed and speed != 1.0) else DEFAULT_LENGTH_SCALE

        if self.use_daemon:
            request = {"text": clean_text, "spk": spk, "voice": v,
                       "length_scale": length_scale, "out": out_path}
            if self.steps is not None:
                request["steps"] = int(self.steps)
            if self.temperature is not None:
                request["temperature"] = float(self.temperature)
            dmgr.synthesize("emojivoice", request, auto_start=True, timeout=120.0)
            return

        # ── One-shot subprocess fallback ──
        if not os.path.exists(VENV_PYTHON):
            sys.exit(
                f"[emojivoice] venv not found at {EMOJIVOICE_VENV}\n"
                f"  Run: marmalade-tts install emojivoice"
            )
        ckpt = self._checkpoint(v)
        if not os.path.exists(ckpt):
            sys.exit(
                f"[emojivoice] speaker checkpoint not found:\n  {ckpt}\n"
                f"  Run: marmalade-tts install emojivoice"
            )
        script = dmgr._find_daemon_script(ONESHOT_SCRIPT)
        if not os.path.exists(script):
            sys.exit(
                f"[emojivoice] one-shot script not found: {script}\n"
                f"  Reinstall: bash install.sh"
            )

        env = os.environ.copy()
        if self.device == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""

        cmd = [
            VENV_PYTHON, script,
            "--text", clean_text,
            "--out", out_path,
            "--checkpoint", ckpt,
            "--spk", str(spk),
            "--length-scale", str(length_scale),
        ]
        if self.steps is not None:
            cmd += ["--steps", str(int(self.steps))]
        if self.temperature is not None:
            cmd += ["--temperature", str(float(self.temperature))]

        proc = subprocess.run(cmd, capture_output=True, env=env)
        if proc.returncode != 0:
            sys.exit(f"[emojivoice] synthesis failed:\n"
                     f"{proc.stderr.decode(errors='replace')}")

    def list_voices(self):
        print("EmojiVoice speakers:")
        for v in VOICES:
            marker = " (default)" if v == self.voice else ""
            print(f"  {v}{marker}")
        emoji_map = EMOJI_SPK.get(self.voice, {})
        print()
        print("Emoji → emotion (put an emoji anywhere in the text — it sets")
        print("the emotional style and is not spoken):")
        print(f"  {'  '.join(emoji_map.keys())}")
        print()
        print('Example:  marmalade-tts emojivoice "I can\'t believe it 🤣"')
