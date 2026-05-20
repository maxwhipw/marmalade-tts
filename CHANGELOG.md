# Changelog

All notable changes to **marmalade-tts** are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- **Batch synthesis is now opt-in via `--batch`.** Multi-line input
  (`@file.txt`, `--stdin`, `--text "a\nb"`) previously triggered batch
  mode implicitly — one WAV per non-empty line. That surprised AI
  agents sending paragraph-broken files. Default now: multi-line input
  goes to a single synthesis call (newlines and all). Pass `--batch`
  for the old one-WAV-per-line behavior.
- **matcha / emojivoice cold path now calls Matcha-TTS's Python API
  directly** instead of shelling out to the upstream `matcha-tts` CLI.
  The CLI is research-codebase residue from ICASSP 2024 — it always
  writes a `.png` mel-spectrogram alongside each `.wav` and has no flag
  to disable that. Two new one-shot scripts (`daemon/matcha-oneshot.py`,
  `daemon/emojivoice-oneshot.py`) share a `daemon/_matcha_synth.py`
  helper with the long-running daemons, so warm and cold paths now go
  through the same code. No PNGs leak anywhere. `matcha-tts` is pinned
  in the installer (`>=0.0.7,<0.1`) since the Python API surface is less
  stable than the CLI's.

### Added
- **Transparent chunking for long inputs.** Each engine declares a
  soft `MAX_CHARS` limit (500 for most, 1000 for piper); inputs longer
  than that are split on sentence boundaries, synthesized per chunk,
  and concatenated into a single WAV before effects and duration are
  measured. One input still produces one WAV — chunking is purely an
  implementation detail. Tunable per-engine via
  `engines.<name>.max_chars` in config (`null` disables).
- **MCP server.** New `marmalade-tts mcp` subcommand runs a stdio Model
  Context Protocol server with three tools: `synthesize`, `list_voices`,
  and `find_voice`. `find_voice` takes a free-text description ("warm
  British male", "energetic young female") and returns the top three
  shipped voices with a `why` field naming the matched terms — word-token
  overlap against a curated description table (so "male" doesn't match
  inside "female"), no LLM call, inspectable. `synthesize` routes through
  the same shared synth module the CLI uses, so preprocessing rules
  apply uniformly. The MCP SDK is an optional dep
  (`pip install marmalade-tts[mcp]`); without it, `marmalade-tts mcp`
  prints an install hint and exits 1. Add to Claude Code with
  `claude mcp add marmalade-tts -- marmalade-tts mcp`. Full setup in
  `docs/mcp.md`. piper/coqui are deliberately omitted from the voice
  catalog — their voices are user-installed model paths, not bare names.
- **Voice aliases / personas.** Config-defined named bundles
  (`aliases.narrator = {engine: kokoro, voice: george, speed: 0.95,
  effects: ["reverb=15"]}`) invoke positionally like an engine name:
  `marmalade-tts narrator "Once upon a time"`. Precedence: explicit CLI
  flags > alias defaults > engine config defaults. Engine names are
  reserved — an alias that collides is ignored with a warning. Alias
  names complete in bash/zsh alongside engine names; `--list-aliases`
  enumerates what's configured.
- **Streaming batch playback.** Multi-line batch playback no longer
  waits for the whole script to render before playing the first line. A
  producer thread renders utterances sequentially while the main thread
  plays each WAV as soon as it lands in the queue. Lines play in input
  order; the first line plays almost immediately and the rest stream
  behind it. Single-utterance, `--no-play`, and pure `--out`/`--out-dir`
  paths are unchanged. Subtitles and `--json`/`--print-path` reporting
  still happen once all synthesis is done — same final-state output,
  faster perceived start. Intra-utterance (engine-native chunked)
  streaming is a separate future feature.
- **SRT and WebVTT subtitle output.** New `--srt PATH` and `--vtt PATH`
  flags emit a synchronized subtitle file alongside the generated WAVs.
  Cue text is the user's raw input (so emoji and markdown they typed
  appear readable in the subtitle file even though they were stripped
  before synthesis); cue timing is measured from each WAV's duration
  after effects are applied, with a 50 ms gap between consecutive cues.
  Works for both single and batch input; pass both flags to write both
  files. `--json` output also gains a `duration` field per utterance.
  `--srt`, `--vtt`, and `--out-dir` all tab-complete in bash and zsh.
- **`markdown` and `html` preprocessing rules.** A piped README no
  longer reads `**hello**` as "asterisk asterisk hello asterisk
  asterisk" or `<p>hi</p>` as "less than p greater than hi …". The
  `markdown` rule drops bold/italic/code/heading/blockquote/list/link/
  image syntax — link targets are dropped, only the visible text reads
  aloud. Python dunders (`__init__`, `__name__`, `__main__`, `__repr__`,
  …) are preserved via a known-dunder denylist so prose about Python
  code reads correctly. The `html` rule strips tags and decodes entities
  via `html.unescape`. Both are added to every engine profile
  (universally safe) and ordered before `url`/`email` so
  `[text](https://example.com)` comes out as just "text".
