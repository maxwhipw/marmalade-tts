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

    # Pocket
    def test_pocket_builtin_voice(self):
        assert looks_like_voice("pocket", "alba") is True

    def test_pocket_wav_path(self):
        assert looks_like_voice("pocket", "my_voice.wav") is True

    def test_pocket_safetensors_path(self):
        assert looks_like_voice("pocket", "speaker.safetensors") is True

    def test_pocket_all_builtin_voices(self):
        from marmalade_tts.engines.pocket import VOICES
        for v in VOICES:
            assert looks_like_voice("pocket", v)

    def test_pocket_plain_text(self):
        assert looks_like_voice("pocket", "hello world") is False


# ── version ───────────────────────────────────────────────────────────────────

def test_version_string():
    # Match semver-ish (e.g. 0.4.2, 1.0.0-rc1) so we don't have to update tests on every bump
    import re
    assert re.match(r"^\d+\.\d+\.\d+", __version__), f"Bad version: {__version__!r}"


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        with patch("sys.argv", ["marmalade-tts", "--version"]):
            main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


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


# ── Voice positional argument parsing ──────────────────────────────────────────────

class TestVoicePositional:
    """marmalade-tts kitten Kiki 'hello' should pass voice='Kiki' to synthesize."""

    def _run_with_voice(self, argv, engine_cls_name, engine_mock_cls):
        fake_config = {
            "defaults": {"engine": "kitten", "speed": 1.0, "play": False, "preprocessing": False},
            "engines": {
                "kitten": {"voice": "Kiki", "model_size": "micro", "daemon": False, "device": "cpu"},
                "kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"},
                "pocket": {"voice": "alba", "device": "cpu"},
            },
            "presets": {},
        }
        mock_synth = MagicMock()
        with patch("sys.argv", argv), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=fake_config), \
             patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"), \
             patch("marmalade_tts.cli.play_wav"), \
             patch("marmalade_tts.cli.os.unlink"), \
             patch("marmalade_tts.cli.os.path.exists", return_value=True), \
             patch(f"marmalade_tts.cli.{engine_cls_name}") as MockEngine, \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {argv[1]: MockEngine}):
            MockEngine.return_value.synthesize = mock_synth
            main()
        return mock_synth

    def test_kitten_voice_positional(self):
        mock_synth = self._run_with_voice(
            ["marmalade-tts", "kitten", "Kiki", "hello world"],
            "KittenEngine", MagicMock()
        )
        mock_synth.assert_called_once()
        call_kwargs = mock_synth.call_args[1]
        assert call_kwargs.get("voice") == "Kiki"

    def test_kokoro_voice_positional(self):
        mock_synth = self._run_with_voice(
            ["marmalade-tts", "kokoro", "af_heart", "hello world"],
            "KokoroEngine", MagicMock()
        )
        mock_synth.assert_called_once()
        call_kwargs = mock_synth.call_args[1]
        assert call_kwargs.get("voice") == "af_heart"

    def test_pocket_voice_positional(self):
        mock_synth = self._run_with_voice(
            ["marmalade-tts", "pocket", "alba", "hello world"],
            "PocketEngine", MagicMock()
        )
        mock_synth.assert_called_once()
        call_kwargs = mock_synth.call_args[1]
        assert call_kwargs.get("voice") == "alba"


# ── Preset resolution ────────────────────────────────────────────────────────────────────

