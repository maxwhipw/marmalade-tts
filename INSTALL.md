# INSTALL.md — marmalade-tts-cli Prerequisites

## System Requirements

- Linux (tested on Ubuntu 24.04 / TUXEDO OS)
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

## marmalade-tts Installation

```bash
# Clone the repo
git clone http://george:3000/max/marmalade-tts-cli.git /tmp/marmalade-tts-cli

# Run the install script
cd /tmp/marmalade-tts-cli
bash install.sh
```

This copies files to `~/.local/bin/` and `~/.local/lib/marmalade-tts/`,
creates the default config if missing, and installs the systemd user service.
