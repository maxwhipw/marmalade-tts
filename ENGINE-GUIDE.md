# ENGINE-GUIDE.md — How to Add a New TTS Engine

This guide walks through every file you must touch to add a new TTS engine to
marmalade-tts. Follow the steps in order; skipping steps leads to a partially
integrated engine (the `pocket` engine was originally added this way — it's
used as the worked example throughout).

---

## Overview of Files to Touch

| # | File | What to do |
|---|------|-----------|
| 1 | `marmalade_tts/engines/{name}.py` | Create the engine class |
| 2 | `marmalade_tts/cli.py` | Register in `ENGINE_CLASSES` |
| 3 | `marmalade_tts/config.py` | Add to `DEFAULT_CONFIG["engines"]` and presets |
| 4 | `marmalade_tts/preprocessing.py` | Add to `ENGINE_PROFILES` |
| 5 | `marmalade_tts/completion.py` | Add to `ENGINES`, add voice list |
| 6 | `marmalade_tts/init.py` | Add to `ENGINE_INFO` and `ENGINE_ORDER` |
| 7 | `config-default.yaml` | Add engine section and preset entries |
| 8 | `daemon/` | (Daemon only) Create `{name}-daemon.py` |
| 9 | `marmalade_tts/daemon.py` | (Daemon only) Add to `ENGINE_DAEMONS` / `ENGINE_PYTHON` |
| 10 | `systemd/` | (Daemon only) Create `marmalade-{name}.service` |
| 11 | `tests/` | Write unit + integration tests |
| 12 | `README.md` | Update engine table and examples |
| 13 | `INSTALL.md` | Add installation instructions |
| 14 | `marmalade_tts/installer.py` (+ `models.json`) | Add the `INSTALL_RECIPES` entry so `init` / `install` can install the engine |

> **Checklist at the end of this file.** Print it, check each box.

---

## Step 1 — Create the Engine Class

**File:** `marmalade_tts/engines/{name}.py`

The engine class must:
- Import `Engine` from the parent package: `from . import Engine`
- Extend `Engine` (not just define a standalone class)
- Set `name = "{name}"` as a class attribute
- Implement `synthesize(text, out_path, **kwargs)`
- Implement (or inherit) `list_voices()`

### Minimal template

```python
"""My new TTS engine."""

from . import Engine

VOICES = ["voice_one", "voice_two"]  # if applicable


class MyEngine(Engine):
    """MyEngine — short description."""

    name = "myengine"

    def __init__(self, cfg: dict):
        self.voice = cfg.get("voice", "voice_one")
        self.device = cfg.get("device", "cpu")

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, **kwargs):
        v = voice or self.voice
        # ... call the underlying library / subprocess
        # must write a valid WAV file to out_path

    def list_voices(self):
        print("MyEngine voices:")
        for v in VOICES:
            marker = " (default)" if v == self.voice else ""
            print(f"  {v}{marker}")
```

### Example — Pocket engine (what was originally missing)

The original `pocket.py` had:
```python
# WRONG — no import, no inheritance, no name attribute
class PocketEngine:
    ...
```

The fix:
```python
from . import Engine

class PocketEngine(Engine):
    name = "pocket"
    ...
```

Forgetting this means `isinstance(engine, Engine)` checks fail and the engine
won't behave consistently across the codebase.

### Honoring `--speed` (required)

Every engine MUST honor the `speed` kwarg passed to `synthesize()`. The
contract is non-negotiable: a user who passes `--speed 1.4` expects faster
audio, regardless of which engine they picked.

Two paths, in order of preference:

1. **Native speed** — pass through to the underlying library's
   tempo/length-scale parameter. Examples in-tree:

   | Engine     | Native knob                                  |
   |------------|----------------------------------------------|
   | kitten     | `KittenTTS.generate(..., speed=...)`         |
   | kokoro     | `pipeline(..., speed=...)` / CLI `--speed`   |
   | piper      | `SynthesisConfig.length_scale = 1.0 / speed` |
   | matcha     | `length_scale = 1.0 / speed`                 |
   | emojivoice | `length_scale = 1.0 / speed`                 |
   | coqui      | `TTS.tts_to_file(..., speed=...)`            |

   Note: matcha-family `length_scale` is inverted (higher = slower) — divide.

