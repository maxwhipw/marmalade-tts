"""CLI entrypoint for marmalade-tts.

Coordinator only — parses argv, dispatches subcommands, resolves the
config and engine, then hands off to ``synth.run_batch``. The pure
helpers (text/voice/out paths/preset/effects/subtitles/aliases) live in
``cli_helpers.py`` and the synthesis loop lives in ``synth.py``.

The trailing re-exports keep test files (which patch
``marmalade_tts.cli.<symbol>`` heavily) working without modification.
"""

import argparse
import os
import sys
import yaml

from . import __version__
from . import config as cfg_mod
from . import daemon
from . import preprocessing as pp
from .playback import play_wav, make_tmp_wav, wav_duration
from .completion import bash_completion, zsh_completion
from .engines.kitten import KittenEngine, VOICES as KITTEN_VOICES
from .engines.kokoro import KokoroEngine, is_voice_token as kokoro_is_voice_token
from .engines.piper import PiperEngine
from .engines.coqui import CoquiEngine
from .engines.pocket import PocketEngine, VOICES as POCKET_VOICES
from .engines.matcha import MatchaEngine
from .engines.emojivoice import EmojiVoiceEngine, VOICES as EMOJIVOICE_VOICES
from . import effects as fx

from . import cli_helpers
from . import synth as _synth
from .cli_helpers import (
    resolve_text,
    looks_like_voice,
    apply_preset,
    resolve_text_and_voice,
    resolve_preprocessing,
    apply_effects_if_any,
    resolve_out_paths,
    print_aliases,
    report_outputs,
    write_subtitles_for_results,
)
from .synth import SynthResult, synthesize_one, run_batch

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


# ── Backward-compat private re-exports ──────────────────────────────────────
# Older callers (mcp_server.synthesize_text used to do this) and a handful of
# tests reach for the underscore names. Keep cheap aliases so the rename to
# public symbols in cli_helpers / synth doesn't break anyone.
_apply_preset = apply_preset
_resolve_text_and_voice = resolve_text_and_voice
_resolve_preprocessing = resolve_preprocessing
_apply_effects_if_any = apply_effects_if_any
_resolve_out_paths = resolve_out_paths
_print_aliases = print_aliases
_report_outputs = report_outputs
_write_subtitles = write_subtitles_for_results
_synthesize_one = synthesize_one


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


