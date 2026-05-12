"""
Audio effects post-processing for marmalade-tts.

Effects are applied after synthesis using sox. Each effect is a named
transformation with optional parameters. Multiple effects are chained
in a single sox invocation.

Built-in presets combine effects for common use cases (robot, cave, etc.).
Custom presets can be defined in config under effects.presets.

Dependencies:
  sox — required for any effect processing
       apt install sox   /   brew install sox

Usage (CLI):
  marmalade-tts "Hello" --effect reverb=50
  marmalade-tts "Hello" --effect pitch=200 --effect reverb=30
  marmalade-tts "Hello" --effect robot         # named preset
  marmalade-tts --list-effects                 # show all effects and presets
"""

import os
import shutil
import subprocess
import sys
import tempfile

# ── Effect definitions ────────────────────────────────────────────────────────
# Each entry: (sox_args_template, description, param_description)
# {value} is replaced by the user-supplied parameter.

EFFECTS = {
    # name          sox args (list)                                         description                           param hint
    "reverb":   (lambda p: ["reverb", str(p or 50)],
                 "Add room reverb",                                         "amount 0-100 (default 50)"),
    "pitch":    (lambda p: ["pitch", str(p or 100)],
                 "Shift pitch in cents (100 cents = 1 semitone)",           "cents, e.g. 200 (up) or -300 (down)"),
    "tempo":    (lambda p: ["tempo", str(p or 1.2)],
                 "Change speed without shifting pitch",                     "factor, e.g. 1.2 (faster) or 0.8 (slower)"),
    "echo":     (lambda p: _parse_echo(p),
                 "Add echo/delay",                                          "gain-in:gain-out:delay-ms:decay, e.g. 0.8:0.88:60:0.4"),
    "overdrive":(lambda p: ["overdrive", str(p or 20)],
                 "Add overdrive/distortion (robotic quality)",              "gain 1-100 (default 20)"),
    "flanger":  (lambda p: ["flanger"],
                 "Add flanger modulation (sci-fi wobble)",                  "no parameter needed"),
    "chorus":   (lambda p: _parse_chorus(p),
                 "Add chorus (doubled-voice effect)",                       "optional: gain-in:gain-out:delay:decay:speed:depth"),
    "treble":   (lambda p: ["treble", str(p or 6)],
                 "Boost or cut high frequencies (EQ)",                     "dB, e.g. 6 (boost) or -6 (cut)"),
    "bass":     (lambda p: ["bass", str(p or 6)],
                 "Boost or cut low frequencies (EQ)",                      "dB, e.g. 6 (boost) or -6 (cut)"),
    "bandpass": (lambda p: _parse_bandpass(p),
                 "Bandpass filter — keep only a frequency range",           "low-hz:high-hz, e.g. 300:3400 (telephone)"),
    "speed":    (lambda p: ["speed", str(p or 1.2)],
                 "Change speed AND pitch together",                         "factor, e.g. 1.2 (faster+higher)"),
    "vol":      (lambda p: ["vol", str(p or 2.0)],
                 "Adjust volume",                                           "factor, e.g. 2.0 (double) or 0.5 (half)"),
    "normalize":(lambda p: ["norm"],
                 "Normalize audio to peak level",                           "no parameter needed"),
    "fade":     (lambda p: _parse_fade(p),
                 "Add fade in/out",                                         "in-seconds:out-seconds, e.g. 0.1:0.5"),
}


# ── Built-in presets ──────────────────────────────────────────────────────────

BUILTIN_PRESETS = {
    "robot":       ["overdrive=20", "pitch=-300", "reverb=10"],
    "cave":        ["reverb=80", "echo=0.6:0.6:120:0.3"],
    "chipmunk":    ["pitch=400", "tempo=0.95"],
    "deep":        ["pitch=-400", "bass=6"],
    "telephone":   ["bandpass=300:3400", "overdrive=5", "vol=1.5"],
    "whisper":     ["vol=0.4", "treble=4", "reverb=20"],
    "stadium":     ["reverb=90", "echo=0.8:0.7:80:0.25"],
    "megaphone":   ["bandpass=500:4000", "overdrive=30", "vol=2.0"],
    "slow_deep":   ["pitch=-200", "tempo=0.8"],
    "fast_high":   ["pitch=200", "tempo=1.3"],
}


# ── Parameter parsers ─────────────────────────────────────────────────────────

def _parse_echo(p) -> list:
    """echo=0.8:0.88:60:0.4  →  ['echo', '0.8', '0.88', '60', '0.4']"""
    if not p:
        return ["echo", "0.8", "0.88", "60", "0.4"]
    parts = str(p).split(":")
    if len(parts) == 4:
        return ["echo"] + parts
    raise ValueError(f"echo expects gain-in:gain-out:delay-ms:decay, got: {p!r}")


def _parse_bandpass(p) -> list:
    """bandpass=300:3400  →  sinc filter low-pass + high-pass"""
    if not p:
        return ["sinc", "300-3400"]
    parts = str(p).split(":")
    if len(parts) == 2:
        return ["sinc", f"{parts[0]}-{parts[1]}"]
    raise ValueError(f"bandpass expects low-hz:high-hz, got: {p!r}")


