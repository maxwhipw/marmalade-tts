"""Tests for marmalade_tts.daemon — path helpers, status, start/stop logic."""

import sys
import os
import signal
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, mock_open

import marmalade_tts.daemon as daemon_mod


# ── _paths ────────────────────────────────────────────────────────────────────

class TestPaths:
    def test_all_engines_have_paths(self):
        for engine in ["kitten", "kokoro", "piper", "coqui", "matcha", "emojivoice"]:
            sock, pid, svc, script = daemon_mod._paths(engine)
            assert sock.endswith(".sock")
            assert pid.endswith(".pid")
            assert svc.endswith(".service")
            assert script.endswith("-daemon.py")

    def test_paths_runtime_files_under_base_dir(self):
        base = daemon_mod.BASE_DIR
        for engine in ["kitten", "kokoro", "piper", "coqui", "matcha", "emojivoice"]:
            sock, pid, _svc, _script = daemon_mod._paths(engine)
            assert sock.startswith(base)
            assert pid.startswith(base)

    def test_script_path_ends_in_daemon_py(self):
        for engine in ["kitten", "kokoro", "piper", "coqui", "matcha", "emojivoice"]:
            _sock, _pid, _svc, script = daemon_mod._paths(engine)
            assert script.endswith("-daemon.py")


# ── _find_daemon_script ──────────────────────────────────────────────────────


class TestFindDaemonScript:
    def test_finds_user_daemon_subdir(self, tmp_path):
        # install.sh layout: <BASE>/daemon/<engine>-daemon.py
        d = tmp_path / "daemon"
        d.mkdir()
        script = d / "kitten-daemon.py"
        script.write_text("# stub")
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            assert daemon_mod._find_daemon_script("kitten-daemon.py") == str(script)

    def test_finds_legacy_user_root(self, tmp_path):
        # v0.4.2 install.sh layout: <BASE>/<engine>-daemon.py
        script = tmp_path / "kitten-daemon.py"
        script.write_text("# stub")
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            assert daemon_mod._find_daemon_script("kitten-daemon.py") == str(script)

    def test_falls_back_to_canonical_path_when_missing(self, tmp_path):
        # Nothing on disk → return the canonical install.sh path so error
        # messages point users to the expected location.
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            result = daemon_mod._find_daemon_script("kitten-daemon.py")
            assert result == str(tmp_path / "daemon" / "kitten-daemon.py")

    def test_unknown_engine_raises(self):
        with pytest.raises(KeyError):
            daemon_mod._paths("nonexistent")


# ── is_running ────────────────────────────────────────────────────────────────

class TestIsRunning:
    def test_no_pid_file(self, tmp_path):
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            assert daemon_mod.is_running("kitten") is False

    def test_pid_file_process_alive(self, tmp_path):
        pid_path = tmp_path / "kitten.pid"
        pid_path.write_text(str(os.getpid()))  # current process is definitely alive
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            assert daemon_mod.is_running("kitten") is True

    def test_pid_file_process_dead(self, tmp_path):
        pid_path = tmp_path / "kitten.pid"
        pid_path.write_text("999999")  # very unlikely to be a real PID
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            # Should return False (process not found → OSError)
            result = daemon_mod.is_running("kitten")
            assert result is False

    def test_corrupt_pid_file(self, tmp_path):
        pid_path = tmp_path / "kitten.pid"
        pid_path.write_text("not_a_number")
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            assert daemon_mod.is_running("kitten") is False


# ── _systemd_available ────────────────────────────────────────────────────────

