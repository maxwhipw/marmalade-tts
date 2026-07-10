"""MCP server — expose marmalade-tts to AI agents.

Three tools, served over stdio:

  - synthesize(text, engine?, voice?, speed?, out_path?)
      Render text to a WAV through the same code path the CLI uses.
  - list_voices(engine?)
      Enumerate shipped voices (kokoro / kitten / pocket / emojivoice).
  - find_voice(description)
      Free-text → ranked voice matches via keyword-overlap scoring.
      No LLM call; pure heuristic, inspectable.

Run with: ``marmalade-tts mcp``.

This module is import-safe without the optional ``mcp`` SDK: the pure
helpers (``list_voices_data``, ``find_voice_matches``, ``synthesize_text``)
are unit-testable on their own. Only ``run()`` actually imports FastMCP.
"""

from __future__ import annotations

import re

from . import config as cfg_mod
from .cli import ENGINE_CLASSES
from .engines import EngineError
from .playback import make_tmp_wav


# ── Voice descriptions ───────────────────────────────────────────────────────
# Curated, tactful, one-line each. Skip piper and coqui — their voices are
# user-installed model paths, not bare names, and an MCP client can't
# enumerate the user's local .onnx / tts_models/... files.

VOICE_DESCRIPTIONS: dict[tuple[str, str], dict[str, str]] = {
    # (engine, voice): {language, description}

    # ── kokoro ──
    ("kokoro", "heart"):      {"language": "American English",
                               "description": "Warm American female, conversational, friendly"},
    ("kokoro", "bella"):      {"language": "American English",
                               "description": "Bright American female, expressive"},
    ("kokoro", "nicole"):     {"language": "American English",
                               "description": "Calm American female, narration"},
    ("kokoro", "adam"):       {"language": "American English",
                               "description": "American male, neutral and clear"},
    ("kokoro", "michael"):    {"language": "American English",
                               "description": "American male, warm and grounded"},
    ("kokoro", "emma"):       {"language": "British English",
                               "description": "British female, articulate"},
    ("kokoro", "isabella"):   {"language": "British English",
                               "description": "British female, polished"},
    ("kokoro", "george"):     {"language": "British English",
                               "description": "British male, warm narrator"},
    ("kokoro", "lewis"):      {"language": "British English",
                               "description": "British male, conversational"},
    ("kokoro", "alpha"):      {"language": "Japanese",
                               "description": "Japanese female, soft (best for Japanese)"},
    ("kokoro", "gongitsune"): {"language": "Japanese",
                               "description": "Japanese female, storyteller (best for Japanese)"},
    ("kokoro", "kumo"):       {"language": "Japanese",
                               "description": "Japanese male, calm (best for Japanese)"},
    ("kokoro", "xiaobei"):    {"language": "Mandarin",
                               "description": "Mandarin female (best for Mandarin)"},
    ("kokoro", "yunjian"):    {"language": "Mandarin",
                               "description": "Mandarin male (best for Mandarin)"},

    # ── kitten ──
    # Kitten ships eight named voices. Descriptions are deliberately neutral
    # where the upstream catalog gives us little to go on — better than
    # inventing flattery.
    ("kitten", "Bella"):  {"language": "English",
                           "description": "Female English voice, bright, lightweight"},
    ("kitten", "Jasper"): {"language": "English",
                           "description": "Male English voice, lightweight"},
    ("kitten", "Luna"):   {"language": "English",
                           "description": "Female English voice, lightweight"},
    ("kitten", "Bruno"):  {"language": "English",
                           "description": "Male English voice, lightweight"},
    ("kitten", "Rosie"):  {"language": "English",
                           "description": "Female English voice, lightweight"},
    ("kitten", "Hugo"):   {"language": "English",
                           "description": "Male English voice, lightweight"},
    ("kitten", "Kiki"):   {"language": "English",
                           "description": "Female English voice, friendly, lightweight, default"},
    ("kitten", "Leo"):    {"language": "English",
                           "description": "Male English voice, lightweight"},

    # ── pocket ──
    ("pocket", "alba"):    {"language": "English",
                            "description": "English-accented female, gentle"},
    ("pocket", "marius"):  {"language": "English",
                            "description": "French male, accented English"},
    ("pocket", "javert"):  {"language": "English",
                            "description": "Stern male, dramatic narrator"},
    ("pocket", "jean"):    {"language": "English",
                            "description": "Male, steady"},
    ("pocket", "fantine"): {"language": "English",
                            "description": "Female, soft and emotive"},
    ("pocket", "cosette"): {"language": "English",
                            "description": "Bright young female"},
    ("pocket", "eponine"): {"language": "English",
                            "description": "Young female, melancholic"},
    ("pocket", "azelma"):  {"language": "English",
                            "description": "Young female"},

    # ── emojivoice ──
    ("emojivoice", "paige"): {"language": "English",
                              "description": "American female, expressive — emoji in text sets the emotional style"},
}


