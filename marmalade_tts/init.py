"""Interactive and non-interactive init wizard for marmalade-tts."""

import os
import sys

from .engines.api import VOICES as _API_VOICE_CHOICES
from .engines.kokoro import (
    VOICES_BY_LANG as _KOKORO_VOICES_BY_LANG,
    is_voice_token as _kokoro_is_voice_token,
)

# Flatten kokoro voice list into a single ordered list of bare names.
_KOKORO_VOICE_CHOICES = [v for voices in _KOKORO_VOICES_BY_LANG.values() for v in voices]

# Engine metadata used by both the TUI and non-interactive paths.
ENGINE_INFO = {
    "kitten": {
        "label": "Kitten TTS",
        "desc":  "Fast, lightweight, great quality. Ships by default.",
        "size":  "~23–80 MB (nano/micro/mini)",
        "default": True,
        "options": {
            "model_size": {
                "prompt": "Model size",
                "choices": ["nano", "micro", "mini"],
                "default": "micro",
                "help": "nano (~23MB, fastest)  micro (~41MB, balanced)  mini (~80MB, best quality)",
            },
        },
    },
    "piper": {
        "label": "Piper",
        "desc":  "Very fast ONNX engine. Many community voices available.",
        "size":  "~15–75 MB per voice model",
        "default": True,
        "options": {},
    },
    "kokoro": {
        "label": "Kokoro",
        "desc":  "High quality, multilingual. Needs ~500 MB + optional GPU.",
        "size":  "~500 MB",
        "default": False,
        "options": {
            "voice": {
                "prompt": "Default voice",
                "choices": _KOKORO_VOICE_CHOICES,
                "default": "heart",
                # Custom validator: accepts bare names AND canonical IDs
                # (e.g. both "george" and "bm_george"). Used by the
                # non-interactive path; the interactive picker still
                # shows only the bare names from `choices`.
                "validate": _kokoro_is_voice_token,
                "help": ("Voices grouped by natural language: American (heart, bella, "
                         "nicole, adam, michael), British (emma, isabella, george, "
                         "lewis), Japanese (alpha, gongitsune, kumo), Mandarin "
                         "(xiaobei, yunjian). Each voice defaults to its natural "
                         "language."),
            },
        },
    },
    "coqui": {
        "label": "Coqui TTS",
        "desc":  "Research-grade, many models. Largest download, slowest startup.",
        "size":  "~200 MB – 2 GB depending on model",
        "default": False,
        "options": {},
    },
    "pocket": {
        "label": "Pocket TTS",
        "desc":  "CPU-only, 100M params, ~200ms latency, voice cloning. English only.",
        "size":  "~200 MB (model auto-downloads from HuggingFace)",
        "default": False,
        "options": {
            "voice": {
                "prompt": "Default voice",
                "choices": ["alba", "marius", "javert", "jean", "fantine", "cosette", "eponine", "azelma"],
                "default": "alba",
                "help": "Built-in voices. You can also clone any voice from a .wav file.",
            },
        },
    },
    "matcha": {
        "label": "Matcha-TTS",
        "desc":  "Fast flow-matching neural TTS. Clear, natural English. Needs espeak-ng.",
        "size":  "~73 MB model + ~50 MB vocoder (auto-download on first use)",
        "default": False,
        "options": {},
    },
    "emojivoice": {
        "label": "EmojiVoice",
        "desc":  "Emoji-controlled expressive TTS — 🤣😭😡 in the text set the emotion. English.",
        "size":  "~78 MB speaker checkpoint (manual download — see INSTALL.md)",
        "default": False,
        "options": {
            "voice": {
                "prompt": "Speaker",
                "choices": ["paige"],
                "default": "paige",
                "help": "paige — the verified EmojiVoice speaker checkpoint.",
            },
        },
    },
    "api": {
        "label": "API TTS",
        "desc":  "Hosted OpenAI-compatible TTS (Venice by default). Needs an API key + network.",
        "size":  "nothing to download",
        "default": False,
        "options": {
            "voice": {
                "prompt": "Default voice",
                "choices": _API_VOICE_CHOICES,
                "default": "af_heart",
                # Voices are provider/model-dependent (choices only lists
                # Venice's tts-kokoro set) — accept anything non-interactively.
                "validate": lambda v: bool(v),
                "help": ("Venice tts-kokoro voice IDs shown; other models/providers "
                         "have their own — run `marmalade-tts api --list`. "
                         "Set VENICE_API_KEY (or engines.api.api_key_env) before use."),
            },
        },
    },
}