2. **sox fallback** — if upstream has no native knob, post-process the
   WAV with the shared helper:

   ```python
   from . import Engine, sox_tempo

   def synthesize(self, text, out_path, speed=1.0, **kwargs):
       # ... write out_path via the underlying library
       sox_tempo(out_path, speed)   # no-op when speed == 1.0
   ```

   `sox_tempo` preserves pitch (it's sox's `tempo` effect, not `speed`).
   If sox isn't installed it warns once on stderr and leaves the file
   untouched — synthesis still succeeds, the audio just plays at the
   original rate.

   Pocket is the in-tree example: `pocket-tts`'s API has no speed
   parameter, so `pocket.py` uses `sox_tempo` after writing the WAV.

**Anti-pattern:** accepting `speed` in your signature and then ignoring
it. This silently breaks the user's `--speed` flag. If you genuinely
can't honor it, raise an explicit error — don't lie.

### Expose every native feature as a knob (required)

When you add an engine, audit the upstream library's runtime API and
expose every meaningful parameter as a config key. Do not hardcode
choices the user might reasonably want to change. The same anti-pattern
that produced the `--speed` silent-drop produced everything else this
guide had to backfill — flagged-but-unwired knobs (coqui's speed,
piper's voice), hidden expressivity knobs (matcha's `steps`/
`temperature`, piper's `noise_scale`), and missing model-specific
features (coqui's `speaker_wav` for XTTS cloning, coqui's `emotion` for
Tortoise).

How to decide where each knob lives:

| Knob shape                         | Surface as           |
|------------------------------------|----------------------|
| Per-utterance choice (voice, language, speaker, emotion) | CLI flag + config key |
| Tuning knob (expressivity, sampling temperature, solver steps) | Config-only          |
| Voice-cloning reference            | CLI flag + config key (so an LLM agent can switch references per turn) |
| Anything the upstream library lets you set per-call | Plumb through both subprocess and daemon paths |

Pattern for optional knobs that have an upstream default:

```python
self.knob = cfg.get("knob")   # None means "use upstream's default"
...
if self.knob is not None:                 # don't pass when unset
    request["knob"] = float(self.knob)    # → daemon
    cmd += ["--knob", str(self.knob)]     # → subprocess
```

`None` ≠ falsy. Use `is not None`, not truthiness — a config value of
`0` or `""` is a deliberate setting, not "unset". See
[`engines/coqui.py`](marmalade_tts/engines/coqui.py) for the in-tree
example covering speed, speaker, speaker_idx, language, speaker_wav,
and emotion.

Document the new knobs in:
- `marmalade_tts/config.py` (DEFAULT_CONFIG)
- `config-default.yaml` (annotated example)
- `marmalade_tts/completion.py` (config paths for tab-completion)
- `docs/engine-knobs.md` (the user-facing reference)

---

## Step 2 — Register in `cli.py`

**File:** `marmalade_tts/cli.py`

Add the import and register the engine in `ENGINE_CLASSES`.

```python
# At the top with other engine imports:
from .engines.myengine import MyEngine, VOICES as MY_VOICES

# In the ENGINE_CLASSES dict:
ENGINE_CLASSES = {
    "kitten":   KittenEngine,
    "kokoro":   KokoroEngine,
    "piper":    PiperEngine,
    "coqui":    CoquiEngine,
    "pocket":   PocketEngine,
    "myengine": MyEngine,      # ← add here
}
```

Also update the `looks_like_voice()` function to recognise voice tokens
for your engine:

```python
def looks_like_voice(engine: str, token: str) -> bool:
    ...
    if engine == "myengine":
        return token in MY_VOICES  # or whatever heuristic applies
    ...
```

If the preset system should do something specific for your engine (e.g. pick
a voice or model size), also update the preset-resolution block in `main()`:

```python
if preset_name:
    presets = config.get("presets", {}).get(preset_name, {})
    preset_val = presets.get(engine_name)
    if preset_val:
        if engine_name == "kitten":
            eng_cfg["model_size"] = preset_val
        elif engine_name == "myengine":
            eng_cfg["voice"] = preset_val   # ← add your case
        ...
```

---

## Step 3 — Add to `config.py` DEFAULT_CONFIG

**File:** `marmalade_tts/config.py`

Add a default config block and preset entries:

```python
DEFAULT_CONFIG = {
    ...
    "presets": {
        "fast":     {..., "myengine": "voice_one"},
        "balanced": {..., "myengine": "voice_two"},
        "quality":  {..., "myengine": "voice_two"},
    },
    "engines": {
        ...
        "myengine": {
            "device": "cpu",
            "voice": "voice_one",
            # add any engine-specific defaults
        },
    },
}
```

> **Lesson from pocket:** `config.py` was initially missing a `pocket` entry,
> meaning `engine_cfg(config, "pocket")` returned only the global defaults
> and users couldn't configure pocket in their YAML without it auto-appearing
> in the default structure.

---

## Step 4 — Add to `preprocessing.py` ENGINE_PROFILES

**File:** `marmalade_tts/preprocessing.py`

Decide which text normalization rules your engine needs. Engines that handle
certain patterns natively can skip those rules; engines with no normalization
support should include everything.

```python
ENGINE_PROFILES = {
    ...
    "myengine": [
        "currency", "percentage", "ordinal", "time", "date",
        "email", "url", "filename", "abbreviation", "number",
        "math", "ampersand", "hashtag",
    ],
}
```

**Rule reference:**

| Rule | Expands | Example |
|------|---------|---------|
| `currency` | `$100` → `100 dollars` | Money amounts |
| `percentage` | `50%` → `50 percent` | Percentages |
| `ordinal` | `1st` → `first` | Ordinal numbers |
| `time` | `10:30` → `ten thirty` | Clock times |
| `date` | `01/15/2025` → `January fifteenth, 2025` | Dates |
| `email` | `user@example.com` → `user at example dot com` | Email addresses |
| `url` | `https://example.com` → `example dot com` | URLs |
| `filename` | `notes.txt` → `notes dot T X T` | File extensions |
| `abbreviation` | `U.S.A.` → `U S A` | Common abbreviations |
| `number` | `42` → `forty-two` | Bare numbers |
| `math` | `x = y` → `x equals y` | Math symbols |
| `ampersand` | `bread & butter` → `bread and butter` | Ampersand |
| `hashtag` | `#100` → `number 100` | Hashtags |
| `emoji` | `hello 🤣` → `hello` | Strip emojis (every engine except `emojivoice`) |

**Guidance by engine type:**
- Handles nothing natively → include all rules (like `piper`, `kitten`, `pocket`)
- Handles numbers/abbreviations natively → skip `number`, `abbreviation` (like `kokoro`)
- Handles basic numbers → skip `number`, `ordinal` (like `coqui`)
- **Consumes emojis itself** → exclude `emoji` (only `emojivoice` so far — it
  maps the emoji to a speaker id, so the rule would force every line to the
  neutral speaker)

> **Lesson from pocket:** Pocket was omitted from `ENGINE_PROFILES`, so it fell
> back to the kitten profile silently. Explicit is better than silent fallback.

---

## Step 5 — Add to `completion.py`

**File:** `marmalade_tts/completion.py`

Add the engine name to `ENGINES` and (if applicable) add a voice list:

```python
ENGINES = ["kitten", "kokoro", "piper", "coqui", "pocket", "myengine"]

MY_VOICES = ["voice_one", "voice_two", "voice_three"]
```

Then wire up the voice list in the bash/zsh completion functions so that
`marmalade-tts myengine <TAB>` suggests voices.

In `bash_completion()`:
```python
my_voices = " ".join(MY_VOICES)

# In the f-string:
local my_voices="{my_voices}"

# In the "second positional after engine" block:
case "${{words[1]}}" in
    kitten)   COMPREPLY=( $(compgen -W "$kitten_voices" -- "$cur") ) ;;
    kokoro)   COMPREPLY=( $(compgen -W "$kokoro_voices" -- "$cur") ) ;;
    myengine) COMPREPLY=( $(compgen -W "$my_voices" -- "$cur") ) ;;  # ← add
    *)        COMPREPLY=( $(compgen -W "$flags" -- "$cur") ) ;;
esac
```

In `zsh_completion()`, similarly add `myengine` to the relevant completion spec.

> **Lesson from pocket:** `completion.py` originally listed only four engines.
> Running `marmalade-tts pocket <TAB>` gave no completions and skipped voice
> suggestions.

---

## Step 6 — Add to `init.py`

**File:** `marmalade_tts/init.py`

Add to `ENGINE_INFO`:

```python
ENGINE_INFO = {
    ...
    "myengine": {
        "label": "MyEngine TTS",
        "desc":  "One-line description for the setup wizard.",
        "size":  "~XXX MB (describe model size or download)",
        "default": False,  # True if it should be pre-selected in the wizard
        "options": {
            "voice": {
                "prompt": "Default voice",
                "choices": ["voice_one", "voice_two"],
                "default": "voice_one",
                "help": "Brief description of each voice",
            },
        },
    },
}
```

Add to `ENGINE_ORDER`:

```python
ENGINE_ORDER = ["kitten", "piper", "kokoro", "coqui", "pocket", "myengine"]
```

Also add a default-setting clause in `init_non_interactive()` and `init_interactive()`:

```python
elif eng == "myengine":
    cfg.setdefault("voice", "voice_one")
```

> **Lesson from pocket:** `init.py` was one of the files updated correctly for
> pocket. A new engine's wizard entry is essential so `marmalade-tts init`
> can configure it interactively.

---

## Step 7 — Update `config-default.yaml`

**File:** `config-default.yaml`

This is the *documented* default config shipped with the repo (not the
programmatic defaults in `config.py`). They must stay in sync.

Add your engine to:

1. The `engines:` section:
```yaml
engines:
  ...
  myengine:
    device: cpu
    voice: voice_one
    # any other defaults
```

2. The `presets:` section:
```yaml
presets:
  fast:
    ...
    myengine: voice_one
  balanced:
    ...
    myengine: voice_two
  quality:
    ...
    myengine: voice_two
```

Also verify that `defaults.engine` is what you intend. The file and `config.py`
DEFAULT_CONFIG must agree.

> **Lesson from pocket:** `config-default.yaml` had `defaults.engine: pocket`
> while `config.py` had `defaults.engine: kokoro`. This mismatch confused
> users who read the YAML (they'd see pocket as the default, but code said
> kokoro). Always reconcile these two sources.

---

## Step 8 — (Daemon only) Create `daemon/{name}-daemon.py`

Only needed if your engine has a slow model load time (> ~1s) and benefits
from staying resident in memory.

Look at `daemon/kitten-daemon.py` for the reference implementation. The daemon:
- Listens on a Unix socket at `~/.local/share/marmalade-tts/{name}.sock`
- Writes its PID to `~/.local/share/marmalade-tts/{name}.pid`
- Accepts newline-delimited JSON: `{"text": "...", "out": "...", "voice": "...", "speed": 1.0}`
- Responds with: `{"ok": true, "out": "..."}` or `{"ok": false, "error": "..."}`

> **Note for pocket:** Pocket TTS loads in ~200ms, so **no daemon is needed**.
> This step was intentionally skipped for pocket.

---

## Step 9 — (Daemon only) Register in `marmalade_tts/daemon.py`

**File:** `marmalade_tts/daemon.py`

Add to `ENGINE_DAEMONS`:

```python
ENGINE_DAEMONS = {
    ...
    "myengine": ("myengine.sock", "myengine.pid",
                 "marmalade-myengine.service", "myengine-daemon.py"),
}
```

Add to `ENGINE_PYTHON` (the venv Python path for the daemon):

```python
ENGINE_PYTHON = {
    ...
    "myengine": [
        os.path.expanduser("~/.local/share/myengine-venv/bin/python"),
    ],
}
```

---

## Step 10 — (Daemon only) Create `systemd/marmalade-{name}.service`

Copy one of the existing service files (e.g. `systemd/marmalade-kitten.service`)
and adapt it. Key things to change:

- `Description=`
- `ExecStart=` — point to the right Python interpreter and daemon script
- `Environment=` — set engine-specific env vars (model path, voice, etc.)

Install the service with the install script or manually:
```bash
cp systemd/marmalade-myengine.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now marmalade-myengine
```

---

## Step 11 — Write Tests

### New file: `tests/test_{name}.py`

```python
"""Tests for the {name} engine."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from marmalade_tts.engines import Engine


def test_myengine_inherits_from_engine():
    from marmalade_tts.engines.myengine import MyEngine
    assert issubclass(MyEngine, Engine)


def test_myengine_has_name():
    from marmalade_tts.engines.myengine import MyEngine
    assert MyEngine.name == "myengine"


def test_list_voices_runs(capsys):
    from marmalade_tts.engines.myengine import MyEngine
    eng = MyEngine({"voice": "voice_one", "device": "cpu"})
    eng.list_voices()
    captured = capsys.readouterr()
    assert "voice_one" in captured.out


def test_synthesize_calls_library(tmp_path):
    from marmalade_tts.engines.myengine import MyEngine
    out_path = str(tmp_path / "out.wav")
    with patch("marmalade_tts.engines.myengine.some_library") as mock_lib:
        mock_lib.synthesize.return_value = b""  # adapt as needed
        eng = MyEngine({"voice": "voice_one", "device": "cpu"})
        eng.synthesize("Hello", out_path)
    mock_lib.synthesize.assert_called_once()
```

### Additions to `tests/test_cli.py`

- Test voice positional parsing: `marmalade-tts myengine voice_one "hello"` → `voice="voice_one"`
- Test `looks_like_voice("myengine", ...)` for valid and invalid tokens
- Test preset resolution for `--fast` / `--balanced` / `--quality`

### Additions to `tests/test_preprocessing.py`

- `assert "myengine" in ENGINE_PROFILES`
- Test that the profile applies the expected rules

### Additions to `tests/test_config.py`

- `assert "myengine" in cfg_mod.DEFAULT_CONFIG["engines"]`
- `assert engine_cfg(config, "myengine")` returns expected defaults

### Additions to `tests/test_init.py`

- `assert "myengine" in ENGINE_ORDER`
- `assert "myengine" in ENGINE_INFO`
- Test that `init_non_interactive(["myengine"])` returns correct defaults
- Test voice validation (invalid voice exits with non-zero code)

### Smoke test (optional, in `tests/test_smoke.py`)

Add a `@pytest.mark.smoke` test that actually synthesises a short utterance.
This only runs when the engine is installed (`pytest -m smoke`).

---

## Step 12 — Update `README.md`

- Add a row to the **Engines** table
- Add a section under **Engines & Voices** with usage examples
- Add preset examples if applicable
- Add a `pocket:` (or your engine's) entry to the **Full config reference** section

---

## Step 13 — Update `INSTALL.md`

`INSTALL.md` documents what the installer does under the hood, plus a
manual-fallback appendix. Add:
- A row to the per-engine reference table (venv, Python, pip, system deps, models)
- A `### myengine` block in the manual-fallback appendix mirroring your recipe

---

## Step 14 — Add an installer recipe

**File:** `marmalade_tts/installer.py` (and `marmalade_tts/models.json` if the
engine needs files fetched).

This is what makes `marmalade-tts init` and `marmalade-tts install myengine`
actually install your engine — do it early in practice, not last; the engine
is not usable hands-off without it.

Add an entry to `INSTALL_RECIPES`:

```python
INSTALL_RECIPES = {
    ...
    "myengine": {
        "python": None,            # or "3.11" if the engine needs a specific version
        "venv": "~/.local/share/myengine-venv",   # MUST match the engine module's
                                                  # venv constant AND daemon.py ENGINE_PYTHON
        "pip": ["myengine-tts"],   # packages / wheel URLs for `uv pip install`
        "pip_post": [],            # extra `uv pip install` invocations, each a list of args
        "system_deps": [],         # e.g. ["espeak-ng"] — installed via the distro pkg manager
        "models": None,            # model-ids from models.json, or None if it auto-downloads
        "warm_cache": None,        # Python snippet run in the venv to pre-download models
        "selftest_text": "Marmalade myengine self test.",
    },
}
```

If the engine needs files that aren't auto-downloaded (a voice model, a
checkpoint), add a `models.json` entry and list its id under `models`:

```json
"myengine-default-voice": {
  "engine": "myengine",
  "files": [
    {
      "dest": "~/.local/share/myengine/voices/default.bin",
      "sha256": null,
      "sources": [
        {"type": "https", "url": "https://.../default.bin"}
      ]
    }
  ]
}
```

> **Critical:** the recipe's `venv` path must be identical to the venv
> constant in `engines/{name}.py` and (for daemon engines) the path in
> `daemon.py`'s `ENGINE_PYTHON`. `test_installer.py` asserts this — keep all
> three in sync. Every engine is invoked by an explicit venv path, never via
> `$PATH` or an in-process import, so the post-install self-test exercises
> the exact code path the CLI uses.

---

## Checklist

Use this before opening a PR or committing a new engine.

### Core integration
- [ ] `engines/{name}.py` — class inherits from `Engine`, has `name = "{name}"`
- [ ] `engines/{name}.py` — `synthesize()` writes a valid WAV to `out_path`
- [ ] `engines/{name}.py` — `list_voices()` prints available voices
- [ ] `cli.py` — imported and added to `ENGINE_CLASSES`
- [ ] `cli.py` — `looks_like_voice()` handles the new engine
- [ ] `cli.py` — preset resolution block handles the new engine (if relevant)
- [ ] `config.py` — added to `DEFAULT_CONFIG["engines"]` with sensible defaults
- [ ] `config.py` — added to `DEFAULT_CONFIG["presets"]` (fast/balanced/quality)
- [ ] `preprocessing.py` — added to `ENGINE_PROFILES` with appropriate rules
- [ ] `completion.py` — added to `ENGINES` list
- [ ] `completion.py` — voice list added and wired into bash/zsh completion
- [ ] `init.py` — added to `ENGINE_INFO` with label/desc/size/default/options
- [ ] `init.py` — added to `ENGINE_ORDER`
- [ ] `init.py` — default-setting clause in `init_non_interactive` / `init_interactive`
- [ ] `config-default.yaml` — engine section added
- [ ] `config-default.yaml` — preset entries added
- [ ] `config-default.yaml` and `config.py` agree on `defaults.engine`

### Daemon (skip if engine loads fast)
- [ ] `daemon/{name}-daemon.py` — socket server implemented
- [ ] `daemon.py` — added to `ENGINE_DAEMONS`
- [ ] `daemon.py` — added to `ENGINE_PYTHON`
- [ ] `systemd/marmalade-{name}.service` — service file created

### Tests
- [ ] `tests/test_{name}.py` — inherits Engine, list_voices, synthesize (mocked)
- [ ] `tests/test_cli.py` — voice positional parsing, looks_like_voice, presets
- [ ] `tests/test_preprocessing.py` — profile exists, rules applied correctly
- [ ] `tests/test_config.py` — in DEFAULT_CONFIG, engine_cfg returns correct defaults
- [ ] `tests/test_init.py` — in ENGINE_ORDER, ENGINE_INFO, voice validation
- [ ] All tests pass: `python -m pytest tests/ -v -m "not smoke"`

### Docs
- [ ] `README.md` — engines table updated
- [ ] `README.md` — usage examples section added
- [ ] `README.md` — config reference includes new engine
- [ ] `INSTALL.md` — per-engine reference table row + manual-fallback block added

### Installer
- [ ] `installer.py` — `INSTALL_RECIPES` entry added with all required keys
- [ ] `installer.py` — recipe `venv` matches the engine module's venv constant
      and `daemon.py` `ENGINE_PYTHON` (test_installer.py asserts this)
- [ ] `models.json` — entry added if the engine needs files fetched (and the
      id is listed under the recipe's `models`)
- [ ] `marmalade-tts install {name}` installs the engine and the self-test passes

---

## Common Mistakes (learn from `pocket`)

The `pocket` engine was added without touching several files. Here's what was
missed and the symptoms each caused:

| File missed | Symptom |
|-------------|---------|
| `engines/pocket.py` missing `Engine` inheritance | `isinstance` checks fail; no `name` attribute |
| `config.py` missing `pocket` in `DEFAULT_CONFIG` | `engine_cfg(config, "pocket")` returns only global defaults |
| `preprocessing.py` missing `pocket` profile | Falls back to `kitten` profile silently — no error |
| `completion.py` missing `pocket` in `ENGINES` | Tab completion doesn't list `pocket` as an engine |
| `config-default.yaml` wrong `defaults.engine` | Docs and code disagree on the default engine |
| `cli.py` dead code referencing undefined `config` | `NameError` if that branch were ever reached |

Run `python -m pytest tests/ -v -m "not smoke"` after each step to catch
integration gaps early.
