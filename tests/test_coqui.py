"""Tests for the Coqui TTS engine — knob propagation through both the
subprocess and daemon code paths."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

from marmalade_tts.engines import Engine


# ── Engine class structure ──────────────────────────────────────────────────


class TestCoquiEngineStructure:
    def test_inherits_from_engine(self):
        from marmalade_tts.engines.coqui import CoquiEngine
        assert issubclass(CoquiEngine, Engine)

    def test_has_name_attribute(self):
        from marmalade_tts.engines.coqui import CoquiEngine
        assert CoquiEngine.name == "coqui"

    def test_default_model(self):
        from marmalade_tts.engines.coqui import CoquiEngine
        eng = CoquiEngine({})
        assert eng.model == "tts_models/en/ljspeech/tacotron2-DDC"

    def test_config_knobs_default_to_none(self):
        # All optional knobs default to None so we know whether to pass them.
        from marmalade_tts.engines.coqui import CoquiEngine
        eng = CoquiEngine({})
        assert eng.speaker is None
        assert eng.speaker_idx is None
        assert eng.language is None
        assert eng.speaker_wav is None
        assert eng.emotion is None


# ── Subprocess path (CLI flags) ─────────────────────────────────────────────


def _mock_subprocess():
    """Patch os.path.exists and subprocess.run; return the mock_run object."""
    fake_proc = MagicMock(returncode=0, stderr=b"")
    exists_patch = patch("marmalade_tts.engines.coqui.os.path.exists",
                         return_value=True)
    run_patch = patch("marmalade_tts.engines.coqui.subprocess.run",
                      return_value=fake_proc)
    return exists_patch, run_patch


class TestCoquiSubprocess:
    def test_speed_now_propagates(self, tmp_path):
        # Regression: previously the wrapper accepted `speed` and silently
        # dropped it. It must now appear on the CLI.
        from marmalade_tts.engines.coqui import CoquiEngine
        exists_patch, run_patch = _mock_subprocess()
        with exists_patch, run_patch as mock_run:
            CoquiEngine({}).synthesize("Hi", str(tmp_path / "o.wav"), speed=1.4)
        cmd = mock_run.call_args[0][0]
        assert "--speed" in cmd
        assert cmd[cmd.index("--speed") + 1] == "1.4"

    def test_speed_1_is_omitted(self, tmp_path):
        # Speed 1.0 is the default — don't add a redundant flag.
        from marmalade_tts.engines.coqui import CoquiEngine
        exists_patch, run_patch = _mock_subprocess()
        with exists_patch, run_patch as mock_run:
            CoquiEngine({}).synthesize("Hi", str(tmp_path / "o.wav"), speed=1.0)
        cmd = mock_run.call_args[0][0]
        assert "--speed" not in cmd

    def test_speaker_kwarg_propagates(self, tmp_path):
        from marmalade_tts.engines.coqui import CoquiEngine
        exists_patch, run_patch = _mock_subprocess()
        with exists_patch, run_patch as mock_run:
            CoquiEngine({}).synthesize("Hi", str(tmp_path / "o.wav"),
                                       speaker="p225")
        cmd = mock_run.call_args[0][0]
        assert "--speaker_idx" in cmd
        assert cmd[cmd.index("--speaker_idx") + 1] == "p225"

    def test_lang_kwarg_propagates(self, tmp_path):
        from marmalade_tts.engines.coqui import CoquiEngine
        exists_patch, run_patch = _mock_subprocess()
        with exists_patch, run_patch as mock_run:
            CoquiEngine({}).synthesize("Hola", str(tmp_path / "o.wav"),
                                       lang="es")
        cmd = mock_run.call_args[0][0]
        assert "--language_idx" in cmd
        assert cmd[cmd.index("--language_idx") + 1] == "es"

    def test_speaker_wav_expands_user_and_propagates(self, tmp_path):
        from marmalade_tts.engines.coqui import CoquiEngine
        exists_patch, run_patch = _mock_subprocess()
        with exists_patch, run_patch as mock_run:
            CoquiEngine({}).synthesize("Hi", str(tmp_path / "o.wav"),
                                       speaker_wav="~/refs/me.wav")
        cmd = mock_run.call_args[0][0]
        assert "--speaker_wav" in cmd
        arg = cmd[cmd.index("--speaker_wav") + 1]
        # ~ was expanded
        assert not arg.startswith("~")
        assert arg.endswith("/refs/me.wav")

    def test_config_values_used_when_no_kwarg(self, tmp_path):
        from marmalade_tts.engines.coqui import CoquiEngine
        exists_patch, run_patch = _mock_subprocess()
        cfg = {"speaker": "p333", "language": "en"}
        with exists_patch, run_patch as mock_run:
            CoquiEngine(cfg).synthesize("Hi", str(tmp_path / "o.wav"))
        cmd = mock_run.call_args[0][0]
        assert "p333" in cmd
        assert "--language_idx" in cmd
        assert cmd[cmd.index("--language_idx") + 1] == "en"

    def test_speaker_name_beats_speaker_idx_in_subprocess(self, tmp_path):
        # When both speaker (name) and speaker_idx (integer) are set, only
        # the named form should appear — otherwise we'd emit --speaker_idx
        # twice and the last one would silently win.
        from marmalade_tts.engines.coqui import CoquiEngine
        exists_patch, run_patch = _mock_subprocess()
        with exists_patch, run_patch as mock_run:
            CoquiEngine({"speaker": "p333", "speaker_idx": 7}).synthesize(
                "Hi", str(tmp_path / "o.wav"))
        cmd = mock_run.call_args[0][0]
        # --speaker_idx appears exactly once, with the named value
        assert cmd.count("--speaker_idx") == 1
        assert cmd[cmd.index("--speaker_idx") + 1] == "p333"

    def test_kwarg_overrides_config(self, tmp_path):
        from marmalade_tts.engines.coqui import CoquiEngine
        exists_patch, run_patch = _mock_subprocess()
        cfg = {"speaker": "p100", "language": "en"}
        with exists_patch, run_patch as mock_run:
            CoquiEngine(cfg).synthesize("Hi", str(tmp_path / "o.wav"),
                                        speaker="p999", lang="es")
        cmd = mock_run.call_args[0][0]
        # The kwarg value, not the config value
        assert "p999" in cmd
        assert "p100" not in cmd
        lang_arg = cmd[cmd.index("--language_idx") + 1]
        assert lang_arg == "es"

    def test_voice_overrides_model(self, tmp_path):
        from marmalade_tts.engines.coqui import CoquiEngine
        exists_patch, run_patch = _mock_subprocess()
        with exists_patch, run_patch as mock_run:
            CoquiEngine({}).synthesize(
                "Hi", str(tmp_path / "o.wav"),
                voice="tts_models/multilingual/multi-dataset/xtts_v2",
            )
        cmd = mock_run.call_args[0][0]
        idx = cmd.index("--model_name")
        assert cmd[idx + 1] == "tts_models/multilingual/multi-dataset/xtts_v2"

    def test_missing_venv_exits(self, tmp_path):
        from marmalade_tts.engines.coqui import CoquiEngine
        with patch("marmalade_tts.engines.coqui.os.path.exists",
                   return_value=False):
            with pytest.raises(SystemExit):
                CoquiEngine({}).synthesize("Hi", str(tmp_path / "o.wav"))


# ── Daemon path ─────────────────────────────────────────────────────────────


class TestCoquiDaemon:
    def test_uses_daemon_when_enabled(self, tmp_path):
        from marmalade_tts.engines.coqui import CoquiEngine
        with patch("marmalade_tts.engines.coqui.dmgr.synthesize") as mock_dmgr:
            CoquiEngine({"daemon": True}).synthesize(
                "Hi", str(tmp_path / "o.wav"))
        mock_dmgr.assert_called_once()
        assert mock_dmgr.call_args[0][0] == "coqui"

    def test_all_knobs_routed_in_daemon_request(self, tmp_path):
        from marmalade_tts.engines.coqui import CoquiEngine
        with patch("marmalade_tts.engines.coqui.dmgr.synthesize") as mock_dmgr:
            CoquiEngine({"daemon": True, "speaker_idx": 5}).synthesize(
                "Hi", str(tmp_path / "o.wav"),
                speed=1.4, speaker="p225", lang="en",
                speaker_wav="/refs/me.wav", emotion="Happy")
        req = mock_dmgr.call_args[0][1]
        assert req["speed"] == 1.4
        assert req["speaker"] == "p225"
        assert req["speaker_idx"] == 5
        assert req["language"] == "en"
        assert req["speaker_wav"] == "/refs/me.wav"
        assert req["emotion"] == "Happy"

    def test_unset_knobs_omitted_from_request(self, tmp_path):
        from marmalade_tts.engines.coqui import CoquiEngine
        with patch("marmalade_tts.engines.coqui.dmgr.synthesize") as mock_dmgr:
            CoquiEngine({"daemon": True}).synthesize(
                "Hi", str(tmp_path / "o.wav"))
        req = mock_dmgr.call_args[0][1]
        # Only the required fields plus the always-set speed
        assert set(req.keys()) == {"text", "out", "speed"}