ENGINE_ORDER = ["kitten", "piper", "kokoro", "coqui", "pocket", "matcha", "emojivoice", "api"]

# ── TUI helpers (stdlib only) ────────────────────────────────────────────────

def _is_tty():
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()


def _read_key():
    """Read a single keypress (Unix). Returns special tokens for arrows."""
    import tty
    import termios

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            if seq == "[A":
                return "UP"
            if seq == "[B":
                return "DOWN"
            return "ESC"
        if ch in ("\r", "\n"):
            return "ENTER"
        if ch == " ":
            return "SPACE"
        if ch in ("q", "Q", "\x03"):  # Ctrl-C
            return "QUIT"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _clear_lines(n):
    """Move cursor up n lines and clear them."""
    for _ in range(n):
        sys.stdout.write("\033[A\033[2K")
    sys.stdout.flush()


def _multi_select(items, defaults=None, title="Select engines"):
    """Arrow-key multi-select. Returns list of selected item keys.

    items:    list of (key, label, description)
    defaults: set of keys that start checked
    """
    if defaults is None:
        defaults = set()

    selected = {k for k, _, _ in items if k in defaults}
    cursor = 0

    def render():
        print(f"\033[1m{title}\033[0m  (↑↓ move, SPACE toggle, ENTER confirm)\n")
        for i, (key, label, desc) in enumerate(items):
            marker = "▸" if i == cursor else " "
            check = "●" if key in selected else "○"
            line = f"  {marker} {check} {label}"
            if desc:
                line += f"  \033[2m— {desc}\033[0m"
            print(line)
        print()

    render()

    while True:
        k = _read_key()
        lines_to_clear = len(items) + 3  # title + blank + items + trailing blank
        _clear_lines(lines_to_clear)

        if k == "UP":
            cursor = (cursor - 1) % len(items)
        elif k == "DOWN":
            cursor = (cursor + 1) % len(items)
        elif k == "SPACE":
            key = items[cursor][0]
            if key in selected:
                selected.discard(key)
            else:
                selected.add(key)
        elif k == "ENTER":
            render()
            return [k for k, _, _ in items if k in selected]
        elif k == "QUIT":
            print("Cancelled.")
            sys.exit(0)

        render()


def _single_select(choices, default=None, prompt="Choose"):
    """Arrow-key single select. Returns the chosen value."""
    cursor = 0
    if default and default in choices:
        cursor = choices.index(default)

    def render():
        print(f"\033[1m{prompt}\033[0m  (↑↓ move, ENTER select)\n")
        for i, c in enumerate(choices):
            marker = "▸" if i == cursor else " "
            dflt = " (default)" if c == default else ""
            print(f"  {marker} {c}{dflt}")
        print()

    render()

    while True:
        k = _read_key()
        lines_to_clear = len(choices) + 3
        _clear_lines(lines_to_clear)

        if k == "UP":
            cursor = (cursor - 1) % len(choices)
        elif k == "DOWN":
            cursor = (cursor + 1) % len(choices)
        elif k == "ENTER":
            render()
            return choices[cursor]
        elif k == "QUIT":
            print("Cancelled.")
            sys.exit(0)

        render()


