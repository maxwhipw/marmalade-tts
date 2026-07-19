# SPEC.md — marmalade-tts-cli Design Specification

## Overview

marmalade-tts is a unified CLI for local text-to-speech. It wraps multiple TTS
engines behind a single command with consistent flags, a shared YAML config, and
an optional persistent daemon for instant-response engines.

## Architecture

```
~/.local/bin/marmalade-tts          ← entrypoint (thin dispatcher)
~/.local/lib/marmalade-tts/         ← Python package
    __init__.py
    cli.py                          ← argparse, subcommands, tab completion
    cli_helpers.py                  ← output formatting (text/json/print-path), alias listing
    config.py                       ← YAML config load/save/set/get
    preprocessing.py                ← text normalization rules + per-engine profiles
    effects.py                      ← sox effect chain builder + built-in presets
    chunking.py                     ← sentence-boundary splitting for long inputs
    subs.py                         ← SRT/WebVTT cue generation
    engines/
        __init__.py                ← Engine base class, run_in_venv/sox_tempo helpers
        kitten.py                   ← Kitten engine (daemon client + subprocess fallback)
        kokoro.py                   ← Kokoro engine (daemon client + subprocess fallback)
        piper.py                    ← Piper engine (daemon client + subprocess fallback)
        coqui.py                    ← Coqui engine (daemon client + subprocess fallback)
        pocket.py                   ← Pocket TTS engine (subprocess into its own venv; no daemon)
        matcha.py                   ← Matcha-TTS engine (daemon client + subprocess fallback)
        emojivoice.py               ← EmojiVoice engine (daemon client + subprocess fallback)
        api.py                      ← API engine (OpenAI-compatible /audio/speech client; no venv)
    daemon.py                       ← Daemon management (start/stop/status, config→env derivation)
    playback.py                     ← WAV playback (paplay/aplay/ffplay)
    completion.py                   ← Shell tab-completion generation

~/.local/share/marmalade-tts/       ← runtime data
    daemon/                         ← standalone daemon scripts (one per daemon-capable engine)
        _common.py                  ← shared serve loop, request/response framing, check_loaded()
        kitten-daemon.py            ← runs in the kittentts venv
        kokoro-daemon.py            ← runs in the kokoro venv
        piper-daemon.py             ← runs in the piper venv
        coqui-daemon.py             ← runs in the coqui venv
        matcha-daemon.py            ← runs in the matcha-tts venv
        emojivoice-daemon.py        ← runs in the emojivoice venv
    <engine>.sock                   ← Unix socket per daemon (created by daemon)
    <engine>.pid                    ← daemon PID file
    <engine>.log                    ← daemon log

~/.config/marmalade-tts/
    config.yaml                     ← user configuration

~/.config/systemd/user/
    marmalade-<engine>.service      ← systemd user service per daemon-capable engine
```

**Engines:** `kitten`, `kokoro`, `piper`, `coqui`, `pocket`, `matcha`,
`emojivoice`, `api` — 8 total. All except `pocket` and `api` support daemon
mode (see `ENGINE_DAEMONS` in `daemon.py`); `pocket` loads fast enough
(~200ms) from its own venv via subprocess that a daemon isn't worth the
complexity, and `api` is a hosted OpenAI-compatible HTTP client (Venice by
default) with nothing to keep warm — no venv, no install step.

## CLI Interface

### Synthesis (primary command)

```
marmalade-tts [ENGINE] [VOICE] TEXT [OPTIONS]
```

