"""Pure helpers extracted from cli.py.

These are the resolution / formatting / reporting functions that don't
need access to the synthesis loop or the orchestration in ``main()``.
Keeping them here lets cli.py stay focused on dispatch and lets future
features add code next to ``main()`` without dragging these along.

A couple of helpers (``resolve_out_paths``, ``apply_effects_if_any``) look
up ``make_tmp_wav`` / ``fx.sox_available`` / ``fx.apply_effects`` through
the ``cli`` module namespace at call time. That's deliberate: many tests
patch those names via ``marmalade_tts.cli.make_tmp_wav`` etc., and
resolving through the ``cli`` module keeps those patches effective after
the refactor.
"""

from __future__ import annotations

import json
import os
import sys

from . import __version__
from . import preprocessing as pp
from . import subtitles as subs
from .engines.kitten import VOICES as KITTEN_VOICES
from .engines.kokoro import is_voice_token as kokoro_is_voice_token
from .engines.pocket import VOICES as POCKET_VOICES
from .engines.emojivoice import VOICES as EMOJIVOICE_VOICES


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

def apply_preset(eng_cfg: dict, engine_name: str, preset_name: str,
                 config: dict) -> None:
    """Mutate ``eng_cfg`` in place to apply a named preset (fast/balanced/quality)."""
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


def resolve_text_and_voice(args, positional, engine_name, parser):
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


def resolve_preprocessing(text, args, eng_cfg, config, engine_name):
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


def apply_effects_if_any(out_path, effect_list, config):
    """Apply effect chain in place. Warns rather than failing on sox issues.

    Looks up sox helpers via the ``cli`` module so tests patching
    ``marmalade_tts.cli.fx.*`` keep working after the refactor."""
    if not effect_list:
        return
    from . import cli  # deferred — cli imports us; resolve patched names here
    if not cli.fx.sox_available():
        print(
            "[marmalade-tts] Note: sox is not installed — audio effects were skipped.\n"
            "  To enable effects: apt install sox   or   brew install sox",
            file=sys.stderr,
        )
        return
    try:
        cli.fx.apply_effects(out_path, out_path, effect_list, config)
    except (ValueError, RuntimeError) as e:
        print(f"[marmalade-tts] Effect warning: {e}", file=sys.stderr)


def resolve_out_paths(args, n: int, config: dict, parser):
    """Resolve output paths for N utterances. Returns (paths, auto_play).

    Rules (apply to single-utterance and batch alike — batch is just N>1):
      --out PATTERN  (contains '%')   : printf-format with 1-based index.
      --out FILE     (no '%')         : literal path; N must be 1.
      --out-dir DIR                   : auto-name 001.wav, 002.wav, …
      neither                          : a tmp WAV per utterance, auto-played.
    """
    from . import cli  # deferred — picks up patched cli.make_tmp_wav
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
    return ([cli.make_tmp_wav() for _ in range(n)],
            config.get("defaults", {}).get("play", True))


def print_aliases(aliases: dict) -> None:
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


def report_outputs(args, engine_name, voice, results, effect_list, eng_cfg,
                   is_batch):
    """Print results in the user-requested format. For batch, --json prints
    a JSON array (one element per utterance); for single, --json keeps the
    same single-object shape it has always had."""
    if args.json:
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


def write_subtitles_for_results(args, results):
    """Emit --srt / --vtt files if requested. Both flags are independent —
    passing both writes both. Cue text comes from ``raw_text`` (original
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
