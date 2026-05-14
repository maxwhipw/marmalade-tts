"""Tests for marmalade_tts.config — YAML config get/set/load/save."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import yaml
from unittest.mock import patch

import marmalade_tts.config as cfg_mod


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_config():
    return {
        "defaults": {
            "engine": "kokoro",
            "speed": 1.0,
            "play": True,
        },
        "engines": {
            "kitten": {"voice": "Kiki", "daemon": True, "model_size": "micro"},
            "kokoro": {"voice": "af_heart", "lang": "a"},
        },
        "presets": {
            "fast": {"kitten": "nano", "kokoro": "af_heart"},
        },
    }


@pytest.fixture
def tmp_config_path(tmp_path):
    return str(tmp_path / "config.yaml")


# ── get_path ─────────────────────────────────────────────────────────────────

class TestGetPath:
    def test_simple_key(self, sample_config):
        val, found = cfg_mod.get_path(sample_config, "defaults.engine")
        assert found
        assert val == "kokoro"

    def test_nested_key(self, sample_config):
        val, found = cfg_mod.get_path(sample_config, "engines.kitten.voice")
        assert found
        assert val == "Kiki"

    def test_missing_key(self, sample_config):
        val, found = cfg_mod.get_path(sample_config, "engines.kitten.nonexistent")
        assert not found
        assert val is None

    def test_missing_top_level(self, sample_config):
        val, found = cfg_mod.get_path(sample_config, "nonexistent.key")
        assert not found

    def test_returns_dict(self, sample_config):
        val, found = cfg_mod.get_path(sample_config, "engines.kitten")
        assert found
        assert isinstance(val, dict)
        assert val["voice"] == "Kiki"

    def test_bool_value(self, sample_config):
        val, found = cfg_mod.get_path(sample_config, "engines.kitten.daemon")
        assert found
        assert val is True

    def test_int_value(self, sample_config):
        val, found = cfg_mod.get_path(sample_config, "defaults.speed")
        assert found
        assert val == 1.0


# ── set_path ─────────────────────────────────────────────────────────────────

class TestSetPath:
    def test_set_existing(self, sample_config):
        cfg_mod.set_path(sample_config, "defaults.engine", "kitten")
        val, _ = cfg_mod.get_path(sample_config, "defaults.engine")
        assert val == "kitten"

    def test_set_creates_parents(self, sample_config):
        cfg_mod.set_path(sample_config, "new.nested.key", "value")
        val, found = cfg_mod.get_path(sample_config, "new.nested.key")
        assert found
        assert val == "value"

    def test_set_numeric_string_parsed(self, sample_config):
        cfg_mod.set_path(sample_config, "defaults.speed", "1.5")
        val, _ = cfg_mod.get_path(sample_config, "defaults.speed")
        assert val == 1.5
        assert isinstance(val, float)

    def test_set_bool_string_parsed(self, sample_config):
        cfg_mod.set_path(sample_config, "defaults.play", "false")
        val, _ = cfg_mod.get_path(sample_config, "defaults.play")
        assert val is False

    def test_set_int_string_parsed(self, sample_config):
        cfg_mod.set_path(sample_config, "engines.kitten.model_size", "nano")
        val, _ = cfg_mod.get_path(sample_config, "engines.kitten.model_size")
        assert val == "nano"

    def test_set_preserves_other_keys(self, sample_config):
        cfg_mod.set_path(sample_config, "defaults.engine", "piper")
        val, _ = cfg_mod.get_path(sample_config, "defaults.speed")
        assert val == 1.0  # unchanged

    def test_set_yes_stays_a_string(self, sample_config):
        """YAML 1.1 'Norway problem': 'yes' should not become bool True."""
        cfg_mod.set_path(sample_config, "defaults.engine", "yes")
        val, _ = cfg_mod.get_path(sample_config, "defaults.engine")
        assert val == "yes"
        assert isinstance(val, str)

    def test_set_on_off_stay_strings(self, sample_config):
        for word in ("on", "off", "no", "y", "n"):
            cfg_mod.set_path(sample_config, "defaults.engine", word)
            val, _ = cfg_mod.get_path(sample_config, "defaults.engine")
            assert val == word
            assert isinstance(val, str)

    def test_set_true_false_become_bool(self, sample_config):
        cfg_mod.set_path(sample_config, "defaults.play", "true")
        val, _ = cfg_mod.get_path(sample_config, "defaults.play")
        assert val is True
        cfg_mod.set_path(sample_config, "defaults.play", "False")  # case-insensitive
        val, _ = cfg_mod.get_path(sample_config, "defaults.play")
        assert val is False

    def test_set_null_becomes_none(self, sample_config):
        cfg_mod.set_path(sample_config, "engines.kokoro.lang", "null")
        val, _ = cfg_mod.get_path(sample_config, "engines.kokoro.lang")
        assert val is None


# ── save / load ───────────────────────────────────────────────────────────────

class TestSaveLoad:
    def test_round_trip(self, sample_config, tmp_config_path):
        with patch.object(cfg_mod, "CONFIG_PATH", tmp_config_path):
            cfg_mod.save(sample_config)
            loaded = cfg_mod.load()
        assert loaded["defaults"]["engine"] == "kokoro"
        assert loaded["engines"]["kitten"]["voice"] == "Kiki"

    def test_load_missing_file_returns_defaults(self, tmp_path):
        missing = str(tmp_path / "nonexistent.yaml")
        with patch.object(cfg_mod, "CONFIG_PATH", missing):
            loaded = cfg_mod.load()
        assert "defaults" in loaded
        assert "engines" in loaded

    def test_save_creates_dirs(self, tmp_path):
        deep_path = str(tmp_path / "a" / "b" / "c" / "config.yaml")
        with patch.object(cfg_mod, "CONFIG_PATH", deep_path):
            cfg_mod.save({"defaults": {"engine": "kitten"}})
        assert os.path.exists(deep_path)

    def test_saved_file_is_valid_yaml(self, sample_config, tmp_config_path):
        with patch.object(cfg_mod, "CONFIG_PATH", tmp_config_path):
            cfg_mod.save(sample_config)
        with open(tmp_config_path) as f:
            data = yaml.safe_load(f)
        assert data["defaults"]["engine"] == "kokoro"


# ── engine_cfg ────────────────────────────────────────────────────────────────

class TestEngineCfg:
    def test_merges_defaults_into_engine(self, sample_config):
        sample_config["defaults"]["device"] = "cpu"
        result = cfg_mod.engine_cfg(sample_config, "kitten")
        assert result["device"] == "cpu"
        assert result["voice"] == "Kiki"

    def test_engine_overrides_defaults(self, sample_config):
        sample_config["defaults"]["speed"] = 1.0
        sample_config["engines"]["kitten"]["speed"] = 1.5
        result = cfg_mod.engine_cfg(sample_config, "kitten")
        assert result["speed"] == 1.5

    def test_unknown_engine_returns_defaults_only(self, sample_config):
        result = cfg_mod.engine_cfg(sample_config, "unknown_engine")
        assert "device" in result

    def test_engine_cfg_does_not_mutate_original(self, sample_config):
        original_kitten = dict(sample_config["engines"]["kitten"])
        cfg_mod.engine_cfg(sample_config, "kitten")
        assert sample_config["engines"]["kitten"] == original_kitten


# ── default config completeness ───────────────────────────────────────────────

class TestDefaultConfig:
    def test_all_engines_present(self):
        cfg = cfg_mod.DEFAULT_CONFIG
        for engine in ["kitten", "kokoro", "piper", "coqui", "pocket"]:
            assert engine in cfg["engines"], f"Missing engine: {engine}"

    def test_all_presets_present(self):
        cfg = cfg_mod.DEFAULT_CONFIG
        for preset in ["fast", "balanced", "quality"]:
            assert preset in cfg["presets"], f"Missing preset: {preset}"

    def test_defaults_have_required_keys(self):
        cfg = cfg_mod.DEFAULT_CONFIG
        for key in ["engine", "device", "speed", "play"]:
            assert key in cfg["defaults"], f"Missing default: {key}"

    def test_pocket_in_default_config(self):
        cfg = cfg_mod.DEFAULT_CONFIG
        assert "pocket" in cfg["engines"]
        assert cfg["engines"]["pocket"]["voice"] == "alba"
        assert cfg["engines"]["pocket"]["device"] == "cpu"

    def test_pocket_engine_cfg_returns_defaults(self):
        result = cfg_mod.engine_cfg(cfg_mod.DEFAULT_CONFIG, "pocket")
        assert result["voice"] == "alba"
        assert result["device"] == "cpu"

    def test_pocket_in_presets(self):
        cfg = cfg_mod.DEFAULT_CONFIG
        for preset in ["fast", "balanced", "quality"]:
            assert "pocket" in cfg["presets"][preset], (
                f"pocket missing from {preset} preset"
            )
