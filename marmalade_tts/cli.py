"""CLI entrypoint for marmalade-tts."""

import argparse
import os
import sys
import yaml

from . import __version__
from . import config as cfg_mod
from . import daemon
from .playback import play_wav, make_tmp_wav
from .completion import bash_completion, zsh_completion
from .engines.kitten import KittenEngine, VOICES as KITTEN_VOICES
from .engines.kokoro import KokoroEngine
from .engines.piper import PiperEngine
from .engines.coqui import CoquiEngine

ENGINE_CLASSES = {
    "kitten": KittenEngine,
    "kokoro": KokoroEngine,
    "piper":  PiperEngine,
    "coqui":  CoquiEngine,
}

ENGINE_NAMES = list(ENGINE_CLASSES.keys())


# ── Text resolution ──────────────────────────────────────────────────────────

def resolve_text(raw: str) -> str:
    """Resolve text from literal, @filename, or - (stdin)."""
    if raw == "-":
        return sys.stdin.read()
    if raw.startswith("@"):
        path = raw[1:]
        with open(path) as f:
            return f.read()
    # Don't auto-read arbitrary paths that look like sentences
    return raw


# ── Subcommand handlers ─────────────────────────────────────────────────────

def cmd_config(args: list):
    """Handle `marmalade-tts config ...`."""
    config = cfg_mod.load()

    if not args or args[0] == "show":
        print(yaml.safe_dump(config, sort_keys=False, default_flow_style=False), end="")
        return

    action = args[0]

    if action == "get" and len(args) >= 2:
        val, found = cfg_mod.get_path(config, args[1])
        if found:
            if isinstance(val, dict):
                print(yaml.safe_dump(val, sort_keys=False, default_flow_style=False), end="")
            else:
                print(val)
        else:
            print(f"[config] Key not found: {args[1]}", file=sys.stderr)
            sys.exit(1)
        return

    if action == "set" and len(args) >= 3:
        key = args[1]
        value = " ".join(args[2:])
        cfg_mod.set_path(config, key, value)
        cfg_mod.save(config)
        # Re-read to show parsed value
        val, _ = cfg_mod.get_path(config, key)
        print(f"[config] {key} = {val}")
        return

    print("[config] Usage: config show | config get <key> | config set <key> <value>",
          file=sys.stderr)
    sys.exit(1)


def cmd_daemon(args: list):
    """Handle `marmalade-tts daemon ...`."""
    if not args or args[0] == "status":
        st = daemon.status()
        if st["running"]:
            print(f"[daemon] kitten running (pid {st['pid']})")
            print(f"  socket: {st['socket']}")
        else:
            print("[daemon] kitten not running")
        return

    if args[0] == "start":
        print("[daemon] Starting kitten daemon...")
        ok = daemon.start(timeout=20.0)
        if ok:
            print("[daemon] kitten ready")
        else:
            print("[daemon] Failed to start kitten daemon", file=sys.stderr)
            sys.exit(1)
        return

    if args[0] == "stop":
        daemon.stop()
        print("[daemon] kitten stopped")
        return

    print("[daemon] Usage: daemon start | daemon stop | daemon status", file=sys.stderr)
    sys.exit(1)


# ── Voice/model heuristic ───────────────────────────────────────────────────

KOKORO_PREFIXES = (
    "af_", "am_", "bf_", "bm_", "hf_", "hm_", "ef_", "em_",
    "ff_", "fm_", "if_", "im_", "pf_", "pm_", "jf_", "jm_", "zf_", "zm_",
)


