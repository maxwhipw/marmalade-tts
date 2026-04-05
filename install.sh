#!/bin/bash
set -euo pipefail
# marmalade-tts installer — copies files to ~/.local/bin and ~/.local/lib
# Run from the repo root: bash install.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$HOME/.local/lib/marmalade-tts"
BIN_DIR="$HOME/.local/bin"
DATA_DIR="$HOME/.local/share/marmalade-tts"
CONFIG_DIR="$HOME/.config/marmalade-tts"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "🍊 Installing marmalade-tts..."

# -- Python package --
echo "  → Copying package to $LIB_DIR"
rm -rf "$LIB_DIR/marmalade_tts"
mkdir -p "$LIB_DIR"
cp -r "$SCRIPT_DIR/marmalade_tts" "$LIB_DIR/"

# -- Entrypoint --
echo "  → Installing entrypoint to $BIN_DIR/marmalade-tts"
mkdir -p "$BIN_DIR"
cp "$SCRIPT_DIR/marmalade-tts" "$BIN_DIR/marmalade-tts"
chmod +x "$BIN_DIR/marmalade-tts"

# -- Daemon script --
echo "  → Installing kitten daemon to $DATA_DIR"
mkdir -p "$DATA_DIR"
cp "$SCRIPT_DIR/daemon/kitten-daemon.py" "$DATA_DIR/kitten-daemon.py"

# -- Default config (only if missing) --
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    echo "  → Creating default config at $CONFIG_DIR/config.yaml"
    mkdir -p "$CONFIG_DIR"
    cp "$SCRIPT_DIR/config-default.yaml" "$CONFIG_DIR/config.yaml"
else
    echo "  → Config already exists, skipping"
fi

# -- Systemd service --
echo "  → Installing systemd service"
mkdir -p "$SYSTEMD_DIR"
cp "$SCRIPT_DIR/systemd/marmalade-kitten.service" "$SYSTEMD_DIR/"
systemctl --user daemon-reload

echo ""
echo "✅ marmalade-tts installed!"
echo ""
echo "Quick start:"
echo "  marmalade-tts daemon start          # start kitten daemon (keeps model in RAM)"
echo "  marmalade-tts kitten 'Hello world'  # instant synthesis"
echo "  marmalade-tts kokoro 'Hello world'  # kokoro engine"
echo ""
echo "Tab completion:"
echo "  eval \"\$(marmalade-tts --completion bash)\"   # add to .bashrc"