class TestSystemdAvailable:
    def test_returns_bool(self):
        result = daemon_mod._systemd_available()
        assert isinstance(result, bool)

    def test_returns_false_when_systemctl_missing(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert daemon_mod._systemd_available() is False

    def test_returns_false_on_timeout(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("systemctl", 3)):
            assert daemon_mod._systemd_available() is False

    def test_returns_true_when_running(self):
        m = MagicMock()
        m.returncode = 0
        with patch("subprocess.run", return_value=m):
            assert daemon_mod._systemd_available() is True


# ── _service_file_exists ──────────────────────────────────────────────────────

class TestServiceFileExists:
    def test_missing_service(self, tmp_path):
        with patch("os.path.expanduser", side_effect=lambda p: p.replace("~", str(tmp_path))):
            result = daemon_mod._service_file_exists("nonexistent.service")
            assert result is False

    def test_existing_service(self, tmp_path):
        svc_dir = tmp_path / ".config" / "systemd" / "user"
        svc_dir.mkdir(parents=True)
        (svc_dir / "marmalade-kitten.service").write_text("[Unit]\n")
        with patch("os.path.expanduser", side_effect=lambda p: p.replace("~", str(tmp_path))):
            result = daemon_mod._service_file_exists("marmalade-kitten.service")
            assert result is True


# ── status ────────────────────────────────────────────────────────────────────

class TestStatus:
    def test_all_engines_returned(self, tmp_path):
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            result = daemon_mod.status()
        assert set(result.keys()) == set(daemon_mod.ENGINE_DAEMONS.keys())

    def test_single_engine(self, tmp_path):
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            result = daemon_mod.status("kitten")
        assert list(result.keys()) == ["kitten"]

    def test_not_running_state(self, tmp_path):
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            result = daemon_mod.status("kitten")
        assert result["kitten"]["running"] is False
        assert result["kitten"]["pid"] is None
        assert result["kitten"]["socket"] is None

    def test_running_state(self, tmp_path):
        pid_path = tmp_path / "kitten.pid"
        pid_path.write_text(str(os.getpid()))
        sock_path = tmp_path / "kitten.sock"
        sock_path.write_text("")  # exists
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            result = daemon_mod.status("kitten")
        assert result["kitten"]["running"] is True
        assert result["kitten"]["pid"] == os.getpid()
        assert result["kitten"]["socket"] is not None

    def test_status_has_service_key(self, tmp_path):
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            result = daemon_mod.status("kitten")
        assert "service" in result["kitten"]
        assert "marmalade-kitten.service" in result["kitten"]["service"]


# ── stop ─────────────────────────────────────────────────────────────────────

class TestStop:
    def test_stop_via_systemd(self, tmp_path):
        with patch.object(daemon_mod, "_systemd_available", return_value=True):
            with patch.object(daemon_mod, "_service_file_exists", return_value=True):
                with patch("subprocess.run") as mock_run:
                    daemon_mod.stop("kitten")
                    mock_run.assert_called_once()
                    cmd = mock_run.call_args[0][0]
                    assert "stop" in cmd
                    assert "marmalade-kitten.service" in cmd

    def test_stop_direct_via_pid(self, tmp_path):
        pid_path = tmp_path / "kitten.pid"
        pid_path.write_text("99999")
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            with patch.object(daemon_mod, "_systemd_available", return_value=False):
                with patch.object(daemon_mod, "_service_file_exists", return_value=False):
                    with patch("os.kill") as mock_kill:
                        daemon_mod.stop("kitten")
                    mock_kill.assert_called_once_with(99999, signal.SIGTERM)

    def test_stop_direct_no_pid_file_is_noop(self, tmp_path):
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            with patch.object(daemon_mod, "_systemd_available", return_value=False):
                with patch.object(daemon_mod, "_service_file_exists", return_value=False):
                    with patch("os.kill") as mock_kill:
                        daemon_mod.stop("kitten")
                    mock_kill.assert_not_called()


# ── _find_python ─────────────────────────────────────────────────────────────

class TestFindPython:
    def test_find_python_no_venv_returns_system_python3(self, tmp_path):
        """When no venv Python exists, _find_python falls back to system python3."""
        with patch.dict(daemon_mod.ENGINE_PYTHON,
                        {"kitten": [str(tmp_path / "nonexistent-venv" / "bin" / "python")]}):
            result = daemon_mod._find_python("kitten")
        assert result is None or "python" in result

    def test_find_python_unknown_engine_falls_back(self):
        """Unknown engine (no entry in ENGINE_PYTHON) returns system python3 or None."""
        result = daemon_mod._find_python("pocket")  # pocket not in ENGINE_PYTHON
        assert result is None or "python" in result

    def test_find_python_returns_existing_venv_path(self, tmp_path):
        """When the venv Python exists, it is returned directly."""
        fake_python = tmp_path / "bin" / "python"
        fake_python.parent.mkdir(parents=True)
        fake_python.touch()
        fake_python.chmod(0o755)
        with patch.dict(daemon_mod.ENGINE_PYTHON, {"kitten": [str(fake_python)]}):
            result = daemon_mod._find_python("kitten")
        assert result == str(fake_python)


# ── synthesize socket protocol ────────────────────────────────────────────────

class TestSynthesizeSocket:
    def test_raises_when_not_running_and_no_autostart(self, tmp_path):
        """Raises when socket file is absent and auto_start=False."""
        # The real check is os.path.exists(sock_path), not is_running()
        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            # tmp_path has no kitten.sock, so synthesize should raise immediately
            with pytest.raises(RuntimeError, match="not running"):
                daemon_mod.synthesize(
                    "kitten",
                    {"text": "hi", "out": "/tmp/x.wav"},
                    auto_start=False
                )

    def test_sends_correct_json_and_returns_path(self, tmp_path):
        """Verify the JSON-over-socket protocol used by the real daemon.synthesize."""
        import json

        # Create the socket file so the path-existence check passes
        sock_path = tmp_path / "kitten.sock"
        sock_path.write_text("")

        request = {"text": "hello", "out": "/tmp/x.wav", "voice": "Kiki", "speed": 1.0}
        response_bytes = (json.dumps({"ok": True, "out": "/tmp/x.wav"}) + "\n").encode()

        # The real code does: client = socket.socket(...); client.connect(); client.sendall();
        # client.recv(); client.close() — NOT used as a context manager.
        mock_client = MagicMock()
        mock_client.recv.return_value = response_bytes

        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            with patch("socket.socket", return_value=mock_client):
                result = daemon_mod.synthesize("kitten", request, auto_start=False)

        assert result == "/tmp/x.wav"

        # Verify connect was called with the real socket path
        mock_client.connect.assert_called_once_with(str(sock_path))

        # Verify the JSON payload sent over the wire
        sent_bytes = mock_client.sendall.call_args[0][0]
        sent_obj = json.loads(sent_bytes.decode().strip())
        assert sent_obj["text"] == "hello"
        assert sent_obj["voice"] == "Kiki"
        assert sent_obj["speed"] == 1.0

        # Verify close() was called (finally block)
        mock_client.close.assert_called_once()

    def test_recv_loop_handles_fragmented_response(self, tmp_path):
        """recv() may return partial data — the loop must accumulate until newline."""
        import json

        sock_path = tmp_path / "kitten.sock"
        sock_path.write_text("")

        full_response = json.dumps({"ok": True, "out": "/tmp/x.wav"}) + "\n"
        # Split into 3 fragments
        fragments = [
            full_response[:10].encode(),
            full_response[10:25].encode(),
            full_response[25:].encode(),
        ]

        mock_client = MagicMock()
        mock_client.recv.side_effect = fragments

        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            with patch("socket.socket", return_value=mock_client):
                result = daemon_mod.synthesize(
                    "kitten", {"text": "hi", "out": "/tmp/x.wav"}, auto_start=False
                )

        assert result == "/tmp/x.wav"
        assert mock_client.recv.call_count == 3

    def test_daemon_error_response_raises(self, tmp_path):
        import json

        sock_path = tmp_path / "kitten.sock"
        sock_path.write_text("")

        response = (json.dumps({"ok": False, "error": "synthesis failed"}) + "\n").encode()
        mock_client = MagicMock()
        mock_client.recv.return_value = response

        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            with patch("socket.socket", return_value=mock_client):
                with pytest.raises(RuntimeError, match="synthesis failed"):
                    daemon_mod.synthesize(
                        "kitten", {"text": "hi", "out": "/tmp/x.wav"}, auto_start=False
                    )

    def test_close_called_even_on_recv_error(self, tmp_path):
        """The finally block must call close() even when recv raises."""
        sock_path = tmp_path / "kitten.sock"
        sock_path.write_text("")

        mock_client = MagicMock()
        mock_client.recv.side_effect = OSError("connection reset")

        with patch.object(daemon_mod, "BASE_DIR", str(tmp_path)):
            with patch("socket.socket", return_value=mock_client):
                with pytest.raises(OSError):
                    daemon_mod.synthesize(
                        "kitten", {"text": "hi", "out": "/tmp/x.wav"}, auto_start=False
                    )

        mock_client.close.assert_called_once()
