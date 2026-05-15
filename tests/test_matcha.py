"""Tests for the Matcha-TTS engine."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

from marmalade_tts.engines import Engine


# ── Engine class structure ────────────────────────────────────────────────────

class TestMatchaEngineStructure:
    def test_inherits_from_engine(self):
        from marmalade_tts.engines.matcha import MatchaEngine
        assert issubclass(MatchaEngine, Engine)

    def test_has_name_attribute(self):
        from marmalade_tts.engines.matcha import MatchaEngine
        assert MatchaEngine.name == "matcha"

    def test_default_model(self):
        from marmalade_tts.engines.matcha import MatchaEngine
        eng = MatchaEngine({"device": "cpu"})
        assert eng.model == "matcha_ljspeech"

    def test_model_from_config(self):
        from marmalade_tts.engines.matcha import MatchaEngine
        eng = MatchaEngine({"device": "cpu", "model": "matcha_vctk"})
        assert eng.model == "matcha_vctk"

    def test_device_defaults_to_cpu(self):
        from marmalade_tts.engines.matcha import MatchaEngine
        assert MatchaEngine({}).device == "cpu"

    def test_daemon_defaults_false(self):
        from marmalade_tts.engines.matcha import MatchaEngine
        assert MatchaEngine({}).use_daemon is False


# ── _is_checkpoint_path helper ────────────────────────────────────────────────

class TestIsCheckpointPath:
    def test_ckpt_extension(self):
        from marmalade_tts.engines.matcha import _is_checkpoint_path
        assert _is_checkpoint_path("model.ckpt") is True

    def test_path_with_separator(self):
        from marmalade_tts.engines.matcha import _is_checkpoint_path
        assert _is_checkpoint_path("/some/path/model.ckpt") is True
        assert _is_checkpoint_path("~/models/x.ckpt") is True

    def test_plain_model_name_is_not_a_path(self):
        from marmalade_tts.engines.matcha import _is_checkpoint_path
        assert _is_checkpoint_path("matcha_ljspeech") is False
        assert _is_checkpoint_path("matcha_vctk") is False


# ── list_voices ───────────────────────────────────────────────────────────────

class TestMatchaListVoices:
    def test_list_voices_runs(self, capsys):
        from marmalade_tts.engines.matcha import MatchaEngine
        MatchaEngine({"model": "matcha_ljspeech"}).list_voices()
        out = capsys.readouterr().out
        assert "matcha_ljspeech" in out
        assert "matcha_vctk" in out


# ── synthesize (subprocess mocked) ───────────────────────────────────────────

class TestMatchaSynthesize:
    def test_subprocess_invocation(self, tmp_path):
        from marmalade_tts.engines.matcha import MatchaEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.matcha.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.matcha.subprocess.run", return_value=fake_proc) as mock_run, \
             patch("marmalade_tts.engines.matcha.glob.glob", return_value=["/tmp/fake/0.wav"]), \
             patch("marmalade_tts.engines.matcha.shutil.move") as mock_move, \
             patch("marmalade_tts.engines.matcha.shutil.rmtree"):
            eng = MatchaEngine({"device": "cpu", "model": "matcha_ljspeech"})
            eng.synthesize("Hello world", out_path)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "--text" in cmd and "Hello world" in cmd
        assert "--model" in cmd and "matcha_ljspeech" in cmd
        assert "--cpu" in cmd
        mock_move.assert_called_once()

    def test_checkpoint_path_uses_checkpoint_flag(self, tmp_path):
        from marmalade_tts.engines.matcha import MatchaEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.matcha.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.matcha.subprocess.run", return_value=fake_proc) as mock_run, \
             patch("marmalade_tts.engines.matcha.glob.glob", return_value=["/tmp/fake/0.wav"]), \
             patch("marmalade_tts.engines.matcha.shutil.move"), \
             patch("marmalade_tts.engines.matcha.shutil.rmtree"):
            eng = MatchaEngine({"device": "cpu", "model": "/models/custom.ckpt"})
            eng.synthesize("Hi", out_path)
        cmd = mock_run.call_args[0][0]
        assert "--checkpoint_path" in cmd
        assert "--model" not in cmd

    def test_speed_inverts_to_speaking_rate(self, tmp_path):
        # marmalade speed (faster = higher) must invert to Matcha's
        # --speaking_rate (a length scale: higher = slower).
        from marmalade_tts.engines.matcha import MatchaEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.matcha.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.matcha.subprocess.run", return_value=fake_proc) as mock_run, \
             patch("marmalade_tts.engines.matcha.glob.glob", return_value=["/tmp/fake/0.wav"]), \
             patch("marmalade_tts.engines.matcha.shutil.move"), \
             patch("marmalade_tts.engines.matcha.shutil.rmtree"):
            MatchaEngine({"device": "cpu"}).synthesize("Hi", out_path, speed=1.5)
        cmd = mock_run.call_args[0][0]
        assert "--speaking_rate" in cmd
        rate = float(cmd[cmd.index("--speaking_rate") + 1])
        assert rate == pytest.approx(1.0 / 1.5)  # speed 1.5 → length scale < 1

    def test_parentheses_stripped_from_text(self, tmp_path):
        from marmalade_tts.engines.matcha import MatchaEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.matcha.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.matcha.subprocess.run", return_value=fake_proc) as mock_run, \
             patch("marmalade_tts.engines.matcha.glob.glob", return_value=["/tmp/fake/0.wav"]), \
             patch("marmalade_tts.engines.matcha.shutil.move"), \
             patch("marmalade_tts.engines.matcha.shutil.rmtree"):
            MatchaEngine({"device": "cpu"}).synthesize("Hello (aside) world", out_path)
        cmd = mock_run.call_args[0][0]
        text_arg = cmd[cmd.index("--text") + 1]
        assert "(" not in text_arg and ")" not in text_arg
        assert "aside" in text_arg

    def test_default_speed_omits_speaking_rate(self, tmp_path):
        from marmalade_tts.engines.matcha import MatchaEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.matcha.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.matcha.subprocess.run", return_value=fake_proc) as mock_run, \
             patch("marmalade_tts.engines.matcha.glob.glob", return_value=["/tmp/fake/0.wav"]), \
             patch("marmalade_tts.engines.matcha.shutil.move"), \
             patch("marmalade_tts.engines.matcha.shutil.rmtree"):
            MatchaEngine({"device": "cpu"}).synthesize("Hi", out_path, speed=1.0)
        cmd = mock_run.call_args[0][0]
        assert "--speaking_rate" not in cmd

    def test_uses_daemon_when_enabled(self, tmp_path):
        from marmalade_tts.engines.matcha import MatchaEngine
        out_path = str(tmp_path / "out.wav")
        with patch("marmalade_tts.engines.matcha.dmgr.synthesize") as mock_dmgr:
            MatchaEngine({"device": "cpu", "daemon": True}).synthesize("Hello", out_path)
        mock_dmgr.assert_called_once()
        assert mock_dmgr.call_args[0][0] == "matcha"

    def test_missing_venv_exits(self, tmp_path):
        from marmalade_tts.engines.matcha import MatchaEngine
        with patch("marmalade_tts.engines.matcha.os.path.exists", return_value=False):
            with pytest.raises(SystemExit):
                MatchaEngine({"device": "cpu"}).synthesize("Hello", str(tmp_path / "o.wav"))

    def test_failed_subprocess_exits(self, tmp_path):
        from marmalade_tts.engines.matcha import MatchaEngine
        fake_proc = MagicMock(returncode=1, stderr=b"boom")
        with patch("marmalade_tts.engines.matcha.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.matcha.subprocess.run", return_value=fake_proc), \
             patch("marmalade_tts.engines.matcha.shutil.rmtree"):
            with pytest.raises(SystemExit):
                MatchaEngine({"device": "cpu"}).synthesize("Hi", str(tmp_path / "o.wav"))
