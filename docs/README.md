# marmalade-tts documentation

This directory is the canonical source for marmalade-tts docs. Everything
here is markdown — readable in GitHub/Forgejo, in any editor, and by any
LLM that can read files. If we ever want a browsable site, the same files
render via GitHub Pages / Forgejo Pages with no source-format change.

## Contents

- **[Engine knobs](engine-knobs.md)** — every per-engine parameter
  (voice, speed, expressivity knobs, model-specific options) and how to
  pass it from the CLI or config.
- **[Roadmap](ROADMAP.md)** — planned and in-flight work.
- **Setup** → see [INSTALL.md](../INSTALL.md) at the repo root.
- **Adding a new engine** → see [ENGINE-GUIDE.md](../ENGINE-GUIDE.md).
- **Packaging** → see [PACKAGING.md](../PACKAGING.md).

## For LLM consumers

[`/llms.txt`](../llms.txt) at the repo root is the curated entry point —
it lists which document covers which topic, so an agent can fetch only
the file it needs instead of crawling the repo.
