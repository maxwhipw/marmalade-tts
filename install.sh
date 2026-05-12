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

# -- Daemon scripts --
echo "  → Installing daemon scripts to $DATA_DIR/daemon"
mkdir -p "$DATA_DIR/daemon"
for f in "$SCRIPT_DIR"/daemon/*-daemon.py "$SCRIPT_DIR"/daemon/_common.py; do
    cp "$f" "$DATA_DIR/daemon/"
    echo "    $(basename $f)"
done

# Remove legacy v0.4.2 layout files (scripts directly under DATA_DIR root)
# so we don't ship two copies and confuse the daemon path resolver.
for f in "$DATA_DIR"/*-daemon.py "$DATA_DIR"/_common.py; do
    [ -f "$f" ] && rm -f "$f"
done

# -- Default config (only if missing) --
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    echo "  → Creating default config at $CONFIG_DIR/config.yaml"
    mkdir -p "$CONFIG_DIR"
    cp "$SCRIPT_DIR/config-default.yaml" "$CONFIG_DIR/config.yaml"
else
    echo "  → Config already exists, skipping"
fi

# -- Systemd services --
echo "  → Installing systemd services"
mkdir -p "$SYSTEMD_DIR"
for f in "$SCRIPT_DIR"/systemd/marmalade-*.service; do
    cp "$f" "$SYSTEMD_DIR/"
    echo "    $(basename $f)"
done
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
