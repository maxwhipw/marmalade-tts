# Changelog

All notable changes to **marmalade-tts** are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- **Tab completion is now engine-aware for voices everywhere it can be.**
  - bash: `piper --voice <TAB>` now completes `.onnx` file paths instead
    of nothing.
  - zsh: the positional voice slot (`marmalade-tts kitten <TAB>`) now
    completes — previously it offered nothing. `--voice` is now
    engine-aware (was lumping every engine's voices together), and piper
    gets `.onnx` file completion.
  - bash flag list gained `--no-effects`, `-q`, `--help`, `-h`.
  - coqui voices (`tts_models/...` specs) remain uncompletable by design —
    enumerating them requires loading the whole coqui stack.

## [0.4.4] — 2026-05-13

CLI surface cleanup before pre-1.0 lock-in. Two independent reviewer
agents went through the syntax matrix and turned up genuine bugs +
inconsistencies; this release fixes them and renames the kokoro voice
surface to drop the upstream prefix.

### Added
- **Kokoro bare voice names.** Voices are now referred to by their
  identifier-shaped bare name (e.g. `george`, `heart`, `alpha`) rather
  than the prefix-encoded upstream form (`bm_george`, `af_heart`). The
  canonical upstream IDs still work everywhere — no breaking change.
- **Voice / language are now orthogonal in kokoro.** Each voice has a
  natural language used by default; override with `--lang` or
  `engines.kokoro.lang` in config. Useful for accent effects (e.g. a
  Japanese voice speaking English text reads as English-with-accent).
- **`--no-effects` flag** to override `effects.defaults.<engine>` from
  config to empty for a single invocation.
- **JSON output includes a `version` field** so scripts can detect what
  shape they're parsing without a separate `--version` call.
- **README "Stability & versioning" section** outlining beta status,
  semver intent post-1.0, and what's documented-and-stable vs not.
- **README "Roadmap" section** with two near-term ideas: input
  language detection and emoji-driven emotional prosody.

### Changed
- **`--completion` and `--list-effects` are now first-position-only.**
  Previously substring-matched against argv — could mis-trigger when
  the word appeared inside synthesis text. (Bug, security-adjacent.)
- **`init --test` now exits non-zero if the test synthesis fails**,
  making the flag usable as a CI gate.
- **`config set` value coercion is now predictable for LLM-generated
  commands**: only `true/false`, `null/~`, and numeric strings are
  coerced; `yes/no/on/off` stay strings. Documented in the README.
- **`--voice` help text** corrected — it applies to every engine, not
  just kitten/kokoro.

### Fixed
- **Piper and Coqui no longer silently accept-and-drop a positional
  voice token.** Previously `marmalade-tts piper ~/voice.onnx "hi"`
  was parsed without errors, then the engine ignored the `voice` kwarg
  and used the configured default model. Now positional voice tokens
  are only recognized for engines whose voices are identifier-shaped
  (kitten, kokoro, pocket). Use `--voice` for piper and coqui.
- **`marmalade-tts <engine> <voice>` (no text) now errors** instead of
  silently synthesizing the literal voice name.
- **`--text "Hi" extra positional words` now errors** instead of
  silently discarding the extra positionals.
- **Kokoro voice detection narrowed.** Previously prefix-matched on 18
  patterns including `hf_`, `pm_`, `em_`, etc., which would have
  swallowed unrelated text-like tokens; now matches against a closed
  list of the 14 voices that actually exist.
- **`init.py` kokoro voice whitelist synced with the engine.** The old
  5-voice list rejected 9 valid voices via `init --non-interactive`.
- Voice lists are now imported from engine modules rather than
  duplicated in `init.py` and `completion.py`.

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
