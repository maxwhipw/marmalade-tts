# scripts/

Helper scripts for common use cases. Copy to `~/.local/bin/` and `chmod +x`.

---

## speak-selection

Speaks the currently **highlighted text** (X11 PRIMARY selection or Wayland primary).

Bind to a KDE global shortcut:
1. Open **System Settings → Shortcuts → Custom Shortcuts**
2. New → Script/Command
3. **Trigger:** keyboard shortcut, e.g. `Meta+Shift+S`
4. **Action:** `~/.local/bin/speak-selection`

Dependencies: `xclip` (X11) or `wl-clipboard` (Wayland)

```sh
sudo apt install xclip          # X11
sudo apt install wl-clipboard   # Wayland
```

---

## speak-clipboard

Speaks the **clipboard** contents (last thing you pressed Ctrl+C on).

Bind to a KDE global shortcut:
1. Same as above, but shortcut `Meta+Shift+C`
2. **Action:** `~/.local/bin/speak-clipboard`

---

## marmalade-pipe

Thin wrapper for shell pipelines — always reads from stdin, never plays automatically.

```sh
echo "Hello world" | marmalade-pipe
cat article.txt | marmalade-pipe --effect robot
cat notes.txt | marmalade-pipe --out spoken.wav
cat README.md | marmalade-pipe --quiet --out out.wav && aplay out.wav
```

All `marmalade-tts` flags pass through.

---

## Agent / script usage

The CLI has first-class support for scripting and agent use:

```sh
# Suppress all status output (exit code is the only signal)
marmalade-tts --quiet "Hello"

# Print only the output WAV path to stdout (capture it in a variable)
WAV=$(marmalade-tts --print-path --no-play "Hello")
aplay "$WAV"

# Get a JSON result for structured consumption
marmalade-tts --json --no-play "Hello"
# → {"ok": true, "engine": "kokoro", "voice": "af_heart", "out": "/tmp/...", ...}

# Read from stdin
echo "Hello" | marmalade-tts --stdin --quiet --out hello.wav

# Pipe-friendly one-liner
echo "Hello from a script" | marmalade-pipe --out greeting.wav
```

Exit codes:
- `0` — synthesis succeeded
- `1` — error (bad args, engine failure, missing text, etc.)