class TestPresetResolution:
    """--fast / --balanced / --quality should update engine config appropriately."""

    def _run_preset(self, preset_flag, engine_name, expected_cfg_key, expected_cfg_val):
        fake_config = {
            "defaults": {"engine": engine_name, "speed": 1.0, "play": False, "preprocessing": False},
            "engines": {
                "kitten": {"voice": "Kiki", "model_size": "micro", "daemon": False, "device": "cpu"},
                "kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"},
                "pocket": {"voice": "alba", "device": "cpu"},
            },
            "presets": {
                "fast":     {"kitten": "nano",  "kokoro": "af_heart", "pocket": "alba"},
                "balanced": {"kitten": "micro", "kokoro": "af_heart", "pocket": "fantine"},
                "quality":  {"kitten": "mini",  "kokoro": "af_heart", "pocket": "cosette"},
            },
        }
        received_cfg = {}

        class FakeEngine:
            def __init__(self, cfg):
                received_cfg.update(cfg)
            def synthesize(self, *a, **kw):
                pass

        with patch("sys.argv", ["marmalade-tts", engine_name, preset_flag, "hello"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=fake_config), \
             patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"), \
             patch("marmalade_tts.cli.play_wav"), \
             patch("marmalade_tts.cli.os.unlink"), \
             patch("marmalade_tts.cli.os.path.exists", return_value=True), \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {engine_name: FakeEngine}):
            main()

        assert received_cfg.get(expected_cfg_key) == expected_cfg_val, (
            f"Expected {expected_cfg_key}={expected_cfg_val!r}, got {received_cfg}"
        )

    def test_kitten_fast_preset_sets_nano(self):
        self._run_preset("--fast", "kitten", "model_size", "nano")

    def test_kitten_quality_preset_sets_mini(self):
        self._run_preset("--quality", "kitten", "model_size", "mini")

    def test_pocket_fast_preset_sets_voice(self):
        self._run_preset("--fast", "pocket", "voice", "alba")

    def test_pocket_balanced_preset_sets_fantine(self):
        self._run_preset("--balanced", "pocket", "voice", "fantine")


# ── --out and passthrough flags ───────────────────────────────────────────────────────────

class TestPassthroughFlags:
    """--out, --lang, --speaker should be forwarded to synthesize."""

    def _run(self, argv, config=None):
        fake_config = config or {
            "defaults": {"engine": "kokoro", "speed": 1.0, "play": False, "preprocessing": False},
            "engines": {
                "kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"},
                "piper":  {"model": "/dev/null", "daemon": False, "device": "cpu"},
            },
            "presets": {},
        }
        received = {}

        class FakeEngine:
            def __init__(self, cfg):
                pass
            def synthesize(self, text, out_path, **kwargs):
                received["text"] = text
                received["out_path"] = out_path
                received["kwargs"] = kwargs

        engine_name = argv[1] if argv[1] in ("kokoro", "piper") else "kokoro"
        with patch("sys.argv", argv), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=fake_config), \
             patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/auto.wav"), \
             patch("marmalade_tts.cli.play_wav"), \
             patch("marmalade_tts.cli.os.unlink"), \
             patch("marmalade_tts.cli.os.path.exists", return_value=True), \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {engine_name: FakeEngine}):
            main()

        return received

    def test_out_flag_sets_output_path(self):
        received = self._run(["marmalade-tts", "kokoro", "hello", "--out", "/tmp/custom.wav"])
        assert received["out_path"] == "/tmp/custom.wav"

    def test_lang_passthrough_for_kokoro(self):
        received = self._run(["marmalade-tts", "kokoro", "hello", "--lang", "b"])
        assert received["kwargs"].get("lang") == "b"

    def test_speaker_passthrough_for_piper(self):
        received = self._run(["marmalade-tts", "piper", "hello", "--speaker", "2"])
        assert received["kwargs"].get("speaker") == "2"


# ── Scripting / agent flags ───────────────────────────────────────────────────

def _fake_synth_config(overrides=None):
    cfg = {
        "defaults": {"engine": "kokoro", "speed": 1.0, "play": True, "preprocessing": False},
        "engines": {"kokoro": {"voice": "af_heart", "lang": "a", "daemon": False, "device": "cpu"}},
        "presets": {},
    }
    if overrides:
        for k, v in overrides.items():
            cfg["defaults"][k] = v
    return cfg


def _run_cli_mocked(argv, config=None, out_path="/tmp/t.wav", stdin_text=None):
    """
    Run main() with a fully mocked kokoro engine.
    Returns (synth_mock, stdout_str, stderr_str).
    """
    import io
    cfg = config or _fake_synth_config()
    synth = MagicMock()

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    patches = [
        patch("sys.argv", argv),
        patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg),
        patch("marmalade_tts.cli.make_tmp_wav", return_value=out_path),
        patch("marmalade_tts.cli.play_wav"),
        patch("marmalade_tts.cli.os.unlink"),
        patch("marmalade_tts.cli.os.path.exists", return_value=True),
        patch("marmalade_tts.cli.KokoroEngine", **{"return_value.synthesize": synth}),
        patch("sys.stdout", stdout_buf),
        patch("sys.stderr", stderr_buf),
    ]
    if stdin_text is not None:
        patches.append(patch("sys.stdin", io.StringIO(stdin_text)))

    with patch("marmalade_tts.cli.KokoroEngine") as MockKokoro:
        MockKokoro.return_value.synthesize = synth
        all_patches = patches[:-2]  # drop the stdout/stderr patches for re-add below
        with patch("sys.argv", argv), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
             patch("marmalade_tts.cli.make_tmp_wav", return_value=out_path), \
             patch("marmalade_tts.cli.play_wav"), \
             patch("marmalade_tts.cli.os.unlink"), \
             patch("marmalade_tts.cli.os.path.exists", return_value=True), \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockKokoro}), \
             patch("sys.stdout", stdout_buf), \
             patch("sys.stderr", stderr_buf):
            if stdin_text is not None:
                import io as _io
                with patch("sys.stdin", _io.StringIO(stdin_text)):
                    main()
            else:
                main()

    return synth, stdout_buf.getvalue(), stderr_buf.getvalue()


