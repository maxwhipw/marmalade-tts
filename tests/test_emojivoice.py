"""Tests for the EmojiVoice engine."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

from marmalade_tts.engines import Engine, EngineError


# ── Engine class structure ────────────────────────────────────────────────────

class TestEmojiVoiceStructure:
    def test_inherits_from_engine(self):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        assert issubclass(EmojiVoiceEngine, Engine)

    def test_has_name_attribute(self):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        assert EmojiVoiceEngine.name == "emojivoice"

    def test_default_voice_is_paige(self):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        assert EmojiVoiceEngine({"device": "cpu"}).voice == "paige"

    def test_voice_from_config(self):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        assert EmojiVoiceEngine({"voice": "paige"}).voice == "paige"

    def test_device_defaults_to_cpu(self):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        assert EmojiVoiceEngine({}).device == "cpu"

    def test_daemon_defaults_false(self):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        assert EmojiVoiceEngine({}).use_daemon is False


# ── VOICES / EMOJI_SPK / CHECKPOINTS consistency ─────────────────────────────

class TestVoicesAndMaps:
    def test_voices_nonempty(self):
        from marmalade_tts.engines.emojivoice import VOICES
        assert "paige" in VOICES

    def test_paige_emoji_map_has_eleven_entries(self):
        from marmalade_tts.engines.emojivoice import EMOJI_SPK
        assert "paige" in EMOJI_SPK
        assert len(EMOJI_SPK["paige"]) == 11

    def test_every_voice_has_map_and_checkpoint(self):
        from marmalade_tts.engines.emojivoice import VOICES, EMOJI_SPK, CHECKPOINTS
        for v in VOICES:
            assert v in EMOJI_SPK, f"{v} missing from EMOJI_SPK"
            assert v in CHECKPOINTS, f"{v} missing from CHECKPOINTS"


# ── parse_emoji — the core emoji→speaker logic ───────────────────────────────

class TestParseEmoji:
    def test_recognized_emoji_sets_spk_and_strips_it(self):
        from marmalade_tts.engines.emojivoice import parse_emoji
        spk, text = parse_emoji("I can't believe it 🤣", "paige")
        assert spk == 15  # 🤣 → 15
        assert "🤣" not in text
        assert "believe" in text

    def test_no_emoji_returns_neutral_and_unchanged_text(self):
        from marmalade_tts.engines.emojivoice import parse_emoji, NEUTRAL_SPK
        spk, text = parse_emoji("Just plain text", "paige")
        assert spk == NEUTRAL_SPK
        assert text == "Just plain text"

    def test_first_recognized_emoji_wins(self):
        from marmalade_tts.engines.emojivoice import parse_emoji
        spk, _ = parse_emoji("starts 😭 then 😡", "paige")
        assert spk == 103  # 😭 → 103, not 😡 → 58

    def test_all_recognized_emojis_are_stripped(self):
        from marmalade_tts.engines.emojivoice import parse_emoji
        spk, text = parse_emoji("a 😭 b 😡 c", "paige")
        assert "😭" not in text and "😡" not in text
        assert text == "a b c"

    def test_unknown_voice_falls_back_to_neutral(self):
        from marmalade_tts.engines.emojivoice import parse_emoji, NEUTRAL_SPK
        spk, text = parse_emoji("hi 🤣", "nonexistent")
        assert spk == NEUTRAL_SPK
        assert text == "hi 🤣"  # no map for the voice → nothing stripped


# ── list_voices ───────────────────────────────────────────────────────────────

class TestEmojiVoiceListVoices:
    def test_list_voices_runs(self, capsys):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        EmojiVoiceEngine({"voice": "paige"}).list_voices()
        out = capsys.readouterr().out
        assert "paige" in out


# ── synthesize ────────────────────────────────────────────────────────────────

class TestEmojiVoiceSynthesize:
    def test_daemon_path_strips_emoji_and_sends_spk(self, tmp_path):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        out_path = str(tmp_path / "out.wav")
        with patch("marmalade_tts.engines.emojivoice.dmgr.synthesize") as mock_dmgr:
            EmojiVoiceEngine({"device": "cpu", "daemon": True}).synthesize(
                "Hello there 😭", out_path)
        mock_dmgr.assert_called_once()
        assert mock_dmgr.call_args[0][0] == "emojivoice"
        req = mock_dmgr.call_args[0][1]
        assert req["spk"] == 103
        assert "😭" not in req["text"]
        # default (no --speed) → EmojiVoice's expressive length scale
        assert req["length_scale"] == 0.8

    def test_subprocess_invocation(self, tmp_path):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.emojivoice.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc) as mock_run:
            EmojiVoiceEngine({"device": "cpu", "voice": "paige"}).synthesize(
                "Wow 😮", out_path)
        cmd = mock_run.call_args[0][0]
        # cmd[0] is the venv python, cmd[1] is the oneshot script
        assert cmd[0].endswith("python")
        assert cmd[1].endswith("emojivoice-oneshot.py")
        assert "--checkpoint" in cmd
        assert "--spk" in cmd and "54" in cmd  # 😮 → 54
        assert "--out" in cmd and out_path in cmd
        # 😮 is stripped from the text the one-shot receives
        text_arg = cmd[cmd.index("--text") + 1]
        assert "😮" not in text_arg
        assert "Wow" in text_arg

    def test_explicit_speed_inverts_length_scale(self, tmp_path):
        # An explicit --speed (faster = higher) inverts to a shorter length
        # scale; it must override EmojiVoice's 0.8 expressive default.
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        out_path = str(tmp_path / "out.wav")
        with patch("marmalade_tts.engines.emojivoice.dmgr.synthesize") as mock_dmgr:
            EmojiVoiceEngine({"device": "cpu", "daemon": True}).synthesize(
                "hello", out_path, speed=2.0)
        req = mock_dmgr.call_args[0][1]
        assert req["length_scale"] == pytest.approx(1.0 / 2.0)

    def test_subprocess_default_length_scale(self, tmp_path):
        # With no --speed override the cold path uses EmojiVoice's
        # expressive 0.8 default.
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.emojivoice.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc) as mock_run:
            EmojiVoiceEngine({"device": "cpu"}).synthesize("hello", out_path)
        cmd = mock_run.call_args[0][0]
        ls = float(cmd[cmd.index("--length-scale") + 1])
        assert ls == pytest.approx(0.8)

    def test_parentheses_stripped_from_text(self, tmp_path):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.emojivoice.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc) as mock_run:
            EmojiVoiceEngine({"device": "cpu"}).synthesize("Hello (aside) world", out_path)
        cmd = mock_run.call_args[0][0]
        text_arg = cmd[cmd.index("--text") + 1]
        assert "(" not in text_arg and ")" not in text_arg

    def test_missing_venv_exits(self, tmp_path):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        with patch("marmalade_tts.engines.emojivoice.os.path.exists", return_value=False):
            with pytest.raises(EngineError):
                EmojiVoiceEngine({"device": "cpu"}).synthesize(
                    "hi", str(tmp_path / "o.wav"))

    def test_missing_checkpoint_exits(self, tmp_path):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        # venv python exists, but the speaker checkpoint does not
        with patch("marmalade_tts.engines.emojivoice.os.path.exists",
                   side_effect=lambda p: p.endswith("python")):
            with pytest.raises(EngineError):
                EmojiVoiceEngine({"device": "cpu"}).synthesize(
                    "hi", str(tmp_path / "o.wav"))

    def test_text_with_only_emoji_exits(self, tmp_path):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        # "😭" alone → cleaned text is empty → should exit rather than synth nothing
        with pytest.raises(EngineError):
            EmojiVoiceEngine({"device": "cpu", "daemon": True}).synthesize(
                "😭", str(tmp_path / "o.wav"))

    def test_failed_subprocess_exits(self, tmp_path):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        fake_proc = MagicMock(returncode=1, stderr=b"boom")
        with patch("marmalade_tts.engines.emojivoice.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc):
            with pytest.raises(EngineError):
                EmojiVoiceEngine({"device": "cpu"}).synthesize(
                    "hi", str(tmp_path / "o.wav"))

    def test_steps_and_temperature_propagate_to_subprocess(self, tmp_path):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.emojivoice.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc) as mock_run:
            EmojiVoiceEngine({"device": "cpu", "steps": 50,
                              "temperature": 0.5}).synthesize("hi", out_path)
        cmd = mock_run.call_args[0][0]
        assert cmd[cmd.index("--steps") + 1] == "50"
        assert cmd[cmd.index("--temperature") + 1] == "0.5"

    def test_no_steps_or_temperature_keeps_cmd_clean(self, tmp_path):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        out_path = str(tmp_path / "out.wav")
        fake_proc = MagicMock(returncode=0, stderr=b"")
        with patch("marmalade_tts.engines.emojivoice.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.os.path.exists", return_value=True), \
             patch("marmalade_tts.engines.subprocess.run", return_value=fake_proc) as mock_run:
            EmojiVoiceEngine({"device": "cpu"}).synthesize("hi", out_path)
        cmd = mock_run.call_args[0][0]
        assert "--steps" not in cmd
        assert "--temperature" not in cmd

    def test_steps_propagates_to_daemon_request(self, tmp_path):
        from marmalade_tts.engines.emojivoice import EmojiVoiceEngine
        out_path = str(tmp_path / "out.wav")
        with patch("marmalade_tts.engines.emojivoice.dmgr.synthesize") as mock_dmgr:
            EmojiVoiceEngine({"device": "cpu", "daemon": True,
                              "steps": 50, "temperature": 0.5}).synthesize(
                "Hello", out_path)
        request = mock_dmgr.call_args[0][1]
        assert request["steps"] == 50
        assert request["temperature"] == 0.5
