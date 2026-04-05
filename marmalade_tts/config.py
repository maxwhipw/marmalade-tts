"""YAML config loader/writer with dot-path get/set."""

import os
import yaml

CONFIG_PATH = os.path.expanduser("~/.config/marmalade-tts/config.yaml")

# ── Default config (used when no file exists) ──────────────────────────────────
DEFAULT_CONFIG = {
    "defaults": {
        "engine": "kokoro",
        "device": "cpu",
        "speed": 1.0,
        "play": True,
    },
    "presets": {
        "fast":     {"kitten": "nano",  "kokoro": "af_heart", "piper": "en_US-lessac-medium", "coqui": "tts_models/en/ljspeech/tacotron2-DDC"},
        "balanced": {"kitten": "micro", "kokoro": "af_heart", "piper": "en_US-lessac-medium", "coqui": "tts_models/en/ljspeech/tacotron2-DDC"},
        "quality":  {"kitten": "mini",  "kokoro": "af_heart", "piper": "en_US-lessac-medium", "coqui": "tts_models/en/ljspeech/tacotron2-DDC"},
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
    },
}


def load() -> dict:
    """Load config from disk, falling back to defaults."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)
        if cfg:
            return cfg
    return dict(DEFAULT_CONFIG)


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


def set_path(cfg: dict, dotpath: str, value):
    """Set a value in cfg by dot-separated key path (creates parents)."""
    keys = dotpath.split(".")
    cur = cfg
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    # Try to parse value as YAML (so numbers/bools are typed correctly)
    if isinstance(value, str):
        try:
            value = yaml.safe_load(value)
        except Exception:
            pass
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
