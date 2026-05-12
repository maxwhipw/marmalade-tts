# Changelog

All notable changes to **marmalade-tts** are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.4.3] — 2026-05-12

### Fixed
- **pipx / pip install now ships daemon scripts.** The wheel now bundles
  `daemon/` as `marmalade_tts/_daemon_scripts/`; `daemon.py` resolves the
  script path via `importlib.resources` as a fallback, so `marmalade-tts
  daemon start` works out of the box on pure pip/pipx installs.
- **.deb / .rpm / AUR systemd units** previously pointed at
  `%h/.local/share/marmalade-tts/<engine>-daemon.py` (the user-install
  path), but those packages install daemon scripts to
  `/usr/share/marmalade-tts/daemon/`. The Makefile and AUR PKGBUILD now
  generate system-targeted unit files that point at the system path.
- Daemon script layout is now consistent across install methods:
  `<base>/daemon/<engine>-daemon.py` for user (install.sh) and system
  (deb/rpm/AUR) installs. install.sh removes the legacy v0.4.2 flat
  layout on upgrade.
- Daemon log messages now include the `voice=` field again (regression
  from the 0.4.2 `_common.py` refactor).
- .deb / .rpm now ship the LICENSE file under `/usr/share/doc/`.

## [0.4.2] — 2026

### Added
- Pocket TTS engine (kyutai-labs/pocket-tts) — CPU-only ~100M-param TTS with
  voice cloning. Loads in ~200 ms, no daemon needed.
- Docker HTTP API server with OpenAI- and ElevenLabs-compatible endpoints.
- Packaging: PyPI (`pyproject.toml`), `.deb` and `.rpm` via fpm, AUR PKGBUILD.
- Credits & acknowledgements section in README; API-compatibility disclaimer.

### Fixed
- Cross-device rename in the effects pipeline (tmpfs `/tmp` → home dir) now
  uses `shutil.move` instead of `os.replace`, and preserves user umask.

### Changed
- Default engine restored to `kitten` (was briefly `kokoro` / `pocket`).

## [0.4.1]

### Added
- Scripting flags: `--quiet`, `--json`, `--print-path`, `--stdin`, `--no-play`.
- KDE hotkey scripts: `speak-selection`, `speak-clipboard`, `marmalade-pipe`.
- Test hardening across the CLI surface.

## [0.4.0]

### Added
- Audio effects via `sox`: 14 effects and 10 built-in presets.
- Per-engine default effects in config.
- Full test suite covering CLI, config, daemon, effects, and preprocessing.
- `marmalade-tts init` — interactive TUI and non-interactive engine setup.

## [0.3.0]

### Added
- Daemon mode for all four (then-) engines (kitten, kokoro, piper, coqui).

## [0.2.0]

### Added
- Text preprocessing (currency, percent, ordinal, time, URL).
- Default-engine inference.
- Improved CLI argument parsing.

## [0.1.0]

- Initial release.
