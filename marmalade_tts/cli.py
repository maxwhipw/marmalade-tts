"""CLI entrypoint for marmalade-tts."""

import argparse
import os
import sys
import yaml

from . import __version__
from . import config as cfg_mod
from . import daemon
from . import preprocessing as pp
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
        val, _ = cfg_mod.get_path(config, key)
        print(f"[config] {key} = {val}")
        return

    print("[config] Usage: config show | config get <key> | config set <key> <value>",
          file=sys.stderr)
    sys.exit(1)


def cmd_daemon(args: list):
    """Handle `marmalade-tts daemon ...`."""
    # Parse optional --engine flag
    engine = None
    filtered = []
    i = 0
    while i < len(args):
        if args[i] == "--engine" and i + 1 < len(args):
            engine = args[i + 1]
            i += 2
        else:
            filtered.append(args[i])
            i += 1
    args = filtered

    if not args or args[0] == "status":
        statuses = daemon.status(engine)  # None = all engines
        for eng, st in statuses.items():
            if st["running"]:
                print(f"[daemon] {eng} running (pid {st['pid']})")
                print(f"  socket: {st['socket']}")
            else:
                print(f"[daemon] {eng} not running")
        return

    if args[0] == "start":
        engines_to_start = [engine] if engine else ["kitten"]  # default to kitten
        for eng in engines_to_start:
            print(f"[daemon] Starting {eng} daemon...")
            ok = daemon.start(eng, timeout=30.0)
            if ok:
                print(f"[daemon] {eng} ready")
            else:
                print(f"[daemon] Failed to start {eng} daemon", file=sys.stderr)
                sys.exit(1)
        return

    if args[0] == "stop":
        engines_to_stop = [engine] if engine else list(daemon.ENGINE_DAEMONS.keys())
        for eng in engines_to_stop:
            if daemon.is_running(eng):
                daemon.stop(eng)
                print(f"[daemon] {eng} stopped")
        return

    if args[0] == "start-all":
        for eng in daemon.ENGINE_DAEMONS:
            print(f"[daemon] Starting {eng}...")
            ok = daemon.start(eng, timeout=30.0)
            print(f"[daemon] {eng} {'ready' if ok else 'FAILED'}")
        return

    if args[0] == "stop-all":
        for eng in daemon.ENGINE_DAEMONS:
            if daemon.is_running(eng):
                daemon.stop(eng)
                print(f"[daemon] {eng} stopped")
        return

    print("[daemon] Usage: daemon [status|start|stop|start-all|stop-all] [--engine ENGINE]",
          file=sys.stderr)
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
    argv = sys.argv[1:]

    # ── Quick intercepts ──
    if "--completion" in argv:
        idx = argv.index("--completion")
        shell = argv[idx + 1] if idx + 1 < len(argv) else "bash"
        print(zsh_completion() if shell == "zsh" else bash_completion())
        return

    if argv and argv[0] == "config":
        cmd_config(argv[1:])
        return
    if argv and argv[0] == "daemon":
        cmd_daemon(argv[1:])
        return

    # ── If first token is not an engine name, inject default engine ──
    # This enables: marmalade-tts "hello" (uses defaults.engine)
    # and:          marmalade-tts --fast "hello"
    first_is_engine = argv and argv[0] in ENGINE_NAMES
    if not first_is_engine and argv:
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
  marmalade-tts "Hello world"                    # uses default engine
  marmalade-tts kokoro "Hello world"             # specify engine
  marmalade-tts kitten Kiki "Hello from Kiki"    # specify engine + voice
  marmalade-tts --fast "Quick test"              # fast preset
  marmalade-tts --no-preprocessing "$100 test"   # skip text normalization
  marmalade-tts config set defaults.engine kitten
  marmalade-tts daemon start
  eval "$(marmalade-tts --completion bash)"
""",
    )
    parser.add_argument("engine", nargs="?", choices=ENGINE_NAMES, default=None,
                        help="TTS engine (uses defaults.engine if omitted)")
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
    # Presets
    preset_grp = parser.add_mutually_exclusive_group()
    preset_grp.add_argument("--fast", action="store_true", help="Fast preset")
    preset_grp.add_argument("--balanced", action="store_true", help="Balanced preset")
    preset_grp.add_argument("--quality", action="store_true", help="Quality preset")
    # Preprocessing
    pp_grp = parser.add_mutually_exclusive_group()
    pp_grp.add_argument("--preprocessing", action="store_true", default=None,
                        help="Enable text preprocessing (default: from config)")
    pp_grp.add_argument("--no-preprocessing", action="store_true",
                        help="Disable text preprocessing")
    parser.add_argument("--list-rules", action="store_true",
                        help="List all available preprocessing rules")
    # Misc
    parser.add_argument("--list", action="store_true",
                        help="List voices/models for the engine")
    parser.add_argument("--version", action="version",
                        version=f"marmalade-tts {__version__}")
    parser.add_argument("--completion", metavar="SHELL",
                        help="Generate shell completion (bash/zsh)")

    args, extra = parser.parse_known_args()
    positional = extra  # text + optional voice override

    # ── List rules ──
    if args.list_rules:
        print("Available preprocessing rules:")
        pp.list_rules()
        return

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
    engine_name = args.engine or config.get("defaults", {}).get("engine", "kitten")

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

    # ── Build engine ──
    engine = ENGINE_CLASSES[engine_name](eng_cfg)

    # ── List mode ──
    if args.list:
        engine.list_voices()
        return

    # ── Resolve text ──
    voice_arg = None
    if args.text:
        text = resolve_text(args.text)
        if positional and looks_like_voice(engine_name, positional[0]):
            voice_arg = positional[0]
    elif not positional:
        parser.error("Provide text (or --text / @file / -)")
    else:
        first = positional[0]
        rest = positional[1:]
        if looks_like_voice(engine_name, first) and rest:
            voice_arg = first
            text = resolve_text(" ".join(rest))
        elif looks_like_voice(engine_name, first) and not rest:
            voice_arg = None
            text = resolve_text(first)
        else:
            voice_arg = None
            text = resolve_text(" ".join(positional))

    if not text.strip():
        sys.exit("[marmalade-tts] No text to synthesize")

    # ── Preprocessing ──
    do_preprocess = True  # default on
    if args.no_preprocessing:
        do_preprocess = False
    elif args.preprocessing:
        do_preprocess = True
    else:
        # Check config: defaults.preprocessing (default: true)
        do_preprocess = config.get("defaults", {}).get("preprocessing", True)
        # Check engine-specific override
        eng_pp = eng_cfg.get("preprocessing")
        if eng_pp is not None:
            if isinstance(eng_pp, bool):
                do_preprocess = eng_pp
            elif isinstance(eng_pp, list):
                do_preprocess = True  # explicit rule list = enabled

    if do_preprocess:
        # Get engine-specific rule list from config, or use default profile
        custom_rules = eng_cfg.get("preprocessing")
        if isinstance(custom_rules, list):
            text = pp.preprocess(text, engine=engine_name, rules=custom_rules)
        else:
            text = pp.preprocess(text, engine=engine_name)

    # ── Resolve voice ──
    voice = args.voice or voice_arg

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
        if not args.out and os.path.exists(out_path):
            os.unlink(out_path)


if __name__ == "__main__":
    main()
