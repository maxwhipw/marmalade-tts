"""Tests for the uninstaller — the file-deletion code path.

Every test is paranoid about NOT touching real ~/.local/share/*-venv/ dirs.
We tmp_path everything that lives on disk and monkeypatch any code that
might reach out to the user's actual filesystem.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, call

import pytest

from marmalade_tts import uninstaller
from marmalade_tts.uninstaller import (
    Report,
    detect_install_method,
    plan_for_engine,
    plan_for_all_engines,
    plan_for_purge,
    purge,
    uninstall_engine,
    uninstall_all_engines,
    REMOVAL_HINTS,
)


# ── Autouse: clear the _safe_paths lru_cache around every test ──────────────
# Stale cache from a relocated-fixture test would otherwise contaminate the
# next test's view of the whitelist.

@pytest.fixture(autouse=True)
def _clear_safe_paths_cache():
    uninstaller._safe_paths.cache_clear()
    yield
    uninstaller._safe_paths.cache_clear()


# ── Fixture: redirect EVERY managed path under tmp_path ─────────────────────

@pytest.fixture
def relocated(tmp_path, monkeypatch):
    """Move every absolute path the uninstaller cares about under tmp_path.

    The trick: monkeypatch INSTALL_RECIPES, BASE_DIR, CONFIG_DIR,
    ENGINE_MODEL_DIRS, SYSTEMD_USER_DIR, and _DIR_MARKERS so the whitelist
    builds against tmp_path paths instead of the user's $HOME.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    # _is_under_managed_root resolves ~ via os.path.expanduser, so we point
    # $HOME at the fake home for the test. (HOME wins on Linux.)
    monkeypatch.setenv("HOME", str(fake_home))

    new_base = str(fake_home / ".local/share/marmalade-tts")
    new_cfg = str(fake_home / ".config/marmalade-tts")
    new_systemd = str(fake_home / ".config/systemd/user")
    new_model_dirs = {
        "piper": str(fake_home / ".local/share/piper"),
        "coqui": str(fake_home / ".local/share/tts"),
    }

    new_recipes = {}
    new_markers = {}
    for name, recipe in uninstaller.INSTALL_RECIPES.items():
        venv_path = str(fake_home / f".local/share/{name}-venv")
        new_recipes[name] = {**recipe, "venv": venv_path}
        new_markers[os.path.abspath(venv_path)] = "pyvenv.cfg"
    new_markers[os.path.abspath(new_base)] = os.path.join("daemon", "_common.py")
    new_markers[os.path.abspath(new_cfg)] = "config.yaml"

    monkeypatch.setattr(uninstaller, "INSTALL_RECIPES", new_recipes)
    monkeypatch.setattr(uninstaller, "BASE_DIR", new_base)
    monkeypatch.setattr(uninstaller, "CONFIG_DIR", new_cfg)
    monkeypatch.setattr(uninstaller, "SYSTEMD_USER_DIR", new_systemd)
    monkeypatch.setattr(uninstaller, "ENGINE_MODEL_DIRS", new_model_dirs)
    monkeypatch.setattr(uninstaller, "_DIR_MARKERS", new_markers)

    # Each test gets a fresh sandbox dict.
    return {
        "home": fake_home,
        "base": new_base,
        "cfg": new_cfg,
        "systemd": new_systemd,
        "venvs": {n: r["venv"] for n, r in new_recipes.items()},
        "models": new_model_dirs,
    }


def _make_venv(path: str) -> None:
    """Create a dir with the pyvenv.cfg marker so it passes the gate."""
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "pyvenv.cfg"), "w") as f:
        f.write("home = /usr/bin\n")


def _make_dir_with_marker(path: str, marker_rel: str) -> None:
    os.makedirs(path, exist_ok=True)
    marker_full = os.path.join(path, marker_rel)
    os.makedirs(os.path.dirname(marker_full), exist_ok=True)
    with open(marker_full, "w") as f:
        f.write("# marker\n")


# ── Dry-run touches nothing ─────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_does_not_remove_anything(self, relocated):
        _make_venv(relocated["venvs"]["kitten"])
        _make_dir_with_marker(relocated["base"], "daemon/_common.py")

        with patch("marmalade_tts.uninstaller.shutil.rmtree") as rm, \
             patch("marmalade_tts.uninstaller.os.unlink") as unlink, \
             patch("marmalade_tts.uninstaller._stop_daemon"):
            report = uninstall_engine("kitten", dry_run=True)

        assert rm.call_count == 0
        assert unlink.call_count == 0
        # And the dirs still exist on disk
        assert os.path.exists(relocated["venvs"]["kitten"])
        # Dry run still reports the paths it WOULD remove.
        assert relocated["venvs"]["kitten"] in report.removed

    def test_dry_run_purge_does_not_remove_anything(self, relocated):
        for v in relocated["venvs"].values():
            _make_venv(v)
        _make_dir_with_marker(relocated["base"], "daemon/_common.py")
        _make_dir_with_marker(relocated["cfg"], "config.yaml")

        with patch("marmalade_tts.uninstaller.shutil.rmtree") as rm, \
             patch("marmalade_tts.uninstaller.os.unlink") as unlink, \
             patch("marmalade_tts.uninstaller._stop_daemon"):
            purge(dry_run=True)

        assert rm.call_count == 0
        assert unlink.call_count == 0


