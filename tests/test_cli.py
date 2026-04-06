"""Tests for CLI argument parsing and dispatch (no synthesis required)."""

import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, call

from marmalade_tts.cli import resolve_text, looks_like_voice, main
from marmalade_tts import __version__


# ── resolve_text ─────────────────────────────────────────────────────────────

class TestResolveText:
    def test_literal(self):
        assert resolve_text("hello world") == "hello world"

    def test_from_file(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("hello from file")
        assert resolve_text(f"@{f}") == "hello from file"

    def test_stdin(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("stdin text"))
        assert resolve_text("-") == "stdin text"

    def test_at_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            resolve_text("@/nonexistent/file.txt")


# ── looks_like_voice ──────────────────────────────────────────────────────────

class TestLooksLikeVoice:
    # Kitten
    def test_kitten_valid_voice(self):
        assert looks_like_voice("kitten", "Kiki") is True

    def test_kitten_invalid_voice(self):
        assert looks_like_voice("kitten", "hello world") is False

    def test_kitten_all_voices(self):
        from marmalade_tts.engines.kitten import VOICES
        for v in VOICES:
            assert looks_like_voice("kitten", v)

    # Kokoro
    def test_kokoro_af_heart(self):
        assert looks_like_voice("kokoro", "af_heart") is True

    def test_kokoro_bm_george(self):
        assert looks_like_voice("kokoro", "bm_george") is True

    def test_kokoro_invalid(self):
        assert looks_like_voice("kokoro", "hello") is False

    # Piper
    def test_piper_onnx(self):
        assert looks_like_voice("piper", "model.onnx") is True

    def test_piper_path(self):
        assert looks_like_voice("piper", "/some/path/model.onnx") is True

    def test_piper_tilde(self):
        assert looks_like_voice("piper", "~/voices/model.onnx") is True

    def test_piper_plain_text(self):
        assert looks_like_voice("piper", "hello world") is False

    # Coqui
    def test_coqui_model(self):
        assert looks_like_voice("coqui", "tts_models/en/ljspeech/tacotron2-DDC") is True

    def test_coqui_plain_text(self):
        assert looks_like_voice("coqui", "hello world") is False


# ── version ───────────────────────────────────────────────────────────────────

def test_version_string():
    assert __version__ == "0.4.0"


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        with patch("sys.argv", ["marmalade-tts", "--version"]):
            main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "0.4.0" in captured.out


# ── --list-effects ────────────────────────────────────────────────────────────

def test_list_effects_flag(capsys):
    with patch("sys.argv", ["marmalade-tts", "--list-effects"]):
        main()
    captured = capsys.readouterr()
    assert "reverb" in captured.out
    assert "robot" in captured.out


# ── --list-rules ──────────────────────────────────────────────────────────────

def test_list_rules_flag(capsys):
    with patch("sys.argv", ["marmalade-tts", "--list-rules"]):
        with patch("marmalade_tts.cli.cfg_mod.load", return_value={
            "defaults": {"engine": "kokoro", "speed": 1.0, "play": False, "preprocessing": True},
            "engines": {"kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"}},
        }):
            main()
    captured = capsys.readouterr()
    assert "currency" in captured.out


# ── completion ────────────────────────────────────────────────────────────────

def test_completion_bash(capsys):
    with patch("sys.argv", ["marmalade-tts", "--completion", "bash"]):
        main()
    captured = capsys.readouterr()
    assert "complete -F _marmalade_tts" in captured.out
    assert "reverb" in captured.out  # effects should be in completion


def test_completion_zsh(capsys):
    with patch("sys.argv", ["marmalade-tts", "--completion", "zsh"]):
        main()
    captured = capsys.readouterr()
    assert "_marmalade-tts" in captured.out


# ── config subcommand ─────────────────────────────────────────────────────────

class TestConfigSubcommand:
    def test_config_show(self, capsys, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path):
            with patch("sys.argv", ["marmalade-tts", "config", "show"]):
                main()
        captured = capsys.readouterr()
        assert "engine" in captured.out

    def test_config_get(self, capsys, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        import marmalade_tts.config as cm
        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path):
            import marmalade_tts.cli as cli_mod
            with patch.object(cli_mod, "cfg_mod", cm):
                with patch("sys.argv", ["marmalade-tts", "config", "get", "defaults.engine"]):
                    main()
        captured = capsys.readouterr()
        # Should print the default engine value
        assert "kokoro" in captured.out or "kitten" in captured.out

    def test_config_get_missing_key_exits(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path):
            with patch("sys.argv", ["marmalade-tts", "config", "get", "no.such.key"]):
                with pytest.raises(SystemExit) as exc:
                    main()
        assert exc.value.code != 0

    def test_config_set(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path):
            with patch("sys.argv", ["marmalade-tts", "config", "set", "defaults.engine", "piper"]):
                main()
        # File should now exist with the right value
        import yaml
        with open(cfg_path) as f:
            saved = yaml.safe_load(f)
        assert saved["defaults"]["engine"] == "piper"


# ── daemon subcommand ─────────────────────────────────────────────────────────