def looks_like_voice(engine: str, token: str) -> bool:
    """Check if a positional token is a voice/model override rather than text."""
    if engine == "kitten":
        return token in KITTEN_VOICES
    if engine == "kokoro":
        return any(token.startswith(p) for p in KOKORO_PREFIXES)
    if engine == "piper":
        return token.endswith(".onnx") or "/" in token or token.startswith("~")
    if engine == "coqui":
        return token.startswith("tts_models/")
    return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # ── Quick intercepts before argparse ──
    argv = sys.argv[1:]

    # Tab completion
    if "--completion" in argv:
        idx = argv.index("--completion")
        shell = argv[idx + 1] if idx + 1 < len(argv) else "bash"
        if shell == "zsh":
            print(zsh_completion())
        else:
            print(bash_completion())
        return

    # Subcommands (before argparse to avoid engine-required errors)
    if argv and argv[0] == "config":
        cmd_config(argv[1:])
        return
    if argv and argv[0] == "daemon":
        cmd_daemon(argv[1:])
        return

    # If first token is not an engine name and a preset flag is present,
    # inject the default engine so argparse doesn't choke.
    has_preset = any(f in argv for f in ("--fast", "--balanced", "--quality"))
    first_is_engine = argv and argv[0] in ENGINE_NAMES
    if has_preset and not first_is_engine:
        config_tmp = cfg_mod.load()
        default_eng = config_tmp.get("defaults", {}).get("engine", "kitten")
        argv.insert(0, default_eng)
        sys.argv = [sys.argv[0]] + argv

    # ── Parse ──
    parser = argparse.ArgumentParser(
        prog="marmalade-tts",
        description="🍊 Unified local TTS — kitten | kokoro | piper | coqui",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  marmalade-tts kokoro "Hello world"
  marmalade-tts kitten Kiki "Hello from Kiki"
  marmalade-tts --fast "Quick test"
  marmalade-tts piper "Hello from Piper" --out hello.wav
  marmalade-tts config set engines.kitten.voice Hugo
  marmalade-tts daemon start
  eval "$(marmalade-tts --completion bash)"
""",
    )
    parser.add_argument("engine", nargs="?", choices=ENGINE_NAMES,
                        default=None,
                        help="TTS engine (optional if preset flag used)")
    parser.add_argument("--text", "-t", default=None,
                        help="Text to synthesize (alternative to positional)")
    parser.add_argument("--out", metavar="FILE",
                        help="Save WAV to file (default: play immediately)")
    parser.add_argument("--play", action="store_true",
                        help="Play audio even when --out is set")
    parser.add_argument("--speed", type=float, default=None,
                        help="Speech speed multiplier (default: 1.0)")
    parser.add_argument("--voice", default=None,
                        help="Voice name override (kitten/kokoro)")
    parser.add_argument("--lang", default=None,
                        help="Language code — kokoro only (a/b/h/e/f/i/p/j/z)")
    parser.add_argument("--speaker", default=None,
                        help="Speaker id — piper multi-speaker models")
    preset = parser.add_mutually_exclusive_group()
    preset.add_argument("--fast", action="store_true",
                        help="Fast preset (smallest models)")
    preset.add_argument("--balanced", action="store_true",
                        help="Balanced preset (mid-size models)")
    preset.add_argument("--quality", action="store_true",
                        help="Quality preset (best fidelity)")
    parser.add_argument("--list", action="store_true",
                        help="List voices/models for the engine")
    parser.add_argument("--version", action="version",
                        version=f"marmalade-tts {__version__}")
    parser.add_argument("--completion", metavar="SHELL",
                        help="Generate shell completion (bash/zsh)")

    args, extra = parser.parse_known_args()
    # Anything argparse didn't consume goes into positional (the text + optional voice)
    positional = extra

    # ── Load config ──
    config = cfg_mod.load()

    # ── Resolve preset ──
    preset_name = None
    if args.fast:
        preset_name = "fast"
    elif args.balanced:
        preset_name = "balanced"
    elif args.quality:
        preset_name = "quality"

    # ── Resolve engine ──
    engine_name = args.engine
    if not engine_name:
        if preset_name:
            engine_name = config.get("defaults", {}).get("engine", "kitten")
        else:
            parser.error("Engine is required (or use --fast/--balanced/--quality)")

    # ── Apply preset to engine config ──
    eng_cfg = cfg_mod.engine_cfg(config, engine_name)
    if preset_name:
        presets = config.get("presets", {}).get(preset_name, {})
        preset_val = presets.get(engine_name)
        if preset_val:
            if engine_name == "kitten":
                eng_cfg["model_size"] = preset_val
            elif engine_name == "kokoro":
                eng_cfg["voice"] = preset_val
            else:
                eng_cfg["model"] = preset_val

    # ── Build engine instance ──
    engine = ENGINE_CLASSES[engine_name](eng_cfg)

    # ── List mode ──
    if args.list:
        engine.list_voices()
        return

    # ── Resolve positional args: [voice] text ──
    # --text flag takes priority as text source
    if args.text:
        text = resolve_text(args.text)
        # positional may still contain a voice override
        voice_arg = positional[0] if positional and looks_like_voice(engine_name, positional[0]) else None
    elif not positional:
        parser.error("Provide text (or --text or @file or -) for synthesis")
    else:
        first = positional[0]
        rest = positional[1:]

        if looks_like_voice(engine_name, first) and rest:
            voice_arg = first
            text_raw = " ".join(rest)
        elif looks_like_voice(engine_name, first) and not rest:
            voice_arg = None
            text_raw = first
        else:
            voice_arg = None
            text_raw = " ".join(positional)

        text = resolve_text(text_raw)
    if not text.strip():
        sys.exit("[marmalade-tts] No text to synthesize")

    # ── Resolve voice from (1) --voice flag, (2) positional, (3) config ──
    voice = args.voice or voice_arg  # None means engine uses its own default

    # ── Output path ──
    if args.out:
        out_path = args.out
        auto_play = False
    else:
        out_path = make_tmp_wav()
        auto_play = config.get("defaults", {}).get("play", True)

    # ── Speed ──
    speed = args.speed or config.get("defaults", {}).get("speed", 1.0)

    # ── Synthesize ──
    synth_kwargs = {"speed": speed}
    if voice:
        synth_kwargs["voice"] = voice
    if args.lang:
        synth_kwargs["lang"] = args.lang
    if args.speaker:
        synth_kwargs["speaker"] = args.speaker

    engine.synthesize(text, out_path, **synth_kwargs)
    print(f"[marmalade-tts] Generated: {out_path}", file=sys.stderr)

    # ── Playback ──
    if auto_play or args.play:
        play_wav(out_path)
        # Clean up temp file after playback
        if not args.out and os.path.exists(out_path):
            os.unlink(out_path)


if __name__ == "__main__":
    main()