# ── Symlink refusal ─────────────────────────────────────────────────────────

class TestSymlinkRefusal:
    def test_refuses_symlink_venv(self, relocated, tmp_path, capsys):
        # Make a REAL symlink at the venv location pointing at /tmp/elsewhere.
        target = tmp_path / "elsewhere"
        target.mkdir()
        venv_path = relocated["venvs"]["kitten"]
        os.makedirs(os.path.dirname(venv_path), exist_ok=True)
        os.symlink(str(target), venv_path)

        with patch("marmalade_tts.uninstaller._stop_daemon"):
            report = uninstall_engine("kitten", dry_run=False)

        # Symlink itself is untouched, and the symlink target survives.
        assert os.path.islink(venv_path)
        assert target.exists()
        # Reported as failed, with reason "symlink".
        symlink_failures = [r for r in report.failed if r[0] == venv_path]
        assert symlink_failures, "expected symlink refusal to be in report.failed"
        assert "symlink" in symlink_failures[0][1].lower()


# ── Whitelist enforcement ───────────────────────────────────────────────────

class TestWhitelistEnforcement:
    def test_off_whitelist_path_refused(self, relocated, tmp_path):
        # Forge a Report and call _safe_remove with a path that lives outside
        # the (already-relocated) whitelist.
        rogue = tmp_path / "rogue"
        rogue.mkdir()
        (rogue / "pyvenv.cfg").write_text("home=/x\n")

        report = Report()
        uninstaller._safe_remove(str(rogue), dry_run=False, report=report)

        assert rogue.exists(), "off-whitelist path must NOT be deleted"
        assert any(r[0] == str(rogue) for r in report.failed)
        assert any("whitelist" in r[1] for r in report.failed)


# ── Marker-file gate ────────────────────────────────────────────────────────

class TestMarkerGate:
    def test_refuses_venv_without_pyvenv_cfg(self, relocated):
        venv = relocated["venvs"]["kitten"]
        os.makedirs(venv)
        # Put a sibling file in so the dir isn't empty (empty is idempotent-ok).
        with open(os.path.join(venv, "random.txt"), "w") as f:
            f.write("not a venv\n")

        with patch("marmalade_tts.uninstaller._stop_daemon"):
            report = uninstall_engine("kitten", dry_run=False)

        # The non-venv dir survives.
        assert os.path.exists(venv)
        assert any(r[0] == venv and "marker" in r[1] for r in report.failed)

    def test_empty_dir_passes_marker_gate(self, relocated):
        # An empty leftover dir is harmless — should be removed without
        # the marker check tripping.
        venv = relocated["venvs"]["kitten"]
        os.makedirs(venv)
        with patch("marmalade_tts.uninstaller._stop_daemon"):
            report = uninstall_engine("kitten", dry_run=False)
        assert not os.path.exists(venv)
        assert venv in report.removed


# ── Daemon stopped before socket removed ────────────────────────────────────

class TestDaemonStopFirst:
    def test_daemon_stop_happens_before_socket_unlink(self, relocated):
        from marmalade_tts import daemon as real_daemon
        venv = relocated["venvs"]["kitten"]
        _make_venv(venv)
        # Touch a real socket file so unlink is called against it.
        sock = os.path.join(relocated["base"], "kitten.sock")
        os.makedirs(os.path.dirname(sock), exist_ok=True)
        open(sock, "w").close()

        order: list[str] = []

        def _stop_side_effect(engine):
            order.append(f"daemon.stop({engine})")

        real_unlink = os.unlink

        def _unlink_spy(p, *a, **kw):
            if p == sock:
                order.append(f"unlink({p})")
            return real_unlink(p, *a, **kw)

        with patch.object(real_daemon, "is_running", return_value=True), \
             patch.object(real_daemon, "stop", side_effect=_stop_side_effect), \
             patch("marmalade_tts.uninstaller._systemctl_user"), \
             patch("marmalade_tts.uninstaller.os.unlink", side_effect=_unlink_spy):
            uninstall_engine("kitten", dry_run=False)

        # The daemon.stop must come strictly before the socket unlink.
        stop_idx = next(i for i, s in enumerate(order) if s.startswith("daemon.stop"))
        unlink_idx = next(i for i, s in enumerate(order) if s.startswith("unlink"))
        assert stop_idx < unlink_idx


