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
        "fast":     {"kitten": "nano",  "kokoro": "af_heart", "piper": "en_US-lessac-medium", "coqui": "tts_models/en/ljspeech/tacotron2-DDC", "pocket": "alba",    "matcha": "matcha_ljspeech", "emojivoice": "paige", "api": "af_heart"},
        "balanced": {"kitten": "micro", "kokoro": "af_heart", "piper": "en_US-lessac-medium", "coqui": "tts_models/en/ljspeech/tacotron2-DDC", "pocket": "fantine", "matcha": "matcha_ljspeech", "emojivoice": "paige", "api": "af_heart"},
        "quality":  {"kitten": "mini",  "kokoro": "af_heart", "piper": "en_US-lessac-medium", "coqui": "tts_models/en/ljspeech/tacotron2-DDC", "pocket": "cosette", "matcha": "matcha_ljspeech", "emojivoice": "paige", "api": "af_heart"},
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
            # noise_scale: 0.667    # expressivity (lower = monotone)
            # noise_w_scale: 0.8    # cadence variation (lower = robotic)
        },
        "coqui": {
            "device": "cpu",
            "model": "tts_models/en/ljspeech/tacotron2-DDC",
            "daemon": False,
            # speaker / speaker_idx / language / speaker_wav / emotion
            # are optional; set the ones your model honors. See
            # docs/engine-knobs.md for which models support what.
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
        "api": {
            "base_url": "https://api.venice.ai/api/v1",
            "model": "tts-kokoro",
            "voice": "af_heart",
            "api_key_env": "VENICE_API_KEY",
            # api_key: sk-...       # inline key (env var preferred)
            # timeout: 120
            # extra: {}             # provider-specific payload passthrough
        },
    },
    # Aliases: named bundles (engine + voice + speed + …) invoked positionally
    # like an engine name — e.g. `marmalade-tts narrator "Once upon a time"`.
    # Engine names are reserved; an alias that shadows one is ignored with a
    # warning. Explicit CLI flags override alias defaults.
    "aliases": {},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` onto ``base``. ``override`` wins.

    Dicts merge key-by-key; lists and scalars are replaced outright (a user
    ``effects.defaults.kitten: [...]`` list is not spliced with the default).
    """
    merged = dict(base)
    for key, val in override.items():
        base_val = merged.get(key)
        if isinstance(base_val, dict) and isinstance(val, dict):
            merged[key] = _deep_merge(base_val, val)
        else:
            merged[key] = val
    return merged


def load() -> dict:
    """Load config from disk, deep-merged over the defaults.

    A hand-written or partial user config (e.g. missing ``presets:``, or a
    ``kitten`` engine block that only sets ``voice``) still gets every
    default key it didn't specify — user values win, defaults fill gaps.
    """
    cfg = load_raw()
    if cfg:
        return _deep_merge(DEFAULT_CONFIG, cfg)
    # Deep copy so callers can mutate without polluting the module-level defaults.
    return copy.deepcopy(DEFAULT_CONFIG)


def load_raw() -> dict:
    """Load the user's config file verbatim — no defaults merged.

    Write paths (``config set``, ``init``) must mutate THIS and save it, not
    the merged view from ``load()``: saving the merged config would pin
    today's defaults into the user's file, so future default changes could
    never reach them.
    """
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"[marmalade-tts] Warning: could not parse {CONFIG_PATH}: {e}",
                  file=sys.stderr)
            print("[marmalade-tts] Falling back to default config.", file=sys.stderr)
    return {}


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
