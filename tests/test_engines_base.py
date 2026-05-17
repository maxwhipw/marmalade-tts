"""Tests for the engines package base — sox_tempo helper, Engine class."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock

from marmalade_tts.engines import Engine, sox_tempo


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
