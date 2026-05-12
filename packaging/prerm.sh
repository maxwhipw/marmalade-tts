#!/bin/bash
# prerm.sh — pre-remove script for marmalade-tts deb package
set -e

ENGINES=(kitten kokoro piper coqui)

# Stop and disable systemd user services if running under a real user session
if [ -n "${DBUS_SESSION_BUS_ADDRESS}" ] || [ -n "${XDG_RUNTIME_DIR}" ]; then
    for engine in "${ENGINES[@]}"; do
        svc="marmalade-${engine}.service"
        if systemctl --user is-active --quiet "${svc}" 2>/dev/null; then
            echo "marmalade-tts: stopping ${svc}"
            systemctl --user stop "${svc}" 2>/dev/null || true
        fi
        if systemctl --user is-enabled --quiet "${svc}" 2>/dev/null; then
            systemctl --user disable "${svc}" 2>/dev/null || true
        fi
    done
    systemctl --user daemon-reload 2>/dev/null || true
fi
