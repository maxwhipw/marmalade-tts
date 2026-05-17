"""Tests for streaming batch playback.

Batch playback is *streaming*: a producer thread renders utterances
sequentially while the main thread plays each WAV as soon as it lands in
the queue. Playback of line N starts while line N+1 is still being
synthesized in the background — the first line plays almost immediately
and the rest stream behind it.

These tests exercise the orchestration in cli.py with the engine and
audio player mocked, asserting:
  * total wall time is meaningfully less than fully-sequential time
    (the second synth overlaps with the first playback)
  * playback happens in input order
  * subtitles still describe every successfully rendered utterance
  * a synth error mid-batch lets already-played lines finish, then
    propagates as the original exception
  * single-utterance is unchanged (no thread spawned)
"""

import os
import sys
import time
import threading
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from marmalade_tts.cli import main


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cfg() -> dict:
    """Minimal config: kokoro default, batch text reads as 3 lines, no
    preprocessing so the mocked engine sees the lines verbatim."""
    return {
        "defaults": {"engine": "kokoro", "speed": 1.0, "play": True,
                     "preprocessing": False},
        "engines": {
            "kokoro": {"voice": "af_heart", "lang": "a", "daemon": False,
                       "device": "cpu"},
        },
        "presets": {},
        "aliases": {},
    }


def _slow_synth(delay_s: float):
    """Build a synthesize() mock that writes an empty file and sleeps."""
    def fake(text, out_path, **kwargs):
        # Write *something* so duration measurement (and any callers checking
        # existence) don't error.
        with open(out_path, "wb") as f:
            # A 44-byte minimal-ish WAV header isn't worth faking — we mock
            # wav_duration too. Just create the file.
            f.write(b"")
        time.sleep(delay_s)
    return fake


def _slow_play(delay_s: float, log: list):
    """Build a play_wav() mock that records the path and sleeps."""
    def fake(path):
        log.append(path)
        time.sleep(delay_s)
    return fake


def _tmp_wav_factory(tmp_path):
    """Hand out a fresh tmp-WAV path per call so each utterance gets its own."""
    counter = {"n": 0}
    def make():
        counter["n"] += 1
        return str(tmp_path / f"stream-{counter['n']}.wav")
    return make


def _run_main(argv, cfg, tmp_path, *, synth_delay=0.05, play_delay=0.10,
              synth_side_effect=None):
    """Run main() with engine + playback mocked, capturing the call order."""
    play_log: list = []
    fake_synth = synth_side_effect or _slow_synth(synth_delay)
    fake_play = _slow_play(play_delay, play_log)
    make_tmp = _tmp_wav_factory(tmp_path)

    MockEngine = MagicMock()
    MockEngine.return_value.synthesize = MagicMock(side_effect=fake_synth)

    with patch("sys.argv", argv), \
         patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
         patch("marmalade_tts.cli.make_tmp_wav", side_effect=make_tmp), \
         patch("marmalade_tts.cli.play_wav", side_effect=fake_play), \
         patch("marmalade_tts.cli.wav_duration", return_value=0.5), \
         patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockEngine}):
        main()

    return play_log, MockEngine


# ── Streaming overlap ────────────────────────────────────────────────────────

class TestStreamingOverlap:
    def test_batch_playback_overlaps_with_synthesis(self, tmp_path):
        """Three utterances at 50ms synth + 100ms play.

        Fully sequential would be 3 * (50 + 100) = 450ms. Streaming should
        let synth N+1 happen while play N is running, so the total is
        closer to: 50 (first synth) + 3 * 100 (three plays) = 350ms,
        with maybe a few ms of overhead. Tolerant bound (<400ms) keeps
        this from being flaky on a slow CI."""
        t0 = time.monotonic()
        play_log, _ = _run_main(
            ["marmalade-tts", "kokoro", "--text", "alpha\nbeta\ngamma"],
            _cfg(), tmp_path, synth_delay=0.05, play_delay=0.10,
        )
        elapsed = time.monotonic() - t0
        assert len(play_log) == 3
        assert elapsed < 0.40, (
            f"streaming should overlap synth with play; got {elapsed:.3f}s"
        )

    def test_playback_order_matches_input(self, tmp_path):
        """Even though synthesis happens on a background thread, playback
        consumes the queue in FIFO order, which is input order."""
        play_log, _ = _run_main(
            ["marmalade-tts", "kokoro", "--text", "alpha\nbeta\ngamma"],
            _cfg(), tmp_path, synth_delay=0.01, play_delay=0.01,
        )
        # We don't know the exact tmp filenames, but we do know the order
        # they were minted (stream-1, stream-2, stream-3).
        assert [os.path.basename(p) for p in play_log] == [
            "stream-1.wav", "stream-2.wav", "stream-3.wav",
        ]


# ── Subtitles still work in streaming mode ──────────────────────────────────

class TestStreamingSubtitles:
    def test_srt_written_with_all_cues_after_streaming_run(self, tmp_path):
        srt_path = tmp_path / "out.srt"
        _run_main(
            ["marmalade-tts", "kokoro",
             "--text", "alpha\nbeta\ngamma",
             "--srt", str(srt_path)],
            _cfg(), tmp_path, synth_delay=0.01, play_delay=0.01,
        )
        body = srt_path.read_text(encoding="utf-8")
        # All three cue texts present, cumulative timing preserved
        # (wav_duration is mocked to return 0.5s, plus the 50ms gap).
        assert "alpha" in body
        assert "beta" in body
        assert "gamma" in body
        # Cue 1: 0.000 → 0.500
        assert "00:00:00,000 --> 00:00:00,500" in body
        # Cue 2: 0.550 → 1.050
        assert "00:00:00,550 --> 00:00:01,050" in body
        # Cue 3: 1.100 → 1.600
        assert "00:00:01,100 --> 00:00:01,600" in body


