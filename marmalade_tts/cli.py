"""CLI entrypoint for marmalade-tts."""

import argparse
import os
import sys
import yaml

from . import __version__
from . import config as cfg_mod
from . import daemon
from . import preprocessing as pp
from .playback import play_wav, make_tmp_wav, wav_duration
from . import subtitles as subs
from .completion import bash_completion, zsh_completion
from .engines.kitten import KittenEngine, VOICES as KITTEN_VOICES
from .engines.kokoro import KokoroEngine, is_voice_token as kokoro_is_voice_token
from .engines.piper import PiperEngine
from .engines.coqui import CoquiEngine
from .engines.pocket import PocketEngine, VOICES as POCKET_VOICES
from .engines.matcha import MatchaEngine
from .engines.emojivoice import EmojiVoiceEngine, VOICES as EMOJIVOICE_VOICES
from . import effects as fx

ENGINE_CLASSES = {
    "kitten":     KittenEngine,
    "kokoro":     KokoroEngine,
    "piper":      PiperEngine,
    "coqui":      CoquiEngine,
    "pocket":     PocketEngine,
    "matcha":     MatchaEngine,
    "emojivoice": EmojiVoiceEngine,
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
                        help="Play a test synthesis through the default engine after setup")
    parser.add_argument("--allow-sudo", action="store_true",
                        help="permit system-package installs via sudo in "
                             "non-interactive mode (interactive init always prompts)")
    parser.add_argument("--reinstall", action="store_true",
                        help="recreate engine venvs even if they already exist")
    parser.add_argument("--skip-selftest", action="store_true",
                        help="skip the post-install synthesis self-test")
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

    # ── Install the selected engines ──
    # marmalade-tts owns the install: each engine gets its own venv, pip
    # packages, system deps and models, then a self-test — the exact same
    # code path as `marmalade-tts install`.
    from . import installer

    print()
    print("  Installing engines — this downloads packages and models and may")
    print("  take several minutes per engine.")
    install_results = installer.install_engines(
        selected,
        allow_sudo=parsed.allow_sudo,
        reinstall=parsed.reinstall,
        skip_selftest=parsed.skip_selftest,
        interactive=not non_interactive,
    )
    install_failed = any(
        r["error"] or (r["selftest"] is not None and not r["selftest"][0])
        for r in install_results
    )

    # ── Optional test synthesis (plays audio through the default engine) ──
    do_test = parsed.test
    if not non_interactive and not do_test:
        do_test = _ask_yn("  Run a test synthesis?", default=True)

    test_failed = False
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
            test_failed = True
            print(f"  ✗ Test failed: {e}", file=sys.stderr)
            print("    You may need to install the engine first. See the hints above.\n",
                  file=sys.stderr)

    print("  🍊 Setup complete. Try: marmalade-tts \"Hello world\"\n")

    # Exit non-zero if any engine failed to install / self-test, or if an
    # explicitly-requested --test synthesis failed — so CI and setup scripts
    # can detect the failure. The config is already saved either way.
    if install_failed or (parsed.test and test_failed):
        sys.exit(1)


def cmd_install(args: list):
    """Handle `marmalade-tts install <engine>...`.

    Installs each engine the hands-off way `init` does — its own venv, pip
    packages, system deps, models — and self-tests it. `init` calls the same
    installer under the hood; this command is for post-init additions.
    """
    import argparse as _ap

    from . import installer
    from .init import _is_tty

    parser = _ap.ArgumentParser(
        prog="marmalade-tts install", add_help=True,
        description="Install TTS engines (venvs, packages, system deps, "
                    "models) and self-test them.")
    parser.add_argument("engines", nargs="+", metavar="ENGINE",
                        help=f"engine(s) to install: "
                             f"{', '.join(installer.INSTALL_RECIPES)}")
    parser.add_argument("--allow-sudo", action="store_true",
                        help="permit system-package installs via sudo in "
                             "non-interactive mode (interactive mode always prompts)")
    parser.add_argument("--reinstall", action="store_true",
                        help="recreate the engine venv even if it already exists")
    parser.add_argument("--skip-selftest", action="store_true",
                        help="skip the post-install synthesis self-test")
    parsed = parser.parse_args(args)

    unknown = [e for e in parsed.engines if e not in installer.INSTALL_RECIPES]
    if unknown:
        print(f"[install] unknown engine(s): {', '.join(unknown)}\n"
              f"  known: {', '.join(installer.INSTALL_RECIPES)}", file=sys.stderr)
        sys.exit(1)

    results = installer.install_engines(
        parsed.engines,
        allow_sudo=parsed.allow_sudo,
        reinstall=parsed.reinstall,
        skip_selftest=parsed.skip_selftest,
        interactive=_is_tty(),
    )
    # Exit non-zero if any engine errored or failed its self-test, so scripts
    # and CI can detect a bad install.
    failed = any(
        r["error"] or (r["selftest"] is not None and not r["selftest"][0])
        for r in results
    )
    if failed:
        sys.exit(1)