# ── Pure helpers (no mcp dep) ───────────────────────────────────────────────

def list_voices_data(engine: str | None = None) -> list[dict]:
    """Return the shipped voice catalog as a list of dicts.

    Filters to one engine when ``engine`` is given. Engines whose voices are
    user-installed model paths (piper, coqui, matcha) are omitted — an MCP
    client can't enumerate those.
    """
    out = []
    for (eng, name), meta in VOICE_DESCRIPTIONS.items():
        if engine and eng != engine:
            continue
        out.append({
            "name": name,
            "engine": eng,
            "language": meta["language"],
            "description": meta["description"],
        })
    return out


# Tiny stopword set — words that show up in voice descriptions ("voice",
# "english") but that the user almost certainly didn't mean as a filter.
_STOPWORDS = frozenset({
    "a", "an", "the", "of", "for", "to", "and", "or", "in", "on", "at",
    "with", "is", "are", "be", "voice", "sounding", "sound", "sounds",
    "like", "that", "this", "i", "want", "need", "give", "me", "please",
})

# Light synonym mapping — fold common variants onto the canonical term that
# actually appears in our description text. Only real remappings; identity
# entries are redundant now that haystack + query share one tokenizer.
_SYNONYMS = {
    "man": "male", "guy": "male", "boy": "male", "gentleman": "male", "men": "male",
    "woman": "female", "girl": "female", "lady": "female", "women": "female",
    "uk": "british",
    "us": "american",
    "low": "deep",
    "high": "bright", "kid": "young", "child": "young",
    "narration": "narrator", "narrate": "narrator",
}

_TERM_RE = re.compile(r"[a-zA-Z]+")


def _tokenize(description: str) -> list[str]:
    """Lowercase, split into word tokens, drop stopwords, apply synonyms."""
    raw = _TERM_RE.findall(description.lower())
    out = []
    seen = set()
    for term in raw:
        if term in _STOPWORDS:
            continue
        term = _SYNONYMS.get(term, term)
        if term in seen:
            continue
        seen.add(term)
        out.append(term)
    return out


def find_voice_matches(description: str, top_k: int = 3) -> list[dict]:
    """Score voices by keyword overlap with `description`. Top-k descending.

    Word-token set overlap on the description text — "british" matches
    "British English" inside george's description, but "male" no longer
    matches inside "female" (the earlier substring scoring did, which made
    "soothing male" rank Bella at the top). Returns at most `top_k` results,
    each with name, engine, score (matched-term count), and a `why` field
    listing which terms matched.
    """
    terms = _tokenize(description)
    if not terms:
        return []

    scored = []
    for (eng, name), meta in VOICE_DESCRIPTIONS.items():
        # Tokenize the haystack the same way as the query so we do set
        # overlap, not substring match. Language label included so
        # "japanese" matches voices whose description says "Japanese
        # female"; redundant for kokoro but harmless and future-proof.
        haystack_text = meta["description"] + " " + meta["language"] + " " + name
        haystack_tokens = set(_TERM_RE.findall(haystack_text.lower()))
        matched = [t for t in terms if t in haystack_tokens]
        if not matched:
            continue
        scored.append({
            "name": name,
            "engine": eng,
            "score": float(len(matched)),
            "why": "matched: " + ", ".join(matched),
        })

    scored.sort(key=lambda r: (-r["score"], r["engine"], r["name"]))
    return scored[:top_k]


