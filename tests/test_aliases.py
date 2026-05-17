"""Tests for voice aliases / personas — config-defined named bundles
invoked positionally like an engine name.

These tests verify dispatch and precedence without actually synthesizing.
They mock the engine class and assert on the kwargs / effect list / voice
that main() prepared.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

from marmalade_tts.cli import main


# ── Fixtures ────────────────────────────────────────────────────────────────

def _cfg_with_aliases(aliases: dict, extra: dict = None) -> dict:
    """Build a minimal config that includes the given aliases."""
    cfg = {
        "defaults": {"engine": "kokoro", "speed": 1.0, "play": False,
                     "preprocessing": False},
        "engines": {
            "kokoro": {"voice": "af_heart", "lang": "a", "daemon": False,
                       "device": "cpu"},
            "kitten": {"voice": "Kiki", "model_size": "micro", "daemon": False,
                       "device": "cpu"},
            "emojivoice": {"voice": "paige", "daemon": False, "device": "cpu"},
            "pocket": {"voice": "alba", "device": "cpu"},
        },
        "presets": {},
        "aliases": aliases,
    }
    if extra:
        cfg.update(extra)
    return cfg


def _run_with_alias(argv, cfg, engine_class_name="KokoroEngine",
                    engine_key="kokoro", capture=False):
    """Run main() with the engine mocked. Returns the mock's synthesize."""
    mock_synth = MagicMock()
    MockEngine = MagicMock()
    MockEngine.return_value.synthesize = mock_synth

    patches = [
        patch("sys.argv", argv),
        patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg),
        patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"),
        patch("marmalade_tts.cli.play_wav"),
        patch("marmalade_tts.cli.os.unlink"),
        patch("marmalade_tts.cli.os.path.exists", return_value=True),
        patch(f"marmalade_tts.cli.{engine_class_name}", MockEngine),
        patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {engine_key: MockEngine}),
    ]
    for p in patches:
        p.__enter__()
    try:
        main()
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)
    return mock_synth, MockEngine


# ── Dispatch ────────────────────────────────────────────────────────────────

class TestAliasDispatch:
    def test_alias_dispatches_to_engine(self):
        cfg = _cfg_with_aliases({
            "narrator": {"engine": "kokoro", "voice": "george"},
        })
        synth, _ = _run_with_alias(
            ["marmalade-tts", "narrator", "Hello world"], cfg)
        synth.assert_called_once()
        # voice from the alias was passed through to synth
        assert synth.call_args[1].get("voice") == "george"

    def test_alias_unknown_falls_through_to_default_engine(self):
        """An unknown first token (not an engine, not an alias) should still
        fall through to the default-engine injection path — i.e. be treated
        as text."""
        cfg = _cfg_with_aliases({})
        synth, _ = _run_with_alias(
            ["marmalade-tts", "freeform text here"], cfg)
        synth.assert_called_once()
        # The whole positional is treated as text.
        assert "freeform text here" in synth.call_args[0][0]


class TestAliasVoiceMerge:
    def test_alias_voice_applied_when_no_voice_flag(self):
        cfg = _cfg_with_aliases({
            "narrator": {"engine": "kokoro", "voice": "george"},
        })
        synth, _ = _run_with_alias(
            ["marmalade-tts", "narrator", "hi"], cfg)
        assert synth.call_args[1].get("voice") == "george"

    def test_explicit_voice_flag_overrides_alias_voice(self):
        cfg = _cfg_with_aliases({
            "narrator": {"engine": "kokoro", "voice": "george"},
        })
        synth, _ = _run_with_alias(
            ["marmalade-tts", "narrator", "hi", "--voice", "heart"], cfg)
        assert synth.call_args[1].get("voice") == "heart"

    def test_positional_voice_overrides_alias_voice(self):
        """`marmalade-tts narrator heart 'hi'` — positional voice wins."""
        cfg = _cfg_with_aliases({
            "narrator": {"engine": "kokoro", "voice": "george"},
        })
        synth, _ = _run_with_alias(
            ["marmalade-tts", "narrator", "heart", "hi"], cfg)
        assert synth.call_args[1].get("voice") == "heart"


class TestAliasSpeedMerge:
    def test_alias_speed_applied_when_no_speed_flag(self):
        cfg = _cfg_with_aliases({
            "narrator": {"engine": "kokoro", "speed": 0.95},
        })
        synth, _ = _run_with_alias(
            ["marmalade-tts", "narrator", "hi"], cfg)
        assert synth.call_args[1].get("speed") == 0.95

    def test_explicit_speed_overrides_alias_speed(self):
        cfg = _cfg_with_aliases({
            "narrator": {"engine": "kokoro", "speed": 0.95},
        })
        synth, _ = _run_with_alias(
            ["marmalade-tts", "narrator", "hi", "--speed", "0.7"], cfg)
        assert synth.call_args[1].get("speed") == 0.7


class TestAliasLangSpeakerEmotion:
    def test_alias_lang_applied(self):
        cfg = _cfg_with_aliases({
            "fast-jp": {"engine": "kokoro", "lang": "j"},
        })
        synth, _ = _run_with_alias(
            ["marmalade-tts", "fast-jp", "hi"], cfg)
        assert synth.call_args[1].get("lang") == "j"

    def test_explicit_lang_overrides_alias_lang(self):
        cfg = _cfg_with_aliases({
            "fast-jp": {"engine": "kokoro", "lang": "j"},
        })
        synth, _ = _run_with_alias(
            ["marmalade-tts", "fast-jp", "hi", "--lang", "a"], cfg)
        assert synth.call_args[1].get("lang") == "a"