# ── Voice/model heuristic ───────────────────────────────────────────────────


def looks_like_voice(engine: str, token: str) -> bool:
    """Check if a positional token is a voice override rather than text.

    Only engines whose voice names are unambiguously identifier-shaped
    (not English text, not file paths) accept positional voices:

      - kitten:      closed list of names
      - kokoro:      closed list of bare names AND canonical IDs
      - pocket:      closed list of names, OR a .wav / .safetensors file path
      - emojivoice:  closed list of speaker names

    piper, coqui and matcha voices are file paths / model specs that are
    structurally too similar to user text. Use ``--voice`` for those.
    """
    if engine == "kitten":
        return token in KITTEN_VOICES
    if engine == "kokoro":
        return kokoro_is_voice_token(token)
    if engine == "pocket":
        return (token in POCKET_VOICES
                or token.endswith(".wav")
                or token.endswith(".safetensors"))
    if engine == "emojivoice":
        return token in EMOJIVOICE_VOICES
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
    elif engine_name in ("kokoro", "pocket", "emojivoice"):
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
        if positional:
            if looks_like_voice(engine_name, positional[0]) and len(positional) == 1:
                voice_arg = positional[0]
            else:
                parser.error(
                    "When --text is given, extra positional arguments are not "
                    "accepted (only an optional voice token before the text)."
                )
        return text, voice_arg
    if not positional:
        parser.error("Provide text (or --text / @file / -)")

    first, rest = positional[0], positional[1:]
    if looks_like_voice(engine_name, first) and rest:
        return resolve_text(" ".join(rest)), first
    if looks_like_voice(engine_name, first) and not rest:
        parser.error(
            f"{first!r} looks like a voice but no text was given. "
            f"Add text, or run `marmalade-tts {engine_name} --list` to see voices."
        )
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


def _resolve_out_paths(args, n: int, config: dict, parser):
    """Resolve output paths for N utterances. Returns (paths, auto_play).

    Rules (apply to single-utterance and batch alike — batch is just N>1):
      --out PATTERN  (contains '%')   : printf-format with 1-based index.
      --out FILE     (no '%')         : literal path; N must be 1.
      --out-dir DIR                   : auto-name 001.wav, 002.wav, …
      neither                          : a tmp WAV per utterance, auto-played.
    """
    if args.out and "%" in args.out:
        return [args.out % (i + 1) for i in range(n)], False
    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)
        width = max(3, len(str(n)))
        return ([os.path.join(args.out_dir, f"{i + 1:0{width}d}.wav")
                 for i in range(n)],
                False)
    if args.out:
        if n != 1:
            parser.error(
                "Batch input (multi-line text) can't write into a single "
                "--out file. Pass --out 'PATTERN-%03d.wav' (with a printf "
                "format) or --out-dir DIR, or omit --out to play each line in "
                "sequence."
            )
        return [args.out], False
    return ([make_tmp_wav() for _ in range(n)],
            config.get("defaults", {}).get("play", True))


def _print_aliases(aliases: dict) -> None:
    """Pretty-print the configured aliases. Used by --list-aliases."""
    if not aliases:
        print("No aliases configured.")
        print()
        print("Define them in ~/.config/marmalade-tts/config.yaml under `aliases:`,")
        print("for example:")
        print()
        print("  aliases:")
        print("    narrator:")
        print("      engine: kokoro")
        print("      voice: george")
        print("      speed: 0.95")
        print("      effects: [\"reverb=15\"]")
        return
    print("Configured aliases:")
    print()
    for name, spec in aliases.items():
        spec = spec or {}
        engine = spec.get("engine", "?")
        bits = []
        voice = spec.get("voice")
        if voice:
            bits.append(f"voice={voice}")
        speed = spec.get("speed")
        if speed is not None:
            bits.append(f"speed={speed}×")
        lang = spec.get("lang")
        if lang:
            bits.append(f"lang={lang}")
        speaker = spec.get("speaker")
        if speaker:
            bits.append(f"speaker={speaker}")
        emotion = spec.get("emotion")
        if emotion:
            bits.append(f"emotion={emotion}")
        effects = spec.get("effects")
        if effects:
            bits.append(f"effects={effects}")
        speaker_wav = spec.get("speaker_wav")
        if speaker_wav:
            bits.append(f"speaker_wav={speaker_wav}")
        suffix = (" — " + ", ".join(bits)) if bits else ""
        print(f"  {name} → {engine}{suffix}")


