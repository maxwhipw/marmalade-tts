"""YAML config loader/writer with dot-path get/set."""

import copy
import os
import sys

import yaml

CONFIG_PATH = os.path.expanduser("~/.config/marmalade-tts/config.yaml")

# ── Default config (used when no file exists) ──────────────────────────────────
DEFAULT_CONFIG = {
    "defaults": {
        "engine": "kitten",
        "device": "cpu",
        "speed": 1.0,
        "play": True,
    },
    "presets": {
        "fast":     {"kitten": "nano",  "kokoro": "af_heart", "piper": "en_US-lessac-medium", "coqui": "tts_models/en/ljspeech/tacotron2-DDC", "pocket": "alba",    "matcha": "matcha_ljspeech", "emojivoice": "paige"},
        "balanced": {"kitten": "micro", "kokoro": "af_heart", "piper": "en_US-lessac-medium", "coqui": "tts_models/en/ljspeech/tacotron2-DDC", "pocket": "fantine", "matcha": "matcha_ljspeech", "emojivoice": "paige"},
        "quality":  {"kitten": "mini",  "kokoro": "af_heart", "piper": "en_US-lessac-medium", "coqui": "tts_models/en/ljspeech/tacotron2-DDC", "pocket": "cosette", "matcha": "matcha_ljspeech", "emojivoice": "paige"},
    },
    "engines": {
        "kitten": {
            "device": "cpu",
            "model_size": "micro",
            "voice": "Kiki",
            "daemon": True,
        },
        "kokoro": {
            "device": "cpu",
            "voice": "af_heart",
            "lang": "a",
            "daemon": False,
        },
        "piper": {
            "device": "cpu",
            "model": "~/.local/share/piper/voices/en_US-lessac-medium.onnx",
            "daemon": False,
        },
        "coqui": {
            "device": "cpu",
            "model": "tts_models/en/ljspeech/tacotron2-DDC",
            "daemon": False,
        },
        "pocket": {
            "device": "cpu",
            "voice": "alba",
        },
        "matcha": {
            "device": "cpu",
            "model": "matcha_ljspeech",
            "daemon": False,
        },
        "emojivoice": {
            "device": "cpu",
            "voice": "paige",
            "daemon": False,
        },
    },
}


def load() -> dict:
    """Load config from disk, falling back to defaults."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"[marmalade-tts] Warning: could not parse {CONFIG_PATH}: {e}",
                  file=sys.stderr)
            print("[marmalade-tts] Falling back to default config.", file=sys.stderr)
            cfg = None
        if cfg:
            return cfg
    # Deep copy so callers can mutate without polluting the module-level defaults.
    return copy.deepcopy(DEFAULT_CONFIG)


def save(cfg: dict):
    """Write config to disk."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)


def get_path(cfg: dict, dotpath: str):
    """Traverse cfg by dot-separated key path. Returns (value, found)."""
    keys = dotpath.split(".")
    cur = cfg
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None, False
    return cur, True


def _coerce_value(s: str):
    """Coerce a CLI-supplied string to a typed Python value.

    Predictable rules (chosen so LLM-generated commands don't surprise):
      - ``true`` / ``false``           → bool  (case-insensitive)
      - ``null`` / ``~`` / empty       → None
      - integer-looking                → int
      - float-looking                  → float
      - everything else                → string, preserved verbatim

    Deliberately does NOT honor YAML 1.1's ``yes/no/on/off`` aliases —
    those are a common footgun (the "Norway problem"). A future engine
    or voice named ``"on"`` keeps its name.
    """
    if not isinstance(s, str):
        return s
    lower = s.strip().lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in ("null", "~", ""):
        return None
    # int — must be pure digits with optional leading sign, no leading zeros
    # weirdness (so "007" stays a string).
    try:
        if s.lstrip("-+").isdigit():
            return int(s)
    except (ValueError, AttributeError):
        pass
    try:
        return float(s)
    except (ValueError, TypeError):
        return s


def set_path(cfg: dict, dotpath: str, value):
    """Set a value in cfg by dot-separated key path (creates parents)."""
    keys = dotpath.split(".")
    cur = cfg
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    if isinstance(value, str):
        value = _coerce_value(value)
    cur[keys[-1]] = value


def engine_cfg(cfg: dict, engine: str) -> dict:
    """Return merged engine config (defaults + engine-specific)."""
    base = {
        "device": cfg.get("defaults", {}).get("device", "cpu"),
        "speed": cfg.get("defaults", {}).get("speed", 1.0),
    }
    eng = cfg.get("engines", {}).get(engine, {})
    base.update(eng)
    return base
