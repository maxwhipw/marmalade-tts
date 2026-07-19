# 🍊 marmalade-tts

<p align="center">
  <img src="assets/mascot.png" alt="marmalade-tts mascot" width="220">
</p>

A unified command-line interface for local text-to-speech synthesis.
Supports multiple engines with a single consistent interface — daemon mode for
fast synthesis, per-engine text preprocessing, and optional audio effects via
[sox](https://sox.sourceforge.net/).

**Related projects:**
[marmalade-tts-android](https://github.com/maxwhipw/marmalade-tts-android) —
native Android TTS app (in development).
[marmalade-android](https://github.com/maxwhipw/marmalade-android) —
OpenClaw AI assistant client (shares the mascot; public release coming soon).

## Hear it

A short demo and a few effect samples (download and play with `paplay`,
`aplay`, or any audio app):

| Sample | What it is |
|--------|-----------|
| [`demos/tahlia-voice-sample/tahlia-intro.wav`](demos/tahlia-voice-sample/tahlia-intro.wav) | Capability-demo clip generated to show off marmalade-tts |
| [`samples/effects/baseline-F.wav`](samples/effects/baseline-F.wav) | Kitten voice, no effects (reference) |
| [`samples/effects/cave-01-F.wav`](samples/effects/cave-01-F.wav) | `--effect cave` (heavy reverb + echo) |
| [`samples/effects/robot-01-F.wav`](samples/effects/robot-01-F.wav) | `--effect robot` (overdrive + pitch + reverb) |
| [`samples/effects/chipmunk-01-F.wav`](samples/effects/chipmunk-01-F.wav) | `--effect chipmunk` (pitch up + faster) |
| [`samples/effects/deep-01-F.wav`](samples/effects/deep-01-F.wav) | `--effect deep` (pitch down + bass) |
| [`samples/effects/alien-01-classic-F.wav`](samples/effects/alien-01-classic-F.wav) | Custom alien chain |
| [`samples/effects/ghost-02-echo-F.wav`](samples/effects/ghost-02-echo-F.wav) | Custom ghost chain |

See [`samples/effects/README.md`](samples/effects/README.md) for the exact
commands used to generate each one.

---

## Installation

Installing marmalade-tts is two steps: install the **CLI** (tiny), then let
it install the **engines** you want. `marmalade-tts init` does the engine
install for you — see [Installing engines](#installing-engines) below.

> **[uv](https://docs.astral.sh/uv/) is required.** The engine installer
> uses it to manage per-engine Python versions and venvs. `pipx install`
> pulls it in automatically; for the other install methods install uv with
> `curl -LsSf https://astral.sh/uv/install.sh | sh`.

### pipx (recommended for most users)

```sh
pipx install marmalade-tts
marmalade-tts init
```

### deb / rpm (system-wide install)

Download the latest `.deb` or `.rpm` from the [GitHub releases page](https://github.com/maxwhipw/marmalade-tts/releases), then:

```sh
# Debian/Ubuntu
sudo dpkg -i marmalade-tts_0.5.0_amd64.deb

# Fedora/RHEL
sudo rpm -i marmalade-tts-0.5.0-1.x86_64.rpm
```

### AUR (Arch Linux) — coming soon

```sh
yay -S marmalade-tts
# or: paru -S marmalade-tts
```

The `packaging/aur/PKGBUILD` is in the repo and Arch users can build
from a clone (`makepkg -si`). Submission to the official AUR is on the
roadmap.

### Manual (git clone)

```sh
git clone https://github.com/maxwhipw/marmalade-tts
cd marmalade-tts
./install.sh
marmalade-tts init
```

---

## Installing engines

**marmalade-tts owns the engine install.** You don't `pip install` engines
yourself — `marmalade-tts init` and `marmalade-tts install <engine>` do it
hands-off: each engine gets its own [uv](https://docs.astral.sh/uv/)-managed
venv, its packages, any system dependencies (e.g. `espeak-ng`, installed via
your distro's package manager with an explicit sudo prompt), and its models.
Each engine is then **self-tested** — marmalade-tts synthesizes a phrase
through the exact code path the CLI uses and confirms a valid WAV comes out.

```sh
# init installs whatever engines you select in the wizard
marmalade-tts init

# install adds engines after the fact (init uses this same code path)
marmalade-tts install matcha emojivoice
marmalade-tts install kokoro --allow-sudo     # non-interactive sudo for system deps
marmalade-tts install piper --reinstall       # recreate the venv from scratch
```

Engine venvs live at `~/.local/share/<engine>-venv`. The manual,
under-the-hood steps are documented in `INSTALL.md` as a fallback — but
`init` / `install` is the supported path.

### Uninstalling

`marmalade-tts uninstall` is the mirror image of `install` — tiered,
interactive by default, and conservative about what it touches.

```sh
marmalade-tts uninstall              # interactive: pick a tier or engine
marmalade-tts uninstall kokoro       # one engine: venv + unit + sock/pid/log
marmalade-tts uninstall --engines    # every engine; keeps daemon dir + config
marmalade-tts uninstall --purge      # everything CLI-managed
marmalade-tts uninstall --purge --dry-run   # see the plan first; touches nothing
marmalade-tts uninstall kokoro -y    # skip the y/N prompt
```

What it does **NOT** delete:

- **The CLI itself.** `~/.local/bin/marmalade-tts` and the Python package
  are never removed. At the end of `--purge` we print the install-method
  command for that (`pipx uninstall`, `sudo apt remove`, etc).
- **The HuggingFace cache** (`~/.cache/huggingface/hub/`) — shared with
  other tools. Clean manually with `huggingface-cli scan-cache` if you
  want kitten/kokoro/pocket weights gone.
- **User voice files outside marmalade's dirs.** If you've pointed
  `engines.pocket.voice` at `~/recordings/me.wav`, that file is left
  alone.

Safety: deletes are gated by a path whitelist, symlinks are refused,
each directory is verified by a marker file (e.g. `pyvenv.cfg`) before
removal, and the command exits non-zero if any path fails.

---

## Engines

| Engine | What it is | Daemon mode |
|--------|-----------|-------------|
| **kitten** | Fast lightweight neural TTS (default) | ✔ enabled by default |
| **kokoro** | High-quality multilingual neural TTS | optional |
| **piper** | Offline neural TTS, many voices | optional |
| **coqui** | Open-source neural TTS toolkit | optional |
| **pocket** | CPU-only 100M-param TTS with voice cloning | n/a (loads in ~200 ms) |
| **matcha** | Fast flow-matching neural TTS, clear English | optional |
| **emojivoice** | Emoji-controlled expressive TTS — 🤣😭😡 in the text set the emotion | optional |
| **api** | Hosted OpenAI-compatible TTS (Venice by default) — needs an API key + network | n/a (nothing to keep warm) |

Install the engines you want with `marmalade-tts install <engine>` (or pick
them in `marmalade-tts init`) — marmalade-tts works with whichever are
present. There's no need to install all of them; even just one is enough to
be useful.

For the full per-engine parameter reference (every voice, speed, and
expressivity knob, plus what each Coqui model honors), see
**[docs/engine-knobs.md](docs/engine-knobs.md)**.

---

## Quick Start

```sh
# Interactive setup (arrow keys to pick engines, voices, model sizes)
marmalade-tts init

# Non-interactive setup (for AI agents / scripts)
marmalade-tts init --non-interactive --engines kitten,piper
marmalade-tts init --non-interactive --engines kitten --set kitten.model_size=nano
marmalade-tts init --non-interactive --engines kitten,kokoro \
  --set kokoro.voice=am_adam --default-engine kokoro --test

# Speak with the default engine
marmalade-tts "Hello world"

# Specify an engine
marmalade-tts kokoro "Hello world"
marmalade-tts kitten "Hello world"

# Read from a file
marmalade-tts @script.txt

# Save to a file instead of playing
marmalade-tts "Hello" --out hello.wav

# Speed up or slow down
marmalade-tts "Hello" --speed 1.4

# Choose a voice (positional voice works for engines whose names look like
# identifiers — kitten, kokoro, pocket. Use --voice for path-shaped voices
# like piper's .onnx files and coqui's tts_models/... specs.)
marmalade-tts kokoro george "Hello"
marmalade-tts kitten Bella "Hello"
marmalade-tts piper --voice ~/voices/en_US-lessac-medium.onnx "Hello"
```

---

## Engines & Voices

### kokoro

```sh
marmalade-tts kokoro "Hello"
marmalade-tts kokoro george "Hello"               # British male, positional
marmalade-tts kokoro nicole "Hello"               # American female
marmalade-tts kokoro alpha "Hello" --lang a       # Japanese voice, English accent
marmalade-tts kokoro --list                       # show all voices
```

Voices are referred to by their **bare name** (e.g. `george`):

| Language | Voices |
|----------|--------|
| American English | `heart`, `bella`, `nicole`, `adam`, `michael` |
| British English  | `emma`, `isabella`, `george`, `lewis` |
| Japanese         | `alpha`, `gongitsune`, `kumo` |
| Mandarin         | `xiaobei`, `yunjian` |

Each voice has a *natural* language but kokoro can speak any voice in any
supported language — pass `--lang a/b/j/z` (or set `engines.kokoro.lang` in
config) to override. Useful for accent effects.

The canonical upstream form (`bm_george`, `af_heart`, etc.) is also
accepted everywhere for back-compat.

### kitten

```sh
marmalade-tts kitten "Hello"
marmalade-tts kitten Kiki "Hello from Kiki"       # specify voice inline
marmalade-tts kitten --list                        # show all voices
marmalade-tts kitten --fast "Quick response"       # nano model
marmalade-tts kitten --quality "Important message" # mini model
```

### piper

```sh
marmalade-tts piper "Hello"
marmalade-tts piper --voice ~/voices/en_US-lessac-medium.onnx "Hello"
marmalade-tts piper "Hello" --speaker 2           # multi-speaker models
```

### coqui

```sh
marmalade-tts coqui "Hello"
marmalade-tts coqui "Hello" --voice tts_models/en/ljspeech/tacotron2-DDC
marmalade-tts coqui --list
```

### pocket

```sh
marmalade-tts pocket "Hello"
marmalade-tts pocket alba "Hello from alba"
marmalade-tts pocket --list                       # show all built-in voices
marmalade-tts pocket my_recording.wav "Cloned!"   # voice cloning from any .wav
```

Built-in voices: `alba`, `marius`, `javert`, `jean`, `fantine`, `cosette`,
`eponine`, `azelma`.

For faster cloning, pre-export the speaker embedding to `.safetensors`:

```sh
pocket-tts export-voice friend.wav --out friend.safetensors
marmalade-tts pocket friend.safetensors "Hi!"
```

> **Note on voice cloning:** Pocket TTS can clone any voice from a short WAV
> sample. Only clone voices you have explicit, informed consent to clone.
> Cloning a real person's voice without permission — to deceive, impersonate,
> harass, or misrepresent them — is harmful and in many jurisdictions illegal.
> The built-in voices are fine for any use.

### matcha

```sh
marmalade-tts matcha "Fast flow-matching neural TTS"
marmalade-tts matcha "Multi-speaker model" --voice matcha_vctk --speaker 5
marmalade-tts matcha --list
```

Matcha-TTS is a fast flow-matching neural TTS. Two built-in models
auto-download on first use: `matcha_ljspeech` (single female speaker,
default) and `matcha_vctk` (multi-speaker — pick one with `--speaker N`,
0–107). A custom checkpoint path also works via `--voice`.
`marmalade-tts install matcha` sets it up — its own Python 3.11 venv and
`espeak-ng`.

### emojivoice

```sh
marmalade-tts emojivoice "I can't believe it 🤣"
marmalade-tts emojivoice "That's so sad 😭"
marmalade-tts emojivoice --list                  # show the emoji set
```

EmojiVoice is an expressive TTS where an **emoji in the text selects the
emotional speaking style** — `🤣` reads amused, `😭` reads sad, `😡` reads
angry, and so on. The emoji can sit anywhere in the text; it sets the
tone and is stripped before synthesis (it is not spoken). Text with no
recognized emoji is read in a neutral style.

Built on Matcha-TTS, in its own Python 3.11 venv. `marmalade-tts install
emojivoice` sets everything up — the venv, `espeak-ng`, and the `paige`
speaker checkpoint.

### api

```sh
export VENICE_API_KEY=...                        # or set engines.api.api_key_env
marmalade-tts api "Hello from the cloud."
marmalade-tts api --voice bm_george "Hello."
marmalade-tts api --list                         # live model + voice list
```

The one engine that isn't local: an OpenAI-compatible `/audio/speech`
client. Defaults target [Venice](https://venice.ai) (models: `tts-kokoro`,
Qwen3-TTS, xAI, Inworld), but any provider with that endpoint shape works —
point `engines.api.base_url` at OpenAI, Groq, DeepInfra, … and set `model`,
`voice`, and `api_key_env` to match. Nothing to install or keep resident:
time-to-first-audio is the network round trip plus server-side synthesis,
which beats a cold local engine by a wide margin. Provider-specific request
fields pass through via `engines.api.extra`. Needs network and a funded
API key; keep a local engine configured as your offline fallback.

---

## Voice aliases / personas

Define named bundles in your config and invoke them positionally like an
engine name. Handy for recurring characters or styles:

```yaml
# ~/.config/marmalade-tts/config.yaml
aliases:
  narrator:
    engine: kokoro
    voice: george
    speed: 0.95
    effects: ["reverb=15"]
  villain:
    engine: emojivoice
    voice: paige
    effects: ["pitch=-200", "reverb=40"]
```

```sh
marmalade-tts narrator "Once upon a time"
marmalade-tts villain "You shall not pass"
marmalade-tts narrator "Now slower" --speed 0.7   # explicit flag wins
marmalade-tts --list-aliases                       # what's configured?
```

Precedence: explicit CLI flags > alias defaults > engine config defaults.
`--no-effects` still kills everything; `--effect` still replaces the
default effect list (including the alias's). Aliases that collide with
an engine name are ignored with a warning — engine names are reserved.

---

## Speed Presets

Choose a quality/speed tradeoff that picks the appropriate model variant:

```sh
marmalade-tts --fast "Hello"       # fastest, smallest model
marmalade-tts --balanced "Hello"   # balanced (default)
marmalade-tts --quality "Hello"    # best quality
```

---

## Text Preprocessing

marmalade-tts normalises text before synthesis so engines hear readable
English instead of symbols. This is **on by default** and tuned per-engine.

```sh
# These are handled automatically:
marmalade-tts "$42.50 is 15% off"
# → "forty-two dollars and fifty cents is fifteen percent off"

marmalade-tts "See https://example.com for details"
# → "See example dot com for details"

marmalade-tts "The 3rd place finisher at 9:30am"
# → "The third place finisher at nine thirty a m"

# Emojis are stripped by default for every engine except emojivoice — which
# consumes them itself to set the emotional style. Without this, espeak-backed
# engines verbalize them as "loudly crying face", "rolling on the floor
# laughing", etc.
marmalade-tts kokoro "I miss you 😭"
# → "I miss you"   (the emoji is dropped)
marmalade-tts emojivoice "I miss you 😭"
# → "I miss you"   (read with the sad style; the engine handles the emoji)

# Turn it off if you've already formatted your text:
marmalade-tts --no-preprocessing "forty two dollars"

# See all available preprocessing rules:
marmalade-tts --list-rules
```

### Per-engine preprocessing config

You can set per-engine rule lists in `~/.config/marmalade-tts/config.yaml`:

```yaml
engines:
  kokoro:
    preprocessing: [currency, percentage, ordinal, time, url]
  piper:
    preprocessing: true    # all rules (default)
  kitten:
    preprocessing: false   # disable entirely
```

---

## Audio Effects

Effects are applied after synthesis using [sox](https://sox.sourceforge.net/).
If sox is not installed, effects are silently skipped with a note — the speech
is still generated.

```sh
# Install sox (required for effects):
apt install sox          # Debian/Ubuntu
brew install sox         # macOS

# Apply a single effect
marmalade-tts "Hello" --effect reverb=50
marmalade-tts "Hello" --effect pitch=200    # shift up 2 semitones
marmalade-tts "Hello" --effect pitch=-300   # shift down 3 semitones

# Chain multiple effects
marmalade-tts "Hello" --effect pitch=200 --effect reverb=30

# Use a built-in preset
marmalade-tts "Hello" --effect robot
marmalade-tts "Hello" --effect cave
marmalade-tts "Hello" --effect telephone

# See all effects and presets
marmalade-tts --list-effects
```

### Built-in effect presets

| Preset | Effects applied |
|--------|----------------|
| `robot` | overdrive + pitch shift + reverb |
| `cave` | heavy reverb + echo |
| `chipmunk` | pitch up + slightly faster |
| `deep` | pitch down + bass boost |
| `telephone` | bandpass filter + overdrive |
| `stadium` | heavy reverb + echo |
| `megaphone` | bandpass + heavy overdrive + volume boost |
| `broadcaster` | radio-DJ polish — low cut, mud cut, compression, presence |
| `podcast` | warm, intimate — low cut, warmth, gentle compression |
| `trailer` | deep cinematic VO — pitch down, compression, controlled reverb |
| `audiobook` | even narration — low cut, compression, clarity, hint of room |
| `walkie_talkie` | handheld radio — tight band, drive, hard squash |
| `vintage_radio` | old AM radio — HP/LP 400-4kHz band, +12 dB mid honk at 1 kHz, tube saturation, leveling compression, subtle AM throb, cabinet reverb |
| `intercom` | PA / intercom — midrange horn, heavy drive, room slap |
| `underwater` | submerged — dark low-pass, chorus, pitch + wobble |
| `alien` | otherworldly — pitch up, phaser + flanger, big space |
| `ethereal` | ethereal haunt — thin lows, pitch shimmer, long reverb |
| `dragon` | monster — chest, growl, grit, doubled chorus, cavern reverb |
| `cyborg` | Dalek/cyborg — ring mod through a telephone band + grit |
| `eight_bit` | 8-bit retro game voice — heavy crush + makeup |
| `glitch` | glitchy lo-fi transmission — crush + ring shimmer through a radio band |

`cyborg`, `eight_bit`, and `glitch` mirror the built-in effects in the
[marmalade-tts-android](https://github.com/maxwhipw/marmalade-tts-android) app.

### Available effects

| Effect | Parameter | Example |
|--------|-----------|---------|
| `reverb` | amount 0–100 (default 50) | `reverb=30` |
| `pitch` | cents (100 = 1 semitone) | `pitch=200` or `pitch=-400` |
| `tempo` | speed factor, no pitch change | `tempo=0.8` |
| `echo` | gain-in:gain-out:delay-ms:decay | `echo=0.8:0.88:60:0.4` |
| `overdrive` | gain 1–100 | `overdrive=20` |
| `flanger` | (none) | `flanger` |
| `chorus` | (none, or 6-part custom) | `chorus` |
| `treble` | dB boost/cut | `treble=6` |
| `bass` | dB boost/cut | `bass=4` |
| `bandpass` | low-hz:high-hz | `bandpass=300:3400` |
| `speed` | factor (pitch shifts too) | `speed=1.2` |
| `vol` | volume multiplier | `vol=2.0` |
| `normalize` | (none) | `normalize` |
| `fade` | in-seconds:out-seconds | `fade=0.1:0.5` |
| `lowpass` | cutoff Hz (default 3000) | `lowpass=4000` |
| `highpass` | cutoff Hz (default 300) | `highpass=400` |
| `mid` | freq:gain (peaking EQ) | `mid=1000:6` |
| `tremolo` | speed:depth (depth 0-1) | `tremolo=5:0.5` |
| `phaser` | speed:decay | `phaser=0.5:0.4` |
| `compressor` | threshold_dB:ratio | `compressor=-20:4` |
| `ringmod` | freq:mix (mix 0-1, Dalek/cyborg timbre) | `ringmod=60:0.7` |
| `bitcrush` | bits:factor (lo-fi crush) | `bitcrush=6:6` |

### Default effects per engine

You can set default effects that apply automatically for a given engine, without
needing `--effect` every time. CLI `--effect` flags override the engine default
entirely.

```yaml
# ~/.config/marmalade-tts/config.yaml
effects:
  defaults:
    kitten: ["reverb=20"]       # subtle warmth on kitten by default
    kokoro: []                  # no default effects (explicit empty = off)
    piper:  []
    coqui:  []

  # Define your own named presets:
  presets:
    warm:      ["reverb=25", "bass=3"]
    dramatic:  ["reverb=70", "echo=0.8:0.6:80:0.3"]
    broadcast: ["bandpass=80:15000", "normalize"]
```

---

## Daemon Mode

Daemon mode keeps the engine model loaded in RAM so the first synthesis
request is instant instead of waiting for model load.

```sh
# Start / stop individual daemons
marmalade-tts daemon start --engine kitten
marmalade-tts daemon stop --engine kitten

# Start all configured daemons
marmalade-tts daemon start-all

# Check what's running
marmalade-tts daemon status
```

Enable daemon mode per-engine in config:

```yaml
engines:
  kitten:
    daemon: true    # start automatically on first use
  kokoro:
    daemon: false
```

Or use systemd to keep the daemon alive across reboots:

```sh
systemctl --user enable marmalade-kitten
systemctl --user start  marmalade-kitten
```

A daemon loads **one** model at startup, derived from your config at the
moment it starts (e.g. kitten's `model_size`, kokoro's `lang`, matcha's
`model`). If you change that config after the daemon is already running,
it keeps serving the old model — it does **not** hot-reload. A request
that doesn't match what's loaded is refused with a restart hint rather
than silently synthesized with the wrong model:

```sh
marmalade-tts daemon stop --engine kitten   # it auto-starts again on next use
```

---

## Configuration

### `marmalade-tts init`

The setup wizard configures engines, voices, and defaults — **and installs
the selected engines** (venvs, packages, system deps, models) and
self-tests each one. Run it again at any time to change your setup.

**Interactive mode** (default when stdin is a TTY):
```sh
marmalade-tts init
```
Uses arrow keys + space to multi-select engines, then walks through per-engine
options (model size, voice, etc.).

**Non-interactive mode** (for AI agents, scripts, CI):
```sh
marmalade-tts init --non-interactive --engines kitten,piper
marmalade-tts init --non-interactive --engines kitten --set kitten.model_size=nano
marmalade-tts init --non-interactive --engines kitten,kokoro \
  --set kokoro.voice=am_adam --default-engine kokoro --test
```

Flags:
- `--non-interactive` — skip TUI prompts (auto-enabled when stdin is not a TTY)
- `--engines LIST` — comma-separated engines to enable
- `--set ENGINE.KEY=VALUE` — override engine options (repeatable)
- `--default-engine NAME` — set the default engine
- `--test` — play a test synthesis through the default engine after setup
- `--allow-sudo` — permit system-package installs via sudo in non-interactive
  mode (interactive init always prompts before any sudo command)
- `--reinstall` — recreate engine venvs even if they already exist
- `--skip-selftest` — skip the post-install synthesis self-test

### `marmalade-tts install`

Adds engines after `init`, using the exact same installer code path. Each
engine gets its own venv, packages, system deps, and models, then a
self-test.

```sh
marmalade-tts install matcha                  # one engine
marmalade-tts install kokoro piper coqui       # several at once
marmalade-tts install emojivoice --allow-sudo  # non-interactive sudo for system deps
marmalade-tts install kitten --reinstall       # recreate the venv
marmalade-tts install matcha --skip-selftest   # skip the post-install self-test
```

Exits non-zero if any engine fails to install or fails its self-test, so
scripts and CI can detect a bad install.

### Manual config

Config is stored at `~/.config/marmalade-tts/config.yaml`.
A default config is written on first run.

```sh
# View current config
marmalade-tts config show

# Get a value
marmalade-tts config get defaults.engine

# Set a value
marmalade-tts config set defaults.engine kitten
marmalade-tts config set defaults.speed 1.2
marmalade-tts config set defaults.play false
```

**Value coercion rules** (predictable so AI agents don't get surprised):

- `true` / `false` (any case) → bool
- `null` / `~` / empty → None
- Integer-looking strings → int
- Float-looking strings → float
- Everything else → string, verbatim

`yes` / `no` / `on` / `off` are **kept as strings**, not coerced to bools.
This is intentional — YAML 1.1's "Norway problem" silently turning the
word "yes" into a boolean is a common footgun.

### Full config reference

```yaml
defaults:
  engine: kitten        # default engine when none is specified
  device: cpu           # cpu or cuda
  speed: 1.0            # speech speed multiplier
  play: true            # play audio automatically (false = save only)
  preprocessing: true   # normalize text before synthesis

presets:
  fast:
    kitten: nano
    kokoro: heart
    piper: en_US-lessac-medium
    coqui: tts_models/en/ljspeech/tacotron2-DDC
    pocket: alba
  balanced:
    # ...same structure...
  quality:
    # ...same structure...

engines:
  kokoro:
    device: cpu
    voice: heart        # bare name (or canonical "af_heart" for back-compat)
    # lang: a           # optional — defaults to the voice's natural language
    daemon: false
    # preprocessing: [currency, percentage]   # or true / false

  kitten:
    device: cpu
    model_size: micro   # nano / micro / mini
    voice: Kiki
    daemon: true

  piper:
    device: cpu
    model: ~/.local/share/piper/voices/en_US-lessac-medium.onnx
    daemon: false

  coqui:
    device: cpu
    model: tts_models/en/ljspeech/tacotron2-DDC
    daemon: false

  pocket:
    device: cpu
    voice: alba         # built-in voice, or path to .wav / .safetensors
    # No daemon needed — Pocket TTS loads fast (~200ms)

  matcha:
    device: cpu
    model: matcha_ljspeech   # matcha_vctk, or a .ckpt path
    daemon: false            # true keeps the model in RAM (recommended)

  emojivoice:
    device: cpu
    voice: paige             # EmojiVoice speaker checkpoint
    daemon: false            # true keeps the model in RAM (recommended)

effects:
  defaults:
    kitten: []
    kokoro: []
    piper:  []
    coqui:  []
  presets:
    warm: ["reverb=25", "bass=3"]
```

---

## Shell Completion

```sh
# bash
eval "$(marmalade-tts --completion bash)"

# zsh
eval "$(marmalade-tts --completion zsh)"

# Or add to your shell rc:
echo 'eval "$(marmalade-tts --completion bash)"' >> ~/.bashrc
```

---

## KDE Global Hotkeys (speak selected text)

The `scripts/` directory contains ready-to-use helpers for binding speech
to keyboard shortcuts in KDE.

Install the scripts:

```sh
cp scripts/speak-selection scripts/speak-clipboard scripts/marmalade-pipe ~/.local/bin/
chmod +x ~/.local/bin/speak-selection ~/.local/bin/speak-clipboard ~/.local/bin/marmalade-pipe
```

Dependencies (pick one per display server):

```sh
sudo apt install xclip          # X11
sudo apt install wl-clipboard   # Wayland
```

Bind in KDE:
1. **System Settings → Shortcuts → Custom Shortcuts**
2. New → Script/Command
3. Set the trigger (e.g. `Meta+Shift+S`) and the action path

| Script | What it speaks | Suggested shortcut |
|--------|---------------|--------------------|
| `speak-selection` | Highlighted text (primary selection) | `Meta+Shift+S` |
| `speak-clipboard` | Last copied text (Ctrl+C) | `Meta+Shift+C` |

See `scripts/SCRIPTS.md` for full details.

---

## Scripting & Agent Use

marmalade-tts is designed to be used from scripts, agents, and pipelines.

```sh
# Read from stdin
echo "Hello world" | marmalade-tts --stdin --no-play --out hello.wav
echo "Hello world" | marmalade-pipe --out hello.wav   # convenience wrapper

# Suppress all status output (exit code only)
marmalade-tts --quiet "Hello"

# Print only the output WAV path to stdout
WAV=$(marmalade-tts --print-path --no-play "Hello")
aplay "$WAV"

# JSON result for structured consumption
marmalade-tts --json --no-play "Hello"
# → {"ok": true, "version": "0.5.0", "engine": "kitten", "voice": "Kiki",
#    "out": "/tmp/...", "effects": [], "text": "Hello", "duration": 0.84}

# Never play back, just generate
marmalade-tts --no-play --out result.wav "Generate but don't play"

# Skip engine-default effects from config (e.g. for a dry signal)
marmalade-tts --no-effects "Hello"

# Combine flags for maximum scriptability
cat script.txt | marmalade-tts --stdin --quiet --json --no-play --out speech.wav
```

Exit codes:
- `0` — success
- non-zero — failure. Specific codes are not promised; expect `1` for
  user-visible errors and `2` from argparse for bad flags.

### MCP server (for AI agents)

marmalade-tts also ships a [Model Context Protocol](https://modelcontextprotocol.io/)
server so AI agents can drive it directly:

```sh
pip install marmalade-tts[mcp]
claude mcp add marmalade-tts -- marmalade-tts mcp
```

Three tools: `synthesize`, `list_voices`, and `find_voice` (free-text
voice search — "warm British male" → `george`). Full setup and tool
reference in [docs/mcp.md](docs/mcp.md).

---

## Text Input Methods

```sh
# Literal text
marmalade-tts "Hello world"

# From a file (@ prefix)
marmalade-tts @speech.txt

# From stdin
echo "Hello world" | marmalade-tts -

# Combine with --out to save a file
marmalade-tts @script.txt --out script.wav
```

## Batch synthesis

By default, a multi-line input (from `@file.txt`, `--stdin`, or
`--text "a\nb"`) goes to a **single** synthesis call — the line breaks
are part of the text, and you get one WAV out. Long inputs are split
internally on sentence boundaries and recombined transparently — see
[Chunking](#chunking-long-inputs) below.

Pass **`--batch`** to opt into per-line splitting: one WAV per non-empty
line, played in sequence (or written via `--out PATTERN` / `--out-dir`).

```sh
# Single WAV — the default. Newlines stay in the text.
marmalade-tts kokoro @chapters.txt

# Narrate chapters.txt line-by-line — opt in with --batch
marmalade-tts kokoro --batch @chapters.txt

# Write one WAV per line into ./out/ (auto-named 001.wav, 002.wav, …)
marmalade-tts kokoro --batch @chapters.txt --out-dir ./out/

# Use a printf pattern instead — chapter-001.wav, chapter-002.wav, …
marmalade-tts kokoro --batch @chapters.txt --out 'chapter-%03d.wav'

# JSON output is an array in batch (one object per utterance)
marmalade-tts kokoro --batch @chapters.txt --no-play --json --out-dir ./out/
```

Blank lines are skipped in batch mode. **The trigger is explicit** — the
old behavior (multi-line input implicitly batches) surprised AI agents
sending paragraph-broken files, so you now have to ask for batch with
the flag.

**Playback is streaming.** When a batch is being played, line N starts
playing as soon as it has finished rendering, while line N+1 is still
being synthesized in the background. The first line plays almost
immediately and the rest stream behind it — big UX win for audiobook
and long-form workflows. Playback order always matches input order;
subtitle (`--srt` / `--vtt`) and `--json` output still describe the
full batch once every line is done.

### Chunking (long inputs)

When a single input exceeds the engine's character limit, marmalade-tts
splits it on sentence boundaries, synthesizes each chunk, and
concatenates the WAVs into a single output — the user-facing contract
is always "one input → one WAV". Limits are conservative defaults; if
you've got an engine that handles long text well (piper does), bump it:

```yaml
# ~/.config/marmalade-tts/config.yaml
engines:
  kokoro:
    max_chars: 800    # raise the chunking threshold
  piper:
    max_chars: null   # disable chunking entirely (piper handles long text)
```

Chunks are joined byte-for-byte at sentence boundaries, so on a very
long input you may notice a brief seam at each join. If you have a
single uninterrupted take that can't tolerate seams, set the engine's
`max_chars: null` to disable chunking and let the engine handle the
full length — usually fine on piper, your-mileage-may-vary on the
smaller neural engines.

Chunking is **not** batch — there's still one output WAV per user input.
Use `--batch` if you want line-by-line splitting instead.

### Subtitles (SRT / WebVTT)

Get a synchronized subtitle file alongside the generated WAV(s) with
`--srt PATH` or `--vtt PATH` (or both). One cue per utterance; cue text
is the **original input** (emoji and markdown the user typed appear
readable in the subtitle, even though they're stripped before synthesis).

```sh
# One WAV per chapter + a single .srt that maps onto them in order
marmalade-tts kokoro --batch @chapters.txt --out-dir ./out/ --srt out/chapters.srt

# WebVTT for the web
marmalade-tts kokoro --batch @chapters.txt --out-dir ./out/ --vtt out/chapters.vtt

# Single utterance also works — one-cue file
marmalade-tts kokoro "Hello world" --no-play --out hello.wav --srt hello.srt
```

Cue timing is measured from each WAV's actual duration (after any sox
effects are applied) with a 50 ms gap between consecutive cues. `--json`
output also gains a `"duration"` field per utterance.

---

## Requirements

- **OS:** Linux (primary target, tested on Ubuntu 24.04). macOS untested but
  most engines (`piper`, `kokoro`, `pocket`, `coqui`) should work. Windows is
  not supported.
- **Python:** 3.10 or newer for the CLI. The engine installer uses
  [uv](https://docs.astral.sh/uv/) to provision per-engine venvs — including
  Python 3.11 for `matcha` / `emojivoice`, which don't build on 3.12.
- **[uv](https://docs.astral.sh/uv/):** required for installing engines.
  `pipx install marmalade-tts` pulls it in; otherwise:
  `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **CPU-only by default.** All engines run on CPU; no GPU needed. Optional
  CUDA acceleration for kokoro/coqui on supported NVIDIA cards.
- **RAM:** ~200 MB for kitten/pocket, ~1.5 GB for kokoro daemon, varies for
  coqui depending on model.
- **Disk (models, downloaded on first use):**
  - Kitten: 23–80 MB (nano/micro/mini)
  - Piper voices: 15–75 MB each
  - Pocket: ~200 MB
  - Kokoro: ~500 MB
  - Coqui: 200 MB – 2 GB depending on model
- **Audio playback:** one of `paplay`, `aplay`, or `ffplay` (already present
  on most Linux desktops).
- **Optional:** `sox` for audio effects, `xclip` / `wl-clipboard` for the
  KDE selection scripts.

The CLI wrapper itself (`pipx install marmalade-tts`) is tiny — engines live
in their own venvs to keep their dependencies isolated. `marmalade-tts init`
walks you through installing whichever engines you want.

---

## Contributing

Want to add a new TTS engine? See **[ENGINE-GUIDE.md](ENGINE-GUIDE.md)** for a
step-by-step walkthrough of every file that needs to be touched.

Engines are first-class citizens in this repo. There is no plugin /
entry-point mechanism for external engines — adding an engine is a PR,
not a third-party install. Each engine addition is treated as a feature
and ships in the next minor version bump.

---

## Stability & versioning

marmalade-tts is currently in **beta** (`0.5.x`). The CLI surface,
config schema, and JSON output are usable today and the project tries
hard not to break working commands, but small changes between minor
versions are still possible until **v1.0.0**.

**At `v1.0.0` the documented CLI surface is _locked_.** "Locked" means a
hard guarantee: the flags, subcommands, config keys, and JSON output
documented in this README will not change in a breaking way except in a
**major version release** (`x.0.0`). From `1.0.0` onward this project
follows [Semantic Versioning](https://semver.org/):

- **Patch** (`1.0.x`) — bug fixes only, no surface changes.
- **Minor** (`1.x.0`) — new engines, new flags, new config keys. Always
  backwards compatible — existing commands keep working unchanged.
- **Major** (`x.0.0`) — the _only_ release type permitted to break the
  locked surface. Breaking changes are called out explicitly in the
  changelog. The project aims to make these rare.

If you're scripting against marmalade-tts, the surfaces documented in
this README are what's covered by the lock. Anything **not** documented
here (help-text wording, `--list*` output formatting, init wizard
prompts, internal subprocess invocation, daemon socket protocol) is not
part of the contract and may evolve in any release.

---

## Roadmap

Ideas under consideration. No promises on timing — feedback and PRs welcome.

### Language detection

Auto-detect the input text's language and route to an appropriate
engine / voice / model — e.g. Japanese text routes to a kokoro Japanese
voice, Mandarin to a kokoro Mandarin voice, the rest stay on the
configured default. Per-language defaults configurable in `config.yaml`.

### Emoji-driven emotional prosody

The **emojivoice** engine delivers the first cut of this: an emoji in
the text selects the emotional speaking style. Future directions —
a shared emoji→emotion layer that maps onto *any* expression-capable
engine, more EmojiVoice speakers, and a wider emoji vocabulary — are
tracked alongside FOSS expressive-TTS research.

### Cross-distro test matrix + CI

**TODO:** add automated cross-distro install/test CI, mirroring the tiered
setup built for the sibling **marmalade-stt-cli** (`scripts/test-matrix.sh` +
a GitHub Actions / Forgejo workflow). The unit suite already exists; what's
missing is verifying the package + its many optional engine deps install and
import cleanly on a matrix of distros (Debian/Ubuntu/Fedora) in fresh
containers, plus a `.deb`-install smoke job. Pattern to copy:
`~/coding/marmalade-stt-cli` — a `device=`-style DI seam for anything that
needs hardware (here: audio output / the synth daemon), pytest markers to split
fast unit tests from slow engine/integration tests, and `docker run` per distro
in the matrix script so CI and local stay in sync. Engine-download tests should
cache models and run on a single distro; the broad matrix stays fast on the
unit tier.

---

## Credits & Acknowledgements

marmalade-tts is a unified wrapper — the real work is done by these engines:

- **[Piper](https://github.com/rhasspy/piper)** — ONNX neural TTS by Michael Hansen / Rhasspy (MIT)
- **[Kokoro](https://github.com/hexgrad/kokoro)** — high-quality multilingual TTS by Hexgrad (Apache 2.0)
- **[KittenTTS](https://github.com/KittenML/KittenTTS)** — fast lightweight neural TTS by KittenML (Apache 2.0)
- **[Coqui TTS](https://github.com/coqui-ai/TTS)** — open-source TTS toolkit by Coqui AI (MPL 2.0)
- **[Pocket TTS](https://github.com/kyutai-labs/pocket-tts)** — CPU-only 100M param TTS with voice cloning by Kyutai Labs (MIT)
- **[Matcha-TTS](https://github.com/shivammehta25/Matcha-TTS)** — fast flow-matching neural TTS by Shivam Mehta et al. (MIT)
- **[EmojiVoice](https://github.com/rosielab/emojivoice)** — emoji-controlled expressive TTS by Tuttösi et al., SFU Rosie Lab (MIT code; runs on Matcha-TTS)
- **[sox](https://sox.sourceforge.net/)** — audio effects processing (GPL)
- **[num2words](https://github.com/savoirfairelinux/num2words)** — number-to-words conversion (LGPL)
- **[espeak-ng](https://github.com/espeak-ng/espeak-ng)** — phonemizer backend for piper / matcha / emojivoice (GPL; invoked as a separate system package, not bundled)

The Docker HTTP API server implements endpoints compatible with the
[OpenAI TTS API](https://platform.openai.com/docs/api-reference/audio/createSpeech)
and [ElevenLabs TTS API](https://elevenlabs.io/docs/api-reference/text-to-speech)
interfaces. While we use their API interface for compatibility, no code from
either project is used — the server is written from scratch using Python's
standard library. This project is not affiliated with or endorsed by OpenAI or
ElevenLabs.

---

## License

MIT — see `LICENSE`.
