# INSTALL.md — How marmalade-tts installs engines

**The supported way to install engines is `marmalade-tts init` (or
`marmalade-tts install <engine>`).** marmalade-tts owns the engine install:
you should not `pip install` engines yourself. This document explains what
the installer does under the hood, and includes a manual-fallback appendix
for the rare case you need to replicate it by hand.

```sh
marmalade-tts init                       # pick engines in the wizard — installs them
marmalade-tts install matcha emojivoice  # add engines later (same code path)
```

## System Requirements

- Linux (tested on Ubuntu 24.04). Other Debian/Ubuntu, Fedora/RHEL, and
  Arch-based distros work — the installer detects `apt`/`dnf`/`pacman`.
- Python 3.10+ for the CLI itself.
- **[uv](https://docs.astral.sh/uv/)** — required. The installer uses it to
  provision per-engine Python versions and venvs. `pipx install marmalade-tts`
  pulls it in; otherwise: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- Audio player: `paplay` (PulseAudio), `aplay` (ALSA), or `ffplay` (FFmpeg).

## What the installer does

For each selected engine, `marmalade-tts install` runs these steps
(`marmalade_tts/installer.py`, `INSTALL_RECIPES`):

1. **Python** — if the engine needs a specific version (3.11 for `matcha`
   and `emojivoice`), `uv python install` provisions it.
2. **venv** — `uv venv` creates a dedicated venv at
   `~/.local/share/<engine>-venv`. Each engine's module and `daemon.py`
   look for the engine there; nothing is installed on `$PATH` or into
   marmalade-tts's own environment.
3. **pip** — `uv pip install` installs the engine's packages (or release
   wheel) into that venv.
4. **system deps** — packages like `espeak-ng` are installed via the
   detected distro package manager. Interactive runs prompt before any
   `sudo` command; non-interactive runs only do it with `--allow-sudo`,
   otherwise they skip with a clear warning. Already-present packages are
   skipped.
5. **models** — files listed in `marmalade_tts/models.json` are downloaded,
   sha256-verified (where a hash is published), and placed at their
   destination. Each model has an ordered list of sources tried in turn.
6. **warm cache** — engines that auto-download models from HuggingFace
   (kitten, kokoro, pocket) pre-fetch them so the first real run works
   offline.
7. **self-test** — marmalade-tts builds the engine the same way the CLI
   does (`daemon: false`) and synthesizes one phrase, asserting a valid
   non-trivial WAV. The install reports PASS / FAIL per engine.

## Per-engine reference

| Engine | venv | Python | pip | system deps | models |
|--------|------|--------|-----|-------------|--------|
| kitten | `~/.local/share/kittentts-venv` | 3.11 | KittenTTS release wheel | — | auto (HuggingFace) |
| kokoro | `~/.local/share/kokoro-venv` | system | `kokoro` `soundfile` | — | auto (HuggingFace) |
| piper | `~/.local/share/piper-venv` | system | `piper-tts` | `espeak-ng` | `en_US-lessac-medium` (manifest) |
| coqui | `~/.local/share/coqui-venv` | system | `coqui-tts` | — | auto (first use) |
| pocket | `~/.local/share/pocket-tts-venv` | system | `pocket-tts` `scipy` | — | auto (HuggingFace) |
| matcha | `~/.local/share/matcha-tts-venv` | **3.11** | `matcha-tts` | `espeak-ng` | auto (matcha-tts) |
| emojivoice | `~/.local/share/emojivoice-venv` | **3.11** | `matcha-tts` | `espeak-ng` | `paige` checkpoint (manifest) |

> matcha-tts does **not** build on Python 3.12 (an old numpy pin uses the
> removed `pkgutil.ImpImporter`) — `matcha` and `emojivoice` therefore pin
> Python 3.11, provisioned by uv.

> **espeak-ng note:** espeak-ng is GPL-licensed. marmalade-tts does not
> bundle or redistribute it — it is a separate system package that
> Matcha-TTS / EmojiVoice / Piper invoke at runtime for phonemization. The
> installer installs it via your distro's package manager.

> **EmojiVoice checkpoint:** the `paige` checkpoint's licence is not
> explicitly stated upstream, so it is not mirrored — the manifest fetches
> it directly from the EmojiVoice authors' Google Drive (via `gdown`, run
> through `uv tool run` so it never has to be a marmalade-tts dependency).

## marmalade-tts (the CLI) installation

```sh
# pipx — recommended (pulls in uv automatically)
pipx install marmalade-tts

# or from a clone
git clone https://github.com/maxwhipw/marmalade-tts /tmp/marmalade-tts
cd /tmp/marmalade-tts && bash install.sh
```

Then run `marmalade-tts init`.

---

## Appendix — manual engine install (fallback only)

You should not normally need this — `marmalade-tts install <engine>` is the
supported path. These steps replicate what the installer does, for
debugging or air-gapped setups. Paths must match exactly what the engine
modules expect (the table above).

### kitten

```sh
uv venv --python 3.11 ~/.local/share/kittentts-venv
uv pip install --python ~/.local/share/kittentts-venv/bin/python \
  https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
```

### kokoro

```sh
uv venv ~/.local/share/kokoro-venv
uv pip install --python ~/.local/share/kokoro-venv/bin/python kokoro soundfile
```

### piper

```sh
uv venv ~/.local/share/piper-venv
uv pip install --python ~/.local/share/piper-venv/bin/python piper-tts
sudo apt install espeak-ng
mkdir -p ~/.local/share/piper/voices && cd ~/.local/share/piper/voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

### coqui

```sh
uv venv ~/.local/share/coqui-venv
uv pip install --python ~/.local/share/coqui-venv/bin/python coqui-tts
```

### pocket

```sh
uv venv ~/.local/share/pocket-tts-venv
uv pip install --python ~/.local/share/pocket-tts-venv/bin/python pocket-tts scipy
```

The model (~200 MB) downloads from HuggingFace on first use. Voice cloning:
pass any `.wav` path as the voice, or pre-export with
`pocket-tts export-voice my_voice.wav --out my_voice.safetensors`.

### matcha

```sh
uv python install 3.11
uv venv --python 3.11 ~/.local/share/matcha-tts-venv
uv pip install --python ~/.local/share/matcha-tts-venv/bin/python matcha-tts
sudo apt install espeak-ng
```

The model (~73 MB) and universal vocoder (~50 MB) auto-download on first use.

### emojivoice

```sh
uv python install 3.11
uv venv --python 3.11 ~/.local/share/emojivoice-venv
uv pip install --python ~/.local/share/emojivoice-venv/bin/python matcha-tts
sudo apt install espeak-ng

# Download the paige checkpoint from the EmojiVoice Google Drive folder:
#   https://drive.google.com/drive/folders/1E_YTAaQxQfFdZYAKs547bgd4epkUbz_5
mkdir -p ~/.local/share/emojivoice/models
# place emoji-hri-paige-inference.ckpt (~78 MB) at:
#   ~/.local/share/emojivoice/models/emoji-hri-paige-inference.ckpt
```

An emoji anywhere in the text (`🤣 😭 😡 🙂 …`) selects an emotional
speaking style; the emoji is stripped before synthesis. Run
`marmalade-tts emojivoice --list` for the full emoji set.
