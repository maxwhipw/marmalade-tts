# Roadmap

Tracked work for marmalade-tts. Not a promise of order or timing —
contributions welcome on any item.

## In flight

_(nothing currently in flight)_

## Planned

### Unified emoji → emotion mapping across engines

Today emoji-driven expressivity is `emojivoice`-only: an emoji in the
text maps to a per-checkpoint speaker id. Coqui exposes a different
shape — `tts_to_file(emotion=...)` accepts an emotion *string* on
certain models (Tortoise, some VITS variants).

Goal: make the same emoji vocabulary work across engines so an LLM can
emit emoji without knowing which engine is downstream.

- Pull the emoji parser out of `engines/emojivoice.py` into a shared
  module (likely `marmalade_tts/emoji_emotion.py`).
- Each emotion-aware engine registers its own emoji → native mapping:
  - EmojiVoice → speaker id (already)
  - Coqui → emotion string (per-model vocabulary)
  - Future engines → whatever shape they take
- Coarse models collapse many emojis into few emotions; fine models map
  closer to 1:1. The user-facing emoji set stays consistent across
  engines so an LLM can emit emoji without knowing which engine is
  downstream.

### Per-voice descriptions for LLM voice selection

Ship a YAML data file with one prose description per shipped voice
(kokoro, kitten, pocket, emojivoice; skip piper/coqui — too many).
Used by an LLM agent to pick a voice for a given task. Descriptions
must be truthful but tactful — describe the voice's strengths without
inventing flattery, omit rather than spin negatives.

### Coqui voice cloning UX

`--speaker-wav` now works for XTTS models (see
[engine-knobs.md § coqui](engine-knobs.md#coqui)). Future polish:
preset/save "cloned voice" profiles so users don't pass the same WAV
path every invocation.

### Train a kitten-sized expressive engine

Standalone marmalade emoji engine targeting kitten/pocket size
(~25–100MB, real-time CPU). Fine-tune from a commercial-OK emotional
speech dataset (CREMA-D / EmoV-DB / DailyTalk), optionally auto-tag
with Gemma 4 E4B audio-input via Venice. See project memory
`project-emoji-emotion-tts` for the recipe sketch.

### Daemon model-switching

Today every engine's daemon loads one model at startup; `--voice` is
ignored in daemon mode for piper and matcha (silently picks the loaded
model). Either swap-on-demand or fall back to the subprocess path when
the requested voice ≠ the loaded one. Touches piper-daemon, matcha-
daemon, and probably emojivoice-daemon.

### AUR submission

`packaging/aur/PKGBUILD` is in-tree; submission to the official AUR is
pending.

## See also

- [CHANGELOG.md](../CHANGELOG.md) — what shipped, when
- [ENGINE-GUIDE.md](../ENGINE-GUIDE.md) — how to add a new engine
- [engine-knobs.md](engine-knobs.md) — per-engine parameter reference
