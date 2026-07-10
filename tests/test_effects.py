"""Tests for marmalade_tts.effects — effect parsing, resolution, sox chain building."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

from marmalade_tts.effects import (
    EFFECTS, BUILTIN_PRESETS,
    sox_available, resolve_effect_list, build_sox_args, apply_effects,
    list_effects, _parse_spec, _parse_echo, _parse_bandpass, _parse_chorus,
    _parse_fade, _parse_mid, _parse_tremolo, _parse_phaser, _parse_compressor,
)


# ── _parse_spec ───────────────────────────────────────────────────────────────

class TestParseSpec:
    def test_with_value(self):
        name, val = _parse_spec("reverb=50")
        assert name == "reverb"
        assert val == "50"

    def test_without_value(self):
        name, val = _parse_spec("flanger")
        assert name == "flanger"
        assert val is None

    def test_with_colon_value(self):
        name, val = _parse_spec("echo=0.8:0.88:60:0.4")
        assert name == "echo"
        assert val == "0.8:0.88:60:0.4"

    def test_strips_whitespace(self):
        name, val = _parse_spec("  reverb = 50  ")
        assert name == "reverb"
        assert val == "50"


# ── Parameter parsers ─────────────────────────────────────────────────────────

class TestParsers:
    def test_echo_default(self):
        args = _parse_echo(None)
        assert args[0] == "echo"
        assert len(args) == 5

    def test_echo_custom(self):
        args = _parse_echo("0.5:0.5:100:0.3")
        assert args == ["echo", "0.5", "0.5", "100", "0.3"]

    def test_echo_bad_format(self):
        with pytest.raises(ValueError):
            _parse_echo("bad")

    def test_bandpass_default(self):
        args = _parse_bandpass(None)
        assert "sinc" in args
        assert "-" in args[1]

    def test_bandpass_custom(self):
        args = _parse_bandpass("300:3400")
        assert args == ["sinc", "300-3400"]

    def test_bandpass_bad_format(self):
        with pytest.raises(ValueError):
            _parse_bandpass("just_one")

    def test_chorus_default(self):
        args = _parse_chorus(None)
        assert args[0] == "chorus"

    def test_fade_default(self):
        args = _parse_fade(None)
        assert args[0] == "fade"

    def test_fade_custom(self):
        args = _parse_fade("0.2:1.0")
        assert args[0] == "fade"
        assert "0.2" in args
        assert "1.0" in args

    def test_fade_bad_format(self):
        with pytest.raises(ValueError):
            _parse_fade("just_one")

    def test_mid_default(self):
        args = _parse_mid(None)
        assert args == ["equalizer", "1000", "1.0q", "0"]

    def test_mid_custom(self):
        args = _parse_mid("2500:6")
        assert args == ["equalizer", "2500", "1.0q", "6"]

    def test_mid_bad_format(self):
        with pytest.raises(ValueError):
            _parse_mid("just_one")

    def test_tremolo_default(self):
        args = _parse_tremolo(None)
        assert args[0] == "tremolo"
        assert args == ["tremolo", "5", "40.0"]

    def test_tremolo_custom(self):
        # depth 0-1 → sox percent
        args = _parse_tremolo("5:0.5")
        assert args == ["tremolo", "5", "50.0"]

    def test_tremolo_bad_format(self):
        with pytest.raises(ValueError):
            _parse_tremolo("just_one")

    def test_phaser_default(self):
        args = _parse_phaser(None)
        assert args[0] == "phaser"
        assert args == ["phaser", "0.7", "0.7", "3.0", "0.4", "0.5", "-s"]

    def test_phaser_custom(self):
        # speed:decay mapped into sox arg positions (decay before speed)
        args = _parse_phaser("0.5:0.4")
        assert args == ["phaser", "0.7", "0.7", "3.0", "0.4", "0.5", "-s"]

    def test_phaser_bad_format(self):
        with pytest.raises(ValueError):
            _parse_phaser("just_one")

    def test_compressor_default(self):
        args = _parse_compressor(None)
        assert args[0] == "compand"
        assert args[1] == "0.005,0.1"

    def test_compressor_custom_transfer_function(self):
        # threshold=-20, ratio=4 -> out_at_zero = -20 + (0 - -20)/4 = -15
        args = _parse_compressor("-20:4")
        assert args == ["compand", "0.005,0.1", "6:-90,-90,-20,-20,0,-15"]

    def test_compressor_ratio_below_one_clamped(self):
        # ratio < 1 is clamped to 1 (out_at_zero would otherwise exceed 0 dBFS)
        args = _parse_compressor("-20:0.5")
        transfer = args[2]
        # clamped ratio of 1 -> out_at_zero = -20 + (0 - -20)/1 = 0
        assert transfer == "6:-90,-90,-20,-20,0,0"

    def test_compressor_bad_format(self):
        with pytest.raises(ValueError):
            _parse_compressor("just_one")


# ── resolve_effect_list ───────────────────────────────────────────────────────

class TestResolveEffectList:
    def test_passthrough_regular_effect(self):
        resolved = resolve_effect_list(["reverb=50"], {})
        assert resolved == ["reverb=50"]

    def test_expands_builtin_preset(self):
        resolved = resolve_effect_list(["robot"], {})
        # robot = overdrive=20, pitch=-100, reverb=10
        assert len(resolved) >= 2
        assert "overdrive=20" in resolved

    def test_expands_user_preset(self):
        config = {"effects": {"presets": {"my_preset": ["reverb=40", "bass=3"]}}}
        resolved = resolve_effect_list(["my_preset"], config)
        assert "reverb=40" in resolved
        assert "bass=3" in resolved

    def test_user_preset_overrides_builtin(self):
        # User can override a builtin preset name
        config = {"effects": {"presets": {"robot": ["pitch=100"]}}}
        resolved = resolve_effect_list(["robot"], config)
        assert resolved == ["pitch=100"]

    def test_mixed_effects_and_presets(self):
        resolved = resolve_effect_list(["robot", "reverb=20"], {})
        assert "reverb=20" in resolved
        assert "overdrive=20" in resolved  # from robot preset

    def test_empty_list(self):
        assert resolve_effect_list([], {}) == []

    def test_unknown_name_passed_through(self):
        # Unknown names pass through (will fail at build_sox_args)
        resolved = resolve_effect_list(["nonexistent=5"], {})
        assert resolved == ["nonexistent=5"]


# ── build_sox_args ────────────────────────────────────────────────────────────

class TestBuildSoxArgs:
    def test_reverb(self):
        args = build_sox_args(["reverb=50"])
        assert args == ["reverb", "50"]

    def test_pitch(self):
        args = build_sox_args(["pitch=200"])
        assert args == ["pitch", "200"]

    def test_flanger_no_value(self):
        args = build_sox_args(["flanger"])
        assert args == ["flanger"]

    def test_chain(self):
        args = build_sox_args(["reverb=30", "pitch=100"])
        assert "reverb" in args
        assert "30" in args
        assert "pitch" in args
        assert "100" in args

    def test_unknown_effect_raises(self):
        with pytest.raises(ValueError, match="Unknown effect"):
            build_sox_args(["nonexistent=5"])

    def test_all_builtin_effects_build(self):
        # Every named effect should build without error with no param
        for name in EFFECTS:
            args = build_sox_args([name])
            assert isinstance(args, list)
            assert len(args) >= 1

    def test_default_reverb(self):
        # reverb with no param should default to 50
        args = build_sox_args(["reverb"])
        assert args == ["reverb", "50"]

    def test_default_pitch(self):
        args = build_sox_args(["pitch"])
        assert args == ["pitch", "100"]

    def test_lowpass_default(self):
        args = build_sox_args(["lowpass"])
        assert args == ["lowpass", "3000"]

    def test_lowpass_custom(self):
        args = build_sox_args(["lowpass=800"])
        assert args == ["lowpass", "800"]

    def test_highpass_default(self):
        args = build_sox_args(["highpass"])
        assert args == ["highpass", "300"]

    def test_highpass_custom(self):
        args = build_sox_args(["highpass=90"])
        assert args == ["highpass", "90"]


# ── All presets build without error ──────────────────────────────────────────

class TestPresets:
    def test_all_builtin_presets_build(self):
        for name, specs in BUILTIN_PRESETS.items():
            # Resolve preset and build args — should not raise
            resolved = resolve_effect_list([name], {})
            args = build_sox_args(resolved)
            assert isinstance(args, list), f"Preset {name} failed to build"

    def test_preset_names_are_strings(self):
        for name in BUILTIN_PRESETS:
            assert isinstance(name, str)

    def test_preset_specs_are_lists(self):
        for name, specs in BUILTIN_PRESETS.items():
            assert isinstance(specs, list), f"Preset {name} specs should be a list"

    def test_new_voice_stackup_presets_present(self):
        # These curated presets were added alongside the new EQ/dynamics effects.
        expected = {
            "broadcaster", "podcast", "trailer", "audiobook", "walkie_talkie",
            "vintage_radio", "intercom", "underwater", "alien", "ethereal", "dragon",
        }
        assert expected.issubset(BUILTIN_PRESETS.keys())

    def test_removed_presets_no_longer_builtin(self):
        # whisper/slow_deep/fast_high were removed; they should not resolve
        # as builtin presets anymore. resolve_effect_list passes unknown
        # names through unchanged, and build_sox_args then rejects them
        # as unknown effects.
        for name in ("whisper", "slow_deep", "fast_high"):
            assert name not in BUILTIN_PRESETS
            resolved = resolve_effect_list([name], {})
            assert resolved == [name]
            with pytest.raises(ValueError, match="Unknown effect"):
                build_sox_args(resolved)


# ── apply_effects ─────────────────────────────────────────────────────────────

class TestApplyEffects:
    def test_skips_if_no_specs(self, tmp_path):
        # Empty spec list → no-op, no sox call needed
        wav = tmp_path / "input.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 40)  # minimal fake WAV
        # Should not raise even if sox is missing
        apply_effects(str(wav), str(tmp_path / "out.wav"), [], {})

    def test_sox_not_found_raises(self, tmp_path):
        wav = tmp_path / "input.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 40)
        with patch("marmalade_tts.effects.sox_available", return_value=False):
            with pytest.raises(RuntimeError, match="sox is required"):
                apply_effects(str(wav), str(tmp_path / "out.wav"), ["reverb=50"], {})

    def test_unknown_effect_raises_before_sox(self, tmp_path):
        wav = tmp_path / "input.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 40)
        with patch("marmalade_tts.effects.sox_available", return_value=True):
            with pytest.raises((ValueError, RuntimeError)):
                apply_effects(str(wav), str(tmp_path / "out.wav"), ["bad_effect=1"], {})

    def test_same_file_uses_temp(self, tmp_path):
        """When in_path == out_path, a temp file should be used then renamed."""
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 40)

        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            # Write something to the target (3rd arg after sox + input)
            target = cmd[2]
            with open(target, "wb") as f:
                f.write(b"RIFF" + b"\x00" * 40)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("marmalade_tts.effects.sox_available", return_value=True):
            with patch("subprocess.run", side_effect=fake_run):
                apply_effects(str(wav), str(wav), ["reverb=50"], {})

        assert len(calls) == 1
        # The temp path used should NOT be the same as the input
        sox_cmd = calls[0]
        assert sox_cmd[1] == str(wav)      # input
        assert sox_cmd[2] != str(wav)      # output was temp file
        # Original file should still exist (renamed from temp)
        assert wav.exists()

    def test_different_files_no_temp(self, tmp_path):
        """When in_path != out_path, output directly to out_path."""
        in_wav = tmp_path / "in.wav"
        out_wav = tmp_path / "out.wav"
        in_wav.write_bytes(b"RIFF" + b"\x00" * 40)

        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            with open(cmd[2], "wb") as f:
                f.write(b"RIFF" + b"\x00" * 40)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("marmalade_tts.effects.sox_available", return_value=True):
            with patch("subprocess.run", side_effect=fake_run):
                apply_effects(str(in_wav), str(out_wav), ["pitch=200"], {})

        assert calls[0][2] == str(out_wav)


# ── list_effects ──────────────────────────────────────────────────────────────

class TestListEffects:
    def test_runs_without_error(self, capsys):
        list_effects()
        captured = capsys.readouterr()
        assert "reverb" in captured.out
        assert "pitch" in captured.out

    def test_shows_presets(self, capsys):
        list_effects()
        captured = capsys.readouterr()
        assert "robot" in captured.out
        assert "cave" in captured.out

    def test_shows_user_presets(self, capsys):
        list_effects(user_presets={"my_voice": ["reverb=30"]})
        captured = capsys.readouterr()
        assert "my_voice" in captured.out

    def test_usage_shown(self, capsys):
        list_effects()
        captured = capsys.readouterr()
        assert "--effect" in captured.out


# ── sox_available ─────────────────────────────────────────────────────────────

def test_sox_available_returns_bool():
    result = sox_available()
    assert isinstance(result, bool)
