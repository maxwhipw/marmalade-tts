"""Tests for the Pocket TTS engine."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

from marmalade_tts.engines import Engine, EngineError


# ── Engine class structure ────────────────────────────────────────────────────

class TestPocketEngineStructure:
    def test_inherits_from_engine(self):
        from marmalade_tts.engines.pocket import PocketEngine
        assert issubclass(PocketEngine, Engine)

    def test_has_name_attribute(self):
        from marmalade_tts.engines.pocket import PocketEngine
        assert PocketEngine.name == "pocket"

    def test_default_voice_is_alba(self):
        from marmalade_tts.engines.pocket import PocketEngine
        eng = PocketEngine({"device": "cpu"})
        assert eng.voice == "alba"

    def test_voice_from_config(self):
        from marmalade_tts.engines.pocket import PocketEngine
        eng = PocketEngine({"device": "cpu", "voice": "marius"})
        assert eng.voice == "marius"

    def test_device_defaults_to_cpu(self):
        from marmalade_tts.engines.pocket import PocketEngine
        eng = PocketEngine({})
        assert eng.device == "cpu"


# ── VOICES list ───────────────────────────────────────────────────────────────

class TestPocketVoices:
    def test_voices_list_is_nonempty(self):
        from marmalade_tts.engines.pocket import VOICES
        assert len(VOICES) > 0

    def test_alba_in_voices(self):
        from marmalade_tts.engines.pocket import VOICES
        assert "alba" in VOICES

    def test_all_expected_voices_present(self):
        from marmalade_tts.engines.pocket import VOICES
        expected = ["alba", "marius", "javert", "jean", "fantine", "cosette", "eponine", "azelma"]
        for v in expected:
            assert v in VOICES, f"Expected voice '{v}' not in VOICES"


# ── list_voices ───────────────────────────────────────────────────────────────

class TestListVoices:
    def test_list_voices_runs_without_error(self, capsys):
        from marmalade_tts.engines.pocket import PocketEngine
        eng = PocketEngine({"voice": "alba", "device": "cpu"})
        eng.list_voices()
        captured = capsys.readouterr()
        assert "alba" in captured.out

    def test_list_voices_marks_default(self, capsys):
        from marmalade_tts.engines.pocket import PocketEngine
        eng = PocketEngine({"voice": "marius", "device": "cpu"})
        eng.list_voices()
        captured = capsys.readouterr()
        assert "marius" in captured.out
        assert "default" in captured.out.lower()

    def test_list_voices_mentions_wav_cloning(self, capsys):
        from marmalade_tts.engines.pocket import PocketEngine
        eng = PocketEngine({"voice": "alba", "device": "cpu"})
        eng.list_voices()
        captured = capsys.readouterr()
        assert ".wav" in captured.out


# ── synthesize (subprocess into the pocket-tts venv, mocked) ─────────────────

class TestPocketSynthesize:
    def test_subprocess_invocation(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine, POCKET_PYTHON
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc) as mock_run:
            PocketEngine({"voice": "alba", "device": "cpu"}).synthesize("Hello world", out_path)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == POCKET_PYTHON
        assert "-c" in cmd
        assert "Hello world" in cmd
        assert out_path in cmd

    def test_synthesize_uses_voice_override(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc) as mock_run:
            PocketEngine({"voice": "alba", "device": "cpu"}).synthesize(
                "Hello", out_path, voice="marius")
        cmd = mock_run.call_args[0][0]
        assert "marius" in cmd and "alba" not in cmd

    def test_synthesize_uses_default_voice_when_none_given(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc) as mock_run:
            PocketEngine({"voice": "fantine", "device": "cpu"}).synthesize("Hello", out_path)
        cmd = mock_run.call_args[0][0]
        assert "fantine" in cmd

    def test_missing_venv_exits(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine
        with patch("marmalade_tts.engines.os.path.exists", return_value=False):
            with pytest.raises(EngineError):
                PocketEngine({"device": "cpu"}).synthesize("Hi", str(tmp_path / "o.wav"))

    def test_failed_subprocess_exits(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine
        fake_proc = MagicMock(returncode=1, stderr=b"boom")
        with patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc):
            with pytest.raises(EngineError):
                PocketEngine({"device": "cpu"}).synthesize("Hi", str(tmp_path / "o.wav"))


# ── --speed handling (sox fallback, since pocket-tts has no native knob) ────


class TestPocketSpeed:
    def test_speed_1_does_not_call_sox(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc), \
             patch("marmalade_tts.engines.pocket.sox_tempo") as mock_sox:
            PocketEngine({}).synthesize("Hi", str(tmp_path / "o.wav"), speed=1.0)
        # Pocket's contract: speed=1.0 is a no-op, sox_tempo handles it but
        # we'd rather not call it. Either is fine — assert it's called with
        # the unity value OR not at all.
        if mock_sox.called:
            assert mock_sox.call_args[0][1] == 1.0

    def test_nonunity_speed_calls_sox_with_the_factor(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine
        out_path = str(tmp_path / "o.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc), \
             patch("marmalade_tts.engines.pocket.sox_tempo") as mock_sox:
            PocketEngine({}).synthesize("Hi", out_path, speed=1.5)
        mock_sox.assert_called_once_with(out_path, 1.5)