# ── Error propagation ──────────────────────────────────────────────────────

class TestStreamingErrorPropagation:
    def test_error_on_second_line_lets_first_play_then_raises(self, tmp_path):
        """Producer raises on utterance 2. Utterance 1 must still play to
        completion. After the consumer drains the queue, the original
        exception propagates so the process exits non-zero."""
        play_log: list = []
        calls = {"n": 0}

        def fake_synth(text, out_path, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom on line 2")
            with open(out_path, "wb") as f:
                f.write(b"")
            time.sleep(0.01)

        srt_path = tmp_path / "out.srt"
        with pytest.raises(RuntimeError, match="boom on line 2"):
            _run_main(
                ["marmalade-tts", "kokoro",
                 "--text", "alpha\nbeta\ngamma",
                 "--srt", str(srt_path)],
                _cfg(), tmp_path,
                synth_side_effect=fake_synth, play_delay=0.01,
            )
        # First line played, second never did (synth failed before it could
        # be enqueued), third never reached.
        # We can't capture the play log directly from _run_main when it
        # raises — re-do it manually for the assertion:
        # but simpler: assert via subtitles which the streaming path writes
        # *before* re-raising.
        body = srt_path.read_text(encoding="utf-8")
        assert "alpha" in body
        # gamma never reached the producer; beta failed before enqueue.
        assert "beta" not in body
        assert "gamma" not in body

    def test_error_path_still_plays_completed_line(self, tmp_path):
        """Same as above but observing the play log directly via a wrapper."""
        play_log: list = []
        calls = {"n": 0}

        def fake_synth(text, out_path, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom")
            with open(out_path, "wb") as f:
                f.write(b"")
            time.sleep(0.01)

        def fake_play(path):
            play_log.append(path)
            time.sleep(0.01)

        MockEngine = MagicMock()
        MockEngine.return_value.synthesize = MagicMock(side_effect=fake_synth)
        make_tmp = _tmp_wav_factory(tmp_path)

        with patch("sys.argv",
                   ["marmalade-tts", "kokoro", "--text", "alpha\nbeta\ngamma"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=_cfg()), \
             patch("marmalade_tts.cli.make_tmp_wav", side_effect=make_tmp), \
             patch("marmalade_tts.cli.play_wav", side_effect=fake_play), \
             patch("marmalade_tts.cli.wav_duration", return_value=0.5), \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES",
                        {"kokoro": MockEngine}):
            with pytest.raises(RuntimeError, match="boom"):
                main()

        assert len(play_log) == 1
        assert os.path.basename(play_log[0]) == "stream-1.wav"


# ── Single-utterance path is unchanged ──────────────────────────────────────

class TestSingleUtteranceUnchanged:
    def test_single_utterance_spawns_no_thread(self, tmp_path):
        """Single-utterance playback uses the straight-line code path —
        no producer thread is started. We check by counting Thread() calls
        between before and after main() (excluding daemon-internal threads)."""
        play_log: list = []
        fake_synth = _slow_synth(0.0)
        fake_play = _slow_play(0.0, play_log)
        make_tmp = _tmp_wav_factory(tmp_path)

        MockEngine = MagicMock()
        MockEngine.return_value.synthesize = MagicMock(side_effect=fake_synth)

        threads_before = set(threading.enumerate())

        with patch("sys.argv", ["marmalade-tts", "kokoro", "--text", "only one"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=_cfg()), \
             patch("marmalade_tts.cli.make_tmp_wav", side_effect=make_tmp), \
             patch("marmalade_tts.cli.play_wav", side_effect=fake_play), \
             patch("marmalade_tts.cli.wav_duration", return_value=0.5), \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockEngine}):
            main()

        # Either no new threads, or only threads that aren't our producer.
        # (Other test infrastructure might have background threads — filter
        # by name to be precise.)
        new_threads = set(threading.enumerate()) - threads_before
        producer_threads = [t for t in new_threads
                            if t.name == "marmalade-producer"]
        assert producer_threads == []
        assert len(play_log) == 1


# ── No-play path is unchanged ──────────────────────────────────────────────

class TestNoPlayPathUnchanged:
    def test_no_play_with_batch_spawns_no_thread(self, tmp_path):
        """`--no-play` with a multi-line batch should NOT trigger streaming
        (nothing to overlap with — no playback at all)."""
        out_dir = tmp_path / "out"
        threads_before = set(threading.enumerate())

        MockEngine = MagicMock()
        MockEngine.return_value.synthesize = MagicMock(
            side_effect=_slow_synth(0.0))

        with patch("sys.argv",
                   ["marmalade-tts", "kokoro",
                    "--text", "alpha\nbeta\ngamma",
                    "--no-play", "--out-dir", str(out_dir)]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=_cfg()), \
             patch("marmalade_tts.cli.play_wav") as pw, \
             patch("marmalade_tts.cli.wav_duration", return_value=0.5), \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockEngine}):
            main()

        new_threads = set(threading.enumerate()) - threads_before
        assert [t for t in new_threads
                if t.name == "marmalade-producer"] == []
        pw.assert_not_called()
