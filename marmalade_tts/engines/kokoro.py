"""Kokoro TTS engine — daemon client with subprocess fallback.

Voice naming
------------
Each kokoro voice has a canonical upstream ID of the form
`<lang><gender>_<name>` (e.g. ``bm_george`` for "British male, George").
marmalade-tts exposes voices by their bare name as the primary form
(e.g. ``george``); the canonical IDs continue to work too.

Voice identity (the embedding) and the language used for pronunciation
are orthogonal in kokoro — the same voice embedding can speak any
supported language. Each voice has a "natural" language; if no other
language is configured, that's what we use. Override order:

  1. ``--lang`` flag on the CLI
  2. ``engines.kokoro.lang`` in config.yaml
  3. The voice's natural language
  4. Fallback to American English (``a``)
"""

import os

from . import Engine, run_in_venv
from .. import daemon as dmgr

# marmalade-tts owns the install: kokoro lives in its own venv and is
# invoked by explicit path, never via $PATH. A bare `kokoro` lookup would
# silently "work" against an unrelated install (or fail confusingly) — an
# explicit venv path makes a working install unambiguous and lets the
# hands-off installer self-test the engine exactly the way the CLI runs it.
KOKORO_VENV = os.path.expanduser("~/.local/share/kokoro-venv")
KOKORO_BIN = os.path.join(KOKORO_VENV, "bin", "kokoro")


# Bare name → canonical kokoro voice ID. Bare names are unique across
# languages today; if upstream adds a name that collides, the canonical
# form continues to work and the bare form will raise.
VOICE_ALIASES = {
    # American English (a)
    "heart":      "af_heart",
    "bella":      "af_bella",
    "nicole":     "af_nicole",
    "adam":       "am_adam",
    "michael":    "am_michael",
    # British English (b)
    "emma":       "bf_emma",
    "isabella":   "bf_isabella",
    "george":     "bm_george",
    "lewis":      "bm_lewis",
    # Japanese (j)
    "alpha":      "jf_alpha",
    "gongitsune": "jf_gongitsune",
    "kumo":       "jm_kumo",
    # Mandarin (z)
    "xiaobei":    "zf_xiaobei",
    "yunjian":    "zm_yunjian",
}

# Canonical voice ID → natural language code (the prefix's first letter).
VOICE_NATURAL_LANG = {canonical: canonical[0]
                      for canonical in VOICE_ALIASES.values()}

# Voice list grouped by natural language, for `--list` output.
VOICES_BY_LANG = {
    "a": ["heart", "bella", "nicole", "adam", "michael"],
    "b": ["emma", "isabella", "george", "lewis"],
    "j": ["alpha", "gongitsune", "kumo"],
    "z": ["xiaobei", "yunjian"],
}

LANG_NAMES = {
    "a": "American English",
    "b": "British English",
    "j": "Japanese",
    "z": "Mandarin",
    # Codes accepted but not currently shipped with voices upstream:
    "h": "Hindi", "e": "Spanish", "f": "French",
    "i": "Italian", "p": "Portuguese",
}

# All tokens the CLI should recognize as a positional voice argument —
# bare names and canonical IDs both count.
ALL_VOICE_TOKENS = frozenset(VOICE_ALIASES.keys()) | frozenset(VOICE_ALIASES.values())


def resolve_voice(token: str) -> str:
    """Return the canonical upstream voice ID for a user-supplied token.

    Accepts both bare names (``george``) and canonical IDs (``bm_george``).
    Unknown tokens are returned unchanged — kokoro itself will error on
    them, which is more informative than us pre-rejecting.
    """
    return VOICE_ALIASES.get(token, token)


def natural_lang(canonical_voice: str) -> str | None:
    """Natural language code for a canonical voice ID, or None if unknown."""
    return VOICE_NATURAL_LANG.get(canonical_voice)


def is_voice_token(token: str) -> bool:
    """Is `token` a valid kokoro voice in either short or canonical form?"""
    return token in ALL_VOICE_TOKENS


class KokoroEngine(Engine):
    name = "kokoro"
    MAX_CHARS = 500

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.voice = cfg.get("voice", "heart")
        # Note: lang is intentionally not defaulted here. When None, the
        # voice's natural language is used. Set explicitly in config or
        # via --lang to force a specific pronunciation.
        self.lang = cfg.get("lang")
        self.device = cfg.get("device", "cpu")
        self.use_daemon = cfg.get("daemon", False)

    def _resolve_lang(self, canonical_voice: str, cli_lang: str | None) -> str:
        """Apply the language-precedence rule.

        --lang flag > config engines.kokoro.lang > voice's natural language
        > fallback "a".
        """
        if cli_lang:
            return cli_lang
        if self.lang:
            return self.lang
        return natural_lang(canonical_voice) or "a"

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, lang: str = None, **kwargs):
        v = resolve_voice(voice or self.voice)
        la = self._resolve_lang(v, lang)

        if self.use_daemon:
            request = {"text": text, "voice": v, "speed": speed,
                       "lang": la, "out": out_path}
            dmgr.synthesize("kokoro", request, auto_start=True)
            return

        # Subprocess fallback
        env_extra = {"HF_HUB_OFFLINE": "1"}
        if self.device == "cpu":
            env_extra["CUDA_VISIBLE_DEVICES"] = ""

        cmd = [KOKORO_BIN, "--voice", v, "--output-file", out_path, "--text", text]
        if la:
            cmd += ["--language", la]
        if speed and speed != 1.0:
            cmd += ["--speed", str(speed)]

        run_in_venv(KOKORO_BIN, cmd, env_extra=env_extra, engine_name="kokoro")

    def list_voices(self):
        print("Kokoro voices (use the bare name, e.g. \"george\"):\n")
        for lang_code, names in VOICES_BY_LANG.items():
            label = LANG_NAMES.get(lang_code, lang_code)
            print(f"  {label} ({lang_code}):")
            print(f"    {', '.join(names)}")
        print()
        print("Each voice uses its natural language by default. Override with")
        print("--lang or set engines.kokoro.lang in your config. The canonical")
        print("upstream form (e.g. \"bm_george\") is also accepted everywhere.")
