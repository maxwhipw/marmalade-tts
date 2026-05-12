# 🍊 marmalade-tts

<p align="center">
  <img src="assets/mascot.png" alt="marmalade-tts mascot" width="220">
</p>

A unified command-line interface for local text-to-speech synthesis.
Supports multiple engines with a single consistent interface — daemon mode for
fast synthesis, per-engine text preprocessing, and optional audio effects via
[sox](https://sox.sourceforge.net/).

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

### pipx (recommended for most users)

```sh
pipx install marmalade-tts
marmalade-tts init
```

> **Note:** PyPI publishing is pending. Until then, use the git-clone path
> below or the `.deb`/`.rpm` from the releases page.

### deb / rpm (system-wide install)

Download the latest `.deb` or `.rpm` from the [GitHub releases page](https://github.com/maxwhipw/marmalade-tts/releases), then:

```sh
# Debian/Ubuntu
sudo dpkg -i marmalade-tts_0.4.3_amd64.deb

# Fedora/RHEL
sudo rpm -i marmalade-tts-0.4.3-1.x86_64.rpm
```

### AUR (Arch Linux)

```sh
yay -S marmalade-tts
# or: paru -S marmalade-tts
```

### Manual (git clone)

```sh
git clone https://github.com/maxwhipw/marmalade-tts
cd marmalade-tts
./install.sh
marmalade-tts init
```

See `INSTALL.md` for per-engine dependencies (pip packages, models).

---

## Engines

| Engine | What it is | Daemon mode |
|--------|-----------|-------------|
| **kitten** | Fast lightweight neural TTS (default) | ✔ recommended |
| **kokoro** | High-quality multilingual neural TTS | optional |
| **piper** | Offline neural TTS, many voices | optional |
| **coqui** | Open-source neural TTS toolkit | optional |
| **pocket** | CPU-only 100M-param TTS with voice cloning | n/a (loads in ~200 ms) |

Install the engines you want — marmalade-tts works with whichever are present.
(There's no need to install all five — even just one engine is enough to be useful.)

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

# Choose a voice
marmalade-tts kokoro "Hello" --voice bm_george
marmalade-tts kitten "Hello" --voice Bella
```

---

## Engines & Voices

### kokoro

```sh
marmalade-tts kokoro "Hello"
marmalade-tts kokoro "Hello" --voice bm_george    # British male
marmalade-tts kokoro "Hello" --voice af_nicole    # American female
marmalade-tts kokoro --list                       # show all voices
```

Voice names follow the pattern `<lang><gender>_<name>`:
- `a` = American English, `b` = British English, `j` = Japanese, `z` = Mandarin
- `f` = female, `m` = male
- Examples: `af_heart`, `am_adam`, `bf_emma`, `bm_george`

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
    preprocessing: [currency, percent, ordinal, time, url]
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
| `robot` | overdrive + deep pitch shift + reverb |
| `cave` | heavy reverb + echo |
| `chipmunk` | pitch up + slightly faster |
| `deep` | pitch down + bass boost |
| `telephone` | bandpass filter + overdrive |
| `whisper` | quieter + treble boost + reverb |
| `stadium` | heavy reverb + echo |
| `megaphone` | bandpass + heavy overdrive + volume boost |
| `slow_deep` | pitch down + slower tempo |
| `fast_high` | pitch up + faster tempo |

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

---

## Configuration

### `marmalade-tts init`

The setup wizard configures engines, voices, and defaults.
Run it again at any time to change your setup.

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
- `--test` — run a test synthesis after setup

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

### Full config reference

```yaml
defaults:
  engine: kokoro        # default engine when none is specified
  device: cpu           # cpu or cuda
  speed: 1.0            # speech speed multiplier
  play: true            # play audio automatically (false = save only)
  preprocessing: true   # normalize text before synthesis

presets:
  fast:
    kitten: nano
    kokoro: af_heart
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
    voice: af_heart
    lang: a             # a=American, b=British, j=Japanese, z=Mandarin
    daemon: false
    # preprocessing: [currency, percent]   # or true / false

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
# → {"ok": true, "engine": "kokoro", "voice": "af_heart", "out": "/tmp/...", "text": "Hello", "effects": []}

# Never play back, just generate
marmalade-tts --no-play --out result.wav "Generate but don't play"

# Combine flags for maximum scriptability
cat script.txt | marmalade-tts --stdin --quiet --json --no-play --out speech.wav
```

Exit codes:
- `0` — synthesis succeeded
- `1` — error (bad args, engine failure, missing text, etc.)

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

---

## Requirements

- **OS:** Linux (primary target, tested on Ubuntu 24.04). macOS untested but
  most engines (`piper`, `kokoro`, `pocket`, `coqui`) should work. Windows is
  not supported.
- **Python:** 3.10 or newer.
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

---

## Credits & Acknowledgements

marmalade-tts is a unified wrapper — the real work is done by these engines:

- **[Piper](https://github.com/rhasspy/piper)** — ONNX neural TTS by Michael Hansen / Rhasspy (MIT)
- **[Kokoro](https://github.com/hexgrad/kokoro)** — high-quality multilingual TTS by Hexgrad (Apache 2.0)
- **[KittenTTS](https://github.com/KittenML/KittenTTS)** — fast lightweight neural TTS by KittenML (Apache 2.0)
- **[Coqui TTS](https://github.com/coqui-ai/TTS)** — open-source TTS toolkit by Coqui AI (MPL 2.0)
- **[Pocket TTS](https://github.com/kyutai-labs/pocket-tts)** — CPU-only 100M param TTS with voice cloning by Kyutai Labs (MIT)
- **[sox](https://sox.sourceforge.net/)** — audio effects processing (GPL)
- **[num2words](https://github.com/savoirfairelinux/num2words)** — number-to-words conversion (LGPL)

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
