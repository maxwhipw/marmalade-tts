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
    config.py                       ← YAML config load/save/set/get
    engines/
        __init__.py
        base.py                     ← Engine base class
        kitten.py                   ← Kitten engine (daemon client + fallback)
        kokoro.py                   ← Kokoro engine (subprocess)
        piper.py                    ← Piper engine (subprocess)
        coqui.py                    ← Coqui engine (subprocess)
    daemon.py                       ← Daemon management (start/stop/status)
    playback.py                     ← WAV playback (paplay/aplay/ffplay)
    completion.py                   ← Shell tab-completion generation

~/.local/share/marmalade-tts/       ← runtime data
    kitten-daemon.py                ← standalone daemon script (runs in kittentts venv)
    kitten.sock                     ← Unix socket (created by daemon)
    kitten.pid                      ← daemon PID file
    kitten.log                      ← daemon log

~/.config/marmalade-tts/
    config.yaml                     ← user configuration

~/.config/systemd/user/
    marmalade-kitten.service        ← systemd user service for kitten daemon
```

## CLI Interface

### Synthesis (primary command)

```
marmalade-tts [ENGINE] [VOICE] TEXT [OPTIONS]
```

- `ENGINE` — optional, one of: `kitten`, `kokoro`, `piper`, `coqui`
  - If omitted, uses `defaults.engine` from config
- `VOICE` — optional positional override for voice/model
  - Kitten: voice name (Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo)
  - Kokoro: voice id (af_heart, af_bella, am_adam, bf_emma, etc.)
  - Piper: path to .onnx model file
  - Coqui: model name (tts_models/en/...)
- `TEXT` — literal string, `@filename` (read from file), or `-` (stdin)

Options:
- `--out FILE` — save WAV to file (default: play immediately via paplay/aplay)
- `--play` — force playback even when --out is set
- `--speed FLOAT` — speech speed multiplier (default: 1.0)
- `--voice NAME` — explicit voice override (alternative to positional)
- `--lang CODE` — language code (kokoro only: a/b/h/e/f/i/p/j/z)
- `--speaker ID` — speaker id (piper multi-speaker models)
- `--fast` — use fast preset (smallest/fastest models)
- `--balanced` — use balanced preset
- `--quality` — use quality preset (largest/best models)
- `--list` — list available voices/models for the engine

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
marmalade-tts daemon status                    # show which daemons are running
```

Only engines with `daemon: true` in their config section will use the daemon path.
Kitten is `daemon: true` by default (model is small enough to keep in RAM ~50-80MB).
Other engines default to subprocess-per-call.

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
  engine: kokoro          # default engine when none specified
  device: cpu             # global default: cpu | cuda | auto
  speed: 1.0              # global default speed
  play: true              # auto-play when no --out given

presets:
  fast:
    kitten: nano           # model_size for kitten
    kokoro: af_heart       # voice for kokoro
    piper: en_US-lessac-medium
    coqui: tts_models/en/ljspeech/tacotron2-DDC
  balanced:
    kitten: micro
    kokoro: af_heart
    piper: en_US-lessac-medium
    coqui: tts_models/en/ljspeech/tacotron2-DDC
  quality:
    kitten: mini
    kokoro: af_heart
    piper: en_US-lessac-medium
    coqui: tts_models/en/ljspeech/tacotron2-DDC

engines:
  kitten:
    device: cpu
    model_size: micro      # nano | micro | mini
    voice: Kiki            # default voice
    daemon: true           # keep model in RAM via daemon
    # voices: Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo
    # model repos:
    #   nano:  KittenML/kitten-tts-nano-0.8   (~23MB)
    #   micro: KittenML/kitten-tts-micro-0.8  (~41MB)
    #   mini:  KittenML/kitten-tts-mini-0.8   (~80MB)

  kokoro:
    device: cpu
    voice: af_heart
    lang: a                # a=US-EN, b=UK-EN, j=Japanese, z=Mandarin, etc.
    daemon: false
    # voices (American EN): af_heart, af_bella, af_nicole, am_adam, am_michael
    # voices (British EN):  bf_emma, bf_isabella, bm_george, bm_lewis

  piper:
    device: cpu
    model: ~/.local/share/piper/voices/en_US-lessac-medium.onnx
    daemon: false

  coqui:
    device: cpu
    model: tts_models/en/ljspeech/tacotron2-DDC
    daemon: false
```

## Engine Details

### Kitten (daemon mode)

**Why a daemon?** KittenTTS loads torch + ONNX runtime + the model on every call.
Cold start is ~5s even from HF cache. The daemon loads once, then synthesis is
~0.3s per request via Unix socket.

Protocol (newline-delimited JSON over Unix socket):
```
→ {"text": "Hello", "voice": "Kiki", "speed": 1.0, "out": "/tmp/x.wav"}
← {"ok": true, "out": "/tmp/x.wav"}
← {"ok": false, "error": "..."}
```

Fallback: if daemon is not running and `daemon: true`, the CLI auto-starts it
via `systemctl --user start marmalade-kitten.service` and waits up to 10s.

If daemon is disabled (`daemon: false`), falls back to subprocess (slow cold start).

### Kokoro

Subprocess call to `kokoro` CLI (pipx venv). Must set `CUDA_VISIBLE_DEVICES=""`
when device=cpu. Also sets `HF_HUB_OFFLINE=1` to avoid network hits after first cache.

### Piper

Subprocess call to `piper` CLI. Text fed via stdin. Speed is inverted
(`--length-scale` = 1/speed). Always CPU (ONNX runtime).

### Coqui

Subprocess call to `tts` CLI (pipx venv, patched for transformers compat).
Must set `CUDA_VISIBLE_DEVICES=""` when device=cpu.

## Environment Considerations

- **GPU:** GTX 1060 Max-Q (Pascal, sm_61) — not compatible with modern torch CUDA.
  All engines default to CPU. The `device: cuda` option exists for future GPUs.
- **HuggingFace cache:** Models cached in `~/.cache/huggingface/hub/`. First run
  downloads; subsequent runs use cache. `HF_HUB_OFFLINE=1` prevents re-checking.
- **Python:** System Python 3.12. Each engine lives in its own venv (pipx or manual).
  The CLI entrypoint uses system Python (only needs PyYAML, no torch).

## File Ownership

- `~/.local/bin/marmalade-tts` — entrypoint script (executable, system python)
- `~/.local/lib/marmalade-tts/` — package code (no venv needed, stdlib + yaml)
- `~/.local/share/marmalade-tts/` — daemon script, socket, pid, log
- `~/.config/marmalade-tts/config.yaml` — user config
- `~/.config/systemd/user/marmalade-kitten.service` — systemd unit
