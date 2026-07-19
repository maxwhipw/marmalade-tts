"""Tests for the API engine (OpenAI-compatible /audio/speech providers)."""

import io
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

from marmalade_tts.engines import EngineError
from marmalade_tts.engines.api import ApiEngine, DEFAULT_BASE_URL


def make_engine(**cfg):
    cfg.setdefault("api_key", "test-key")
    return ApiEngine(cfg)


def fake_response(body: bytes):
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestConfig:
    def test_defaults_target_venice(self):
        eng = make_engine()
        assert eng.base_url == DEFAULT_BASE_URL
        assert eng.model == "tts-kokoro"
        assert eng.voice == "af_heart"

    def test_base_url_trailing_slash_stripped(self):
        eng = make_engine(base_url="https://api.openai.com/v1/")
        assert eng.base_url == "https://api.openai.com/v1"


class TestApiKey:
    def test_inline_key_wins(self):
        eng = ApiEngine({"api_key": "inline", "api_key_env": "MISSING_VAR_X"})
        assert eng._api_key() == "inline"

    def test_env_var_fallback(self):
        eng = ApiEngine({"api_key_env": "MARMALADE_TEST_KEY"})
        with patch.dict(os.environ, {"MARMALADE_TEST_KEY": "from-env"}):
            assert eng._api_key() == "from-env"

    def test_missing_key_raises_with_env_name(self):
        eng = ApiEngine({"api_key_env": "MARMALADE_TEST_MISSING"})
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(EngineError) as exc:
                eng._api_key()
        assert "MARMALADE_TEST_MISSING" in str(exc.value)


class TestSynthesize:
    def test_success_writes_audio_and_sends_expected_payload(self, tmp_path):
        out = str(tmp_path / "out.wav")
        with patch("marmalade_tts.engines.api.urllib.request.urlopen",
                   return_value=fake_response(b"RIFFfake-wav")) as mock_open:
            make_engine().synthesize("hello there", out, voice="bm_george",
                                     speed=1.25)

        req = mock_open.call_args[0][0]
        assert req.full_url == f"{DEFAULT_BASE_URL}/audio/speech"
        assert req.get_header("Authorization") == "Bearer test-key"
        payload = json.loads(req.data)
        assert payload == {"model": "tts-kokoro", "input": "hello there",
                           "voice": "bm_george", "response_format": "wav",
                           "speed": 1.25}
        with open(out, "rb") as f:
            assert f.read() == b"RIFFfake-wav"

    def test_config_voice_used_when_no_override(self, tmp_path):
        out = str(tmp_path / "out.wav")
        with patch("marmalade_tts.engines.api.urllib.request.urlopen",
                   return_value=fake_response(b"x")) as mock_open:
            make_engine(voice="af_sky").synthesize("hi", out)
        assert json.loads(mock_open.call_args[0][0].data)["voice"] == "af_sky"

    def test_extra_passthrough_merged_into_payload(self, tmp_path):
        out = str(tmp_path / "out.wav")
        eng = make_engine(extra={"instructions": "whisper"})
        with patch("marmalade_tts.engines.api.urllib.request.urlopen",
                   return_value=fake_response(b"x")) as mock_open:
            eng.synthesize("hi", out)
        assert json.loads(mock_open.call_args[0][0].data)["instructions"] == "whisper"

    def test_http_error_raises_engine_error_with_provider_message(self, tmp_path):
        err = urllib.error.HTTPError(
            url="u", code=402, msg="Payment Required", hdrs=None,
            fp=io.BytesIO(b'{"error":"USD spend limit exceeded"}'))
        with patch("marmalade_tts.engines.api.urllib.request.urlopen",
                   side_effect=err):
            with pytest.raises(EngineError) as exc:
                make_engine().synthesize("hi", str(tmp_path / "out.wav"))
        assert "402" in str(exc.value)
        assert "USD spend limit exceeded" in str(exc.value)

    def test_network_error_raises_engine_error(self, tmp_path):
        with patch("marmalade_tts.engines.api.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("no route to host")):
            with pytest.raises(EngineError) as exc:
                make_engine().synthesize("hi", str(tmp_path / "out.wav"))
        assert "no route to host" in str(exc.value)

    def test_missing_key_fails_before_any_request(self, tmp_path):
        eng = ApiEngine({"api_key_env": "MARMALADE_TEST_MISSING"})
        with patch.dict(os.environ, {}, clear=True), \
             patch("marmalade_tts.engines.api.urllib.request.urlopen") as mock_open:
            with pytest.raises(EngineError):
                eng.synthesize("hi", str(tmp_path / "out.wav"))
        mock_open.assert_not_called()


class TestListVoices:
    def test_prints_models_and_voices(self, capsys):
        body = json.dumps({"data": [
            {"id": "tts-kokoro",
             "model_spec": {"name": "Kokoro", "voices": ["af_heart", "bm_george"]}},
            {"id": "tts-qwen3-0-6b",
             "model_spec": {"name": "Qwen 3 TTS", "voices": ["Serena"]}},
        ]}).encode()
        with patch("marmalade_tts.engines.api.urllib.request.urlopen",
                   return_value=fake_response(body)):
            make_engine().list_voices()
        out = capsys.readouterr().out
        assert "tts-kokoro" in out and "← configured" in out
        assert "af_heart, bm_george" in out
        assert "Serena" in out

    def test_unreachable_provider_prints_fallback(self, capsys):
        with patch("marmalade_tts.engines.api.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("down")):
            make_engine().list_voices()
        out = capsys.readouterr().out
        assert "Could not list models" in out
        assert "tts-kokoro" in out  # configured model still shown


class TestRegistration:
    def test_engine_registered_everywhere(self):
        from marmalade_tts.cli import ENGINE_CLASSES
        from marmalade_tts.completion import ENGINES
        from marmalade_tts.config import DEFAULT_CONFIG
        from marmalade_tts.init import ENGINE_INFO, ENGINE_ORDER
        from marmalade_tts.preprocessing import ENGINE_PROFILES

        assert ENGINE_CLASSES["api"] is ApiEngine
        assert "api" in ENGINES
        assert "api" in DEFAULT_CONFIG["engines"]
        assert all("api" in DEFAULT_CONFIG["presets"][t]
                   for t in ("fast", "balanced", "quality"))
        assert "api" in ENGINE_INFO and "api" in ENGINE_ORDER
        assert "api" in ENGINE_PROFILES
