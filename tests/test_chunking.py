"""Tests for marmalade_tts.chunking — text splitting + WAV concatenation."""

import sys
import os
import wave
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from marmalade_tts.chunking import (
    chunk_text, concat_wavs, resolve_max_chars,
)


# ── chunk_text ───────────────────────────────────────────────────────────────


class TestChunkText:
    def test_short_input_returns_unchunked(self):
        assert chunk_text("Hello world.", max_chars=500) == ["Hello world."]

    def test_empty_returns_empty_list(self):
        assert chunk_text("", max_chars=500) == []
        assert chunk_text("   \n  ", max_chars=500) == []

    def test_zero_or_none_max_chars_disables_chunking(self):
        long = "x " * 1000
        assert chunk_text(long, max_chars=0) == [long]
        assert chunk_text(long, max_chars=None) == [long]

    def test_paragraph_splits_first(self):
        text = "First paragraph here.\n\nSecond paragraph here."
        # max_chars small enough to force a split but each paragraph fits
        chunks = chunk_text(text, max_chars=30)
        assert chunks == ["First paragraph here.", "Second paragraph here."]

    def test_sentences_packed_greedily(self):
        # Three sentences, ~25 chars each. With max=60, expect two chunks
        # (two sentences in the first, one in the second).
        text = "This is sentence one. This is sentence two. This is sentence three."
        chunks = chunk_text(text, max_chars=60)
        assert len(chunks) == 2
        assert "sentence one" in chunks[0]
        assert "sentence two" in chunks[0]
        assert "sentence three" in chunks[1]

    def test_long_single_sentence_falls_back_to_word_split(self):
        # One sentence with no internal periods; must split on words.
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        chunks = chunk_text(text, max_chars=25)
        # Every chunk fits the limit
        assert all(len(c) <= 25 for c in chunks)
        # All input words still present, in order
        joined = " ".join(chunks)
        assert joined.split() == text.split()

    def test_no_chunk_loses_whitespace_but_preserves_words(self):
        text = "a very long sentence that needs to be broken up by words"
        chunks = chunk_text(text, max_chars=20)
        # Reconstructable word list
        assert " ".join(chunks).split() == text.split()

    def test_word_longer_than_limit_kept_as_own_chunk(self):
        text = "antidisestablishmentarianism short"
        chunks = chunk_text(text, max_chars=10)
        # The long word becomes a chunk by itself; "short" follows.
        assert "antidisestablishmentarianism" in chunks
        assert "short" in chunks


# ── concat_wavs ──────────────────────────────────────────────────────────────


def _silent_wav(path: str, duration_s: float = 0.1, rate: int = 22050):
    frames = int(round(duration_s * rate))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)


class TestConcatWavs:
    def test_single_input_copies_to_output(self, tmp_path):
        a = str(tmp_path / "a.wav")
        out = str(tmp_path / "out.wav")
        _silent_wav(a, 0.5)
        concat_wavs([a], out)
        with wave.open(out, "rb") as w:
            assert w.getnframes() > 0

    def test_three_inputs_concatenate(self, tmp_path):
        paths = []
        for i in range(3):
            p = str(tmp_path / f"part-{i}.wav")
            _silent_wav(p, duration_s=0.2)
            paths.append(p)
        out = str(tmp_path / "out.wav")
        concat_wavs(paths, out)

        with wave.open(out, "rb") as w:
            framerate = w.getframerate()
            nframes = w.getnframes()
        # Total duration ≈ 0.6s (3 × 0.2s); allow a frame or two of rounding
        total_s = nframes / framerate
        assert 0.59 <= total_s <= 0.61

    def test_format_mismatch_raises(self, tmp_path):
        a = str(tmp_path / "a.wav")
        b = str(tmp_path / "b.wav")
        _silent_wav(a, duration_s=0.1, rate=22050)
        _silent_wav(b, duration_s=0.1, rate=16000)  # different rate
        with pytest.raises(ValueError, match="format mismatch"):
            concat_wavs([a, b], str(tmp_path / "out.wav"))

    def test_empty_list_raises(self, tmp_path):
        with pytest.raises(ValueError):
            concat_wavs([], str(tmp_path / "out.wav"))


