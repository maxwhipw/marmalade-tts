"""
Smoke tests — require actual engine binaries to be installed.
These are marked with @pytest.mark.smoke and skipped in CI unless engines are present.

Run with: python -m pytest tests/test_smoke.py -v -m smoke
"""

import sys
import os
import shutil
import subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from marmalade_tts.daemon import is_running, status


# ── Helpers ───────────────────────────────────────────────────────────────────

def has_engine(engine: str) -> bool:
    """Check if an engine's binary/venv is available."""
    checks = {
        "kitten": os.path.exists(os.path.expanduser("~/.local/share/kittentts-venv/bin/python")),
        "kokoro": bool(shutil.which("kokoro")),
        "piper":  bool(shutil.which("piper")),
        "coqui":  bool(shutil.which("tts")),
    }
    return checks.get(engine, False)


def has_sox() -> bool:
    return bool(shutil.which("sox"))


# ── Daemon smoke tests ────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestDaemonSmoke:
    def test_daemon_status_runs(self):
        """daemon status should return without error regardless of state."""
        result = status()
        assert isinstance(result, dict)
        for engine in ["kitten", "kokoro", "piper", "coqui"]:
            assert engine in result

    def test_daemon_status_kitten(self):
        """If kitten daemon is running, it should be reachable."""
        st = status("kitten")
        if st["kitten"]["running"]:
            assert st["kitten"]["socket"] is not None


# ── CLI smoke tests ───────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestCLISmoke:
    def _cli(self, args: list) -> subprocess.CompletedProcess:
        """Run marmalade-tts CLI and return the result."""
        # Try installed binary first, fall back to running via python
        cmd = shutil.which("marmalade-tts")
        if cmd:
            return subprocess.run([cmd] + args, capture_output=True, text=True, timeout=30)
        # Fall back to running module directly
        return subprocess.run(
            [sys.executable, "-m", "marmalade_tts.cli"] + args,
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONPATH": os.path.join(os.path.dirname(__file__), "..")}
        )

    def test_version(self):
        from marmalade_tts import __version__
        r = self._cli(["--version"])
        assert r.returncode == 0
        assert __version__ in r.stdout

    def test_list_effects(self):
        r = self._cli(["--list-effects"])
        assert r.returncode == 0
        assert "reverb" in r.stdout
        assert "robot" in r.stdout

    def test_list_rules(self):
        r = self._cli(["--list-rules"])
        assert r.returncode == 0
        assert "currency" in r.stdout

    def test_config_show(self):
        r = self._cli(["config", "show"])
        assert r.returncode == 0
        assert "engine" in r.stdout

    def test_daemon_status(self):
        r = self._cli(["daemon", "status"])
        assert r.returncode == 0
        assert "kitten" in r.stdout

    def test_bash_completion(self):
        r = self._cli(["--completion", "bash"])
        assert r.returncode == 0
        assert "complete -F _marmalade_tts" in r.stdout

    def test_zsh_completion(self):
        r = self._cli(["--completion", "zsh"])
        assert r.returncode == 0
        assert "_marmalade-tts" in r.stdout


# ── Engine list-voices smoke tests ───────────────────────────────────────────

@pytest.mark.smoke
@pytest.mark.skipif(not has_engine("kitten"), reason="kitten not installed")
def test_kitten_list_voices():
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); from marmalade_tts.engines.kitten import KittenEngine; KittenEngine({}).list_voices()"],
        capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    assert "Kiki" in r.stdout or "Bella" in r.stdout


@pytest.mark.smoke
@pytest.mark.skipif(not has_engine("kokoro"), reason="kokoro not installed")
def test_kokoro_list_voices():
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); from marmalade_tts.engines.kokoro import KokoroEngine; KokoroEngine({}).list_voices()"],
        capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    assert "af_heart" in r.stdout


@pytest.mark.smoke
@pytest.mark.skipif(not has_engine("piper"), reason="piper not installed")
def test_piper_list_voices():
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); from marmalade_tts.engines.piper import PiperEngine; PiperEngine({}).list_voices()"],
        capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    assert r.returncode == 0


# ── Effects smoke tests ──────────────────────────────────────────────────────

@pytest.mark.smoke
@pytest.mark.skipif(not has_sox(), reason="sox not installed")
class TestEffectsSmoke:
    def test_sox_available(self):
        from marmalade_tts.effects import sox_available
        assert sox_available() is True

    def test_apply_reverb(self, tmp_path):
        """Generate a silent WAV and apply reverb — should produce output."""
        from marmalade_tts.effects import apply_effects

        # Generate a short silent WAV with sox itself
        in_wav = str(tmp_path / "silent.wav")
        out_wav = str(tmp_path / "reverb.wav")
        subprocess.run(
            ["sox", "-n", "-r", "24000", "-c", "1", in_wav, "trim", "0.0", "0.5"],
            check=True
        )
        apply_effects(in_wav, out_wav, ["reverb=30"], {})
        assert os.path.exists(out_wav)
        assert os.path.getsize(out_wav) > 0

    def test_apply_preset_robot(self, tmp_path):
        from marmalade_tts.effects import apply_effects

        in_wav = str(tmp_path / "silent.wav")
        out_wav = str(tmp_path / "robot.wav")
        subprocess.run(
            ["sox", "-n", "-r", "24000", "-c", "1", in_wav, "trim", "0.0", "0.5"],
            check=True
        )
        apply_effects(in_wav, out_wav, ["robot"], {})
        assert os.path.exists(out_wav)

    def test_chain_multiple_effects(self, tmp_path):
        from marmalade_tts.effects import apply_effects

        in_wav = str(tmp_path / "silent.wav")
        out_wav = str(tmp_path / "chained.wav")
        subprocess.run(
            ["sox", "-n", "-r", "24000", "-c", "1", in_wav, "trim", "0.0", "0.5"],
            check=True
        )
        apply_effects(in_wav, out_wav, ["reverb=20", "pitch=100", "normalize"], {})
        assert os.path.exists(out_wav)


# ── Kitten daemon synthesis smoke test ───────────────────────────────────────

@pytest.mark.smoke
@pytest.mark.skipif(not has_engine("kitten"), reason="kitten not installed")
@pytest.mark.skipif(not is_running("kitten"), reason="kitten daemon not running")
def test_kitten_daemon_synthesizes(tmp_path):
    """If kitten daemon is running, synthesize a short phrase."""
    from marmalade_tts.daemon import synthesize

    out_wav = str(tmp_path / "output.wav")
    synthesize("kitten", {
        "text": "Hello from marmalade",
        "voice": "Kiki",
        "speed": 1.0,
        "out": out_wav,
    }, auto_start=False)

    assert os.path.exists(out_wav)
    assert os.path.getsize(out_wav) > 1000  # should be a real WAV, not empty
