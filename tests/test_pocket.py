"""Tests for the Pocket TTS engine."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

from marmalade_tts.engines import Engine


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


# ── synthesize (mocked pocket_tts) ───────────────────────────────────────────

# Synthesize tests need numpy because pocket's mocked audio array is
# generated with np.zeros. The structural / VOICES / list_voices tests above
# don't need numpy and should always run.
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # noqa: F811


@pytest.mark.skipif(not HAS_NUMPY, reason="numpy not installed")
class TestPocketSynthesize:
    def _make_mock_pocket_tts(self, audio_data=None):
        """Build a mock pocket_tts module."""
        mock_model = MagicMock()
        mock_model.sample_rate = 22050
        if audio_data is None:
            # Small silent audio array (numpy is guaranteed by importorskip above)
            audio_data = MagicMock()
            audio_data.numpy.return_value = np.zeros(100, dtype="float32")
        mock_model.generate_audio.return_value = audio_data
        mock_model.get_state_for_audio_prompt.return_value = MagicMock()

        mock_tts_module = MagicMock()
        mock_tts_module.TTSModel.load_model.return_value = mock_model

        return mock_tts_module, mock_model

    def _make_mock_scipy(self):
        """Build a mock scipy.io.wavfile module."""
        mock_scipy = MagicMock()
        mock_scipy_io = MagicMock()
        mock_scipy_io_wavfile = MagicMock()
        mock_scipy.io = mock_scipy_io
        mock_scipy_io.wavfile = mock_scipy_io_wavfile
        return mock_scipy, mock_scipy_io, mock_scipy_io_wavfile

    def _patch_scipy(self):
        """Return a patch.dict context that injects mock scipy modules."""
        mock_scipy = MagicMock()
        mock_io = MagicMock()
        mock_wavfile = MagicMock()
        mock_scipy.io = mock_io
        mock_io.wavfile = mock_wavfile
        return {
            "scipy": mock_scipy,
            "scipy.io": mock_io,
            "scipy.io.wavfile": mock_wavfile,
        }, mock_wavfile

    def test_synthesize_calls_generate_audio(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine
        import marmalade_tts.engines.pocket as pocket_mod

        out_path = str(tmp_path / "out.wav")
        mock_tts, mock_model = self._make_mock_pocket_tts()
        scipy_modules, mock_wavfile = self._patch_scipy()

        # Reset module-level cache so our mock is used
        pocket_mod._model = None
        pocket_mod._voice_states = {}

        with patch.dict("sys.modules", {"pocket_tts": mock_tts, **scipy_modules}):
            eng = PocketEngine({"voice": "alba", "device": "cpu"})
            eng.synthesize("Hello world", out_path)

        mock_model.generate_audio.assert_called_once()
        mock_wavfile.write.assert_called_once()

    def test_synthesize_uses_voice_override(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine
        import marmalade_tts.engines.pocket as pocket_mod

        out_path = str(tmp_path / "out.wav")
        mock_tts, mock_model = self._make_mock_pocket_tts()
        scipy_modules, _ = self._patch_scipy()
        pocket_mod._model = None
        pocket_mod._voice_states = {}

        with patch.dict("sys.modules", {"pocket_tts": mock_tts, **scipy_modules}):
            eng = PocketEngine({"voice": "alba", "device": "cpu"})
            eng.synthesize("Hello", out_path, voice="marius")

        # get_state_for_audio_prompt should have been called with "marius", not "alba"
        mock_model.get_state_for_audio_prompt.assert_called_once_with("marius")

    def test_synthesize_caches_voice_state(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine
        import marmalade_tts.engines.pocket as pocket_mod

        out_path = str(tmp_path / "out.wav")
        mock_tts, mock_model = self._make_mock_pocket_tts()
        scipy_modules, _ = self._patch_scipy()
        pocket_mod._model = None
        pocket_mod._voice_states = {}

        with patch.dict("sys.modules", {"pocket_tts": mock_tts, **scipy_modules}):
            eng = PocketEngine({"voice": "alba", "device": "cpu"})
            eng.synthesize("First", out_path)
            eng.synthesize("Second", out_path)

        # get_state_for_audio_prompt should be called only once (cached after first call)
        assert mock_model.get_state_for_audio_prompt.call_count == 1

    def test_synthesize_uses_default_voice_when_none_given(self, tmp_path):
        from marmalade_tts.engines.pocket import PocketEngine
        import marmalade_tts.engines.pocket as pocket_mod

        out_path = str(tmp_path / "out.wav")
        mock_tts, mock_model = self._make_mock_pocket_tts()
        scipy_modules, _ = self._patch_scipy()
        pocket_mod._model = None
        pocket_mod._voice_states = {}

        with patch.dict("sys.modules", {"pocket_tts": mock_tts, **scipy_modules}):
            eng = PocketEngine({"voice": "fantine", "device": "cpu"})
            eng.synthesize("Hello", out_path)  # no voice= kwarg

        mock_model.get_state_for_audio_prompt.assert_called_once_with("fantine")
