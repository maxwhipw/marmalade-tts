"""Tests for SRT / WebVTT subtitle output."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from marmalade_tts.subtitles import (
    CUE_GAP_S,
    _format_timestamp_srt,
    _format_timestamp_vtt,
    build_cues,
    write_srt,
    write_vtt,
)


# ── Timestamp formatting ────────────────────────────────────────────────────

class TestTimestampSrt:
    def test_zero(self):
        assert _format_timestamp_srt(0.0) == "00:00:00,000"

    def test_subsecond(self):
        assert _format_timestamp_srt(0.217) == "00:00:00,217"

    def test_short(self):
        assert _format_timestamp_srt(3.217) == "00:00:03,217"

    def test_minute_and_hour(self):
        # 1h 1m 1.5s
        assert _format_timestamp_srt(3661.5) == "01:01:01,500"

    def test_negative_clamped(self):
        # Defensive — negative shouldn't show up but shouldn't crash either
        assert _format_timestamp_srt(-1.0) == "00:00:00,000"

    def test_millisecond_rounding(self):
        # 1.2345 should round to 1.234 or 1.235 (consistent with Python's round)
        # round-half-to-even: 1234.5 → 1234 ms
        ts = _format_timestamp_srt(1.2345)
        assert ts in ("00:00:01,234", "00:00:01,235")


class TestTimestampVtt:
    def test_uses_period_separator(self):
        assert _format_timestamp_vtt(3.217) == "00:00:03.217"

    def test_zero(self):
        assert _format_timestamp_vtt(0.0) == "00:00:00.000"

    def test_hours(self):
        assert _format_timestamp_vtt(3661.5) == "01:01:01.500"


# ── Cue construction ────────────────────────────────────────────────────────

class TestBuildCues:
    def test_gap_between_cues(self):
        cues = build_cues(
            ["a", "b", "c"],
            [1.0, 2.0, 0.5],
        )
        starts = [c[1] for c in cues]
        ends = [c[2] for c in cues]
        # Cue 1: 0.0 → 1.0
        assert starts[0] == 0.0
        assert ends[0] == 1.0
        # Cue 2 starts at end of 1 + 50ms
        assert starts[1] == pytest.approx(1.05)
        assert ends[1] == pytest.approx(3.05)
        # Cue 3 starts at end of 2 + 50ms
        assert starts[2] == pytest.approx(3.10)
        assert ends[2] == pytest.approx(3.60)

    def test_starts_exact_match(self):
        """The headline assertion from the task spec — durations
        [1.0, 2.0, 0.5] → starts [0.0, 1.05, 3.1]."""
        cues = build_cues(["a", "b", "c"], [1.0, 2.0, 0.5])
        starts = [c[1] for c in cues]
        assert starts == pytest.approx([0.0, 1.05, 3.1])

    def test_gap_constant(self):
        assert CUE_GAP_S == 0.050

    def test_text_passed_through_verbatim(self):
        cues = build_cues(["hello world", "second"], [0.5, 0.5])
        assert cues[0][0] == "hello world"
        assert cues[1][0] == "second"

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            build_cues(["a", "b"], [1.0])

    def test_empty(self):
        assert build_cues([], []) == []


# ── SRT writer ──────────────────────────────────────────────────────────────

class TestWriteSrt:
    def test_basic_format(self, tmp_path):
        path = tmp_path / "out.srt"
        cues = [
            ("Hello world", 0.0, 3.217),
            ("This is line two", 3.267, 5.940),
        ]
        write_srt(str(path), cues)
        body = path.read_text(encoding="utf-8")
        assert body == (
            "1\n"
            "00:00:00,000 --> 00:00:03,217\n"
            "Hello world\n"
            "\n"
            "2\n"
            "00:00:03,267 --> 00:00:05,940\n"
            "This is line two\n"
            "\n"
        )

    def test_uses_comma_separator(self, tmp_path):
        path = tmp_path / "out.srt"
        write_srt(str(path), [("x", 0.0, 1.5)])
        body = path.read_text(encoding="utf-8")
        assert "00:00:01,500" in body
        assert "00:00:01.500" not in body

    def test_creates_parent_dir(self, tmp_path):
        path = tmp_path / "subdir" / "deeper" / "out.srt"
        assert not path.parent.exists()
        write_srt(str(path), [("x", 0.0, 1.0)])
        assert path.exists()

    def test_strips_trailing_newline(self, tmp_path):
        path = tmp_path / "out.srt"
        write_srt(str(path), [("hello\n", 0.0, 1.0)])
        body = path.read_text(encoding="utf-8")
        # Cue text "hello" followed by the blank-line cue separator.
        assert "hello\n\n" in body
        assert "hello\n\n\n" not in body

    def test_multiline_text_preserved(self, tmp_path):
        path = tmp_path / "out.srt"
        write_srt(str(path), [("line one\nline two", 0.0, 1.0)])
        body = path.read_text(encoding="utf-8")
        # SRT explicitly allows multi-line cue text.
        assert "line one\nline two\n" in body

    def test_no_html_escape(self, tmp_path):
        path = tmp_path / "out.srt"
        write_srt(str(path), [("<em>I'm</em>", 0.0, 1.0)])
        body = path.read_text(encoding="utf-8")
        assert "<em>I'm</em>" in body
        assert "&lt;" not in body
        assert "&#39;" not in body


# ── VTT writer ──────────────────────────────────────────────────────────────

class TestWriteVtt:
    def test_basic_format(self, tmp_path):
        path = tmp_path / "out.vtt"
        cues = [
            ("Hello world", 0.0, 3.217),
            ("This is line two", 3.267, 5.940),
        ]
        write_vtt(str(path), cues)
        body = path.read_text(encoding="utf-8")
        assert body == (
            "WEBVTT\n"
            "\n"
            "1\n"
            "00:00:00.000 --> 00:00:03.217\n"
            "Hello world\n"
            "\n"
            "2\n"
            "00:00:03.267 --> 00:00:05.940\n"
            "This is line two\n"
            "\n"
        )

    def test_header_present(self, tmp_path):
        path = tmp_path / "out.vtt"
        write_vtt(str(path), [("x", 0.0, 1.0)])
        body = path.read_text(encoding="utf-8")
        assert body.startswith("WEBVTT\n\n")

    def test_uses_period_separator(self, tmp_path):
        path = tmp_path / "out.vtt"
        write_vtt(str(path), [("x", 0.0, 1.5)])
        body = path.read_text(encoding="utf-8")
        assert "00:00:01.500" in body
        assert "00:00:01,500" not in body

    def test_creates_parent_dir(self, tmp_path):
        path = tmp_path / "subdir" / "out.vtt"
        write_vtt(str(path), [("x", 0.0, 1.0)])
        assert path.exists()


# ── End-to-end (cue gap → SRT body) ─────────────────────────────────────────

class TestEndToEnd:
    def test_build_then_write_srt(self, tmp_path):
        """The headline scenario: durations → cues → SRT file with the
        right timestamps and the 50ms gap baked in."""
        path = tmp_path / "out.srt"
        cues = build_cues(["alpha", "beta", "gamma"], [1.0, 2.0, 0.5])
        write_srt(str(path), cues)
        body = path.read_text(encoding="utf-8")
        # Cue 1: 0.000 → 1.000
        assert "00:00:00,000 --> 00:00:01,000\nalpha" in body
        # Cue 2: 1.050 → 3.050
        assert "00:00:01,050 --> 00:00:03,050\nbeta" in body
        # Cue 3: 3.100 → 3.600
        assert "00:00:03,100 --> 00:00:03,600\ngamma" in body