# ── Engine-specific cleanup (no cross-contamination) ────────────────────────

class TestEngineSpecificCleanup:
    def test_kitten_uninstall_leaves_kokoro_alone(self, relocated):
        _make_venv(relocated["venvs"]["kitten"])
        _make_venv(relocated["venvs"]["kokoro"])

        with patch("marmalade_tts.uninstaller._stop_daemon"), \
             patch("marmalade_tts.uninstaller._systemctl_user"):
            uninstall_engine("kitten", dry_run=False)

        assert not os.path.exists(relocated["venvs"]["kitten"])
        assert os.path.exists(relocated["venvs"]["kokoro"]), \
            "kokoro venv must be untouched by `uninstall kitten`"


# ── --purge prints install-method hint ──────────────────────────────────────

class TestPurgeHint:
    @pytest.mark.parametrize("method", list(REMOVAL_HINTS.keys()))
    def test_hint_printed_for_each_method(self, method, capsys):
        with patch("marmalade_tts.uninstaller.detect_install_method",
                   return_value=method):
            uninstaller.print_removal_hint(method)
        out = capsys.readouterr().out
        # The exact hint string must appear.
        assert REMOVAL_HINTS[method] in out
        # The HF-cache warning is always printed.
        assert "huggingface" in out.lower()

    def test_purge_sets_install_method_on_report(self, relocated):
        for v in relocated["venvs"].values():
            _make_venv(v)
        _make_dir_with_marker(relocated["base"], "daemon/_common.py")
        _make_dir_with_marker(relocated["cfg"], "config.yaml")

        with patch("marmalade_tts.uninstaller._stop_daemon"), \
             patch("marmalade_tts.uninstaller._systemctl_user"), \
             patch("marmalade_tts.uninstaller.detect_install_method",
                   return_value="pipx"):
            report = purge(dry_run=False)

        assert report.install_method == "pipx"


# ── HF cache untouched ──────────────────────────────────────────────────────

class TestHuggingFaceUntouched:
    def test_no_hf_path_in_any_plan(self):
        all_plans = (
            plan_for_purge()
            + plan_for_all_engines()
            + [p for e in uninstaller.INSTALL_RECIPES for p in plan_for_engine(e)]
        )
        for p in all_plans:
            assert ".cache/huggingface" not in p, \
                f"HuggingFace cache path leaked into plan: {p}"
            assert ".cache" not in p, \
                f"~/.cache path leaked into plan: {p}"


# ── User voice file location semantics ──────────────────────────────────────

class TestUserVoiceFiles:
    def test_voice_under_marmalade_dir_is_removed(self, relocated):
        # A user voice file living under ~/.local/share/marmalade-tts/voices/
        # is inside our managed dir, so --purge takes it.
        voices = os.path.join(relocated["base"], "voices")
        os.makedirs(voices)
        voice = os.path.join(voices, "me.wav")
        open(voice, "w").close()
        _make_dir_with_marker(relocated["base"], "daemon/_common.py")

        with patch("marmalade_tts.uninstaller._stop_daemon"), \
             patch("marmalade_tts.uninstaller._systemctl_user"), \
             patch("marmalade_tts.uninstaller.detect_install_method",
                   return_value="unknown"):
            purge(dry_run=False)

        # Voice file is gone because its parent (the marmalade dir) was removed.
        assert not os.path.exists(voice)

    def test_voice_outside_marmalade_dir_is_not_in_plan(self, relocated, tmp_path):
        # A voice at ~/recordings/me.wav is NOT in our managed tree.
        # Any plan we generate must not include it.
        external = tmp_path / "recordings" / "me.wav"
        external.parent.mkdir()
        external.write_bytes(b"")

        plans = plan_for_purge() + plan_for_all_engines()
        for p in plans:
            assert str(external) not in p
            assert "recordings/me.wav" not in p


# ── Idempotency ─────────────────────────────────────────────────────────────

class TestIdempotency:
    def test_uninstall_engine_twice_is_clean(self, relocated):
        _make_venv(relocated["venvs"]["kitten"])
        with patch("marmalade_tts.uninstaller._stop_daemon"), \
             patch("marmalade_tts.uninstaller._systemctl_user"):
            report1 = uninstall_engine("kitten", dry_run=False)
            report2 = uninstall_engine("kitten", dry_run=False)

        assert relocated["venvs"]["kitten"] in report1.removed
        # Second call: nothing left. Every path is "already gone" (skipped).
        assert relocated["venvs"]["kitten"] not in report2.removed
        # Critically: no failures from the second run.
        assert report2.failed == []


