# 🍊 marmalade-tts

A unified command-line interface for local text-to-speech synthesis.
Supports multiple engines with a single consistent interface — daemon mode for
fast synthesis, per-engine text preprocessing, and optional audio effects via
[sox](https://sox.sourceforge.net/).

---

## Engines

| Engine | What it is | Daemon mode |
|--------|-----------|-------------|
| **kokoro** | High-quality neural TTS (default) | optional |
| **kitten** | Fast lightweight neural TTS | ✔ recommended |
| **piper** | Offline neural TTS, many voices | optional |
| **coqui** | Open-source neural TTS toolkit | optional |

Install the engines you want — marmalade-tts works with whichever are present.

---

## Installation

```sh
git clone http://george:3000/marmalade/marmalade-tts-cli
cd marmalade-tts-cli
./install.sh
```

Then follow `INSTALL.md` for per-engine setup.

---

## Quick Start

```sh
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
marmalade-tts kokoro "Hello" --voice bm_george   # British male
marmalade-tts kokoro "Hello" --voice af_sky       # American female
marmalade-tts kokoro --list                       # show all voices
```

Voice names follow the pattern `<lang><gender>_<name>`:
- `a` = American English, `b` = British English
- `f` = female, `m` = male
- Examples: `af_heart`, `am_fenrir`, `bf_emma`, `bm_george`

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
  balanced:
    # ...same structure...
  quality:
    # ...same structure...

engines:
  kokoro:
    device: cpu
    voice: af_heart
    lang: a             # a=American, b=British, h=Hindi, etc.
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

- Python 3.10+
- At least one supported TTS engine installed (see `INSTALL.md`)
- `sox` — optional, required only for audio effects

---

## License

MIT — see `LICENSE`.
