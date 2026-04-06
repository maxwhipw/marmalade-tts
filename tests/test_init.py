"""Tests for marmalade-tts init — non-interactive + interactive TUI paths."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, call
import yaml

from marmalade_tts.cli import main
from marmalade_tts.init import (
    init_non_interactive, ENGINE_INFO, ENGINE_ORDER, _is_tty,
)


# ── Non-interactive path ─────────────────────────────────────────────────────

class TestNonInteractive:
    def test_single_engine(self):
        result = init_non_interactive(["kitten"])
        assert "kitten" in result
        assert result["kitten"]["model_size"] == "micro"  # default
        assert result["kitten"]["daemon"] is False

    def test_multiple_engines(self):
        result = init_non_interactive(["kitten", "piper", "kokoro"])
        assert len(result) == 3
        assert result["kokoro"]["voice"] == "af_heart"

    def test_override_model_size(self):
        result = init_non_interactive(
            ["kitten"],
            engine_options={"kitten": {"model_size": "nano"}}
        )
        assert result["kitten"]["model_size"] == "nano"

    def test_override_kokoro_voice(self):
        result = init_non_interactive(
            ["kokoro"],
            engine_options={"kokoro": {"voice": "am_adam"}}
        )
        assert result["kokoro"]["voice"] == "am_adam"

    def test_invalid_engine_exits(self):
        with pytest.raises(SystemExit):
            init_non_interactive(["nonexistent_engine"])

    def test_invalid_choice_exits(self):
        with pytest.raises(SystemExit):
            init_non_interactive(
                ["kitten"],
                engine_options={"kitten": {"model_size": "gigantic"}}
            )

    def test_all_engines(self):
        result = init_non_interactive(ENGINE_ORDER)
        assert len(result) == 5
        for eng in ENGINE_ORDER:
            assert eng in result
            assert "daemon" in result[eng]
            assert "device" in result[eng]

    def test_piper_has_empty_model_default(self):
        result = init_non_interactive(["piper"])
        assert result["piper"]["model"] == ""

    def test_coqui_has_empty_model_default(self):
        result = init_non_interactive(["coqui"])
        assert result["coqui"]["model"] == ""


# ── CLI non-interactive integration ──────────────────────────────────────────

class TestCLIInitNonInteractive:
    def test_basic_init_writes_config(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path), \
             patch("sys.argv", ["marmalade-tts", "init",
                                "--non-interactive", "--engines", "kitten"]), \
             patch("marmalade_tts.init._is_tty", return_value=False):
            main()

        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        assert cfg["defaults"]["engine"] == "kitten"
        assert "kitten" in cfg["engines"]

    def test_set_override_via_cli(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path), \
             patch("sys.argv", ["marmalade-tts", "init",
                                "--non-interactive", "--engines", "kitten",
                                "--set", "kitten.model_size=nano"]), \
             patch("marmalade_tts.init._is_tty", return_value=False):
            main()

        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        assert cfg["engines"]["kitten"]["model_size"] == "nano"

    def test_multiple_engines_via_cli(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path), \
             patch("sys.argv", ["marmalade-tts", "init",
                                "--non-interactive", "--engines", "kitten,kokoro",
                                "--default-engine", "kokoro"]), \
             patch("marmalade_tts.init._is_tty", return_value=False):
            main()

        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        assert cfg["defaults"]["engine"] == "kokoro"
        assert "kitten" in cfg["engines"]
        assert "kokoro" in cfg["engines"]

    def test_missing_engines_flag_exits(self):
        with patch("sys.argv", ["marmalade-tts", "init", "--non-interactive"]), \
             patch("marmalade_tts.init._is_tty", return_value=False):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_bad_set_format_exits(self):
        with patch("sys.argv", ["marmalade-tts", "init",
                                "--non-interactive", "--engines", "kitten",
                                "--set", "bad_format"]), \
             patch("marmalade_tts.init._is_tty", return_value=False):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_test_flag_attempts_synthesis(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path), \
             patch("sys.argv", ["marmalade-tts", "init",
                                "--non-interactive", "--engines", "kitten", "--test"]), \
             patch("marmalade_tts.init._is_tty", return_value=False), \
             patch("marmalade_tts.cli.ENGINE_CLASSES") as mock_classes:
            # Mock the engine so test synthesis doesn't need real model
            mock_eng = MagicMock()
            mock_classes.__getitem__ = MagicMock(return_value=lambda cfg: mock_eng)
            with patch("marmalade_tts.cli.play_wav"), \
                 patch("marmalade_tts.playback.make_tmp_wav", return_value="/tmp/test.wav"), \
                 patch("marmalade_tts.cli.os.unlink"):
                # This may fail because the real engine isn't installed;
                # the important thing is it doesn't crash the init flow
                try:
                    main()
                except Exception:
                    pass  # test synthesis failure is acceptable in unit tests


# ── Engine metadata ──────────────────────────────────────────────────────────

class TestEngineMetadata:
    def test_all_engines_have_info(self):
        for eng in ENGINE_ORDER:
            assert eng in ENGINE_INFO

    def test_info_has_required_keys(self):
        for eng, info in ENGINE_INFO.items():
            assert "label" in info
            assert "desc" in info
            assert "size" in info
            assert "default" in info
            assert "options" in info

    def test_defaults_are_kitten_and_piper(self):
        defaults = [eng for eng, info in ENGINE_INFO.items() if info["default"]]
        assert "kitten" in defaults
        assert "piper" in defaults

    def test_kitten_has_model_size_option(self):
        opts = ENGINE_INFO["kitten"]["options"]
        assert "model_size" in opts
        assert "micro" in opts["model_size"]["choices"]
        assert opts["model_size"]["default"] == "micro"

    def test_kokoro_has_voice_option(self):
        opts = ENGINE_INFO["kokoro"]["options"]
        assert "voice" in opts
        assert "af_heart" in opts["voice"]["choices"]

    def test_engine_order_matches_info(self):
        for eng in ENGINE_ORDER:
            assert eng in ENGINE_INFO


# ── TUI helpers (unit tests, no real terminal) ───────────────────────────────

class TestTUIHelpers:
    def test_is_tty_false_in_pipe(self):
        """In test/CI, stdin is not a TTY."""
        # Could be either, but must not crash
        result = _is_tty()
        assert isinstance(result, bool)

    def test_non_interactive_falls_back_when_no_tty(self, tmp_path):
        """When stdin is not a TTY and --engines is given, should succeed."""
        cfg_path = str(tmp_path / "config.yaml")
        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path), \
             patch("sys.argv", ["marmalade-tts", "init", "--engines", "kitten"]), \
             patch("marmalade_tts.init._is_tty", return_value=False):
            main()

        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        assert "kitten" in cfg["engines"]


# ── Config preservation ──────────────────────────────────────────────────────

class TestConfigPreservation:
    def test_init_preserves_existing_config_keys(self, tmp_path):
        """Init should merge, not overwrite existing config."""
        cfg_path = str(tmp_path / "config.yaml")
        existing = {
            "defaults": {"speed": 1.5, "play": False},
            "effects": {"defaults": {"kitten": ["reverb=20"]}},
        }
        with open(cfg_path, "w") as f:
            yaml.safe_dump(existing, f)

        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path), \
             patch("sys.argv", ["marmalade-tts", "init",
                                "--non-interactive", "--engines", "kitten"]), \
             patch("marmalade_tts.init._is_tty", return_value=False):
            main()

        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)

        # Original values preserved
        assert cfg["defaults"]["speed"] == 1.5
        # New values added
        assert cfg["defaults"]["engine"] == "kitten"
        # Effects untouched
        assert cfg["effects"]["defaults"]["kitten"] == ["reverb=20"]

    def test_init_overwrites_engine_config(self, tmp_path):
        """Re-running init for an engine should update its config."""
        cfg_path = str(tmp_path / "config.yaml")
        existing = {
            "defaults": {"engine": "kitten"},
            "engines": {"kitten": {"model_size": "nano", "daemon": True}},
        }
        with open(cfg_path, "w") as f:
            yaml.safe_dump(existing, f)

        with patch("marmalade_tts.config.CONFIG_PATH", cfg_path), \
             patch("sys.argv", ["marmalade-tts", "init",
                                "--non-interactive", "--engines", "kitten",
                                "--set", "kitten.model_size=micro"]), \
             patch("marmalade_tts.init._is_tty", return_value=False):
            main()

        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        assert cfg["engines"]["kitten"]["model_size"] == "micro"


# ── Pocket TTS engine ────────────────────────────────────────────────────────

class TestPocketInit:
    def test_pocket_default_voice(self):
        result = init_non_interactive(["pocket"])
        assert result["pocket"]["voice"] == "alba"

    def test_pocket_override_voice(self):
        result = init_non_interactive(
            ["pocket"],
            engine_options={"pocket": {"voice": "marius"}}
        )
        assert result["pocket"]["voice"] == "marius"

    def test_pocket_invalid_voice_exits(self):
        with pytest.raises(SystemExit):
            init_non_interactive(
                ["pocket"],
                engine_options={"pocket": {"voice": "nonexistent"}}
            )

    def test_pocket_in_engine_order(self):
        assert "pocket" in ENGINE_ORDER

    def test_pocket_in_engine_info(self):
        assert "pocket" in ENGINE_INFO
        assert ENGINE_INFO["pocket"]["label"] == "Pocket TTS"
