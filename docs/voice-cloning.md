# Voice cloning

Two of marmalade-tts's engines support voice cloning today: **pocket**
(English only, instant) and **coqui** via the **XTTS v2** model
(17 languages, higher quality, larger download).

> **Use only voices you have the right to clone.** Your own voice, a
> voice you have explicit permission to use, or a public-domain /
> commercial-license sample. Cloning a real person's voice without their
> consent — to impersonate them, embarrass them, or put words in their
> mouth — is wrong regardless of what the tool technically permits. The
> CLI doesn't police this; you have to.

## Quick comparison

| Engine     | How you point it at a voice         | Quality      | Latency      | Languages | Reference length |
|------------|-------------------------------------|--------------|--------------|-----------|------------------|
| pocket     | Positional `.wav` path or `.safetensors` | Good         | ~200 ms      | English   | 5–30 s           |
| coqui XTTS | `--speaker-wav PATH`                | Very good    | Several sec  | 17        | 6+ s (clean)     |

Other engines (kitten, kokoro, piper, matcha, emojivoice) don't support
inference-time cloning — to use your own voice on those you'd have to
fine-tune a model, which is training, not cloning. Out of scope for
this guide.

---

## Pocket TTS cloning

The fastest path. Pocket-tts treats any `.wav` file as a voice prompt
— the model conditions on the recording and synthesizes new speech in
that voice.

```bash
# One-shot — voice is the positional argument
marmalade-tts pocket ~/recordings/me.wav "Hello, this should sound like me."

# Or use --voice
marmalade-tts pocket --voice ~/recordings/me.wav "Another line in my voice"

# Set as the default voice in config
marmalade-tts config set engines.pocket.voice ~/recordings/me.wav
marmalade-tts pocket "Now this default plays in my voice"
```

### Recording the reference clip

- **Duration:** 5–30 seconds of clean speech is plenty. Longer doesn't
  help much and slows the load slightly.
- **Sample rate:** 24 kHz or higher (matches pocket's output). 44.1 or
  48 kHz works fine — pocket-tts resamples internally.
- **Format:** mono `.wav`, 16-bit PCM. If you've got stereo or compressed
  audio, convert first with sox:
  `sox in.mp3 -c 1 -r 24000 out.wav`
- **Content:** continuous speech, no music, minimal background noise.
  Reading any paragraph naturally works better than a single sentence.
- **Don't** use heavily filtered/effected audio — the clone will copy
  the effects, not just the voice.

### Faster startup with `.safetensors`

Pocket re-encodes the WAV's voice embedding on every cold start. For a
voice you use frequently, export it once to `.safetensors` for much
faster loading:

```bash
# Inside pocket's venv
~/.local/share/pocket-tts-venv/bin/pocket-tts export-voice \
    ~/recordings/me.wav ~/.config/marmalade-tts/voices/me.safetensors

# Then use the export
marmalade-tts pocket ~/.config/marmalade-tts/voices/me.safetensors "Hello"
marmalade-tts config set engines.pocket.voice ~/.config/marmalade-tts/voices/me.safetensors
```

The `.safetensors` form skips re-encoding on every call.

---

## Coqui XTTS v2 cloning

XTTS v2 is Coqui's multilingual voice-cloning model — pass a reference
WAV and a target language, get speech in that voice in that language.
The voice transfers across languages: clone an English reference, then
synthesize Spanish in the same voice.

### One-time setup

```bash
# Make sure coqui is installed
marmalade-tts install coqui

# Pin XTTS v2 as the active model
marmalade-tts config set engines.coqui.model \
    tts_models/multilingual/multi-dataset/xtts_v2

# (Recommended) enable the daemon — XTTS is slow to load
marmalade-tts config set engines.coqui.daemon true
marmalade-tts daemon start --engine coqui
```

XTTS v2 is a ~1.8 GB download on first use.

### Cloning

```bash
# Clone the speaker, synthesize in English
marmalade-tts coqui --speaker-wav ~/recordings/me.wav \
                    "Hello in my own voice"

# Same voice, Spanish output
marmalade-tts coqui --speaker-wav ~/recordings/me.wav \
                    --lang es \
                    "Hola, soy yo"

# Set a default reference in config so you don't repeat --speaker-wav
marmalade-tts config set engines.coqui.speaker_wav ~/recordings/me.wav
marmalade-tts coqui "This now uses the configured reference"
```

### Reference clip quality

- **Duration:** 6 seconds minimum. 10–30 seconds gives noticeably better
  cloning. Beyond ~30 s the model gains little.
- **Cleanliness matters more than length:** quiet room, single speaker,
  no music, no overlapping voices. Background noise is copied into the
  clone.
- **Mono `.wav` at 22.05 kHz** is what XTTS expects internally. Other
  rates work but get resampled.
- **Language of the reference doesn't need to match the output.** A
  6-second English clip can drive synthesis in any of the 17 supported
  languages (en, es, fr, de, it, pt, pl, tr, ru, nl, cs, ar, zh, ja, hu,
  ko, hi).

### Combining with other knobs

XTTS honors `--speed` and `--lang`. It mostly ignores `--emotion`
(emotion conditioning in XTTS is driven by the reference clip's tone —
record yourself reading happily, get a happier clone). The full
per-engine knob matrix is in [engine-knobs.md § coqui](engine-knobs.md#coqui).

---

## When cloning isn't the right tool

If you want **your voice** as a default for everything you generate,
cloning is right. If you want a specific named persona (Bella, George,
Hugo) the built-in voices on kokoro / kitten / pocket / emojivoice are
better — they're faster, smaller, and have no consent question attached.
See [engine-knobs.md](engine-knobs.md) for the full voice catalog.

If you want a voice that emits emotion via emoji markup (😡 🤣 😍), use
the **emojivoice** engine — it's a different mechanism (per-style
checkpoints, not cloning) but solves a related "I want expressive
output" problem. See the emojivoice section of
[engine-knobs.md](engine-knobs.md#emojivoice).
