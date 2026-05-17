"""SRT / WebVTT subtitle output for synthesized utterance batches.

A "cue" is ``(text, start_s, end_s)``: the user-facing text plus the
half-open time range it covers in the concatenated audio timeline. The
caller is responsible for building the cue list — typically by walking
the synthesized WAVs in order, reading each duration, and inserting a
small gap between consecutive cues so subtitle readers don't show two
cues on rounding edges.

Two writers, one per format. Both create the parent directory if
missing. SRT uses ``HH:MM:SS,mmm`` (comma decimal) — that's the spec,
not a typo. WebVTT uses ``HH:MM:SS.mmm`` and gets a ``WEBVTT`` header.
"""

from __future__ import annotations

import os


Cue = tuple[str, float, float]


def _format_timestamp_srt(seconds: float) -> str:
    """Format ``seconds`` as ``HH:MM:SS,mmm`` (SRT — comma decimal)."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, rem_ms = divmod(total_ms, 3600 * 1000)
    minutes, rem_ms = divmod(rem_ms, 60 * 1000)
    secs, millis = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format ``seconds`` as ``HH:MM:SS.mmm`` (WebVTT — period decimal)."""
    return _format_timestamp_srt(seconds).replace(",", ".")


def _clean_cue_text(text: str) -> str:
    """Strip trailing newlines from cue text. Don't HTML-escape — SRT/VTT
    aren't HTML and naive escaping would mangle perfectly valid user text."""
    return text.rstrip("\n")


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def write_srt(path: str, cues: list[Cue]) -> None:
    """Write ``cues`` as an SRT file at ``path``. Creates parent dir if needed."""
    _ensure_parent_dir(path)
    parts: list[str] = []
    for i, (text, start, end) in enumerate(cues, start=1):
        parts.append(
            f"{i}\n"
            f"{_format_timestamp_srt(start)} --> {_format_timestamp_srt(end)}\n"
            f"{_clean_cue_text(text)}\n"
            f"\n"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))


def write_vtt(path: str, cues: list[Cue]) -> None:
    """Write ``cues`` as a WebVTT file at ``path``. Creates parent dir if needed."""
    _ensure_parent_dir(path)
    parts: list[str] = ["WEBVTT\n\n"]
    for i, (text, start, end) in enumerate(cues, start=1):
        parts.append(
            f"{i}\n"
            f"{_format_timestamp_vtt(start)} --> {_format_timestamp_vtt(end)}\n"
            f"{_clean_cue_text(text)}\n"
            f"\n"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))


# 50ms keeps consecutive cues from overlapping on the rounding edge — SRT
# readers display the cue whose range contains the playhead, and adjacent
# cues whose start exactly equals the prev end can flicker both on screen.
CUE_GAP_S = 0.050


def build_cues(texts: list[str], durations: list[float]) -> list[Cue]:
    """Build a contiguous cue list from per-utterance text + duration.

    Cue 1 starts at 0.0. Each subsequent cue starts at the previous cue's
    end + ``CUE_GAP_S``. The list lengths must match.
    """
    if len(texts) != len(durations):
        raise ValueError(
            f"texts ({len(texts)}) and durations ({len(durations)}) must match"
        )
    cues: list[Cue] = []
    cursor = 0.0
    for text, dur in zip(texts, durations):
        start = cursor
        end = start + max(0.0, float(dur))
        cues.append((text, start, end))
        cursor = end + CUE_GAP_S
    return cues