# ── _safe_paths whitelist contents ──────────────────────────────────────────

class TestWhitelistContents:
    def test_every_venv_is_whitelisted(self):
        paths = uninstaller._safe_paths()
        for recipe in uninstaller.INSTALL_RECIPES.values():
            assert os.path.expanduser(recipe["venv"]) in paths

    def test_every_systemd_unit_is_whitelisted(self):
        paths = uninstaller._safe_paths()
        for eng in uninstaller.INSTALL_RECIPES:
            assert any(
                f"marmalade-{eng}.service" in p for p in paths
            ), f"systemd unit for {eng} missing from whitelist"

    def test_every_engine_log_socket_pid_is_whitelisted(self):
        paths = uninstaller._safe_paths()
        for eng in uninstaller.INSTALL_RECIPES:
            for sfx in (".sock", ".pid", ".log"):
                assert any(p.endswith(f"{eng}{sfx}") for p in paths)

    def test_config_and_base_dirs_whitelisted(self):
        paths = uninstaller._safe_paths()
        assert any(p.endswith("marmalade-tts") and ".local/share" in p for p in paths)
        assert any(p.endswith("marmalade-tts") and ".config" in p for p in paths)


# ── Install-method detection ────────────────────────────────────────────────

class TestDetectInstallMethod:
    def test_unknown_when_binary_not_on_path(self):
        with patch("marmalade_tts.uninstaller.shutil.which", return_value=None):
            assert detect_install_method() == "unknown"

    def test_detects_pipx(self):
        with patch("marmalade_tts.uninstaller.shutil.which",
                   return_value="/home/u/.local/bin/marmalade-tts"), \
             patch("marmalade_tts.uninstaller.os.path.realpath",
                   return_value="/home/u/.local/pipx/venvs/marmalade-tts/bin/marmalade-tts"):
            assert detect_install_method() == "pipx"

    def test_detects_manual(self, tmp_path):
        bin_path = str(tmp_path / "marmalade-tts")
        lib_dir = os.path.expanduser("~/.local/lib/marmalade-tts")
        with patch("marmalade_tts.uninstaller.shutil.which", return_value=bin_path), \
             patch("marmalade_tts.uninstaller.os.path.realpath",
                   return_value=os.path.expanduser("~/.local/bin/marmalade-tts")), \
             patch("marmalade_tts.uninstaller.os.path.isdir",
                   side_effect=lambda p: p == lib_dir):
            assert detect_install_method() == "manual"


# ── cmd_uninstall CLI plumbing ──────────────────────────────────────────────
# Lightweight tests for the CLI-layer behaviors the deeper safety tests don't
# touch: EOF on the prompt aborts, --dry-run wins over -y.

class TestCmdUninstall:
    def test_eof_on_prompt_aborts(self, capsys):
        """User hitting Ctrl-D / EOF at the y/N prompt must abort, not proceed."""
        from marmalade_tts.cli import cmd_uninstall

        with patch("marmalade_tts.init._is_tty", return_value=True), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value={}), \
             patch("builtins.input", side_effect=EOFError), \
             patch("marmalade_tts.uninstaller.uninstall_engine") as mock_uninstall, \
             patch("marmalade_tts.uninstaller.print_plan"):
            cmd_uninstall(["kitten"])
        out = capsys.readouterr().out
        assert "aborted" in out.lower()
        mock_uninstall.assert_not_called()

    def test_dry_run_overrides_yes(self, capsys):
        """--dry-run must win over -y: no actual delete call is made even
        though -y would normally skip the prompt."""
        from marmalade_tts.cli import cmd_uninstall

        with patch("marmalade_tts.init._is_tty", return_value=True), \
             patch("marmalade_tts.cli.cfg_mod.load", return_value={}), \
             patch("marmalade_tts.uninstaller.uninstall_engine") as mock_uninstall, \
             patch("marmalade_tts.uninstaller.uninstall_all_engines") as mock_all, \
             patch("marmalade_tts.uninstaller.purge") as mock_purge, \
             patch("marmalade_tts.uninstaller.print_plan"):
            cmd_uninstall(["kitten", "--dry-run", "-y"])
        out = capsys.readouterr().out
        assert "--dry-run: no files were touched." in out
        # None of the destructive paths called — the dry-run branch returns
        # before the execute block, regardless of -y.
        mock_uninstall.assert_not_called()
        mock_all.assert_not_called()
        mock_purge.assert_not_called()
