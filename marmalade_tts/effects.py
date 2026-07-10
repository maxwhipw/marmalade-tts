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
    "lowpass":  (lambda p: ["lowpass", str(p or 3000)],
                 "Low-pass filter — roll off highs",                        "cutoff Hz (default 3000)"),
    "highpass": (lambda p: ["highpass", str(p or 300)],
                 "High-pass filter — roll off lows",                        "cutoff Hz (default 300)"),
    "mid":      (lambda p: _parse_mid(p),
                 "Peaking (mid-band) EQ",                                   "freq:gain, e.g. 1000:6"),
    "tremolo":  (lambda p: _parse_tremolo(p),
                 "Amplitude tremolo (volume LFO)",                          "speed:depth, e.g. 5:0.5 (depth 0-1)"),
    "phaser":   (lambda p: _parse_phaser(p),
                 "Phaser — sweeping notches (sci-fi)",                      "speed:decay, e.g. 0.5:0.4"),
    "compressor":(lambda p: _parse_compressor(p),
                 "Downward compressor (tame dynamics)",                     "threshold_dB:ratio, e.g. -20:4"),
}


# ── Built-in presets ──────────────────────────────────────────────────────────

BUILTIN_PRESETS = {
    "robot":       ["overdrive=20", "pitch=-100", "reverb=10", "vol=0.7"],
    "cave":        ["reverb=80", "echo=0.6:0.6:120:0.3"],
    "chipmunk":    ["pitch=400", "tempo=0.95"],
    "deep":        ["pitch=-400", "bass=6"],
    "telephone":   ["bandpass=300:3400", "overdrive=5", "vol=1.5"],
    "stadium":     ["reverb=90", "echo=0.8:0.7:80:0.25"],
    "megaphone":   ["bandpass=500:4000", "overdrive=30", "vol=1.5"],
    # Curated voice stackups — pro vocal chains + character voices.
    # Order follows the convention: filters/EQ → compression → drive →
    # modulation → reverb last.
    "broadcaster": ["highpass=90", "mid=300:-3", "compressor=-18:3",
                    "mid=3000:3", "treble=3", "bass=2"],
    "podcast":     ["highpass=80", "bass=3", "compressor=-20:2.5",
                    "mid=250:-2", "treble=2"],
    "trailer":     ["pitch=-250", "bass=5", "compressor=-18:4",
                    "mid=2500:2", "reverb=22"],
    "audiobook":   ["highpass=85", "compressor=-22:3", "mid=2500:2", "reverb=10"],
    "walkie_talkie": ["highpass=400", "lowpass=5000", "overdrive=8",
                      "compressor=-24:6", "vol=1.3"],
    "vintage_radio": ["highpass=400", "lowpass=4000", "mid=1000:12",
                      "overdrive=8", "compressor=-26:3", "tremolo=4:0.15",
                      "reverb=8", "vol=1.3"],
    "intercom":    ["bandpass=450:2500", "overdrive=18", "mid=1500:4",
                    "reverb=30", "vol=1.5"],
    "underwater":  ["lowpass=700", "chorus", "pitch=-80", "tremolo=1.5:0.2",
                    "vol=1.35"],
    "alien":       ["pitch=150", "phaser=0.4:0.5", "flanger", "reverb=30"],
    "ethereal":    ["highpass=250", "pitch=120", "reverb=70",
                    "tremolo=3:0.25", "treble=3"],
    "dragon":      ["pitch=-450", "bass=7", "mid=700:4", "compressor=-18:4",
                    "overdrive=14", "chorus", "reverb=25"],
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


def _parse_mid(p) -> list:
    """mid=1000:6  →  ['equalizer', '1000', '1.0q', '6']  (peaking EQ, fixed Q=1)"""
    freq, gain = "1000", "0"
    if p:
        parts = str(p).split(":")
        if len(parts) != 2:
            raise ValueError(f"mid expects freq:gain, got: {p!r}")
        freq, gain = parts
    return ["equalizer", freq, "1.0q", gain]


def _parse_tremolo(p) -> list:
    """tremolo=5:0.5  →  ['tremolo', '5', '50']  (depth 0-1 → sox percent)"""
    speed, depth = "5", "0.4"
    if p:
        parts = str(p).split(":")
        if len(parts) != 2:
            raise ValueError(f"tremolo expects speed:depth, got: {p!r}")
        speed, depth = parts
    return ["tremolo", speed, str(float(depth) * 100)]


def _parse_phaser(p) -> list:
    """phaser=0.5:0.4  →  ['phaser', '0.7', '0.7', '3.0', '0.4', '0.5', '-s'] (speed:decay)"""
    speed, decay = "0.5", "0.4"
    if p:
        parts = str(p).split(":")
        if len(parts) != 2:
            raise ValueError(f"phaser expects speed:decay, got: {p!r}")
        speed, decay = parts
    # sox phaser: gain-in gain-out delay decay speed shape
    return ["phaser", "0.7", "0.7", "3.0", decay, speed, "-s"]


def _parse_compressor(p) -> list:
    """compressor=-20:4  →  a sox `compand` with a two-segment downward curve.

    Maps threshold (dBFS) + ratio to a compand transfer function: unity below
    threshold, then `ratio:1` reduction from threshold up to 0 dBFS.
    """
    threshold, ratio = -20.0, 4.0
    if p:
        parts = str(p).split(":")
        if len(parts) != 2:
            raise ValueError(f"compressor expects threshold_dB:ratio, got: {p!r}")
        threshold, ratio = float(parts[0]), float(parts[1])
    # Output level at 0 dBFS input after compression above the threshold.
    out_at_zero = threshold + (0.0 - threshold) / max(ratio, 1.0)
    # compand attack,decay  soft-knee:in1,out1,in2,out2
    transfer = f"6:-90,-90,{threshold:g},{threshold:g},0,{out_at_zero:g}"
    return ["compand", "0.005,0.1", transfer]


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