class TestDaemonSubcommand:
    def test_daemon_status(self, capsys):
        fake_status = {
            "kitten": {"running": True, "pid": 12345, "socket": "/tmp/kitten.sock", "service": "x"},
            "kokoro": {"running": False, "pid": None, "socket": None, "service": "x"},
            "piper":  {"running": False, "pid": None, "socket": None, "service": "x"},
            "coqui":  {"running": False, "pid": None, "socket": None, "service": "x"},
        }
        with patch("sys.argv", ["marmalade-tts", "daemon", "status"]):
            with patch("marmalade_tts.daemon.status", return_value=fake_status):
                main()
        captured = capsys.readouterr()
        assert "kitten" in captured.out
        assert "running" in captured.out
        assert "12345" in captured.out

    def test_daemon_stop_not_running_is_noop(self, capsys):
        with patch("sys.argv", ["marmalade-tts", "daemon", "stop", "--engine", "kokoro"]):
            with patch("marmalade_tts.daemon.is_running", return_value=False):
                main()
        # Should not raise


# ── synthesize routing ────────────────────────────────────────────────────────

class TestSynthesizeRouting:
    """Verify that the right engine and options are passed through."""

    def _run_synth(self, argv, engine_mock):
        """Helper: patch the engine's synthesize and run main."""
        fake_config = {
            "defaults": {"engine": "kokoro", "speed": 1.0, "play": False, "preprocessing": False},
            "engines": {
                "kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"},
                "kitten": {"voice": "Kiki", "model_size": "micro", "daemon": False, "device": "cpu"},
                "piper":  {"model": "/dev/null", "daemon": False, "device": "cpu"},
                "coqui":  {"model": "tts_models/en/ljspeech/tacotron2-DDC", "daemon": False, "device": "cpu"},
            },
            "presets": {},
        }
        with patch("sys.argv", argv):
            with patch("marmalade_tts.cli.cfg_mod.load", return_value=fake_config):
                with patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/test.wav"):
                    with patch("marmalade_tts.cli.play_wav"):
                        with patch("marmalade_tts.cli.os.unlink"):
                            with patch("marmalade_tts.cli.os.path.exists", return_value=True):
                                with patch.object(engine_mock, "synthesize") as mock_synth:
                                    main()
                                    return mock_synth

    def test_default_engine_used(self):
        fake_config = {
            "defaults": {"engine": "kokoro", "speed": 1.0, "play": False, "preprocessing": False},
            "engines": {"kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"}},
            "presets": {},
        }
        mock_synth = MagicMock()
        # Patch the engine class inside the ENGINE_CLASSES dict
        with patch("sys.argv", ["marmalade-tts", "hello world"]):
            with patch("marmalade_tts.cli.cfg_mod.load", side_effect=[fake_config, fake_config]):
                with patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"):
                    with patch("marmalade_tts.cli.play_wav"):
                        with patch("marmalade_tts.cli.os.unlink"):
                            with patch("marmalade_tts.cli.os.path.exists", return_value=True):
                                with patch("marmalade_tts.cli.KokoroEngine") as MockKokoro:
                                    MockKokoro.return_value.synthesize = mock_synth
                                    # ENGINE_CLASSES must also be patched to return our mock
                                    with patch.dict("marmalade_tts.cli.ENGINE_CLASSES",
                                                    {"kokoro": MockKokoro}):
                                        main()
        mock_synth.assert_called_once()

    def test_speed_passed_through(self):
        fake_config = {
            "defaults": {"engine": "kokoro", "speed": 1.0, "play": False, "preprocessing": False},
            "engines": {"kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"}},
            "presets": {},
        }
        mock_synth = MagicMock()
        with patch("sys.argv", ["marmalade-tts", "kokoro", "hello", "--speed", "1.5"]):
            with patch("marmalade_tts.cli.cfg_mod.load", return_value=fake_config):
                with patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"):
                    with patch("marmalade_tts.cli.play_wav"):
                        with patch("marmalade_tts.cli.os.unlink"):
                            with patch("marmalade_tts.cli.os.path.exists", return_value=True):
                                with patch("marmalade_tts.cli.KokoroEngine") as MockKokoro:
                                    MockKokoro.return_value.synthesize = mock_synth
                                    with patch.dict("marmalade_tts.cli.ENGINE_CLASSES",
                                                    {"kokoro": MockKokoro}):
                                        main()
        mock_synth.assert_called_once()
        call_kwargs = mock_synth.call_args[1]
        assert call_kwargs.get("speed") == 1.5

    def test_effect_applied_after_synthesis(self):
        from marmalade_tts.engines.kokoro import KokoroEngine
        with patch("marmalade_tts.cli.KokoroEngine") as MockKokoro:
            MockKokoro.return_value.synthesize = MagicMock()
            with patch("marmalade_tts.cli.fx.sox_available", return_value=True):
                with patch("marmalade_tts.cli.fx.apply_effects") as mock_apply:
                    fake_config = {
                        "defaults": {"engine": "kokoro", "speed": 1.0, "play": False, "preprocessing": False},
                        "engines": {"kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"}},
                        "presets": {},
                    }
                    with patch("sys.argv", ["marmalade-tts", "kokoro", "hello", "--effect", "reverb=50"]):
                        with patch("marmalade_tts.cli.cfg_mod.load", return_value=fake_config):
                            with patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"):
                                with patch("marmalade_tts.cli.play_wav"):
                                    with patch("marmalade_tts.cli.os.unlink"):
                                        with patch("marmalade_tts.cli.os.path.exists", return_value=True):
                                            with patch.dict("marmalade_tts.cli.ENGINE_CLASSES",
                                                            {"kokoro": MockKokoro}):
                                                main()
            mock_apply.assert_called_once()
            call_args = mock_apply.call_args
            assert "reverb=50" in call_args[0][2]  # effect spec in 3rd positional arg

    def test_engine_default_effects_applied_when_no_cli_effect(self):
        """effects.defaults.<engine> in config should be used when no --effect is given."""
        with patch("marmalade_tts.cli.KokoroEngine") as MockKokoro:
            MockKokoro.return_value.synthesize = MagicMock()
            with patch("marmalade_tts.cli.fx.sox_available", return_value=True):
                with patch("marmalade_tts.cli.fx.apply_effects") as mock_apply:
                    fake_config = {
                        "defaults": {"engine": "kokoro", "speed": 1.0, "play": False, "preprocessing": False},
                        "engines": {"kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"}},
                        "presets": {},
                        "effects": {"defaults": {"kokoro": ["reverb=20", "bass=3"]}},
                    }
                    with patch("sys.argv", ["marmalade-tts", "kokoro", "hello"]):
                        with patch("marmalade_tts.cli.cfg_mod.load", return_value=fake_config):
                            with patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"):
                                with patch("marmalade_tts.cli.play_wav"):
                                    with patch("marmalade_tts.cli.os.unlink"):
                                        with patch("marmalade_tts.cli.os.path.exists", return_value=True):
                                            with patch.dict("marmalade_tts.cli.ENGINE_CLASSES",
                                                            {"kokoro": MockKokoro}):
                                                main()
            mock_apply.assert_called_once()
            specs = mock_apply.call_args[0][2]
            assert "reverb=20" in specs
            assert "bass=3" in specs

    def test_cli_effects_override_engine_defaults(self):
        """--effect on CLI should completely replace engine defaults, not stack."""
        with patch("marmalade_tts.cli.KokoroEngine") as MockKokoro:
            MockKokoro.return_value.synthesize = MagicMock()
            with patch("marmalade_tts.cli.fx.sox_available", return_value=True):
                with patch("marmalade_tts.cli.fx.apply_effects") as mock_apply:
                    fake_config = {
                        "defaults": {"engine": "kokoro", "speed": 1.0, "play": False, "preprocessing": False},
                        "engines": {"kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"}},
                        "presets": {},
                        "effects": {"defaults": {"kokoro": ["reverb=20"]}},
                    }
                    with patch("sys.argv", ["marmalade-tts", "kokoro", "hello", "--effect", "pitch=300"]):
                        with patch("marmalade_tts.cli.cfg_mod.load", return_value=fake_config):
                            with patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"):
                                with patch("marmalade_tts.cli.play_wav"):
                                    with patch("marmalade_tts.cli.os.unlink"):
                                        with patch("marmalade_tts.cli.os.path.exists", return_value=True):
                                            with patch.dict("marmalade_tts.cli.ENGINE_CLASSES",
                                                            {"kokoro": MockKokoro}):
                                                main()
            mock_apply.assert_called_once()
            specs = mock_apply.call_args[0][2]
            assert "pitch=300" in specs
            assert "reverb=20" not in specs  # engine default was NOT merged in

    def test_missing_sox_warns_and_continues(self, capsys):
        """When sox is absent, a note is printed but synthesis still completes."""
        with patch("marmalade_tts.cli.KokoroEngine") as MockKokoro:
            MockKokoro.return_value.synthesize = MagicMock()
            with patch("marmalade_tts.cli.fx.sox_available", return_value=False):
                fake_config = {
                    "defaults": {"engine": "kokoro", "speed": 1.0, "play": False, "preprocessing": False},
                    "engines": {"kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"}},
                    "presets": {},
                }
                with patch("sys.argv", ["marmalade-tts", "kokoro", "hello", "--effect", "reverb=50"]):
                    with patch("marmalade_tts.cli.cfg_mod.load", return_value=fake_config):
                        with patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"):
                            with patch("marmalade_tts.cli.play_wav"):
                                with patch("marmalade_tts.cli.os.unlink"):
                                    with patch("marmalade_tts.cli.os.path.exists", return_value=True):
                                        with patch.dict("marmalade_tts.cli.ENGINE_CLASSES",
                                                        {"kokoro": MockKokoro}):
                                            main()  # must NOT raise or sys.exit
        captured = capsys.readouterr()
        assert "sox" in captured.err.lower()
        assert "skipped" in captured.err.lower() or "not installed" in captured.err.lower()