class TestScriptingFlags:
    def test_quiet_suppresses_stderr(self):
        _, out, err = _run_cli_mocked(["marmalade-tts", "kokoro", "hello", "--quiet", "--no-play"])
        assert "Generated" not in err
        assert "marmalade-tts" not in err

    def test_default_prints_generated_to_stderr(self):
        cfg = _fake_synth_config({"play": False})
        _, out, err = _run_cli_mocked(["marmalade-tts", "kokoro", "hello"], config=cfg)
        assert "Generated" in err

    def test_print_path_outputs_to_stdout(self):
        cfg = _fake_synth_config({"play": False})
        _, out, err = _run_cli_mocked(
            ["marmalade-tts", "kokoro", "hello", "--print-path", "--no-play"],
            config=cfg, out_path="/tmp/t.wav"
        )
        assert out.strip() == "/tmp/t.wav"
        # "Generated" should NOT also appear on stderr when --print-path is used
        assert "Generated" not in err

    def test_json_output_is_valid_json(self):
        import json
        cfg = _fake_synth_config({"play": False})
        _, out, err = _run_cli_mocked(
            ["marmalade-tts", "kokoro", "hello", "--json", "--no-play"],
            config=cfg
        )
        result = json.loads(out.strip())
        assert result["ok"] is True
        assert result["engine"] == "kokoro"
        assert result["out"] == "/tmp/t.wav"
        assert "text" in result

    def test_json_includes_text_field(self):
        import json
        cfg = _fake_synth_config({"play": False})
        _, out, _ = _run_cli_mocked(
            ["marmalade-tts", "kokoro", "say this please", "--json", "--no-play"],
            config=cfg
        )
        result = json.loads(out.strip())
        assert result["text"] == "say this please"

    def test_json_includes_effects_list(self):
        import json
        cfg = _fake_synth_config({"play": False})
        with patch("marmalade_tts.cli.fx.sox_available", return_value=True), \
             patch("marmalade_tts.cli.fx.apply_effects"):
            _, out, _ = _run_cli_mocked(
                ["marmalade-tts", "kokoro", "hello", "--json", "--no-play", "--effect", "reverb=30"],
                config=cfg
            )
        result = json.loads(out.strip())
        assert "reverb=30" in result["effects"]

    def test_no_play_skips_playback_even_when_config_wants_play(self):
        # Config says play=True, --no-play should override
        cfg = _fake_synth_config({"play": True})
        with patch("marmalade_tts.cli.play_wav") as mock_play:
            with patch("sys.argv", ["marmalade-tts", "kokoro", "hello", "--no-play"]), \
                 patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
                 patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"), \
                 patch("marmalade_tts.cli.os.path.exists", return_value=True), \
                 patch("marmalade_tts.cli.KokoroEngine") as MockKokoro, \
                 patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockKokoro}):
                MockKokoro.return_value.synthesize = MagicMock()
                main()
        mock_play.assert_not_called()

    def test_stdin_flag_reads_stdin(self):
        synth, _, _ = _run_cli_mocked(
            ["marmalade-tts", "kokoro", "--stdin", "--no-play"],
            stdin_text="hello from stdin"
        )
        synth.assert_called_once()
        text_arg = synth.call_args[0][0]
        assert "hello from stdin" in text_arg

    def test_empty_text_exits_nonzero(self):
        cfg = _fake_synth_config({"play": False})
        with patch("sys.argv", ["marmalade-tts", "kokoro", "   "]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
             patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code != 0
