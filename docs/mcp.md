# MCP server

marmalade-tts ships an optional [Model Context Protocol](https://modelcontextprotocol.io/)
server so AI agents (Claude Code, Claude Desktop, any MCP-aware client) can
drive it directly: pick a voice, synthesize speech, get back a WAV path.

## Install

```sh
pip install marmalade-tts[mcp]
# or, with pipx:
pipx install 'marmalade-tts[mcp]'
```

This pulls in the [`mcp`](https://pypi.org/project/mcp/) Python SDK. Engines
themselves are installed the usual way (`marmalade-tts init` /
`marmalade-tts install <engine>`).

## Hook it up

### Claude Code

```sh
claude mcp add marmalade-tts -- marmalade-tts mcp
```

### Claude Desktop

Add this to your `claude_desktop_config.json` (path varies by OS — see the
[Claude Desktop docs](https://modelcontextprotocol.io/quickstart/user)):

```json
{
  "mcpServers": {
    "marmalade-tts": {
      "command": "marmalade-tts",
      "args": ["mcp"]
    }
  }
}
```

### Any other MCP client

Run `marmalade-tts mcp` as a stdio subprocess. That's the whole protocol.

## Tools

### `synthesize`

Render text to a WAV file.

| Arg | Type | Notes |
|-----|------|-------|
| `text` | string, required | The text to speak |
| `engine` | string, optional | `kitten` / `kokoro` / `piper` / `coqui` / `pocket` / `matcha` / `emojivoice`. Uses the configured default when omitted. |
| `voice` | string, optional | Voice name — engine-specific. Discover with `list_voices` / `find_voice`. |
| `speed` | number, default `1.0` | Speech-rate multiplier. |
| `out_path` | string, optional | Where to write the WAV. A temp file is used when omitted. |

Returns `{"out": "/path/to/file.wav", "engine": "kokoro", "voice": "george"}`.

### `list_voices`

List shipped voices, with one-line descriptions.

| Arg | Type | Notes |
|-----|------|-------|
| `engine` | string, optional | Filter to one engine. |

Returns a list of `{name, engine, language, description}`. Covers `kokoro`,
`kitten`, `pocket`, and `emojivoice`. `piper` and `coqui` are omitted —
their voices are user-installed model paths, not bare names, so an MCP
client can't enumerate them anyway.

### `find_voice`

Free-text → ranked voice matches. **The headline tool.**

| Arg | Type | Notes |
|-----|------|-------|
| `description` | string, required | e.g. "warm British male", "energetic young female", "deep narrator" |

Returns the top 3 matches, each `{name, engine, score, why}`. Scoring is
pure keyword overlap against the curated description table — no LLM call.
The `why` field lists which terms matched, so the agent can see why a voice
came back.

## Example

A typical agent flow:

1. `find_voice("warm British male narrator")` → `george (kokoro)` top.
2. `synthesize("Once upon a time…", engine="kokoro", voice="george")`
   → `{"out": "/tmp/…wav", …}`.
3. Agent plays / attaches the WAV.

## Limitations

- `find_voice` is a keyword matcher, not a semantic embedding search.
  "soothing" won't match "calm" unless they share a literal substring.
  Pragmatic synonyms (`man` → `male`, `lady` → `female`) are handled
  explicitly.
- Voice descriptions for `kitten` voices are deliberately neutral —
  upstream provides little to characterize them beyond the names.
- Voices that depend on user-installed model files (piper `.onnx`,
  coqui `tts_models/...`, matcha custom checkpoints) are intentionally
  not exposed by `list_voices` / `find_voice`.
