# INSTALL.md — marmalade-tts Prerequisites

## System Requirements

- Linux (tested on Ubuntu 24.04). Other Debian/Ubuntu-based distros should
  work. Fedora/RHEL users: substitute `apt` commands with `dnf` equivalents.
- Python 3.10+ (system python, no venv needed for the CLI itself)
- PyYAML (`apt install python3-yaml` or already present)
- pipx (`apt install pipx`)
- Audio player: `paplay` (PulseAudio), `aplay` (ALSA), or `ffplay` (FFmpeg)

## Engine Installation

### Piper (fastest to install)

```bash
pipx install piper-tts
mkdir -p ~/.local/share/piper/voices && cd ~/.local/share/piper/voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

### Kokoro

```bash
pipx install kokoro
# Fix torch for Pascal GPUs (optional, CPU mode works fine):
# ~/.local/share/pipx/venvs/kokoro/bin/python -m pip install torch==2.4.1 --index-url https://download.pytorch.org/whl/cu124
```

### Kitten TTS

Kitten has no CLI entrypoint, so it lives in a dedicated venv:

```bash
python3 -m venv ~/.local/share/kittentts-venv
~/.local/share/kittentts-venv/bin/pip install \
  https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
```

Pre-cache models (avoids network hits at runtime):

```bash
CUDA_VISIBLE_DEVICES="" ~/.local/share/kittentts-venv/bin/python -c "
from kittentts import KittenTTS
KittenTTS('KittenML/kitten-tts-nano-0.8')
KittenTTS('KittenML/kitten-tts-micro-0.8')
print('Models cached')
"
```

### Coqui TTS

```bash
pipx install coqui-tts
# Inject torch (coqui doesn't auto-install it):
~/.local/share/pipx/venvs/coqui-tts/bin/python -m pip install \
  torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu124
```

Note: Coqui 0.27.5 requires a patch for transformers compatibility.
The install script handles this automatically.

### Pocket TTS

Pocket TTS runs in-process (no venv required if installed system-wide).
For isolation, a venv is recommended:

```bash
# Option 1: system-wide (simple)
pip install pocket-tts

# Option 2: isolated venv (recommended)
python3 -m venv ~/.local/share/pocket-tts-venv
~/.local/share/pocket-tts-venv/bin/pip install pocket-tts
```

The model (~200MB) downloads automatically from HuggingFace on first use.
Subsequent runs use the cache (`~/.cache/huggingface/hub/`).

Voice cloning (optional): export a speaker voice from any `.wav` file:

```bash
pocket-tts export-voice my_voice.wav --out my_voice.safetensors
marmalade-tts pocket "Hello" --voice my_voice.safetensors
```

## marmalade-tts Installation

```bash
# Clone the repo
git clone https://github.com/maxwhipw/marmalade-tts.git /tmp/marmalade-tts

# Run the install script
cd /tmp/marmalade-tts
bash install.sh
```

This copies files to `~/.local/bin/` and `~/.local/lib/marmalade-tts/`,
creates the default config if missing, and installs the systemd user service.