# ── Effects precedence ──────────────────────────────────────────────────────

class TestAliasEffects:
    def _run_capturing_effects(self, argv, cfg):
        """Run with sox-mocked and capture the effect_list apply_effects saw."""
        MockEngine = MagicMock()
        MockEngine.return_value.synthesize = MagicMock()
        seen = {}
        with patch("sys.argv", argv), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
             patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"), \
             patch("marmalade_tts.cli.play_wav"), \
             patch("marmalade_tts.cli.os.unlink"), \
             patch("marmalade_tts.cli.os.path.exists", return_value=True), \
             patch("marmalade_tts.cli.fx.sox_available", return_value=True), \
             patch("marmalade_tts.cli.fx.apply_effects") as mock_apply, \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockEngine}):
            main()
            seen["effects"] = (
                mock_apply.call_args[0][2] if mock_apply.call_args else None
            )
            seen["called"] = mock_apply.called
        return seen

    def test_alias_effects_applied_when_no_effect_flag(self):
        cfg = _cfg_with_aliases({
            "villain": {"engine": "kokoro",
                        "effects": ["pitch=-200", "reverb=40"]},
        })
        seen = self._run_capturing_effects(
            ["marmalade-tts", "villain", "boo"], cfg)
        assert seen["called"]
        assert "pitch=-200" in seen["effects"]
        assert "reverb=40" in seen["effects"]

    def test_explicit_effect_flag_replaces_alias_effects(self):
        cfg = _cfg_with_aliases({
            "villain": {"engine": "kokoro",
                        "effects": ["pitch=-200", "reverb=40"]},
        })
        seen = self._run_capturing_effects(
            ["marmalade-tts", "villain", "boo", "--effect", "robot"], cfg)
        assert seen["effects"] == ["robot"]

    def test_no_effects_flag_kills_alias_effects(self):
        cfg = _cfg_with_aliases({
            "villain": {"engine": "kokoro",
                        "effects": ["pitch=-200", "reverb=40"]},
        })
        # apply_effects must NOT be called when effect_list is empty.
        MockEngine = MagicMock()
        MockEngine.return_value.synthesize = MagicMock()
        with patch("sys.argv", ["marmalade-tts", "villain", "boo", "--no-effects"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg), \
             patch("marmalade_tts.cli.make_tmp_wav", return_value="/tmp/t.wav"), \
             patch("marmalade_tts.cli.play_wav"), \
             patch("marmalade_tts.cli.os.unlink"), \
             patch("marmalade_tts.cli.os.path.exists", return_value=True), \
             patch("marmalade_tts.cli.fx.sox_available", return_value=True), \
             patch("marmalade_tts.cli.fx.apply_effects") as mock_apply, \
             patch.dict("marmalade_tts.cli.ENGINE_CLASSES", {"kokoro": MockEngine}):
            main()
        mock_apply.assert_not_called()

    def test_alias_effects_take_precedence_over_engine_default_effects(self):
        """alias.effects must replace effects.defaults.<engine>, not stack."""
        cfg = _cfg_with_aliases(
            {"villain": {"engine": "kokoro", "effects": ["pitch=-200"]}},
            extra={"effects": {"defaults": {"kokoro": ["reverb=20", "bass=3"]}}},
        )
        seen = self._run_capturing_effects(
            ["marmalade-tts", "villain", "boo"], cfg)
        assert seen["effects"] == ["pitch=-200"]


# ── Reserved-name collision ─────────────────────────────────────────────────

class TestReservedNameCollision:
    def test_collision_with_engine_name_warns_and_uses_engine(self, capsys):
        cfg = _cfg_with_aliases({
            "kokoro": {"engine": "kitten", "voice": "Kiki"},
        })
        synth, _ = _run_with_alias(
            ["marmalade-tts", "kokoro", "hi"], cfg)
        # The kokoro engine should run, not the alias's kitten target.
        synth.assert_called_once()
        captured = capsys.readouterr()
        assert "shadows engine" in captured.err.lower() or \
               "alias" in captured.err.lower()


# ── Malformed aliases ───────────────────────────────────────────────────────

class TestMalformedAliases:
    def test_alias_without_engine_errors(self, capsys):
        cfg = _cfg_with_aliases({
            "broken": {"voice": "george"},  # missing 'engine'
        })
        with patch("sys.argv", ["marmalade-tts", "broken", "hi"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1
        err = capsys.readouterr().err.lower()
        assert "engine" in err

    def test_alias_with_unknown_engine_errors(self, capsys):
        cfg = _cfg_with_aliases({
            "broken": {"engine": "nopesuchengine", "voice": "x"},
        })
        with patch("sys.argv", ["marmalade-tts", "broken", "hi"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1
        err = capsys.readouterr().err.lower()
        assert "nopesuchengine" in err or "unknown engine" in err


# ── --list-aliases ──────────────────────────────────────────────────────────

class TestListAliases:
    def test_list_aliases_quick_intercept(self, capsys):
        cfg = _cfg_with_aliases({
            "narrator": {"engine": "kokoro", "voice": "george", "speed": 0.95},
        })
        with patch("sys.argv", ["marmalade-tts", "--list-aliases"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg):
            main()
        out = capsys.readouterr().out
        assert "narrator" in out
        assert "kokoro" in out

    def test_list_aliases_with_empty_config(self, capsys):
        cfg = _cfg_with_aliases({})
        with patch("sys.argv", ["marmalade-tts", "--list-aliases"]), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value=cfg):
            main()
        out = capsys.readouterr().out
        assert "no aliases" in out.lower()