def cmd_uninstall(args: list):
    """Handle `marmalade-tts uninstall [<engine>] [--engines] [--purge] ...`.

    Tiered cleanup of CLI-managed state. Mirrors ``marmalade-tts install``:

      marmalade-tts uninstall              # interactive: pick a tier / engine
      marmalade-tts uninstall <engine>     # one engine (venv + unit + sock/pid/log)
      marmalade-tts uninstall --engines    # every engine; keep config + daemon dir
      marmalade-tts uninstall --purge      # everything CLI-managed
      marmalade-tts uninstall --dry-run    # print the plan, don't touch anything
      marmalade-tts uninstall -y           # skip the confirmation prompt

    The CLI binary itself and the HuggingFace cache are NEVER deleted by
    this command (the HF cache is shared with other tools). On --purge we
    print the install-method-specific removal command for the CLI.
    """
    import argparse as _ap

    from . import uninstaller
    from .init import _is_tty

    parser = _ap.ArgumentParser(
        prog="marmalade-tts uninstall", add_help=True,
        description="Remove CLI-managed state (engine venvs, daemon scripts, "
                    "systemd units, sockets/pids/logs, config). NEVER removes "
                    "the CLI binary itself or the HuggingFace cache.")
    parser.add_argument("engine", nargs="?", default=None,
                        help=f"single engine to uninstall: "
                             f"{', '.join(uninstaller.INSTALL_RECIPES)}")
    parser.add_argument("--engines", action="store_true",
                        help="uninstall all engines (keep daemon dir + config)")
    parser.add_argument("--purge", action="store_true",
                        help="uninstall everything CLI-managed (engines + "
                             "daemon dir + config + pronunciations + all "
                             "systemd units)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan and exit without touching anything")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="skip the interactive confirmation prompt")
    parsed = parser.parse_args(args)

    # ── Resolve tier ──
    chosen = [bool(parsed.engine), parsed.engines, parsed.purge]
    if sum(chosen) > 1:
        print("[uninstall] pick at most one of: <engine>, --engines, --purge",
              file=sys.stderr)
        sys.exit(1)

    tier = None  # "engine" | "engines" | "purge"
    engine_name = None
    if parsed.engine:
        if parsed.engine not in uninstaller.INSTALL_RECIPES:
            print(f"[uninstall] unknown engine: {parsed.engine!r}\n"
                  f"  known: {', '.join(uninstaller.INSTALL_RECIPES)}",
                  file=sys.stderr)
            sys.exit(1)
        tier, engine_name = "engine", parsed.engine
    elif parsed.engines:
        tier = "engines"
    elif parsed.purge:
        tier = "purge"

    # ── Interactive tier picker (no args + TTY) ──
    if tier is None:
        if not _is_tty():
            print("[uninstall] No tier specified. Pass <engine>, --engines, "
                  "--purge, or run interactively from a TTY.", file=sys.stderr)
            sys.exit(1)
        print("marmalade-tts uninstall — what should I remove?\n")
        print("  1) a single engine          (its venv + unit + sock/pid/log)")
        print("  2) all engines              (keeps daemon dir + config)")
        print("  3) PURGE everything         (engines + daemon dir + config)")
        print("  q) cancel")
        try:
            resp = input("\n  Choice [1/2/3/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            resp = "q"
        if resp == "1":
            print("\n  Engines: " + ", ".join(uninstaller.INSTALL_RECIPES))
            try:
                engine_name = input("  Engine name: ").strip()
            except (EOFError, KeyboardInterrupt):
                engine_name = ""
            if engine_name not in uninstaller.INSTALL_RECIPES:
                print(f"[uninstall] unknown engine: {engine_name!r}",
                      file=sys.stderr)
                sys.exit(1)
            tier = "engine"
        elif resp == "2":
            tier = "engines"
        elif resp == "3":
            tier = "purge"
        else:
            print("[uninstall] cancelled.")
            return

    # ── Build the plan + print it ──
    if tier == "engine":
        plan = uninstaller.plan_for_engine(engine_name)
        header = f"Plan for: uninstall {engine_name}"
    elif tier == "engines":
        plan = uninstaller.plan_for_all_engines()
        header = "Plan for: uninstall --engines  (every engine)"
    else:  # purge
        plan = uninstaller.plan_for_purge()
        header = "Plan for: uninstall --purge  (EVERYTHING CLI-managed)"

    uninstaller.print_plan(plan, header)

    # ── Dry-run wins over -y ──
    if parsed.dry_run:
        print("\n[uninstall] --dry-run: no files were touched.")
        return

    # ── Confirm in interactive mode unless -y was given ──
    if not parsed.yes and _is_tty():
        try:
            resp = input("\nProceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            resp = ""
        if resp not in ("y", "yes"):
            print("[uninstall] aborted.")
            return

    # ── Execute ──
    if tier == "engine":
        report = uninstaller.uninstall_engine(engine_name, dry_run=False)
    elif tier == "engines":
        report = uninstaller.uninstall_all_engines(dry_run=False)
    else:
        report = uninstaller.purge(dry_run=False)

    # ── Summary ──
    print("\n[uninstall] ━━ summary ━━")
    print(f"  removed: {len(report.removed)}")
    print(f"  skipped (already gone): {len(report.skipped)}")
    print(f"  failed:  {len(report.failed)}")
    for p, why in report.failed:
        print(f"    ✗ {p}: {why}")

    if tier == "purge":
        uninstaller.print_removal_hint(report.install_method or "unknown")

    if report.failed:
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


# ── Argument parser ─────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser. Extracted so ``main()`` stays
    readable — argparse setup is mostly help text and adds no real logic."""
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
  marmalade-tts @chapters.txt --batch --out-dir ./out/  # one WAV per line
  eval "$(marmalade-tts --completion bash)"
""",
    )
    parser.add_argument("engine", nargs="?", choices=ENGINE_NAMES, default=None,
                        help="TTS engine (uses defaults.engine if omitted)")
    parser.add_argument("--text", "-t", default=None,
                        help="Text to synthesize (alternative to positional)")
    parser.add_argument("--batch", action="store_true",
                        help="Treat each non-empty input line as a separate "
                             "utterance and produce one WAV per line. Without "
                             "this flag the whole input (line breaks and all) "
                             "goes to a single synthesis call. Long inputs are "
                             "still chunked internally and recombined into one "
                             "WAV per input — see Chunking in the README.")
    parser.add_argument("--out", metavar="FILE",
                        help="Save WAV to file (default: play immediately). "
                             "With --batch, pass a printf pattern like "
                             "'chapter-%%03d.wav' to get one file per line.")
    parser.add_argument("--out-dir", metavar="DIR", default=None,
                        help="Write output WAVs into DIR. Files are auto-named "
                             "(001.wav, 002.wav, …). Useful with --batch.")
    parser.add_argument("--srt", metavar="FILE", default=None,
                        help="Write a SubRip (.srt) subtitle file synchronized "
                             "to the generated audio. One cue per utterance; "
                             "works for both single-utterance and --batch runs.")
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
    return parser


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
    if argv and argv[0] == "uninstall":
        cmd_uninstall(argv[1:])
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
        print_aliases(config_tmp.get("aliases") or {})
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
    parser = _build_parser()
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
        print_aliases(config.get("aliases") or {})
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
    apply_preset(eng_cfg, engine_name, preset_name, config)

    # ── Build engine ──
    engine = ENGINE_CLASSES[engine_name](eng_cfg)

    # ── List mode ──
    if args.list:
        engine.list_voices()
        return

    # ── Resolve text and voice ──
    text, voice_arg = resolve_text_and_voice(args, positional, engine_name, parser)

    if not text.strip():
        sys.exit("[marmalade-tts] No text to synthesize")

    # ── Split into utterances ──
    # Batch mode is now opt-in via --batch: each non-empty line becomes a
    # separate WAV. Without --batch, the entire input goes to a single
    # synthesis call. Inputs longer than the engine's MAX_CHARS are still
    # split transparently inside synth.synthesize_one and re-concatenated;
    # that's chunking, not batch — see chunking.py.
    if args.batch:
        nonempty_lines = [ln for ln in text.splitlines() if ln.strip()]
        utterances = nonempty_lines if nonempty_lines else [text]
    else:
        utterances = [text]
    is_batch = len(utterances) > 1

    # ── Resolve voice ──
    # Precedence: --voice > positional voice token > alias.voice
    voice = args.voice or voice_arg
    if voice is None and alias_overrides and alias_overrides.get("voice"):
        voice = alias_overrides["voice"]

    # ── Output paths ──
    out_paths, auto_play = resolve_out_paths(args, len(utterances), config, parser)

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

    # ── Preprocessing mode (encodes the --preprocessing / --no-preprocessing
    # flags so synth.synthesize_one can honor them; None = use config). ──
    if args.no_preprocessing:
        preprocess_mode = False
    elif args.preprocessing:
        preprocess_mode = True
    else:
        preprocess_mode = None
    custom_rules = eng_cfg.get("preprocessing") if isinstance(
        eng_cfg.get("preprocessing"), list) else None

    # ── Synthesize + (maybe) play ──
    should_play = (auto_play or args.play) and not args.no_play

    # Streaming path: only when we're actually going to play AND there's more
    # than one utterance — single utterances have nothing to overlap with, and
    # silent --out-only runs gain nothing from a background thread. Streaming
    # is handled by synth.run_batch(streaming=True, on_ready=...); on_ready
    # plays the WAV and cleans up tmp files. Subtitles + report run after
    # streaming finishes so the user-visible final state is identical to the
    # sequential path.
    if should_play and is_batch:
        def _on_ready(r):
            play_wav(r["out"])
            if not args.out and not args.out_dir and os.path.exists(r["out"]):
                try:
                    os.unlink(r["out"])
                except OSError:
                    pass

        def _on_interrupt(r):
            # Best-effort cleanup of rendered-but-unplayed tmp WAVs.
            if not args.out and not args.out_dir and os.path.exists(r["out"]):
                try:
                    os.unlink(r["out"])
                except OSError:
                    pass

        results, producer_error = run_batch(
            utterances, out_paths,
            engine=engine, engine_name=engine_name,
            eng_cfg=eng_cfg, config=config,
            synth_kwargs=synth_kwargs, effect_list=effect_list,
            preprocess_mode=preprocess_mode, custom_rules=custom_rules,
            streaming=True, on_ready=_on_ready, on_interrupt=_on_interrupt,
        )

        # Subtitles + report run whether or not the producer raised — they
        # describe what *did* render successfully. The exception (if any)
        # is then re-raised so the process exits non-zero with a clear cause.
        write_subtitles_for_results(args, results)
        report_outputs(args, engine_name, voice, results, effect_list,
                       eng_cfg, is_batch)

        if producer_error is not None:
            raise producer_error
        if not results:
            sys.exit("[marmalade-tts] No text to synthesize after preprocessing")
        return

    # Non-streaming path: single utterance, --no-play, or --out-only run.
    results, _ = run_batch(
        utterances, out_paths,
        engine=engine, engine_name=engine_name,
        eng_cfg=eng_cfg, config=config,
        synth_kwargs=synth_kwargs, effect_list=effect_list,
        preprocess_mode=preprocess_mode, custom_rules=custom_rules,
        streaming=False,
    )

    if not results:
        sys.exit("[marmalade-tts] No text to synthesize after preprocessing")

    # ── Subtitle output ──
    write_subtitles_for_results(args, results)

    # ── Output reporting ──
    report_outputs(args, engine_name, voice, results, effect_list, eng_cfg, is_batch)

    # ── Playback ──
    if should_play:
        for r in results:
            play_wav(r["out"])
            if not args.out and not args.out_dir and os.path.exists(r["out"]):
                os.unlink(r["out"])


if __name__ == "__main__":
    main()
