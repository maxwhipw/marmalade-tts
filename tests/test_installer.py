"""Tests for the hands-off engine installer."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from marmalade_tts import installer


# ── Recipes ──────────────────────────────────────────────────────────────────

class TestInstallRecipes:
    def test_every_engine_has_a_recipe(self):
        from marmalade_tts.init import ENGINE_INFO
        for eng in ENGINE_INFO:
            assert eng in installer.INSTALL_RECIPES, f"{eng} missing a recipe"

    def test_recipe_has_required_keys(self):
        required = {"python", "venv", "pip", "pip_post", "system_deps",
                    "models", "warm_cache", "selftest_text"}
        for name, recipe in installer.INSTALL_RECIPES.items():
            assert required <= set(recipe), f"{name} recipe missing keys"

    def test_matcha_and_emojivoice_require_python_311(self):
        # matcha-tts does not build on 3.12 — these MUST pin 3.11.
        assert installer.INSTALL_RECIPES["matcha"]["python"] == "3.11"
        assert installer.INSTALL_RECIPES["emojivoice"]["python"] == "3.11"

    def test_recipe_venv_matches_engine_module_constant(self):
        # The installer must create venvs exactly where each engine module
        # (and daemon.py) looks for them.
        from marmalade_tts.engines import kitten, kokoro, piper, coqui, pocket, matcha, emojivoice
        pairs = {
            "kitten": kitten.KITTEN_VENV,
            "kokoro": kokoro.KOKORO_VENV,
            "piper": piper.PIPER_VENV,
            "coqui": coqui.COQUI_VENV,
            "pocket": pocket.POCKET_VENV,
            "matcha": matcha.MATCHA_VENV,
            "emojivoice": emojivoice.EMOJIVOICE_VENV,
        }
        for name, module_venv in pairs.items():
            recipe_venv = os.path.expanduser(installer.INSTALL_RECIPES[name]["venv"])
            assert recipe_venv == module_venv, f"{name} venv path mismatch"

    def test_recipe_venv_matches_daemon_engine_python(self):
        from marmalade_tts import daemon
        for name, recipe in installer.INSTALL_RECIPES.items():
            if name == "pocket":
                continue  # pocket has no daemon
            recipe_python = os.path.join(
                os.path.expanduser(recipe["venv"]), "bin", "python")
            assert recipe_python in daemon.ENGINE_PYTHON[name], \
                f"{name} daemon ENGINE_PYTHON path mismatch"


# ── uv location ──────────────────────────────────────────────────────────────

class TestUvBin:
    def test_uv_found_on_path(self):
        with patch("marmalade_tts.installer.shutil.which", return_value="/usr/bin/uv"):
            assert installer.uv_bin() == "/usr/bin/uv"

    def test_uv_found_in_local_bin(self, tmp_path):
        fake_uv = tmp_path / "uv"
        fake_uv.write_text("")
        with patch("marmalade_tts.installer.shutil.which", return_value=None), \
             patch("marmalade_tts.installer.os.path.expanduser",
                   side_effect=lambda p: str(fake_uv) if p.endswith("/uv") else p):
            assert installer.uv_bin() == str(fake_uv)

    def test_uv_missing_exits(self):
        with patch("marmalade_tts.installer.shutil.which", return_value=None), \
             patch("marmalade_tts.installer.os.path.exists", return_value=False):
            with pytest.raises(SystemExit):
                installer.uv_bin()


# ── Distro detection ─────────────────────────────────────────────────────────

class TestDetectDistro:
    def test_detects_apt(self):
        with patch("marmalade_tts.installer.shutil.which",
                   side_effect=lambda c: "/usr/bin/apt-get" if c == "apt-get" else None):
            assert installer.detect_distro() == "apt-get"

    def test_detects_pacman(self):
        with patch("marmalade_tts.installer.shutil.which",
                   side_effect=lambda c: "/usr/bin/pacman" if c == "pacman" else None):
            assert installer.detect_distro() == "pacman"

    def test_returns_none_when_unknown(self):
        with patch("marmalade_tts.installer.shutil.which", return_value=None):
            assert installer.detect_distro() is None


# ── System deps + sudo gating ────────────────────────────────────────────────

class TestEnsureSystemDeps:
    def test_present_dep_is_skipped(self):
        with patch("marmalade_tts.installer.shutil.which", return_value="/usr/bin/espeak-ng"):
            results = installer.ensure_system_deps(["espeak-ng"], allow_sudo=False,
                                                   interactive=False)
        assert results == [("espeak-ng", "present")]

    def test_missing_dep_non_interactive_without_allow_sudo_is_skipped(self):
        with patch("marmalade_tts.installer._dep_present", return_value=False), \
             patch("marmalade_tts.installer.shutil.which",
                   side_effect=lambda c: "/usr/bin/apt-get" if c == "apt-get" else None), \
             patch("marmalade_tts.installer._run") as mock_run:
            results = installer.ensure_system_deps(["espeak-ng"], allow_sudo=False,
                                                   interactive=False)
        mock_run.assert_not_called()
        assert ("espeak-ng", "skipped") in results

    def test_missing_dep_non_interactive_with_allow_sudo_installs(self):
        with patch("marmalade_tts.installer._dep_present", return_value=False), \
             patch("marmalade_tts.installer.shutil.which",
                   side_effect=lambda c: "/usr/bin/apt-get" if c == "apt-get" else None), \
             patch("marmalade_tts.installer._run") as mock_run:
            results = installer.ensure_system_deps(["espeak-ng"], allow_sudo=True,
                                                   interactive=False)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "sudo" in cmd and "espeak-ng" in cmd
        assert ("espeak-ng", "installed") in results

    def test_missing_dep_no_pkgmgr_is_skipped(self):
        with patch("marmalade_tts.installer._dep_present", return_value=False), \
             patch("marmalade_tts.installer.shutil.which", return_value=None), \
             patch("marmalade_tts.installer._run") as mock_run:
            results = installer.ensure_system_deps(["espeak-ng"], allow_sudo=True,
                                                   interactive=False)
        mock_run.assert_not_called()
        assert ("espeak-ng", "skipped-no-pkgmgr") in results

    def test_interactive_decline_skips(self):
        with patch("marmalade_tts.installer._dep_present", return_value=False), \
             patch("marmalade_tts.installer.shutil.which",
                   side_effect=lambda c: "/usr/bin/apt-get" if c == "apt-get" else None), \
             patch("marmalade_tts.installer._run") as mock_run, \
             patch("builtins.input", return_value="n"):
            results = installer.ensure_system_deps(["espeak-ng"], allow_sudo=False,
                                                   interactive=True)
        mock_run.assert_not_called()
        assert ("espeak-ng", "skipped") in results

    def test_interactive_accept_installs(self):
        with patch("marmalade_tts.installer._dep_present", return_value=False), \
             patch("marmalade_tts.installer.shutil.which",
                   side_effect=lambda c: "/usr/bin/apt-get" if c == "apt-get" else None), \
             patch("marmalade_tts.installer._run") as mock_run, \
             patch("builtins.input", return_value=""):
            results = installer.ensure_system_deps(["espeak-ng"], allow_sudo=False,
                                                   interactive=True)
        mock_run.assert_called_once()
        assert ("espeak-ng", "installed") in results


class TestHasEspeakNg:
    def test_binary_present(self):
        with patch("marmalade_tts.installer.shutil.which", return_value="/usr/bin/espeak-ng"):
            assert installer._has_espeak_ng() is True

    def test_lib_present_via_ctypes(self):
        # Binary missing; ctypes.CDLL succeeds on the first soname.
        mock_cdll = MagicMock(return_value=MagicMock())
        with patch("marmalade_tts.installer.shutil.which", return_value=None), \
             patch("ctypes.CDLL", mock_cdll):
            assert installer._has_espeak_ng() is True

    def test_neither_present(self):
        with patch("marmalade_tts.installer.shutil.which", return_value=None), \
             patch("ctypes.CDLL", side_effect=OSError("not found")):
            assert installer._has_espeak_ng() is False


# ── Manifest + model fetching ────────────────────────────────────────────────

class TestManifest:
    def test_manifest_parses(self):
        manifest = installer.load_manifest()
        assert "models" in manifest
        assert "piper-en_US-lessac-medium" in manifest["models"]
        assert "emojivoice-paige" in manifest["models"]

    def test_piper_entry_has_two_files(self):
        manifest = installer.load_manifest()
        files = manifest["models"]["piper-en_US-lessac-medium"]["files"]
        dests = [f["dest"] for f in files]
        assert any(d.endswith(".onnx") for d in dests)
        assert any(d.endswith(".onnx.json") for d in dests)

    def test_emojivoice_entry_uses_gdrive(self):
        manifest = installer.load_manifest()
        src = manifest["models"]["emojivoice-paige"]["files"][0]["sources"][0]
        assert src["type"] == "gdrive"
        assert src["filename"] == "emoji-hri-paige-inference.ckpt"

    def test_recipe_model_ids_exist_in_manifest(self):
        manifest = installer.load_manifest()
        for name, recipe in installer.INSTALL_RECIPES.items():
            for mid in (recipe["models"] or []):
                assert mid in manifest["models"], f"{name}: {mid} not in manifest"


class TestFetchModel:
    def _fspec(self, dest, sources, sha256=None):
        return {"dest": dest, "sha256": sha256, "sources": sources}

    def test_already_present_no_sha_is_skipped(self, tmp_path):
        dest = tmp_path / "model.bin"
        dest.write_bytes(b"x" * 4096)
        fspec = self._fspec(str(dest), [{"type": "https", "url": "http://x"}])
        with patch("marmalade_tts.installer._http_download") as mock_dl:
            status = installer._fetch_file(fspec, "test-model")
        mock_dl.assert_not_called()
        assert status == "present"

    def test_source_fallback_tries_next_on_failure(self, tmp_path):
        dest = tmp_path / "model.bin"
        fspec = self._fspec(str(dest), [
            {"type": "https", "url": "http://bad"},
            {"type": "https", "url": "http://good"},
        ])

        def fake_dl(url, d):
            if url == "http://bad":
                raise RuntimeError("boom")
            with open(d, "wb") as f:
                f.write(b"y" * 4096)

        with patch("marmalade_tts.installer._http_download", side_effect=fake_dl) as mock_dl:
            status = installer._fetch_file(fspec, "test-model")
        assert mock_dl.call_count == 2
        assert status == "downloaded"

    def test_all_sources_fail_raises(self, tmp_path):
        dest = tmp_path / "model.bin"
        fspec = self._fspec(str(dest), [{"type": "https", "url": "http://bad"}])
        with patch("marmalade_tts.installer._http_download",
                   side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                installer._fetch_file(fspec, "test-model")

    def test_sha256_mismatch_rejects_and_raises(self, tmp_path):
        dest = tmp_path / "model.bin"
        fspec = self._fspec(str(dest), [{"type": "https", "url": "http://x"}],
                            sha256="0" * 64)

        def fake_dl(url, d):
            with open(d, "wb") as f:
                f.write(b"z" * 4096)

        with patch("marmalade_tts.installer._http_download", side_effect=fake_dl):
            with pytest.raises(RuntimeError):
                installer._fetch_file(fspec, "test-model")
        assert not dest.exists()  # bad download removed


# ── Self-test ────────────────────────────────────────────────────────────────

class TestSelftest:
    def _wav_writer(self, frames=8000):
        """Return a synthesize() stand-in that writes a minimal valid WAV."""
        import wave

        def _synth(text, out_path, **kwargs):
            with wave.open(out_path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(22050)
                w.writeframes(b"\x00\x00" * frames)
        return _synth

    def test_selftest_pass(self):
        mock_engine = MagicMock()
        mock_engine.synthesize.side_effect = self._wav_writer()
        with patch("marmalade_tts.cli.ENGINE_CLASSES",
                   {"kitten": lambda cfg: mock_engine}):
            ok, msg = installer.selftest("kitten", "hello")
        assert ok is True

    def test_selftest_fail_on_engine_exit(self):
        def _exit(*a, **k):
            raise SystemExit("[kitten] boom")
        mock_engine = MagicMock()
        mock_engine.synthesize.side_effect = _exit
        with patch("marmalade_tts.cli.ENGINE_CLASSES",
                   {"kitten": lambda cfg: mock_engine}):
            ok, msg = installer.selftest("kitten", "hello")
        assert ok is False

    def test_selftest_fail_on_tiny_output(self):
        def _tiny(text, out_path, **kwargs):
            with open(out_path, "wb") as f:
                f.write(b"RIFF")
        mock_engine = MagicMock()
        mock_engine.synthesize.side_effect = _tiny
        with patch("marmalade_tts.cli.ENGINE_CLASSES",
                   {"kitten": lambda cfg: mock_engine}):
            ok, msg = installer.selftest("kitten", "hello")
        assert ok is False

    def test_selftest_fail_when_no_output(self):
        mock_engine = MagicMock()
        mock_engine.synthesize.return_value = None  # writes nothing
        with patch("marmalade_tts.cli.ENGINE_CLASSES",
                   {"kitten": lambda cfg: mock_engine}):
            ok, msg = installer.selftest("kitten", "hello")
        assert ok is False


# ── install_engine orchestration ─────────────────────────────────────────────

class TestInstallEngine:
    def test_unknown_engine_exits(self):
        with pytest.raises(SystemExit):
            installer.install_engine("nonexistent")

    def test_happy_path_runs_all_steps(self, tmp_path):
        venv = tmp_path / "kokoro-venv"
        recipe = {
            "python": None,
            "venv": str(venv),
            "pip": ["kokoro"],
            "pip_post": [],
            "system_deps": [],
            "models": None,
            "warm_cache": None,
            "selftest_text": "hi",
        }
        with patch.dict(installer.INSTALL_RECIPES, {"kokoro": recipe}), \
             patch("marmalade_tts.installer.uv_venv") as mock_venv, \
             patch("marmalade_tts.installer.uv_pip_install") as mock_pip, \
             patch("marmalade_tts.installer.selftest", return_value=(True, "ok")):
            result = installer.install_engine("kokoro", interactive=False)
        mock_venv.assert_called_once()
        mock_pip.assert_called_once()
        assert result["error"] is None
        assert result["selftest"] == (True, "ok")

    def test_skip_selftest(self, tmp_path):
        venv = tmp_path / "kokoro-venv"
        recipe = {
            "python": None, "venv": str(venv), "pip": ["kokoro"], "pip_post": [],
            "system_deps": [], "models": None, "warm_cache": None,
            "selftest_text": "hi",
        }
        with patch.dict(installer.INSTALL_RECIPES, {"kokoro": recipe}), \
             patch("marmalade_tts.installer.uv_venv"), \
             patch("marmalade_tts.installer.uv_pip_install"), \
             patch("marmalade_tts.installer.selftest") as mock_st:
            result = installer.install_engine("kokoro", skip_selftest=True,
                                              interactive=False)
        mock_st.assert_not_called()
        assert result["selftest"] is None

    def test_pip_failure_captured_in_result(self, tmp_path):
        venv = tmp_path / "kokoro-venv"
        recipe = {
            "python": None, "venv": str(venv), "pip": ["kokoro"], "pip_post": [],
            "system_deps": [], "models": None, "warm_cache": None,
            "selftest_text": "hi",
        }
        with patch.dict(installer.INSTALL_RECIPES, {"kokoro": recipe}), \
             patch("marmalade_tts.installer.uv_venv"), \
             patch("marmalade_tts.installer.uv_pip_install",
                   side_effect=subprocess.CalledProcessError(1, "uv")):
            result = installer.install_engine("kokoro", interactive=False)
        assert result["error"] is not None
        assert result["selftest"] is None

    def test_python_version_triggers_uv_python_install(self, tmp_path):
        venv = tmp_path / "matcha-venv"
        recipe = {
            "python": "3.11", "venv": str(venv), "pip": ["matcha-tts"], "pip_post": [],
            "system_deps": [], "models": None, "warm_cache": None,
            "selftest_text": "hi",
        }
        with patch.dict(installer.INSTALL_RECIPES, {"matcha": recipe}), \
             patch("marmalade_tts.installer.uv_python_install") as mock_pyinstall, \
             patch("marmalade_tts.installer.uv_venv"), \
             patch("marmalade_tts.installer.uv_pip_install"), \
             patch("marmalade_tts.installer.selftest", return_value=(True, "ok")):
            installer.install_engine("matcha", interactive=False)
        mock_pyinstall.assert_called_once_with("3.11")


class TestInstallEngines:
    def test_summary_reports_all(self, tmp_path):
        recipe = {
            "python": None, "venv": str(tmp_path / "v"), "pip": ["x"], "pip_post": [],
            "system_deps": [], "models": None, "warm_cache": None, "selftest_text": "hi",
        }
        with patch.dict(installer.INSTALL_RECIPES, {"kokoro": recipe}), \
             patch("marmalade_tts.installer.uv_venv"), \
             patch("marmalade_tts.installer.uv_pip_install"), \
             patch("marmalade_tts.installer.selftest", return_value=(True, "ok")):
            results = installer.install_engines(["kokoro"], interactive=False)
        assert len(results) == 1
        assert results[0]["engine"] == "kokoro"
