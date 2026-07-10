"""Tests for the engines package base — sox_tempo helper, Engine class."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

from marmalade_tts.engines import Engine, EngineError, run_in_venv, sox_tempo


# ── Engine base class ────────────────────────────────────────────────────────


class TestEngineBase:
    def test_synthesize_not_implemented(self):
        eng = Engine()
        try:
            eng.synthesize("hi", "/tmp/x.wav")
        except NotImplementedError:
            return
        raise AssertionError("Engine.synthesize should raise NotImplementedError")

    def test_default_name_is_empty(self):
        assert Engine.name == ""


# ── run_in_venv helper ───────────────────────────────────────────────────────


class TestRunInVenv:
    def test_missing_venv_raises_engine_error_with_hint(self):
        # No subprocess is spawned when the venv binary is absent.
        with patch("marmalade_tts.engines.os.path.exists", return_value=False), \
             patch("marmalade_tts.engines.subprocess.run") as mock_run:
            with pytest.raises(EngineError) as exc:
                run_in_venv("/nope/bin/python", ["/nope/bin/python", "-c", "x"],
                            engine_name="pocket")
        mock_run.assert_not_called()
        assert "pocket" in str(exc.value)
        assert "install pocket" in str(exc.value)

    def test_nonzero_exit_raises_with_decoded_stderr(self):
        fake_proc = MagicMock(returncode=1, stderr=b"kaboom")
        with patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc):
            with pytest.raises(EngineError) as exc:
                run_in_venv("/bin/python", ["/bin/python"], engine_name="kokoro")
        assert "kokoro" in str(exc.value)
        assert "kaboom" in str(exc.value)

    def test_success_passes_env_extra_and_stdin(self):
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run",
                   return_value=fake_proc) as mock_run:
            run_in_venv("/bin/python", ["/bin/python", "hi"],
                        env_extra={"CUDA_VISIBLE_DEVICES": ""},
                        stdin=b"text", engine_name="piper")
        mock_run.assert_called_once()
        # stdin is forwarded via input=, env_extra lands in the passed env.
        assert mock_run.call_args.kwargs["input"] == b"text"
        assert mock_run.call_args.kwargs["env"]["CUDA_VISIBLE_DEVICES"] == ""


# ── sox_tempo helper ─────────────────────────────────────────────────────────


class TestSoxTempo:
    def test_speed_1_is_noop(self, tmp_path):
        # No sox call, no file mutation. The path doesn't even need to exist.
        with patch("marmalade_tts.engines.subprocess.run") as mock_run:
            sox_tempo(str(tmp_path / "nope.wav"), 1.0)
        mock_run.assert_not_called()

    def test_falsy_speed_is_noop(self, tmp_path):
        with patch("marmalade_tts.engines.subprocess.run") as mock_run:
            sox_tempo(str(tmp_path / "x.wav"), 0)
            sox_tempo(str(tmp_path / "x.wav"), None)
        mock_run.assert_not_called()

    def test_missing_sox_warns_and_leaves_file(self, tmp_path, capsys):
        wav = tmp_path / "in.wav"
        wav.write_bytes(b"riff-fake")
        with patch("marmalade_tts.engines.shutil.which", return_value=None), \
             patch("marmalade_tts.engines.subprocess.run") as mock_run:
            sox_tempo(str(wav), 1.4)
        mock_run.assert_not_called()
        assert wav.read_bytes() == b"riff-fake"
        err = capsys.readouterr().err
        assert "sox" in err.lower()

    def test_passes_speed_factor_to_sox(self, tmp_path):
        wav = tmp_path / "in.wav"
        wav.write_bytes(b"original")
        fake_proc = MagicMock(returncode=0, stderr=b"")

        def fake_run(cmd, capture_output):
            # sox writes to cmd[2]; simulate by creating the file
            with open(cmd[2], "wb") as f:
                f.write(b"stretched")
            return fake_proc

        with patch("marmalade_tts.engines.shutil.which", return_value="/usr/bin/sox"), \
             patch("marmalade_tts.engines.subprocess.run", side_effect=fake_run) as mock_run:
            sox_tempo(str(wav), 1.4)
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "sox"
        assert cmd[1] == str(wav)
        # cmd[2] is a tmp WAV; cmd[3:] is the effect
        assert cmd[3] == "tempo"
        assert cmd[4] == "1.4"
        # File was atomically replaced with the stretched output
        assert wav.read_bytes() == b"stretched"

    def test_sox_failure_warns_and_leaves_original(self, tmp_path, capsys):
        wav = tmp_path / "in.wav"
        wav.write_bytes(b"original")
        fake_proc = MagicMock(returncode=1, stderr=b"sox: boom")
        with patch("marmalade_tts.engines.shutil.which", return_value="/usr/bin/sox"), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc):
            sox_tempo(str(wav), 1.4)
        # Original is untouched and a warning was printed
        assert wav.read_bytes() == b"original"
        assert "sox" in capsys.readouterr().err.lower()
