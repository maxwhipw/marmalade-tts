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
from .engines.pocket import PocketEngine, VOICES as POCKET_VOICES
from . import effects as fx

ENGINE_CLASSES = {
    "kitten": KittenEngine,
    "kokoro": KokoroEngine,
    "piper":  PiperEngine,
    "coqui":  CoquiEngine,
    "pocket": PocketEngine,
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


def cmd_init(args: list):
    """Handle `marmalade-tts init` — interactive or scripted engine setup.

    Interactive (default):
        marmalade-tts init

    Non-interactive (for AI agents / scripts):
        marmalade-tts init --non-interactive --engines kitten,piper
        marmalade-tts init --non-interactive --engines kitten --set kitten.model_size=nano
    """
    import argparse as _ap
    from .init import init_interactive, init_non_interactive, _is_tty, _ask_yn

    parser = _ap.ArgumentParser(prog="marmalade-tts init", add_help=True)
    parser.add_argument("--non-interactive", action="store_true",
                        help="Skip TUI prompts; require --engines")
    parser.add_argument("--engines", type=str, default="",
                        help="Comma-separated engines to enable (e.g. kitten,piper,kokoro)")
    parser.add_argument("--set", action="append", dest="overrides", default=[],
                        help="Engine option override: engine.key=value (repeatable)")
    parser.add_argument("--default-engine", type=str, default="",
                        help="Set the default engine explicitly")
    parser.add_argument("--test", action="store_true",
                        help="Run a test synthesis after setup")
    parsed = parser.parse_args(args)

    # ── Determine mode ──
    non_interactive = parsed.non_interactive or not _is_tty()

    # Parse --set overrides into {engine: {key: value}}
    engine_options = {}
    for override in parsed.overrides:
        if "=" not in override or "." not in override.split("=", 1)[0]:
            print(f"[init] Invalid --set format: {override!r}  (expected engine.key=value)",
                  file=sys.stderr)
            sys.exit(1)
        path, value = override.split("=", 1)
        eng, key = path.split(".", 1)
        engine_options.setdefault(eng, {})[key] = value

    if non_interactive:
        # ── Non-interactive path ──
        engine_list = [e.strip() for e in parsed.engines.split(",") if e.strip()]
        if not engine_list:
            print("[init] --engines required in non-interactive mode", file=sys.stderr)
            sys.exit(1)

        engines_cfg = init_non_interactive(engine_list, engine_options)
        selected = engine_list
        default_engine = parsed.default_engine or selected[0]

    else:
        # ── Interactive TUI path ──
        selected, engines_cfg, default_engine = init_interactive()

    # ── Write config ──
    config = cfg_mod.load()
    config.setdefault("defaults", {})["engine"] = default_engine
    config.setdefault("defaults", {}).setdefault("speed", 1.0)
    config.setdefault("defaults", {}).setdefault("play", True)
    config.setdefault("defaults", {}).setdefault("preprocessing", True)

    for eng, ecfg in engines_cfg.items():
        config.setdefault("engines", {})[eng] = ecfg

    cfg_mod.save(config)

    print(f"  ✓ Config saved to {cfg_mod.CONFIG_PATH}")
    print(f"  ✓ Default engine: {default_engine}")
    print(f"  ✓ Engines configured: {', '.join(selected)}")

    # ── Install hints ──
    print()
    for eng in selected:
        if eng == "piper" and not engines_cfg.get(eng, {}).get("model"):
            print("  📦 Piper needs a voice model. Download one:")
            print("     mkdir -p ~/.local/share/piper/voices && cd ~/.local/share/piper/voices")
            print("     wget <model-url>.onnx && wget <model-url>.onnx.json")
            print("     See: https://huggingface.co/rhasspy/piper-voices")
            print()
        if eng == "kokoro":
            print("  📦 Kokoro: install via  pipx install kokoro")
            print()
        if eng == "coqui" and not engines_cfg.get(eng, {}).get("model"):
            print("  📦 Coqui: install via  pipx install coqui-tts")
            print()

    # ── Optional test synthesis ──
    do_test = parsed.test
    if not non_interactive and not do_test:
        do_test = _ask_yn("  Run a test synthesis?", default=True)

    if do_test:
        print(f"\n  🔊 Testing {default_engine}...")
        try:
            eng_cfg = engines_cfg.get(default_engine, {})
            engine = ENGINE_CLASSES[default_engine](eng_cfg)
            tmp = make_tmp_wav()
            engine.synthesize("Hello! Marmalade T T S is ready.", tmp, speed=1.0)
            play_wav(tmp)
            try:
                os.unlink(tmp)
            except OSError:
                pass
            print("  ✓ Test passed!\n")
        except Exception as e:
            print(f"  ✗ Test failed: {e}", file=sys.stderr)
            print("    You may need to install the engine first. See the hints above.\n",
                  file=sys.stderr)

    print("  🍊 Setup complete. Try: marmalade-tts \"Hello world\"\n")



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
    if engine == "pocket":
        return token in POCKET_VOICES or token.endswith(".wav") or token.endswith(".safetensors")
    return False


# ── main() helpers ──────────────────────────────────────────────────────────


def _apply_preset(eng_cfg: dict, engine_name: str, preset_name: str, config: dict) -> None:
    """Mutate `eng_cfg` in place to apply a named preset (fast/balanced/quality)."""
    if not preset_name:
        return
    preset_val = config.get("presets", {}).get(preset_name, {}).get(engine_name)
    if not preset_val:
        return
    if engine_name == "kitten":
        eng_cfg["model_size"] = preset_val
    elif engine_name in ("kokoro", "pocket"):
        eng_cfg["voice"] = preset_val
    else:
        eng_cfg["model"] = preset_val


def _resolve_text_and_voice(args, positional, engine_name, parser):
    """Resolve (text, voice_arg) from --stdin / --text / positional args."""
    voice_arg = None
    if args.stdin:
        return sys.stdin.read(), None
    if args.text:
        text = resolve_text(args.text)
        if positional and looks_like_voice(engine_name, positional[0]):
            voice_arg = positional[0]
        return text, voice_arg
    if not positional:
        parser.error("Provide text (or --text / @file / -)")

    first, rest = positional[0], positional[1:]
    if looks_like_voice(engine_name, first) and rest:
        return resolve_text(" ".join(rest)), first
    if looks_like_voice(engine_name, first) and not rest:
        # Just a voice token with no follow-up text — treat token as text.
        return resolve_text(first), None
    return resolve_text(" ".join(positional)), None


def _resolve_preprocessing(text, args, eng_cfg, config, engine_name):
    """Apply preprocessing per CLI flags and config. Returns the (possibly) transformed text."""
    if args.no_preprocessing:
        do_preprocess = False
    elif args.preprocessing:
        do_preprocess = True
    else:
        do_preprocess = config.get("defaults", {}).get("preprocessing", True)
        eng_pp = eng_cfg.get("preprocessing")
        if eng_pp is not None:
            if isinstance(eng_pp, bool):
                do_preprocess = eng_pp
            elif isinstance(eng_pp, list):
                do_preprocess = True

    if not do_preprocess:
        return text

    custom_rules = eng_cfg.get("preprocessing")
    if isinstance(custom_rules, list):
        return pp.preprocess(text, engine=engine_name, rules=custom_rules)
    return pp.preprocess(text, engine=engine_name)


def _apply_effects_if_any(out_path, effect_list, config):
    """Apply effect chain in place. Warns rather than failing on sox issues."""
    if not effect_list:
        return
    if not fx.sox_available():
        print(
            "[marmalade-tts] Note: sox is not installed — audio effects were skipped.\n"
            "  To enable effects: apt install sox   or   brew install sox",
            file=sys.stderr,
        )
        return
    try:
        fx.apply_effects(out_path, out_path, effect_list, config)
    except (ValueError, RuntimeError) as e:
        print(f"[marmalade-tts] Effect warning: {e}", file=sys.stderr)


def _report_output(args, engine_name, voice, out_path, effect_list, text, eng_cfg):
    """Print the per-run result in the user-requested format."""
    if args.json:
        import json
        print(json.dumps({
            "ok": True,
            "engine": engine_name,
            "voice": voice or eng_cfg.get("voice"),
            "out": out_path,
            "effects": effect_list,
            "text": text,
        }))
    elif args.print_path:
        print(out_path)
    elif not args.quiet:
        print(f"[marmalade-tts] Generated: {out_path}", file=sys.stderr)


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
    if argv and argv[0] == "init":
        cmd_init(argv[1:])
        return
    if "--list-effects" in argv:
        config_tmp = cfg_mod.load()
        user_presets = config_tmp.get("effects", {}).get("presets", {})
        fx.list_effects(user_presets)
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
        description="🍊 Unified local TTS — kitten | kokoro | piper | coqui | pocket",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  marmalade-tts "Hello world"                    # uses default engine
  marmalade-tts kokoro "Hello world"             # specify engine
  marmalade-tts kitten Kiki "Hello from Kiki"    # specify engine + voice
  marmalade-tts pocket alba "Voice cloning ready"   # pocket engine + voice
  marmalade-tts pocket my_voice.wav "Cloned voice"  # pocket voice cloning
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
    parser.add_argument("--effect", metavar="EFFECT", action="append", dest="effects",
                        help="Apply audio effect after synthesis (repeatable). "
                             "Format: name or name=value, e.g. reverb=50, pitch=200, robot. "
                             "Run --list-effects to see all effects and presets.")
    parser.add_argument("--list-effects", action="store_true",
                        help="List all available audio effects and presets")
    parser.add_argument("--list", action="store_true",
                        help="List voices/models for the engine")
    parser.add_argument("--version", action="version",
                        version=f"marmalade-tts {__version__}")
    parser.add_argument("--completion", metavar="SHELL",
                        help="Generate shell completion (bash/zsh)")
    # Agent / scripting flags
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress all status output on stderr")
    parser.add_argument("--json", action="store_true",
                        help="Print a JSON result object to stdout instead of status text")
    parser.add_argument("--print-path", action="store_true",
                        help="Print the output WAV path to stdout (useful for scripts)")
    parser.add_argument("--stdin", action="store_true",
                        help="Read text from stdin (shorthand for passing -)")
    parser.add_argument("--no-play", action="store_true",
                        help="Never play audio, even if defaults.play is true")

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
    _apply_preset(eng_cfg, engine_name, preset_name, config)

    # ── Build engine ──
    engine = ENGINE_CLASSES[engine_name](eng_cfg)

    # ── List mode ──
    if args.list:
        engine.list_voices()
        return

    # ── Resolve text and voice ──
    text, voice_arg = _resolve_text_and_voice(args, positional, engine_name, parser)

    if not text.strip():
        sys.exit("[marmalade-tts] No text to synthesize")

    # ── Preprocessing ──
    text = _resolve_preprocessing(text, args, eng_cfg, config, engine_name)

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

    # ── Effects ──
    # CLI --effect flags override engine defaults entirely. If no CLI flag is
    # given, fall back to effects.defaults.<engine> from config.
    effect_list = args.effects or (
        config.get("effects", {}).get("defaults", {}).get(engine_name, [])
    )
    _apply_effects_if_any(out_path, effect_list, config)

    # ── Output reporting ──
    _report_output(args, engine_name, voice, out_path, effect_list, text, eng_cfg)

    # ── Playback ──
    should_play = (auto_play or args.play) and not args.no_play
    if should_play:
        play_wav(out_path)
        if not args.out and os.path.exists(out_path):
            os.unlink(out_path)


if __name__ == "__main__":
    main()