def _report_outputs(args, engine_name, voice, results, effect_list, eng_cfg, is_batch):
    """Print results in the user-requested format. For batch, --json prints
    a JSON array (one element per utterance); for single, --json keeps the
    same single-object shape it has always had."""
    if args.json:
        import json
        payload = [{
            "ok": True,
            "version": __version__,
            "engine": engine_name,
            "voice": voice or eng_cfg.get("voice"),
            "out": r["out"],
            "effects": effect_list,
            "text": r["text"],
            "duration": r.get("duration", 0.0),
        } for r in results]
        print(json.dumps(payload if is_batch else payload[0]))
    elif args.print_path:
        for r in results:
            print(r["out"])
    elif not args.quiet:
        for r in results:
            print(f"[marmalade-tts] Generated: {r['out']}", file=sys.stderr)


def _synthesize_one(utt, out_path, engine, args, eng_cfg, config,
                    engine_name, effect_list, synth_kwargs):
    """Run preprocessing → synth → effects → duration measurement for one
    utterance. Returns the result dict (matching the existing shape consumed
    by subtitles / --json / playback) or None if the preprocessed text is
    empty (the line was just whitespace or got stripped to nothing).

    Pulled out of main() so the sequential and streaming paths both call
    into the same code and can't drift apart."""
    processed = _resolve_preprocessing(utt, args, eng_cfg, config, engine_name)
    if not processed.strip():
        return None
    engine.synthesize(processed, out_path, **synth_kwargs)
    _apply_effects_if_any(out_path, effect_list, config)
    # Measure duration AFTER effects — sox tempo/speed/fade change length.
    try:
        duration = wav_duration(out_path)
    except Exception:
        duration = 0.0
    return {
        "out": out_path,
        "text": processed,
        "raw_text": utt,
        "duration": duration,
    }


