# marmalade-tts-cli

🍊 Unified local TTS command-line tool. One command, four engines, instant synthesis.

## Quick Start

```bash
# Synthesize with default engine (reads from config)
marmalade-tts "Hello, I am Marmalade"

# Pick an engine explicitly
marmalade-tts kokoro "Hello world"
marmalade-tts kitten "Hello from Kitten" --voice Kiki
marmalade-tts piper "Hello from Piper"
marmalade-tts coqui "Hello from Coqui"

# Quality presets
marmalade-tts --fast "Quick and light"
marmalade-tts --quality "Best fidelity"

# Save to file instead of playing
marmalade-tts kokoro "Save this" --out output.wav

# Read from file
marmalade-tts kokoro @script.txt --out narration.wav

# Config management
marmalade-tts config show
marmalade-tts config set defaults.engine kitten
marmalade-tts config set engines.kitten.voice Hugo

# Daemon management (kitten stays in RAM for instant response)
marmalade-tts daemon start
marmalade-tts daemon stop
marmalade-tts daemon status
```

## Engines

| Engine | Backend | Typical Latency | Notes |
|--------|---------|-----------------|-------|
| **kitten** | KittenTTS (ONNX) | ~0.3s (daemon) / ~5s (cold) | Smallest models, daemon keeps in RAM |
| **kokoro** | Kokoro (PyTorch) | ~12s (cold) | 82M params, high quality |
| **piper** | Piper (ONNX) | ~1s | Fast, multilingual, many community voices |
| **coqui** | Coqui TTS (PyTorch) | ~3s | Tacotron2, many models available |

## Configuration

YAML config at `~/.config/marmalade-tts/config.yaml`. Editable directly or via `marmalade-tts config set`.

## Installation

See [INSTALL.md](INSTALL.md) for prerequisites and setup.

## License

MIT
