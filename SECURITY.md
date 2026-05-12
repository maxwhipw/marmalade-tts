# Security Policy

## Supported versions

Only the latest released `0.4.x` line receives security fixes.

## Reporting a vulnerability

If you find a security issue, please **do not** open a public GitHub issue.

Instead, use GitHub's private vulnerability reporting:

1. Go to https://github.com/maxwhipw/marmalade-tts/security/advisories/new
2. Describe the issue, impact, and reproduction steps.

We aim to acknowledge reports within 7 days and to publish a fix or
mitigation within 30 days when possible.

## Scope

In scope:

- The `marmalade_tts` CLI package.
- The Docker HTTP API server in `docker/server.py`.
- Helper scripts in `scripts/`.
- Packaging in `packaging/` and `Makefile`.

Out of scope — please report directly to upstream:

- The TTS engines themselves (kittentts, kokoro, piper, coqui, pocket-tts).
- Audio playback backends (paplay, aplay, ffplay).
- `sox`, `num2words`, `pyyaml`.

## Docker HTTP API server

The Docker server in `docker/server.py` is intended for local or
trusted-network use behind authentication. The default deployment is
loopback-only with a randomly-generated API key. Before exposing the server
to a network, read the **Security Model** section of `docker/README.md`.