# ── resolve_max_chars ────────────────────────────────────────────────────────


class _DummyEngine:
    MAX_CHARS = 500


class TestResolveMaxChars:
    def test_config_override_wins(self):
        assert resolve_max_chars(_DummyEngine(), {"max_chars": 200}) == 200

    def test_config_null_disables_chunking(self):
        assert resolve_max_chars(_DummyEngine(), {"max_chars": None}) is None

    def test_config_zero_disables_chunking(self):
        assert resolve_max_chars(_DummyEngine(), {"max_chars": 0}) is None

    def test_engine_default_used_when_no_config(self):
        assert resolve_max_chars(_DummyEngine(), {}) == 500

    def test_no_max_chars_anywhere_returns_none(self):
        class NoLimit:
            pass
        assert resolve_max_chars(NoLimit(), {}) is None

    def test_bool_is_not_a_valid_limit(self):
        class BoolEngine:
            MAX_CHARS = True  # would be 1 if we naively coerced
        assert resolve_max_chars(BoolEngine(), {}) is None


# ── Integration: synthesize_one chunks long input transparently ─────────────


class TestSynthesizeOneChunking:
    """When the input exceeds the engine's MAX_CHARS, synth.synthesize_one
    should split the text, call engine.synthesize for each chunk into a
    temp WAV, and concat the result into the requested out_path. The
    user-facing contract: one input → one WAV."""

    def test_long_input_calls_engine_multiple_times(self, tmp_path):
        from unittest.mock import MagicMock
        from marmalade_tts.synth import synthesize_one

        engine = MagicMock()
        engine.MAX_CHARS = 30
        # Each call writes a tiny silent WAV at the requested path.
        engine.synthesize.side_effect = (
            lambda text, out_path, **kw: _silent_wav(out_path, duration_s=0.1)
        )

        # Three sentences that won't fit together in a 30-char chunk.
        text = "First sentence here. Second sentence here. Third sentence here."
        out = str(tmp_path / "combined.wav")

        result = synthesize_one(
            text, out,
            engine=engine, engine_name="kokoro",
            eng_cfg={}, config={"defaults": {"preprocessing": False}},
            synth_kwargs={}, effect_list=[],
            preprocess_mode=False, custom_rules=None,
        )

        assert result is not None
        assert engine.synthesize.call_count >= 2  # at least one split happened
        # Combined output is a real WAV
        with wave.open(out, "rb") as w:
            assert w.getnframes() > 0

    def test_short_input_calls_engine_once(self, tmp_path):
        from unittest.mock import MagicMock
        from marmalade_tts.synth import synthesize_one

        engine = MagicMock()
        engine.MAX_CHARS = 500
        engine.synthesize.side_effect = (
            lambda text, out_path, **kw: _silent_wav(out_path, duration_s=0.1)
        )

        out = str(tmp_path / "single.wav")
        synthesize_one(
            "Short text.", out,
            engine=engine, engine_name="kokoro",
            eng_cfg={}, config={"defaults": {"preprocessing": False}},
            synth_kwargs={}, effect_list=[],
            preprocess_mode=False, custom_rules=None,
        )

        assert engine.synthesize.call_count == 1
        assert engine.synthesize.call_args[0][0] == "Short text."

    def test_config_max_chars_overrides_engine_default(self, tmp_path):
        """engines.<name>.max_chars in config wins over the class attribute."""
        from unittest.mock import MagicMock
        from marmalade_tts.synth import synthesize_one

        engine = MagicMock()
        engine.MAX_CHARS = 9999  # engine default is huge
        engine.synthesize.side_effect = (
            lambda text, out_path, **kw: _silent_wav(out_path, duration_s=0.1)
        )

        out = str(tmp_path / "x.wav")
        # Force chunking via config to a very small value
        synthesize_one(
            "First sentence. Second sentence. Third sentence.",
            out,
            engine=engine, engine_name="kokoro",
            eng_cfg={"max_chars": 20},
            config={"defaults": {"preprocessing": False}},
            synth_kwargs={}, effect_list=[],
            preprocess_mode=False, custom_rules=None,
        )

        assert engine.synthesize.call_count >= 2