def synthesize_text(
    text: str,
    engine: str | None = None,
    voice: str | None = None,
    speed: float = 1.0,
    out_path: str | None = None,
) -> dict:
    """Render text to a WAV, reusing the CLI's preprocessing + effects flow.

    Returns ``{"out": path, "engine": name, "voice": resolved-voice}``.
    """
    # Lazy-import to avoid a circular import with cli at module load.
    from . import synth

    config = cfg_mod.load()
    engine_name = engine or config.get("defaults", {}).get("engine", "kitten")
    if engine_name not in ENGINE_CLASSES:
        raise ValueError(
            f"Unknown engine: {engine_name!r}. "
            f"Known: {', '.join(ENGINE_CLASSES)}"
        )

    eng_cfg = cfg_mod.engine_cfg(config, engine_name)
    eng = ENGINE_CLASSES[engine_name](eng_cfg)

    out = out_path or make_tmp_wav()

    synth_kwargs: dict = {"speed": speed}
    if voice:
        synth_kwargs["voice"] = voice

    # Engine-default effects (CLI applies these by default; match that here).
    effect_list = config.get("effects", {}).get("defaults", {}).get(engine_name, [])

    # Route through the shared synth loop — same preprocessing rules,
    # same effects pass, same duration measurement as the CLI. MCP always
    # preprocesses (preprocess_mode=True); the per-engine rule list from
    # config still flows through.
    result = synth.synthesize_one(
        text, out,
        engine=eng,
        engine_name=engine_name,
        eng_cfg=eng_cfg,
        config=config,
        synth_kwargs=synth_kwargs,
        effect_list=effect_list,
        preprocess_mode=True,
        custom_rules=None,
    )

    if result is None:
        raise ValueError("No text to synthesize after preprocessing")

    return {
        "out": result.out,
        "engine": engine_name,
        "voice": voice or eng_cfg.get("voice", ""),
    }


# ── MCP server wiring ───────────────────────────────────────────────────────

def run() -> None:
    """Start the stdio MCP server. Imports FastMCP lazily."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("marmalade-tts")

    @mcp.tool()
    def synthesize(
        text: str,
        engine: str | None = None,
        voice: str | None = None,
        speed: float = 1.0,
        out_path: str | None = None,
    ) -> dict:
        """Synthesize `text` to a WAV file.

        Args:
          text: The text to speak.
          engine: kitten | kokoro | piper | coqui | pocket | matcha | emojivoice.
                  Uses the configured default when omitted.
          voice: Voice name (engine-specific). Use `list_voices` or `find_voice`
                 to discover what's available.
          speed: Speech-rate multiplier; 1.0 is natural, 1.4 is fast, 0.8 is slow.
          out_path: Where to write the WAV. A temp file is used when omitted.

        Returns: `{"out": path, "engine": name, "voice": resolved-voice}`,
        or `{"error": "..."}` if synthesis fails (a missing engine venv or a
        subprocess error). A failed synthesis returns an error result — it
        must never take down the server process.
        """
        try:
            return synthesize_text(text, engine=engine, voice=voice,
                                   speed=speed, out_path=out_path)
        except EngineError as e:
            return {"error": str(e)}

    @mcp.tool()
    def list_voices(engine: str | None = None) -> list[dict]:
        """List shipped voices, optionally filtered to one engine.

        Covers kokoro, kitten, pocket, and emojivoice. piper and coqui are
        omitted because their voices are user-installed model paths, not
        bare names.

        Returns a list of `{name, engine, language, description}`.
        """
        return list_voices_data(engine)

    @mcp.tool()
    def find_voice(description: str) -> list[dict]:
        """Find voices matching a free-text description.

        Examples:
          - "warm British male" → george (kokoro)
          - "Japanese female"   → alpha or gongitsune (kokoro)
          - "expressive emoji"  → paige (emojivoice)

        Scoring is keyword-overlap against a curated description table — no
        LLM call. Returns the top 3 matches with a `why` field listing the
        matched terms.
        """
        return find_voice_matches(description)

    mcp.run()