def _write_subtitles(args, results):
    """Emit --srt / --vtt files if requested. Both flags are independent —
    passing both writes both. Cue text comes from `raw_text` (original
    user input), so emoji/markdown that were stripped during preprocessing
    still appear in the subtitle file the user sees."""
    if not (args.srt or args.vtt):
        return
    texts = [r["raw_text"] for r in results]
    durations = [r.get("duration", 0.0) for r in results]
    cues = subs.build_cues(texts, durations)
    if args.srt:
        subs.write_srt(args.srt, cues)
        if not args.quiet:
            print(f"[marmalade-tts] Wrote subtitles: {args.srt}", file=sys.stderr)
    if args.vtt:
        subs.write_vtt(args.vtt, cues)
        if not args.quiet:
            print(f"[marmalade-tts] Wrote subtitles: {args.vtt}", file=sys.stderr)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    argv = sys.argv[1:]

    # ── Quick intercepts (only when explicitly given as the first argument,
    # so they can't trigger from text content like
    # `marmalade-tts kokoro "tell me about --completion"`). ──
    if argv and argv[0] == "--completion":
        shell = argv[1] if len(argv) > 1 else "bash"
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
    if argv and argv[0] == "install":
        cmd_install(argv[1:])
        return
    if argv and argv[0] == "mcp":
        from . import mcp_server
        try:
            mcp_server.run()
        except ImportError:
            print("MCP support not installed. Run: pip install marmalade-tts[mcp]",
                  file=sys.stderr)
            sys.exit(1)
        return
    if argv and argv[0] == "--list-effects":
        config_tmp = cfg_mod.load()
        user_presets = config_tmp.get("effects", {}).get("presets", {})
        fx.list_effects(user_presets)
        return

    if argv and argv[0] == "--list-aliases":
        config_tmp = cfg_mod.load()
        _print_aliases(config_tmp.get("aliases") or {})
        return

    # ── Alias expansion + default-engine injection ──
    # Both need the config; load it once and share. Aliases are config-defined
    # named bundles (engine + voice + speed + …) invoked positionally like an
    # engine name. Engine names are reserved — an alias whose name collides
    # with an engine name is ignored with a warning (config might be partial
    # during edits; don't hard-fail).
    alias_overrides = None
    _config_tmp = None
    if argv:
        _config_tmp = cfg_mod.load()
        aliases = _config_tmp.get("aliases") or {}
        name = argv[0]
        if name in aliases:
            if name in ENGINE_NAMES:
                # Reserved-name collision — engine wins, skip the alias.
                print(
                    f"[marmalade-tts] Warning: alias {name!r} shadows engine "
                    f"name and is ignored.",
                    file=sys.stderr,
                )
            else:
                spec = aliases[name] or {}
                engine = spec.get("engine")
                if not engine:
                    print(
                        f"[marmalade-tts] Alias {name!r} has no 'engine' field.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                if engine not in ENGINE_NAMES:
                    print(
                        f"[marmalade-tts] Alias {name!r} references unknown "
                        f"engine {engine!r}.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                # Rewrite argv so the rest of dispatch sees the engine name,
                # and stash the rest of the alias spec for later merging.
                argv[0] = engine
                sys.argv = [sys.argv[0]] + argv
                alias_overrides = {k: v for k, v in spec.items() if k != "engine"}

    # ── If first token is not an engine name, inject default engine ──
    # This enables: marmalade-tts "hello" (uses defaults.engine)
    # and:          marmalade-tts --fast "hello"
    first_is_engine = argv and argv[0] in ENGINE_NAMES
    if not first_is_engine and argv:
        if _config_tmp is None:
            _config_tmp = cfg_mod.load()
        default_eng = _config_tmp.get("defaults", {}).get("engine", "kitten")
        argv.insert(0, default_eng)
        sys.argv = [sys.argv[0]] + argv

    # ── Parse ──
    parser = argparse.ArgumentParser(
        prog="marmalade-tts",
        description="🍊 Unified local TTS — kitten | kokoro | piper | coqui | pocket | matcha | emojivoice",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  marmalade-tts "Hello world"                    # uses default engine
  marmalade-tts kokoro "Hello world"             # specify engine
  marmalade-tts kitten Kiki "Hello from Kiki"    # positional voice
  marmalade-tts kokoro george "Hello"            # bare-name kokoro voice
  marmalade-tts pocket alba "Voice cloning ready"
  marmalade-tts pocket my_voice.wav "Cloned voice"  # pocket voice cloning
  marmalade-tts piper --voice ~/voices/foo.onnx "Hi"  # piper needs --voice
  marmalade-tts matcha "Fast flow-matching TTS"
  marmalade-tts emojivoice "I can't believe it 🤣"  # emoji sets the emotion
  marmalade-tts --fast "Quick test"              # fast preset
  marmalade-tts --no-preprocessing "$100 test"   # skip text normalization
  marmalade-tts config set defaults.engine kitten
  marmalade-tts daemon start
  marmalade-tts init                             # set up + install engines
  marmalade-tts install matcha emojivoice        # add engines after init
  marmalade-tts @chapters.txt --out-dir ./out/   # batch: one WAV per line
  eval "$(marmalade-tts --completion bash)"
""",
    )
    parser.add_argument("engine", nargs="?", choices=ENGINE_NAMES, default=None,
                        help="TTS engine (uses defaults.engine if omitted)")
    parser.add_argument("--text", "-t", default=None,
                        help="Text to synthesize (alternative to positional)")
    parser.add_argument("--out", metavar="FILE",
                        help="Save WAV to file (default: play immediately). "
                             "In batch mode (multi-line input), pass a printf "
                             "pattern like 'chapter-%%03d.wav' to get one file "
                             "per line.")
    parser.add_argument("--out-dir", metavar="DIR", default=None,
                        help="Write output WAVs into DIR. Files are auto-named "
                             "(001.wav, 002.wav, …). Useful for batch mode "
                             "(multi-line input).")
    parser.add_argument("--srt", metavar="FILE", default=None,
                        help="Write a SubRip (.srt) subtitle file synchronized "
                             "to the generated audio. One cue per utterance; "
                             "works for both single and batch (multi-line) input.")
    parser.add_argument("--vtt", metavar="FILE", default=None,
                        help="Write a WebVTT (.vtt) subtitle file synchronized "
                             "to the generated audio. Same shape as --srt; pass "
                             "both flags to write both files.")
    parser.add_argument("--play", action="store_true",
                        help="Play audio even when --out is set")
    parser.add_argument("--speed", type=float, default=None,
                        help="Speech speed multiplier (default: 1.0)")
    parser.add_argument("--voice", default=None,
                        help="Voice/model override (engine-specific format). "
                             "For piper and coqui, --voice is required (positional "
                             "voices are not supported).")
    parser.add_argument("--lang", default=None,
                        help="Language code. Kokoro uses single-letter codes "
                             "(a=American, b=British, j=Japanese, z=Mandarin) "
                             "and defaults to the voice's natural language. "
                             "Coqui multilingual models use IETF codes "
                             "(en, es, fr, …).")
    parser.add_argument("--speaker", default=None,
                        help="Speaker id or name. Piper multi-speaker models "
                             "take an integer; Coqui multi-speaker models "
                             "(e.g. VITS-VCTK) take a name like 'p225'.")
    parser.add_argument("--speaker-wav", dest="speaker_wav", default=None,
                        help="Reference WAV for voice cloning. Coqui XTTS "
                             "models clone the speaker from this file. "
                             "(Pocket clones by passing the WAV as the voice "
                             "directly — see `pocket --list`.)")
    parser.add_argument("--emotion", default=None,
                        help="Emotion label. Honored by Coqui emotion-aware "
                             "models (Tortoise, some VITS variants); the "
                             "label vocabulary is per-model. Silently "
                             "ignored by models without emotion support.")
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
    parser.add_argument("--no-effects", action="store_true",
                        help="Skip all effects, including engine defaults from config.")
    parser.add_argument("--list-effects", action="store_true",
                        help="List all available audio effects and presets")
    parser.add_argument("--list-aliases", action="store_true",
                        help="List configured voice aliases / personas")
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

    # ── List aliases (also handled as a quick intercept above, but this
    # catches `marmalade-tts kokoro --list-aliases` etc.) ──
    if args.list_aliases:
        config = cfg_mod.load()
        _print_aliases(config.get("aliases") or {})
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

    # ── Split into utterances ──
    # Multi-line input → batch mode (one WAV per non-empty line). DELIBERATE
    # implicit trigger — see memory project_batch_synthesis.
    nonempty_lines = [ln for ln in text.splitlines() if ln.strip()]
    utterances = nonempty_lines if len(nonempty_lines) > 1 else [text]
    is_batch = len(utterances) > 1

    # ── Resolve voice ──
    # Precedence: --voice > positional voice token > alias.voice
    voice = args.voice or voice_arg
    if voice is None and alias_overrides and alias_overrides.get("voice"):
        voice = alias_overrides["voice"]

    # ── Output paths ──
    out_paths, auto_play = _resolve_out_paths(args, len(utterances), config, parser)

    # ── Speed ──
    # Precedence: --speed > alias.speed > defaults.speed
    if args.speed is not None:
        speed = args.speed
    elif alias_overrides and alias_overrides.get("speed") is not None:
        speed = alias_overrides["speed"]
    else:
        speed = config.get("defaults", {}).get("speed", 1.0)

    # ── Synth kwargs (the same for every utterance in a batch) ──
    # Each kwarg follows the same null-fallback pattern: explicit CLI flag
    # wins, then alias default, then engine defaults are left to the engine.
    synth_kwargs = {"speed": speed}
    if voice:
        synth_kwargs["voice"] = voice
    lang = args.lang or (alias_overrides.get("lang") if alias_overrides else None)
    if lang:
        synth_kwargs["lang"] = lang
    speaker = args.speaker or (alias_overrides.get("speaker") if alias_overrides else None)
    if speaker:
        synth_kwargs["speaker"] = speaker
    speaker_wav = args.speaker_wav or (alias_overrides.get("speaker_wav") if alias_overrides else None)
    if speaker_wav:
        synth_kwargs["speaker_wav"] = speaker_wav
    emotion = args.emotion or (alias_overrides.get("emotion") if alias_overrides else None)
    if emotion:
        synth_kwargs["emotion"] = emotion
    # Pass through any extra alias keys we don't recognise — the engine will
    # honor what it understands and ignore the rest. (See design rule #5.)
    if alias_overrides:
        for k, v in alias_overrides.items():
            if k in ("voice", "speed", "lang", "speaker", "speaker_wav",
                     "emotion", "effects"):
                continue
            synth_kwargs.setdefault(k, v)

    # ── Effects: same for every utterance ──
    # Precedence: --no-effects > --effect flags > alias.effects > engine defaults.
    if args.no_effects:
        effect_list = []
    elif args.effects:
        effect_list = args.effects
    elif alias_overrides and alias_overrides.get("effects"):
        effect_list = alias_overrides["effects"]
    else:
        effect_list = (
            config.get("effects", {}).get("defaults", {}).get(engine_name, [])
        )

    # ── Synthesize + (maybe) play ──
    # Preprocessing runs per-line so an emoji on line 3 doesn't affect line 1,
    # and a blank line after preprocessing is silently skipped. We capture
    # `raw_text` (the user's original line, pre-preprocessing) for subtitles
    # so emoji/markdown the user typed show up readable in the .srt/.vtt
    # even though those chars are stripped before synthesis.
    should_play = (auto_play or args.play) and not args.no_play

    # Streaming path: only when we're actually going to play AND there's more
    # than one utterance — single utterances have nothing to overlap with, and
    # silent --out-only runs gain nothing from a background thread. A producer
    # thread renders sequentially while the main thread plays in input order;
    # subtitles and the --json/--print-path report still happen once all
    # synthesis is done, so the user-visible final state is identical.
    if should_play and is_batch:
        import queue
        import threading

        play_q: "queue.Queue" = queue.Queue()
        results: list = []
        producer_error: list = []

        def _produce():
            try:
                for utt, out_path in zip(utterances, out_paths):
                    r = _synthesize_one(
                        utt, out_path, engine, args, eng_cfg, config,
                        engine_name, effect_list, synth_kwargs,
                    )
                    if r is None:
                        continue
                    results.append(r)
                    play_q.put(r)
            except BaseException as e:
                producer_error.append(e)
            finally:
                play_q.put(None)  # sentinel: end of stream

        prod = threading.Thread(
            target=_produce, daemon=True, name="marmalade-producer")
        prod.start()

        # Consume in FIFO order — same order the producer pushed, which is the
        # input order. Tmp WAVs (no --out / --out-dir) are cleaned up as we go,
        # exactly like the non-streaming path does in a separate loop.
        try:
            while True:
                r = play_q.get()
                if r is None:
                    break
                play_wav(r["out"])
                if not args.out and not args.out_dir and os.path.exists(r["out"]):
                    try:
                        os.unlink(r["out"])
                    except OSError:
                        pass
        except KeyboardInterrupt:
            # Best-effort cleanup of any tmp WAVs that were already rendered
            # but not yet played. Producer is a daemon thread, so it dies
            # with the process; we just don't leave files behind that we
            # know the paths to.
            if not args.out and not args.out_dir:
                # Drain whatever's already in the queue without blocking.
                try:
                    while True:
                        r = play_q.get_nowait()
                        if r is None:
                            continue
                        if os.path.exists(r["out"]):
                            try:
                                os.unlink(r["out"])
                            except OSError:
                                pass
                except queue.Empty:
                    pass
            raise

        prod.join()

        # Subtitles + report run whether or not the producer raised — they
        # describe what *did* render successfully. The exception (if any)
        # is then re-raised so the process exits non-zero with a clear cause.
        _write_subtitles(args, results)
        _report_outputs(args, engine_name, voice, results, effect_list,
                        eng_cfg, is_batch)

        if producer_error:
            raise producer_error[0]
        if not results:
            sys.exit("[marmalade-tts] No text to synthesize after preprocessing")
        return

    # Non-streaming path: single utterance, --no-play, or --out-only run.
    # Same sequential loop the CLI has always used — no thread spawned.
    results = []
    for utt, out_path in zip(utterances, out_paths):
        r = _synthesize_one(
            utt, out_path, engine, args, eng_cfg, config,
            engine_name, effect_list, synth_kwargs,
        )
        if r is not None:
            results.append(r)

    if not results:
        sys.exit("[marmalade-tts] No text to synthesize after preprocessing")

    # ── Subtitle output ──
    _write_subtitles(args, results)

    # ── Output reporting ──
    _report_outputs(args, engine_name, voice, results, effect_list, eng_cfg, is_batch)

    # ── Playback ──
    if should_play:
        for r in results:
            play_wav(r["out"])
            if not args.out and not args.out_dir and os.path.exists(r["out"]):
                os.unlink(r["out"])


if __name__ == "__main__":
    main()
