#!/bin/bash
# postinst.sh — post-install script for marmalade-tts deb package
set -e

CONFIG_DIR="${HOME}/.config/marmalade-tts"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
DEFAULT_CONFIG="/usr/share/marmalade-tts/config-default.yaml"

# Create default user config if not already present
if [ ! -f "${CONFIG_FILE}" ]; then
    mkdir -p "${CONFIG_DIR}"
    if [ -f "${DEFAULT_CONFIG}" ]; then
        cp "${DEFAULT_CONFIG}" "${CONFIG_FILE}"
        echo "marmalade-tts: created default config at ${CONFIG_FILE}"
    fi
fi

# Reload systemd user daemon if running under a real user session
if [ -n "${DBUS_SESSION_BUS_ADDRESS}" ] || [ -n "${XDG_RUNTIME_DIR}" ]; then
    systemctl --user daemon-reload 2>/dev/null || true
fi

echo "marmalade-tts installed. Run 'marmalade-tts init' to set up engines."
