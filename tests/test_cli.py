"""Tests for CLI argument parsing and dispatch (no synthesis required)."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

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

    # Kokoro — bare names and canonical IDs both detected
    def test_kokoro_canonical_id(self):
        assert looks_like_voice("kokoro", "af_heart") is True
        assert looks_like_voice("kokoro", "bm_george") is True

    def test_kokoro_bare_name(self):
        assert looks_like_voice("kokoro", "heart") is True
        assert looks_like_voice("kokoro", "george") is True
        assert looks_like_voice("kokoro", "alpha") is True

    def test_kokoro_invalid(self):
        assert looks_like_voice("kokoro", "hello") is False
        # Unknown prefix-shaped tokens should not match (closed list, not prefix family)
        assert looks_like_voice("kokoro", "xy_nonsense") is False

    # Piper — does NOT accept positional voice; --voice is required
    def test_piper_path_not_treated_as_voice(self):
        assert looks_like_voice("piper", "model.onnx") is False
        assert looks_like_voice("piper", "/some/path/model.onnx") is False
        assert looks_like_voice("piper", "~/voices/model.onnx") is False
        assert looks_like_voice("piper", "hello world") is False

    # Coqui — does NOT accept positional voice; --voice is required
    def test_coqui_model_not_treated_as_voice(self):
        assert looks_like_voice("coqui", "tts_models/en/ljspeech/tacotron2-DDC") is False
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

    # EmojiVoice — closed list of speaker names
    def test_emojivoice_valid_speaker(self):
        assert looks_like_voice("emojivoice", "paige") is True

    def test_emojivoice_plain_text_not_a_voice(self):
        assert looks_like_voice("emojivoice", "hello world") is False
        assert looks_like_voice("emojivoice", "I can't believe it 🤣") is False

    # Matcha — model specs, not positional voices; use --voice
    def test_matcha_model_not_treated_as_voice(self):
        assert looks_like_voice("matcha", "matcha_ljspeech") is False
        assert looks_like_voice("matcha", "/models/custom.ckpt") is False
        assert looks_like_voice("matcha", "hello world") is False


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


def test_completion_bash_includes_voices(capsys):
    """Bash completion should embed the voice lists for kitten/kokoro/pocket."""
    with patch("sys.argv", ["marmalade-tts", "--completion", "bash"]):
        main()
    out = capsys.readouterr().out
    assert "Kiki" in out                       # kitten voice
    assert "george" in out                     # kokoro bare name
    assert "bm_george" in out                  # kokoro canonical form
    assert "alba" in out                       # pocket voice


def test_completion_bash_piper_voice_uses_file_completion(capsys):
    """piper --voice should fall back to .onnx file completion, not a voice list."""
    with patch("sys.argv", ["marmalade-tts", "--completion", "bash"]):
        main()
    out = capsys.readouterr().out
    # The --voice case statement must route piper to _filedir onnx.
    assert "piper)      _filedir onnx" in out


def test_completion_zsh(capsys):
    with patch("sys.argv", ["marmalade-tts", "--completion", "zsh"]):
        main()
    captured = capsys.readouterr()
    assert "_marmalade-tts" in captured.out


def test_completion_zsh_is_engine_aware(capsys):
    """zsh completion should have a state machine that completes voices per-engine."""
    with patch("sys.argv", ["marmalade-tts", "--completion", "zsh"]):
        main()
    out = capsys.readouterr().out
    # State-machine markers and the engine-aware voice helper.
    assert "->arg2" in out                     # positional voice slot has a state
    assert "->voiceflag" in out                # --voice flag has a state
    assert "_marmalade_voices" in out          # the shared engine-aware helper
    assert "_files -g '*.onnx'" in out         # piper file completion in zsh too


def test_completion_only_at_argv0(capsys):
    """--completion must NOT trigger when it appears mid-argv (e.g. inside text)."""
    # If --completion were substring-matched, this would print the bash
    # completion script and skip synthesis. The fix makes it argv[0]-only,
    # so the test ends up trying to synthesize and gets to the engine layer.
    with patch("sys.argv", ["marmalade-tts", "kokoro", "tell me about --completion"]):
        with patch("marmalade_tts.cli.cfg_mod.load", return_value={
            "defaults": {"engine": "kokoro", "speed": 1.0, "play": False, "preprocessing": False},
            "engines": {"kokoro": {"voice": "heart", "daemon": False, "device": "cpu"}},
        }):
            # We don't need synthesis to actually work — we just verify that
            # main() doesn't short-circuit on --completion. Patch the engine
            # class so synthesize is a no-op and main() proceeds normally.
            with patch("marmalade_tts.cli.ENGINE_CLASSES",
                       {"kokoro": lambda cfg: MagicMock()}), \
                 patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"), \
                 patch("marmalade_tts.cli.play_wav"), \
                 patch("marmalade_tts.cli.os.unlink"):
                main()
    captured = capsys.readouterr()
    # The completion script signature must NOT appear in stdout.
    assert "complete -F _marmalade_tts" not in captured.out


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

    def test_kokoro_bare_voice_positional(self):
        """Bare kokoro voice names work positionally (e.g. 'george' not 'bm_george')."""
        mock_synth = self._run_with_voice(
            ["marmalade-tts", "kokoro", "george", "hello world"],
            "KokoroEngine", MagicMock()
        )
        mock_synth.assert_called_once()
        assert mock_synth.call_args[1].get("voice") == "george"


# ── Error paths ──────────────────────────────────────────────────────────────


class TestErrorPaths:
    """The CLI should error early on malformed argument combinations."""

    def test_voice_without_text_errors(self):
        # User typed a voice but no text — should error, not synthesize the voice name
        cfg = _fake_synth_config({"play": False})
        with patch("sys.argv", ["marmalade-tts", "kitten", "Kiki"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
             pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code != 0

    def test_kokoro_voice_without_text_errors(self):
        cfg = _fake_synth_config({"play": False})
        with patch("sys.argv", ["marmalade-tts", "kokoro", "george"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
             pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code != 0

    def test_text_flag_with_extra_positionals_errors(self):
        """--text "Hi" plus extra positionals that aren't a voice → error."""
        cfg = _fake_synth_config({"play": False})
        with patch("sys.argv", ["marmalade-tts", "kokoro", "--text", "Hello", "extra", "words"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
             pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code != 0

    def test_text_flag_with_voice_positional_works(self):
        """--text "Hi" plus a single voice-shaped positional is allowed (voice override)."""
        cfg = _fake_synth_config({"play": False})
        with patch("marmalade_tts.cli.fx.sox_available", return_value=False):
            mock_eng = MagicMock()
            with patch("sys.argv", ["marmalade-tts", "kitten", "Kiki", "--text", "Hi", "--no-play"]), \
                 patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
                 patch("marmalade_tts.cli.ENGINE_CLASSES", {"kitten": lambda c: mock_eng}), \
                 patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"):
                main()
        assert mock_eng.synthesize.call_args[1].get("voice") == "Kiki"


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
                "matcha": {"model": "matcha_ljspeech", "daemon": False, "device": "cpu"},
                "emojivoice": {"voice": "paige", "daemon": False, "device": "cpu"},
            },
            "presets": {
                "fast":     {"kitten": "nano",  "kokoro": "af_heart", "pocket": "alba",    "matcha": "matcha_ljspeech", "emojivoice": "paige"},
                "balanced": {"kitten": "micro", "kokoro": "af_heart", "pocket": "fantine", "matcha": "matcha_ljspeech", "emojivoice": "paige"},
                "quality":  {"kitten": "mini",  "kokoro": "af_heart", "pocket": "cosette", "matcha": "matcha_ljspeech", "emojivoice": "paige"},
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

    def test_matcha_fast_preset_sets_model(self):
        # matcha is a model-spec engine — preset resolves into `model`
        self._run_preset("--fast", "matcha", "model", "matcha_ljspeech")

    def test_emojivoice_fast_preset_sets_voice(self):
        # emojivoice is a closed-list-voice engine — preset resolves into `voice`
        self._run_preset("--fast", "emojivoice", "voice", "paige")


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

    def test_json_includes_version(self):
        import json
        cfg = _fake_synth_config({"play": False})
        _, out, _ = _run_cli_mocked(
            ["marmalade-tts", "kokoro", "hello", "--json", "--no-play"],
            config=cfg
        )
        result = json.loads(out.strip())
        assert result["version"] == __version__

    def test_no_effects_flag_overrides_config_defaults(self):
        """--no-effects must override effects.defaults.<engine> from config."""
        import json
        cfg = _fake_synth_config({"play": False})
        # Configure a default effect for kokoro
        cfg.setdefault("effects", {}).setdefault("defaults", {})["kokoro"] = ["reverb=40"]
        with patch("marmalade_tts.cli.fx.sox_available", return_value=True), \
             patch("marmalade_tts.cli.fx.apply_effects") as mock_apply:
            _, out, _ = _run_cli_mocked(
                ["marmalade-tts", "kokoro", "hello", "--json", "--no-play", "--no-effects"],
                config=cfg
            )
        result = json.loads(out.strip())
        assert result["effects"] == []
        # apply_effects should not have been called (empty list short-circuits)
        mock_apply.assert_not_called()

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


# ── install subcommand ───────────────────────────────────────────────────────

def _ok_result(engine, ok=True):
    return {"engine": engine, "venv": f"/tmp/{engine}-venv", "system_deps": [],
            "models": [], "selftest": (ok, "ok" if ok else "boom"), "error": None}


class TestInstallSubcommand:
    def test_install_routes_to_installer(self):
        with patch("sys.argv", ["marmalade-tts", "install", "kitten"]), \
             patch("marmalade_tts.installer.install_engines",
                   return_value=[_ok_result("kitten")]) as mock_inst:
            main()
        mock_inst.assert_called_once()
        assert mock_inst.call_args[0][0] == ["kitten"]

    def test_install_multiple_engines(self):
        with patch("sys.argv", ["marmalade-tts", "install", "kitten", "matcha"]), \
             patch("marmalade_tts.installer.install_engines",
                   return_value=[_ok_result("kitten"), _ok_result("matcha")]) as mock_inst:
            main()
        assert mock_inst.call_args[0][0] == ["kitten", "matcha"]

    def test_install_flags_passed_through(self):
        with patch("sys.argv", ["marmalade-tts", "install", "kitten",
                                "--allow-sudo", "--reinstall", "--skip-selftest"]), \
             patch("marmalade_tts.init._is_tty", return_value=False), \
             patch("marmalade_tts.installer.install_engines",
                   return_value=[_ok_result("kitten")]) as mock_inst:
            main()
        kwargs = mock_inst.call_args[1]
        assert kwargs["allow_sudo"] is True
        assert kwargs["reinstall"] is True
        assert kwargs["skip_selftest"] is True
        assert kwargs["interactive"] is False

    def test_install_unknown_engine_exits(self):
        with patch("sys.argv", ["marmalade-tts", "install", "bogus"]), \
             patch("marmalade_tts.installer.install_engines") as mock_inst:
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code != 0
        mock_inst.assert_not_called()

    def test_install_failed_selftest_exits_nonzero(self):
        with patch("sys.argv", ["marmalade-tts", "install", "kitten"]), \
             patch("marmalade_tts.installer.install_engines",
                   return_value=[_ok_result("kitten", ok=False)]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code != 0

    def test_install_success_no_exit(self):
        with patch("sys.argv", ["marmalade-tts", "install", "kitten"]), \
             patch("marmalade_tts.installer.install_engines",
                   return_value=[_ok_result("kitten")]):
            main()  # no SystemExit


# ── Batch mode (opt-in via --batch) ──────────────────────────────────────────

class _BatchHarness:
    """Patches engine + tempfile/playback for batch tests. Each call to
    make_tmp_wav returns a fresh path so we can tell utterances apart."""
    def __init__(self, argv, stdin_text=None, cfg=None):
        self.argv = argv
        self.stdin_text = stdin_text
        self.cfg = cfg or _fake_synth_config()
        self.synth = MagicMock()
        self.tmp_paths_used = []
        self.played = []

    def __enter__(self):
        import io
        self.stack = []

        def fake_make_tmp_wav():
            p = f"/tmp/batch-{len(self.tmp_paths_used)}.wav"
            self.tmp_paths_used.append(p)
            return p

        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        MockEngine = MagicMock()
        MockEngine.return_value.synthesize = self.synth

        patches = [
            patch("sys.argv", self.argv),
            patch("marmalade_tts.cli.cfg_mod.load", return_value=self.cfg),
            patch("marmalade_tts.cli.make_tmp_wav", side_effect=fake_make_tmp_wav),
            patch("marmalade_tts.cli.play_wav", side_effect=self.played.append),
            patch("marmalade_tts.cli.os.unlink"),
            patch("marmalade_tts.cli.os.path.exists", return_value=True),
            patch("marmalade_tts.cli.os.makedirs"),
            patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockEngine}),
            patch("sys.stdout", self.stdout),
            patch("sys.stderr", self.stderr),
        ]
        if self.stdin_text is not None:
            patches.append(patch("sys.stdin", io.StringIO(self.stdin_text)))
        for p in patches:
            p.__enter__()
            self.stack.append(p)
        return self

    def __exit__(self, *a):
        for p in reversed(self.stack):
            p.__exit__(*a)


class TestBatchMode:
    """Batch mode is now opt-in via --batch. Without the flag, multi-line
    inputs go to a single synthesize call (the line breaks are part of the
    text). Chunking inside synthesize_one is a separate, transparent
    mechanism — see TestChunking below."""

    def test_batch_flag_splits_into_lines(self):
        with _BatchHarness(["marmalade-tts", "kokoro", "--no-play", "--batch",
                            "--text", "line one\nline two\nline three"]) as h:
            main()
        # Three lines → three synthesize calls.
        assert h.synth.call_count == 3
        texts = [c.args[0] for c in h.synth.call_args_list]
        assert texts == ["line one", "line two", "line three"]

    def test_multiline_without_batch_is_one_utterance(self):
        """Default: multi-line input goes to a SINGLE synthesize call.
        Previously triggered batch implicitly — that surprised AI agents
        sending paragraph-broken files, so batch is now opt-in."""
        with _BatchHarness(["marmalade-tts", "kokoro", "--no-play",
                            "--text", "line one\nline two\nline three"]) as h:
            main()
        assert h.synth.call_count == 1
        # Whole text (newlines and all) is passed through to the engine.
        assert h.synth.call_args[0][0] == "line one\nline two\nline three"

    def test_singleline_stays_single(self):
        with _BatchHarness(["marmalade-tts", "kokoro", "--no-play",
                            "--text", "just one line"]) as h:
            main()
        assert h.synth.call_count == 1
        assert h.synth.call_args[0][0] == "just one line"

    def test_batch_skips_blank_lines(self):
        with _BatchHarness(["marmalade-tts", "kokoro", "--no-play", "--batch",
                            "--text", "first\n\n   \nsecond"]) as h:
            main()
        assert h.synth.call_count == 2
        texts = [c.args[0] for c in h.synth.call_args_list]
        assert texts == ["first", "second"]

    def test_batch_out_pattern_substitutes_index(self, tmp_path):
        pat = str(tmp_path / "chap-%03d.wav")
        with _BatchHarness(["marmalade-tts", "kokoro", "--no-play", "--batch",
                            "--out", pat,
                            "--text", "a\nb\nc"]) as h:
            main()
        paths = [c.args[1] for c in h.synth.call_args_list]
        assert paths == [str(tmp_path / "chap-001.wav"),
                         str(tmp_path / "chap-002.wav"),
                         str(tmp_path / "chap-003.wav")]

    def test_batch_out_dir_auto_names(self, tmp_path):
        with _BatchHarness(["marmalade-tts", "kokoro", "--no-play", "--batch",
                            "--out-dir", str(tmp_path),
                            "--text", "a\nb"]) as h:
            main()
        paths = [c.args[1] for c in h.synth.call_args_list]
        assert paths == [str(tmp_path / "001.wav"),
                         str(tmp_path / "002.wav")]

    def test_batch_out_file_without_pattern_errors(self):
        with _BatchHarness(["marmalade-tts", "kokoro", "--batch",
                            "--out", "single.wav",
                            "--text", "line one\nline two"]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code != 0

    def test_batch_json_returns_array(self):
        with _BatchHarness(["marmalade-tts", "kokoro", "--no-play", "--batch",
                            "--json", "--text", "alpha\nbeta"]) as h:
            main()
            out = h.stdout.getvalue()
        import json
        payload = json.loads(out)
        assert isinstance(payload, list)
        assert len(payload) == 2
        assert payload[0]["text"] == "alpha"
        assert payload[1]["text"] == "beta"

    def test_json_single_returns_object(self):
        with _BatchHarness(["marmalade-tts", "kokoro", "--no-play", "--json",
                            "--text", "just alpha"]) as h:
            main()
            out = h.stdout.getvalue()
        import json
        payload = json.loads(out)
        assert isinstance(payload, dict)
        assert payload["text"] == "just alpha"

    def test_batch_print_path_one_per_line(self, tmp_path):
        pat = str(tmp_path / "out-%d.wav")
        with _BatchHarness(["marmalade-tts", "kokoro", "--no-play", "--batch",
                            "--print-path", "--out", pat,
                            "--text", "a\nb\nc"]) as h:
            main()
            out = h.stdout.getvalue().strip().splitlines()
        assert out == [str(tmp_path / "out-1.wav"),
                       str(tmp_path / "out-2.wav"),
                       str(tmp_path / "out-3.wav")]

    def test_batch_plays_sequentially(self):
        cfg = _fake_synth_config({"play": True})
        with _BatchHarness(["marmalade-tts", "kokoro", "--batch",
                            "--text", "a\nb\nc"], cfg=cfg) as h:
            main()
        # play_wav called once per utterance, in order.
        assert len(h.played) == 3

    def test_stdin_multiline_without_batch_is_single(self):
        """Multi-line stdin without --batch is also a single utterance."""
        with _BatchHarness(["marmalade-tts", "kokoro", "--stdin", "--no-play"],
                           stdin_text="line one\nline two") as h:
            main()
        assert h.synth.call_count == 1

    def test_stdin_multiline_with_batch_splits(self):
        with _BatchHarness(["marmalade-tts", "kokoro", "--stdin", "--no-play",
                            "--batch"], stdin_text="line one\nline two") as h:
            main()
        assert h.synth.call_count == 2


# ── Subtitle output ──────────────────────────────────────────────────────────

def _write_silence_wav(path: str, duration_s: float = 0.5, rate: int = 22050) -> None:
    """Write a tiny PCM silence WAV at `path`. Used by the subtitle tests to
    simulate engine output we can read back with wave.open()."""
    import wave
    frames = int(round(duration_s * rate))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)


class TestSubtitleOutput:
    """End-to-end --srt / --vtt flags with a mocked engine that writes
    real (silent) WAVs so wave.open() can read their duration back."""

    def _run_with_srt(self, argv, tmp_path, stdin_text=None, wav_duration_s=0.5):
        """Patch the kokoro engine to write a tiny silent WAV at the path
        the CLI passes in, so wav_duration() reads a real duration."""
        cfg = _fake_synth_config({"play": False})
        synth = MagicMock(
            side_effect=lambda text, out_path, **kw:
                _write_silence_wav(out_path, duration_s=wav_duration_s)
        )
        import io
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        # Real tmp WAVs so wave.open() works.
        tmp_counter = [0]

        def real_tmp_wav():
            tmp_counter[0] += 1
            p = str(tmp_path / f"tmp-{tmp_counter[0]}.wav")
            # The engine mock writes the WAV; pre-create to satisfy any check.
            return p

        with patch("sys.argv", argv), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
             patch("marmalade_tts.cli.make_tmp_wav", side_effect=real_tmp_wav), \
             patch("marmalade_tts.cli.play_wav"), \
             patch("marmalade_tts.cli.KokoroEngine") as MockKokoro, \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockKokoro}), \
             patch("sys.stdout", stdout_buf), \
             patch("sys.stderr", stderr_buf):
            MockKokoro.return_value.synthesize = synth
            if stdin_text is not None:
                with patch("sys.stdin", io.StringIO(stdin_text)):
                    main()
            else:
                main()
        return stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_srt_single_utterance(self, tmp_path):
        srt = tmp_path / "out.srt"
        _, err = self._run_with_srt(
            ["marmalade-tts", "kokoro", "Hello world",
             "--no-play", "--out", str(tmp_path / "out.wav"),
             "--srt", str(srt)],
            tmp_path,
            wav_duration_s=1.0,
        )
        assert srt.exists()
        body = srt.read_text(encoding="utf-8")
        # One cue starting at 0
        assert "1\n00:00:00,000 --> " in body
        assert "Hello world" in body
        # Stderr note
        assert "Wrote subtitles" in err
        assert str(srt) in err

    def test_srt_batch_three_lines(self, tmp_path):
        srt = tmp_path / "chapters.srt"
        out_dir = tmp_path / "out"
        _, err = self._run_with_srt(
            ["marmalade-tts", "kokoro", "--no-play", "--batch",
             "--out-dir", str(out_dir),
             "--text", "alpha\nbeta\ngamma",
             "--srt", str(srt)],
            tmp_path,
            wav_duration_s=1.0,
        )
        assert srt.exists()
        body = srt.read_text(encoding="utf-8")
        # Three cues
        assert body.count("-->") == 3
        # Texts present
        assert "alpha" in body
        assert "beta" in body
        assert "gamma" in body
        # Cue 1 starts at 0, cue 2 starts at 1.0 + 0.050 = 01,050
        assert "00:00:00,000 --> 00:00:01,000\nalpha" in body
        assert "00:00:01,050 --> 00:00:02,050\nbeta" in body
        assert "00:00:02,100 --> 00:00:03,100\ngamma" in body

    def test_srt_uses_raw_text_not_preprocessed(self, tmp_path):
        """Subtitle text should be the user's original input — emoji and
        markdown that get stripped during preprocessing must still show
        up in the .srt because that's what the user typed."""
        srt = tmp_path / "out.srt"
        cfg = _fake_synth_config({"play": False})
        # Turn preprocessing ON so emojis would actually be stripped.
        cfg["defaults"]["preprocessing"] = True

        synth = MagicMock(
            side_effect=lambda text, out_path, **kw:
                _write_silence_wav(out_path, duration_s=0.5)
        )
        import io
        stderr_buf = io.StringIO()
        tmp_counter = [0]

        def real_tmp_wav():
            tmp_counter[0] += 1
            return str(tmp_path / f"tmp-{tmp_counter[0]}.wav")

        with patch("sys.argv",
                   ["marmalade-tts", "kokoro", "--no-play",
                    "--text", "I love it 🤣",
                    "--srt", str(srt)]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
             patch("marmalade_tts.cli.make_tmp_wav", side_effect=real_tmp_wav), \
             patch("marmalade_tts.cli.play_wav"), \
             patch("marmalade_tts.cli.KokoroEngine") as MockKokoro, \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockKokoro}), \
             patch("sys.stderr", stderr_buf):
            MockKokoro.return_value.synthesize = synth
            main()

        body = srt.read_text(encoding="utf-8")
        # Raw text (with emoji) appears in the subtitle file
        assert "🤣" in body
        # Sanity: the engine was called with the preprocessed (stripped) form
        synth_text = synth.call_args[0][0]
        assert "🤣" not in synth_text

    def test_vtt_basic_header(self, tmp_path):
        vtt = tmp_path / "out.vtt"
        _, _ = self._run_with_srt(
            ["marmalade-tts", "kokoro", "Hello world",
             "--no-play", "--out", str(tmp_path / "out.wav"),
             "--vtt", str(vtt)],
            tmp_path,
        )
        body = vtt.read_text(encoding="utf-8")
        assert body.startswith("WEBVTT\n\n")
        assert "Hello world" in body
        # Period decimal separator
        assert "00:00:00.000" in body

    def test_srt_and_vtt_both(self, tmp_path):
        srt = tmp_path / "out.srt"
        vtt = tmp_path / "out.vtt"
        _, _ = self._run_with_srt(
            ["marmalade-tts", "kokoro", "Hello",
             "--no-play", "--out", str(tmp_path / "out.wav"),
             "--srt", str(srt), "--vtt", str(vtt)],
            tmp_path,
        )
        assert srt.exists()
        assert vtt.exists()

    def test_srt_creates_parent_dir(self, tmp_path):
        srt = tmp_path / "subs" / "deep" / "out.srt"
        _, _ = self._run_with_srt(
            ["marmalade-tts", "kokoro", "Hello",
             "--no-play", "--out", str(tmp_path / "out.wav"),
             "--srt", str(srt)],
            tmp_path,
        )
        assert srt.exists()

    def test_no_srt_flag_writes_nothing(self, tmp_path):
        """Without --srt or --vtt, no subtitle file is created."""
        _, _ = self._run_with_srt(
            ["marmalade-tts", "kokoro", "Hello",
             "--no-play", "--out", str(tmp_path / "out.wav")],
            tmp_path,
        )
        # No .srt or .vtt anywhere in tmp_path
        assert not any(p.suffix in (".srt", ".vtt") for p in tmp_path.iterdir())

    def test_json_includes_duration(self, tmp_path):
        """The --json payload should gain a `duration` field per utterance."""
        import json
        cfg = _fake_synth_config({"play": False})
        synth = MagicMock(
            side_effect=lambda text, out_path, **kw:
                _write_silence_wav(out_path, duration_s=0.5)
        )
        import io
        stdout_buf = io.StringIO()
        tmp_counter = [0]

        def real_tmp_wav():
            tmp_counter[0] += 1
            return str(tmp_path / f"tmp-{tmp_counter[0]}.wav")

        with patch("sys.argv",
                   ["marmalade-tts", "kokoro", "Hello",
                    "--no-play", "--json"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
             patch("marmalade_tts.cli.make_tmp_wav", side_effect=real_tmp_wav), \
             patch("marmalade_tts.cli.play_wav"), \
             patch("marmalade_tts.cli.KokoroEngine") as MockKokoro, \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockKokoro}), \
             patch("sys.stdout", stdout_buf):
            MockKokoro.return_value.synthesize = synth
            main()
        payload = json.loads(stdout_buf.getvalue())
        assert "duration" in payload
        # 0.5 s silence WAV → duration should be close to 0.5
        assert 0.45 <= payload["duration"] <= 0.55
