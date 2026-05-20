"""Text chunking and WAV concatenation.

Each engine declares a soft character limit (``MAX_CHARS`` on the engine
class, or ``engines.<name>.max_chars`` in config). When a single user
input exceeds the limit, the CLI silently splits it on sentence
boundaries, synthesizes each chunk, and concatenates the resulting WAVs
into the requested output. The user sees one WAV out for one input in
— that's the contract.

This is **not** batch mode. Batch mode (``--batch``) is the per-line one-
WAV-per-line behavior. Chunking is transparent: it preserves the
input → output count.
"""

from __future__ import annotations

import os
import re
import shutil
import wave

# Sentence boundary: punctuation followed by whitespace. Lookbehind keeps
# the punctuation attached to the preceding chunk.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Paragraph boundary: one or more blank lines.
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into pieces no longer than ``max_chars`` characters.

    Cascade of split strategies, each finer than the last:
      1. Whole text already fits → return ``[text]``.
      2. Paragraph splits (``\\n\\n``); each paragraph chunked recursively.
      3. Sentence splits; sentences greedily packed up to the limit.
      4. Single overlong sentence → word splits.

    Never returns empty strings. Strips whitespace from each piece.
    """
    if max_chars is None or max_chars <= 0 or len(text) <= max_chars:
        return [text] if text.strip() else []

    paragraphs = [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]
    if len(paragraphs) > 1:
        out: list[str] = []
        for p in paragraphs:
            out.extend(chunk_text(p, max_chars))
        return out

    sentences = [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]
    if len(sentences) > 1:
        return _pack_sentences(sentences, max_chars)

    # One long sentence — fall back to word splits.
    return _split_by_words(text, max_chars)


def _pack_sentences(sentences: list[str], max_chars: int) -> list[str]:
    """Greedy bin-pack of sentences up to ``max_chars`` per bin."""
    out: list[str] = []
    cur = ""
    for s in sentences:
        candidate = (cur + " " + s).strip() if cur else s
        if len(candidate) <= max_chars:
            cur = candidate
            continue
        if cur:
            out.append(cur)
        if len(s) <= max_chars:
            cur = s
        else:
            # A single sentence is itself overlong — drop down to words.
            out.extend(_split_by_words(s, max_chars))
            cur = ""
    if cur:
        out.append(cur)
    return out


def _split_by_words(text: str, max_chars: int) -> list[str]:
    words = text.split()
    out: list[str] = []
    cur = ""
    for w in words:
        candidate = (cur + " " + w).strip() if cur else w
        if len(candidate) <= max_chars:
            cur = candidate
        else:
            if cur:
                out.append(cur)
            cur = w  # if a single word is longer than max_chars, it stays as-is
    if cur:
        out.append(cur)
    return out


def concat_wavs(in_paths: list[str], out_path: str) -> None:
    """Concatenate WAVs end-to-end into ``out_path``.

    All inputs must have identical sample rate, channels, and sample width
    — which is always true for chunks produced by the same engine in one
    synthesis call. Empty input list raises ``ValueError``.
    """
    if not in_paths:
        raise ValueError("concat_wavs: no input files")

    if len(in_paths) == 1:
        if os.path.abspath(in_paths[0]) != os.path.abspath(out_path):
            shutil.copyfile(in_paths[0], out_path)
        return

    with wave.open(in_paths[0], "rb") as src:
        nchannels = src.getnchannels()
        sampwidth = src.getsampwidth()
        framerate = src.getframerate()

    with wave.open(out_path, "wb") as dst:
        dst.setnchannels(nchannels)
        dst.setsampwidth(sampwidth)
        dst.setframerate(framerate)
        for p in in_paths:
            with wave.open(p, "rb") as src:
                if (src.getnchannels(), src.getsampwidth(),
                        src.getframerate()) != (nchannels, sampwidth, framerate):
                    raise ValueError(
                        f"concat_wavs: format mismatch — {p} has "
                        f"{src.getnchannels()}ch/{src.getsampwidth()*8}-bit/"
                        f"{src.getframerate()}Hz; expected {nchannels}ch/"
                        f"{sampwidth*8}-bit/{framerate}Hz."
                    )
                dst.writeframes(src.readframes(src.getnframes()))


def resolve_max_chars(engine, eng_cfg: dict) -> int | None:
    """Effective per-engine character limit.

    Config (``engines.<name>.max_chars``) overrides the engine's class
    attribute. ``None``, ``0``, or any non-positive-int value disables
    chunking. Robust to mocked engines (where attribute access can return
    arbitrary objects).
    """
    if "max_chars" in eng_cfg:
        v = eng_cfg["max_chars"]
    else:
        v = getattr(engine, "MAX_CHARS", None)
    # bool is a subclass of int in Python — exclude it explicitly so
    # `MAX_CHARS = True` is treated as "not configured".
    if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
        return None
    return v