- **Pronunciation dictionary.** New `pronounce` preprocessing rule
  reads `~/.config/marmalade-tts/pronunciations.yaml` on first use and
  substitutes whole-word, case-insensitive matches with their spoken
  form. Missing or empty file → no-op. Hyphenated keys are allowed
  (`marmalade-tts: marmalade T T S`) and the match boundary treats `-`
  as a non-boundary char, so a key `marmalade-tts` won't bleed into a
  compound like `marmalade-tts-cli`. Empty / non-string YAML keys are
  filtered before the regex compiles, so a `"": foo` typo can't
  garble every utterance. Keys sorted longest-first so multi-word
  entries beat their prefixes. Placed late in the rule order, after
  numbers/abbreviations, so substitutions operate on already-normalized
  text.
- **Quality knobs for matcha + emojivoice.** Both engines now read
  `engines.matcha.steps` / `engines.matcha.temperature` (and the
  emojivoice equivalents) from config. `steps` is matcha-tts's
  ODE-solver iteration count — the main quality lever; default 10
  (fast), 50 is noticeably less robotic at ~5× the synthesis time.
  Propagates through both the daemon (warm) and one-shot (cold) paths.
  Unset → engine venv's own default applies, so existing configs are
  unaffected.
- **Batch synthesis (universal).** Multi-line text input — from `@file.txt`,
  `--stdin`, or `--text "a\nb"` — now produces one WAV per non-empty line.
  Plays each through the speakers in sequence, or writes them via the new
  `--out-dir DIR` flag or a `--out PATTERN` with a printf format
  (`'chapter-%03d.wav'`). `--json` returns an array of result objects in
  batch (one per utterance); single-line input keeps the original
  single-object shape. The trigger is **implicit** on multi-line input —
  a deliberate UX tradeoff documented in agent memory; revisit if it
  surprises users.
- **`emoji` preprocessing rule.** Strips emojis before synthesis for every
  engine except `emojivoice`. Without this, espeak-backed engines (kokoro,
  piper, matcha, …) verbalize them as their Unicode names — `😭` becomes
  "loudly crying face", `🤣` becomes "rolling on the floor laughing". Now
  on by default in every engine's profile. Remove `emoji` from
  `engines.<name>.preprocessing` in config to keep emojis (e.g. for
  emojivoice). The emoji rule is intentionally **omitted** from
  `emojivoice`'s default profile so the emotion emoji survives
  preprocessing and reaches the engine.

### Fixed
- matcha / emojivoice subprocess invocations now run with `cwd` set to
  their per-call tempdir, so the spectrogram `.png` that matcha-tts writes
  alongside each `.wav` lands in the tempdir we clean up — not the user's
  current directory. (Was leaking `utterance_NNN.png` files into cwd.)

## [0.5.0] — 2026-05-14

Hands-off engine installation, and two new expressive engines.

### Added
- **`matcha` and `emojivoice` engines.** Matcha-TTS is a fast
  flow-matching neural TTS; EmojiVoice runs on Matcha-TTS and lets an
  emoji in the text select the emotional speaking style (`🤣` amused,
  `😭` sad, `😡` angry, …). Both have daemon + systemd support.
- **Hands-off engine installer.** `marmalade-tts init` now *installs* the
  engines you select — venvs, packages, system dependencies, and models —
  instead of just printing hints. A new `marmalade-tts install <engine>…`
  command does the same for post-init additions (`init` uses it under the
  hood). Each engine is self-tested after install: marmalade-tts
  synthesizes a phrase through the real CLI code path and asserts a valid
  WAV. Flags: `--allow-sudo`, `--reinstall`, `--skip-selftest`.
- **`marmalade_tts/models.json`** — model manifest with redundant download
  sources and sha256 verification, consumed by the installer.

### Changed
- **uv is now a hard dependency.** The installer uses it to provision
  per-engine Python versions and venvs cross-distro (matcha / emojivoice
  require Python 3.11 — matcha-tts does not build on 3.12).
- **Every engine now lives in its own venv at `~/.local/share/<engine>-venv`
  and is invoked by explicit path.** kokoro/coqui/piper previously called a
  bare command from `$PATH`; pocket imported `pocket-tts` in-process. All
  now call into their own venv explicitly — uniform, and the installer's
  self-test exercises the exact path the CLI uses. The kokoro/piper/coqui
  venvs moved off the old `~/.local/share/pipx/venvs/...` locations.
- **Tab completion is now engine-aware for voices everywhere it can be.**
  - bash: `piper --voice <TAB>` now completes `.onnx` file paths instead
    of nothing.
  - zsh: the positional voice slot (`marmalade-tts kitten <TAB>`) now
    completes — previously it offered nothing. `--voice` is now
    engine-aware (was lumping every engine's voices together), and piper
    gets `.onnx` file completion.
  - bash flag list gained `--no-effects`, `-q`, `--help`, `-h`.
  - the `install` subcommand and its flags are completed too.
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