def _ask_yn(prompt, default=True):
    """Simple y/n prompt with default."""
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        resp = input(f"{prompt} {suffix}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not resp:
        return default
    return resp in ("y", "yes")


# ── Non-interactive init ─────────────────────────────────────────────────────

def init_non_interactive(engines, engine_options=None):
    """Configure engines without prompts. Returns config dict updates.

    Args:
        engines:        list of engine names (e.g. ["kitten", "piper"])
        engine_options: dict of {engine: {option: value}} overrides
                        e.g. {"kitten": {"model_size": "nano"}}
    """
    if engine_options is None:
        engine_options = {}

    engines_cfg = {}
    for eng in engines:
        if eng not in ENGINE_INFO:
            print(f"[init] Unknown engine: {eng}", file=sys.stderr)
            sys.exit(1)

        info = ENGINE_INFO[eng]
        cfg = {}

        # Apply defaults, then overrides
        for opt_key, opt_meta in info["options"].items():
            value = engine_options.get(eng, {}).get(opt_key, opt_meta["default"])
            # Validate: custom validator wins; otherwise fall back to choices.
            if "validate" in opt_meta:
                if not opt_meta["validate"](value):
                    print(f"[init] Invalid {opt_key} for {eng}: {value!r}",
                          file=sys.stderr)
                    sys.exit(1)
            elif "choices" in opt_meta and value not in opt_meta["choices"]:
                print(f"[init] Invalid {opt_key} for {eng}: {value!r} "
                      f"(valid: {', '.join(opt_meta['choices'])})", file=sys.stderr)
                sys.exit(1)
            cfg[opt_key] = value

        # Engine-specific defaults
        if eng == "kitten":
            cfg.setdefault("model_size", "micro")
        elif eng == "kokoro":
            cfg.setdefault("voice", "heart")
            # Note: no 'lang' default. Voice's natural language is used unless
            # the user sets one explicitly with `config set engines.kokoro.lang`
            # or --lang on the CLI.
        elif eng == "piper":
            cfg.setdefault("model", "")
        elif eng == "coqui":
            cfg.setdefault("model", "")
        elif eng == "pocket":
            cfg.setdefault("voice", "alba")
        elif eng == "matcha":
            cfg.setdefault("model", "matcha_ljspeech")
        elif eng == "emojivoice":
            cfg.setdefault("voice", "paige")
        elif eng == "api":
            cfg.setdefault("voice", "af_heart")

        cfg.setdefault("daemon", False)
        cfg.setdefault("device", "cpu")
        engines_cfg[eng] = cfg

    return engines_cfg


# ── Interactive init (TUI) ───────────────────────────────────────────────────

def init_interactive():
    """Run the full interactive setup wizard. Returns (selected_engines, engines_cfg, default_engine)."""
    print()
    print("  🍊 \033[1mmarmalade-tts setup\033[0m")
    print("  ─────────────────────────────")
    print()
    print("  Choose which TTS engines to install.")
    print("  Kitten ships by default and is recommended for most users.")
    print("  You can change this later with: marmalade-tts config")
    print()

    # Build items for multi-select
    items = []
    defaults = set()
    for eng in ENGINE_ORDER:
        info = ENGINE_INFO[eng]
        desc = f"{info['desc']}  ({info['size']})"
        items.append((eng, info["label"], desc))
        if info["default"]:
            defaults.add(eng)

    selected = _multi_select(items, defaults=defaults, title="Engines")

    if not selected:
        print("No engines selected. At least one is required.")
        sys.exit(1)

    print(f"\n  ✓ Selected: {', '.join(selected)}\n")

    # Per-engine options
    engines_cfg = {}
    for eng in selected:
        info = ENGINE_INFO[eng]
        cfg = {}

        if info["options"]:
            print(f"  \033[1m{info['label']} options:\033[0m")

        for opt_key, opt_meta in info["options"].items():
            if len(opt_meta["choices"]) > 1:
                if opt_meta.get("help"):
                    print(f"  {opt_meta['help']}")
                value = _single_select(
                    opt_meta["choices"],
                    default=opt_meta["default"],
                    prompt=opt_meta["prompt"],
                )
            else:
                value = opt_meta["default"]
            cfg[opt_key] = value

        # Engine-specific defaults
        if eng == "kitten":
            cfg.setdefault("model_size", "micro")
        elif eng == "kokoro":
            cfg.setdefault("voice", "heart")
            # Note: no 'lang' default. Voice's natural language is used unless
            # the user sets one explicitly with `config set engines.kokoro.lang`
            # or --lang on the CLI.
        elif eng == "piper":
            cfg.setdefault("model", "")
        elif eng == "coqui":
            cfg.setdefault("model", "")
        elif eng == "pocket":
            cfg.setdefault("voice", "alba")
        elif eng == "matcha":
            cfg.setdefault("model", "matcha_ljspeech")
        elif eng == "emojivoice":
            cfg.setdefault("voice", "paige")
        elif eng == "api":
            cfg.setdefault("voice", "af_heart")

        cfg.setdefault("daemon", False)
        cfg.setdefault("device", "cpu")
        engines_cfg[eng] = cfg

    # Pick default engine
    if len(selected) == 1:
        default_engine = selected[0]
    else:
        print()
        default_engine = _single_select(
            selected,
            default=selected[0],
            prompt="Default engine (used when no engine is specified)",
        )

    print(f"\n  ✓ Default engine: {default_engine}\n")

    return selected, engines_cfg, default_engine