def _parse_chorus(p) -> list:
    """chorus with sensible defaults."""
    if not p:
        return ["chorus", "0.8", "0.9", "55", "0.4", "0.25", "2", "-s"]
    parts = str(p).split(":")
    if len(parts) == 6:
        return ["chorus"] + parts + ["-s"]
    raise ValueError(f"chorus expects gain-in:gain-out:delay:decay:speed:depth, got: {p!r}")


def _parse_fade(p) -> list:
    """fade=0.1:0.5  →  fade in 0.1s, fade out 0.5s"""
    if not p:
        return ["fade", "0.05", "0", "0.3"]
    parts = str(p).split(":")
    if len(parts) == 2:
        # sox fade format: fade [type] fade-in-length [stop-position] fade-out-length
        return ["fade", parts[0], "0", parts[1]]
    raise ValueError(f"fade expects in-seconds:out-seconds, got: {p!r}")


# ── Public API ────────────────────────────────────────────────────────────────

def sox_available() -> bool:
    """Check if sox is installed."""
    return shutil.which("sox") is not None


def resolve_effect_list(effect_specs: list[str], config: dict) -> list[str]:
    """Resolve a list of effect specs, expanding preset names.

    A spec is either:
      - A preset name: "robot"
      - An effect=value: "reverb=50"
      - An effect name (no value): "flanger"

    Returns a flat list of effect specs (no presets, all resolved).
    """
    # Merge builtin presets with user-defined presets from config
    user_presets = config.get("effects", {}).get("presets", {})
    all_presets = {**BUILTIN_PRESETS, **user_presets}

    resolved = []
    for spec in effect_specs:
        if spec in all_presets:
            # Expand preset — presets can contain other presets (one level deep)
            for sub_spec in all_presets[spec]:
                if sub_spec in all_presets:
                    resolved.extend(all_presets[sub_spec])
                else:
                    resolved.append(sub_spec)
        else:
            resolved.append(spec)
    return resolved


def _parse_spec(spec: str) -> tuple[str, object]:
    """Parse 'reverb=50' → ('reverb', '50'), 'flanger' → ('flanger', None)."""
    if "=" in spec:
        name, _, value = spec.partition("=")
        return name.strip(), value.strip()
    return spec.strip(), None


def build_sox_args(effect_specs: list[str]) -> list[str]:
    """Build the sox effect chain args from a list of resolved specs.

    Returns a list suitable for appending to a sox command, e.g.:
      ['reverb', '50', 'pitch', '200', 'norm']
    """
    args = []
    for spec in effect_specs:
        name, value = _parse_spec(spec)
        if name not in EFFECTS:
            raise ValueError(f"Unknown effect: {name!r}. Run --list-effects to see available effects.")
        builder, _desc, _hint = EFFECTS[name]
        args.extend(builder(value))
    return args


def apply_effects(in_path: str, out_path: str, effect_specs: list[str], config: dict = None):
    """Apply audio effects to a WAV file using sox.

    Args:
        in_path:      Input WAV file.
        out_path:     Output WAV file (can be the same as in_path — uses temp file).
        effect_specs: List of effect specs, e.g. ["reverb=50", "pitch=200", "robot"].
        config:       Full config dict (for user-defined presets).

    Raises:
        RuntimeError: If sox is not installed or the sox command fails.
    """
    if config is None:
        config = {}

    resolved = resolve_effect_list(effect_specs, config)
    if not resolved:
        return

    if not sox_available():
        raise RuntimeError(
            "sox is required for audio effects but was not found.\n"
            "Install it: apt install sox   or   brew install sox"
        )

    sox_chain = build_sox_args(resolved)

    # If in_path == out_path, write to a temp file first then rename
    same_file = os.path.realpath(in_path) == os.path.realpath(out_path)
    if same_file:
        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        target = tmp_path
    else:
        target = out_path

    cmd = ["sox", in_path, target] + sox_chain
    try:
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"sox failed:\n{err}")
        if same_file:
            # shutil.move (not os.replace) — handles cross-filesystem moves
            # (e.g. tmpfs /tmp → ext4 home dir, which os.replace can't do).
            shutil.move(tmp_path, out_path)
            # tempfile.mkstemp creates with 0600; restore the user's default umask
            # so the final output is readable like any other file they create.
            try:
                umask = os.umask(0)
                os.umask(umask)
                os.chmod(out_path, 0o666 & ~umask)
            except OSError:
                pass
    except Exception:
        if same_file and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def list_effects(user_presets: dict = None):
    """Print all available effects and presets."""
    print("Available effects:")
    for name, (_, desc, hint) in EFFECTS.items():
        print(f"  {name:<12} {desc}")
        if hint:
            print(f"               param: {hint}")

    print()
    print("Built-in presets:")
    for name, specs in BUILTIN_PRESETS.items():
        print(f"  {name:<12} {' + '.join(specs)}")

    if user_presets:
        print()
        print("User presets (from config):")
        for name, specs in user_presets.items():
            print(f"  {name:<12} {' + '.join(specs)}")

    print()
    print("Usage:")
    print("  marmalade-tts \"Hello\" --effect reverb=50")
    print("  marmalade-tts \"Hello\" --effect pitch=200 --effect reverb=30")
    print("  marmalade-tts \"Hello\" --effect robot        # named preset")