- `ENGINE` — optional, one of: `kitten`, `kokoro`, `piper`, `coqui`, `pocket`,
  `matcha`, `emojivoice`, `api` (or a configured alias — see README "Voice
  aliases / personas")
  - If omitted, uses `defaults.engine` from config
- `VOICE` — optional positional override for voice/model, for engines whose
  voice identifiers look like plain names (kitten, kokoro, pocket, matcha,
  emojivoice). Path-shaped voices (piper's `.onnx` files, coqui's
  `tts_models/...` specs) need `--voice`.
  - Kitten: voice name (Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo)
  - Kokoro: bare voice name (george, heart, ...) or canonical form (af_heart, bm_george, ...)
  - Piper: path to .onnx model file (via `--voice`)
  - Coqui: model name (tts_models/en/...) (via `--voice`)
  - Pocket: built-in voice name, or a `.wav`/`.safetensors` path for cloning
  - API: provider voice IDs are model-dependent (open set) — use `--voice`
  - Matcha: model name (matcha_ljspeech, matcha_vctk) or a `.ckpt` path
  - EmojiVoice: speaker checkpoint name (paige)
- `TEXT` — literal string, `@filename` (read from file), or `-` (stdin)

Options:
- `--out FILE` — save WAV to file (default: play immediately via paplay/aplay)
- `--play` — force playback even when --out is set
- `--speed FLOAT` — speech speed multiplier (default: 1.0)
- `--voice NAME` — explicit voice override (alternative to positional)
- `--lang CODE` — language code (kokoro only: a/b/h/e/f/i/p/j/z)
- `--speaker ID` — speaker id (piper multi-speaker models; matcha_vctk 0-107)
- `--fast` — use fast preset (smallest/fastest models)
- `--balanced` — use balanced preset
- `--quality` — use quality preset (largest/best models)
- `--list` — list available voices/models for the engine
- `--batch` — opt into per-line synthesis for multi-line input (one WAV per
  non-empty line); without it, multi-line input is a single synthesis call
- `--out-dir DIR` — with `--batch`, write one auto-numbered WAV per line
- `--srt PATH` / `--vtt PATH` — write a synchronized subtitle file alongside
  the WAV(s)
- `--effect SPEC` — apply an audio effect or named preset (repeatable)
- `--no-effects` — skip engine-default effects from config
- `--preprocessing` / `--no-preprocessing` — toggle text normalization
- `--json` — structured JSON result instead of human-readable text
- `--print-path` — print only the output WAV path
- `--quiet` — suppress all status output
- `--stdin` — read text from stdin

### Config subcommand

```
marmalade-tts config show                      # print full YAML config
marmalade-tts config get <dotpath>             # get a single value
marmalade-tts config set <dotpath> <value>     # set a value (auto-creates parents)
```

Dot-path examples: `defaults.engine`, `engines.kitten.voice`, `presets.fast.kitten`

### Daemon subcommand

```
marmalade-tts daemon start [--engine ENGINE]   # start daemon (default: kitten)
marmalade-tts daemon stop [--engine ENGINE]    # stop daemon
marmalade-tts daemon start-all                 # start every daemon-capable engine with daemon: true
marmalade-tts daemon stop-all                  # stop all running daemons
marmalade-tts daemon status                    # show which daemons are running
```

Only engines with `daemon: true` in their config section will use the daemon path.
Kitten is `daemon: true` by default (model is small enough to keep in RAM ~50-80MB).
Other daemon-capable engines (kokoro, piper, coqui, matcha, emojivoice) default to
subprocess-per-call unless `daemon: true` is set. `pocket` has no daemon mode.

A daemon loads exactly one model, derived from config at start time (see
`_daemon_env()` in `daemon.py` — e.g. `KITTEN_MODEL` from
`engines.kitten.model_size`, `KOKORO_LANG` from `engines.kokoro.lang`).
Each daemon script validates every request against what it loaded
(`check_loaded()` in `daemon/_common.py`) and refuses — with a restart
hint — a request whose resolved model/voice doesn't match, rather than
silently synthesizing with the wrong model. Config changes made while a
daemon is running require `marmalade-tts daemon stop --engine X`; it
auto-starts again (with the new config) on next use.

### Tab Completion

```
eval "$(marmalade-tts --completion bash)"      # add to .bashrc
eval "$(marmalade-tts --completion zsh)"       # add to .zshrc
```

Completions cover: engine names, voice names (per-engine), subcommands, flags,
config dot-paths, and preset names.

## Configuration Schema

```yaml
defaults:
  engine: kitten          # default engine when none specified
  device: cpu             # global default: cpu | cuda | auto
  speed: 1.0              # global default speed
  play: true              # auto-play when no --out given
  preprocessing: true     # normalize text before synthesis (global toggle)

presets:
  fast:
    kitten: nano           # model_size for kitten
    kokoro: af_heart       # voice for kokoro
    piper: en_US-lessac-medium
    coqui: tts_models/en/ljspeech/tacotron2-DDC
    pocket: alba
    matcha: matcha_ljspeech
    emojivoice: paige
  balanced:
    # ...same structure, model_size: micro / alternate voices...
  quality:
    # ...same structure, model_size: mini / alternate voices...

engines:
  kitten:
    device: cpu
    model_size: micro      # nano | micro | mini
    voice: Kiki            # default voice
    daemon: true           # keep model in RAM via daemon
    # preprocessing: [currency, number, filename]   # override the default rule profile
    # max_chars: 500        # chunking threshold (see Chunking below)
    # voices: Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo
    # model repos:
    #   nano:  KittenML/kitten-tts-nano-0.8   (~23MB)
    #   micro: KittenML/kitten-tts-micro-0.8  (~41MB)
    #   mini:  KittenML/kitten-tts-mini-0.8   (~80MB)

  kokoro:
    device: cpu
    voice: heart            # bare name (canonical af_heart also accepted)
    lang: a                # a=US-EN, b=UK-EN, j=Japanese, z=Mandarin, etc.
    daemon: false
    # voices (American EN): heart, bella, nicole, adam, michael
    # voices (British EN):  emma, isabella, george, lewis
    # voices (Japanese):    alpha, gongitsune, kumo
    # voices (Mandarin):    xiaobei, yunjian

  piper:
    device: cpu
    model: ~/.local/share/piper/voices/en_US-lessac-medium.onnx
    daemon: false
    # noise_scale: 0.667    # timbre variation per utterance
    # noise_w_scale: 0.8    # per-phoneme duration variation

  coqui:
    device: cpu
    model: tts_models/en/ljspeech/tacotron2-DDC
    daemon: false
    # speaker / speaker_idx / language / speaker_wav / emotion — model-specific,
    # passed straight through to TTS.tts_to_file (see docs/engine-knobs.md)

  pocket:
    device: cpu           # CPU-only (pocket-tts has no GPU support)
    voice: alba            # built-in voice or path to .wav/.safetensors
    # No daemon mode — Pocket TTS loads fast (~200ms)

  matcha:
    device: cpu
    model: matcha_ljspeech   # matcha_vctk (multi-speaker, --speaker 0-107), or a .ckpt path
    daemon: false            # true keeps the model in RAM
    # steps: 50              # flow-matching ODE solver iterations (default 10)
    # temperature: 0.667     # sampling stochasticity

  emojivoice:
    device: cpu
    voice: paige             # EmojiVoice speaker checkpoint
    daemon: false            # true keeps the model in RAM
    # steps / temperature — same knobs as matcha (runs on Matcha-TTS)

  api:
    base_url: https://api.venice.ai/api/v1   # any OpenAI-compatible /audio/speech host
    model: tts-kokoro
    voice: af_heart
    api_key_env: VENICE_API_KEY   # env var holding the key (or inline api_key)
    # timeout: 120
    # extra: {}               # provider-specific payload passthrough

# Named bundles of engine + voice + speed + effects, invoked positionally
# like an engine name (see README "Voice aliases / personas").
aliases:
  narrator:
    engine: kokoro
    voice: george
    speed: 0.95
    effects: ["reverb=15"]

# Audio effects (requires sox). Presets combine EFFECTS entries; defaults
# apply automatically per engine unless overridden by --effect.
effects:
  defaults:
    kitten: []
    kokoro: []
    piper:  []
    coqui:  []
  presets:
    warm: ["reverb=25", "bass=3"]
```

## Engine Details

Every daemon-capable engine (kitten, kokoro, piper, coqui, matcha,
emojivoice) follows the same shape: the `Engine.synthesize()` implementation
is a **daemon client with subprocess fallback** — if `daemon: true` in
config it talks to the engine's persistent daemon over a Unix socket
(auto-starting it if not running), otherwise it shells out to the venv's
CLI/interpreter per call. `pocket` is subprocess-only; no daemon exists for
it.

### Daemon protocol (newline-delimited JSON over Unix socket)

```
→ {"text": "Hello", "voice": "Kiki", "speed": 1.0, "out": "/tmp/x.wav", "model": "micro"}
← {"ok": true, "out": "/tmp/x.wav"}
← {"ok": false, "error": "..."}
```

Each request carries the model/voice/lang identity the client's config
resolved to; the daemon (`daemon/_common.py: check_loaded()`) refuses a
request that doesn't match what it loaded at startup, returning
`{"ok": false, "error": "..."}` with a restart hint instead of silently
synthesizing with the wrong model.

Auto-start: if a daemon-enabled engine's socket isn't present,
`marmalade_tts/daemon.py: synthesize()` calls `start()`, which tries
`systemctl --user start marmalade-<engine>.service` first (if the unit
file is installed) and falls back to a detached `subprocess.Popen` of the
daemon script otherwise. `start()` waits up to **30s** for the socket to
appear. Once connected, a synthesis request has its own default timeout of
**120s** (`daemon.py: synthesize(..., timeout=120.0)`) — generous headroom
for slower engines (matcha/emojivoice on a big chunk) without the CLI
hanging forever if a daemon wedges.

### Kitten (daemon mode by default)

**Why a daemon?** KittenTTS loads torch + ONNX runtime + the model on every
call. Cold start is ~5s even from HF cache. The daemon loads once, then
synthesis is ~0.3s per request via Unix socket. `daemon: true` out of the
box in `config-default.yaml`.

### Kokoro

Daemon client with subprocess fallback. Subprocess path shells into the
`kokoro` CLI in the engine's own venv (`~/.local/share/kokoro-venv`). Must
set `CUDA_VISIBLE_DEVICES=""` when device=cpu. Also sets `HF_HUB_OFFLINE=1`
to avoid network hits after first cache. `daemon: false` by default (model
is ~1.4GB in RAM — opt in if the memory cost is worth the instant-response
tradeoff).

### Piper

Daemon client with subprocess fallback. Subprocess path shells into the
`piper` CLI in the engine's own venv (`~/.local/share/piper-venv`). Speed is
inverted (`--length-scale` = 1/speed). Always CPU (ONNX runtime).

### Coqui

Daemon client with subprocess fallback. Subprocess path shells into the
`tts` CLI in the engine's own venv (`~/.local/share/coqui-venv`). Must set
`CUDA_VISIBLE_DEVICES=""` when device=cpu.

### Matcha

Daemon client with subprocess fallback, in its own Python 3.11 venv
(`~/.local/share/matcha-tts-venv`) alongside `espeak-ng`. Flow-matching ODE
model — `steps` (default 10) trades speed for quality, `temperature`
(default 0.667) controls sampling stochasticity. Two built-in checkpoints
auto-download on first use: `matcha_ljspeech` (single speaker) and
`matcha_vctk` (multi-speaker, `--speaker 0-107`).

### EmojiVoice

Daemon client with subprocess fallback, in its own Python 3.11 venv
(`~/.local/share/emojivoice-venv`). Runs on Matcha-TTS, so shares its
`steps`/`temperature` knobs. An emoji in the input text selects the
emotional speaking style (parsed and stripped before synthesis); text
without a recognized emoji reads in a neutral style. Only the `paige`
speaker checkpoint ships today.

### Pocket

Subprocess-only (no daemon) call into the engine's own venv
(`~/.local/share/pocket-tts-venv`): the venv's Python runs a short inline
script that imports `pocket-tts`. This keeps pocket's heavy torch
dependency out of marmalade-tts's own environment. The model loads in
~200ms, so a persistent daemon isn't worth the complexity.

Voice options:
- Built-in names: `alba`, `marius`, `javert`, `jean`, `fantine`, `cosette`, `eponine`, `azelma`
- Voice cloning: pass a `.wav` file path — the model extracts speaker embeddings on the fly
- Faster cloning: export to `.safetensors` with `pocket-tts export-voice`

Model weight (~200MB) is auto-downloaded from HuggingFace on first use.

## Environment Considerations

- **GPU:** Older or unsupported CUDA GPUs may not be compatible with current torch.
  All engines default to CPU. The `device: cuda` option exists for systems with
  modern, compatible GPUs.
- **HuggingFace cache:** Models cached in `~/.cache/huggingface/hub/`. First run
  downloads; subsequent runs use cache. `HF_HUB_OFFLINE=1` prevents re-checking.
- **Python:** System Python 3.10+ for the CLI entrypoint (only needs PyYAML +
  num2words, no torch). Each engine lives in its own venv at
  `~/.local/share/<engine>-venv`, created by the installer via uv. matcha and
  emojivoice pin Python 3.11 (matcha-tts does not build on 3.12).

## File Ownership

- `~/.local/bin/marmalade-tts` — entrypoint script (executable, system python)
- `~/.local/lib/marmalade-tts/` — package code (no venv needed, stdlib + yaml)
- `~/.local/share/marmalade-tts/` — daemon scripts, sockets, pid files, logs (one set per daemon-capable engine)
- `~/.config/marmalade-tts/config.yaml` — user config
- `~/.config/systemd/user/marmalade-<engine>.service` — systemd unit per daemon-capable engine
