"""Engine base class, registry, and shared helpers."""

import os
import shutil
import subprocess
import sys
import tempfile


class EngineError(Exception):
    """A synthesis failed recoverably (missing venv, subprocess error, …).

    Engines raise this instead of calling ``sys.exit`` so a single failed
    synthesis can't kill a long-lived host process (the MCP server). The
    boundaries catch it: the CLI prints the message and exits 1, the MCP
    server returns a tool error, and the installer's self-test reports it.
    """


class Engine:
    """Base class for TTS engines."""

    name: str = ""

    # Soft character limit for a single ``synthesize`` call. When a user
    # input exceeds this, the CLI splits on sentence boundaries, calls
    # synthesize per chunk, and concatenates the resulting WAVs — the user
    # still sees one WAV out for one input in. ``None`` = engine handles
    # arbitrary lengths gracefully, don't chunk. Override per engine.
    MAX_CHARS: "int | None" = None

    def synthesize(self, text: str, out_path: str, **kwargs):
        """Synthesize text to a WAV file. Subclasses must implement."""
        raise NotImplementedError

    def list_voices(self):
        """Print available voices/models. Subclasses should override."""
        print(f"[{self.name}] No voice listing available.")


# ── Shared helpers ──────────────────────────────────────────────────────────


def run_in_venv(venv_bin: str, cmd: list, *, env_extra: dict | None = None,
                stdin: bytes | None = None, engine_name: str = "engine") -> None:
    """Run an engine's synthesis subprocess, raising ``EngineError`` on failure.

    Every engine's cold path is the same shape: verify the venv binary
    exists, copy the environment (adding a few vars), run the command
    captured, and turn a nonzero exit into a helpful error. This centralises
    that boilerplate.

      venv_bin    — path to the engine's venv executable (kokoro bin, venv
                    python, …). Missing → raise with an install hint.
      cmd         — the argv to run (``cmd[0]`` is usually ``venv_bin``).
      env_extra   — extra environment variables to set on top of a copy of
                    ``os.environ`` (e.g. ``CUDA_VISIBLE_DEVICES=""``).
      stdin       — bytes to feed on stdin (piper reads its text this way).
      engine_name — used to prefix error messages, matching the old
                    ``[<engine>] …`` convention.

    Raises ``EngineError`` if the venv is missing or the subprocess exits
    nonzero (message includes the decoded stderr). Returns None on success.
    """
    if not os.path.exists(venv_bin):
        raise EngineError(
            f"[{engine_name}] venv not found at {venv_bin}\n"
            f"  Run: marmalade-tts install {engine_name}"
        )

    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)

    proc = subprocess.run(cmd, input=stdin, capture_output=True, env=env)
    if proc.returncode != 0:
        raise EngineError(
            f"[{engine_name}] synthesis failed:\n"
            f"{proc.stderr.decode(errors='replace')}"
        )


def sox_tempo(wav_path: str, speed: float) -> None:
    """Time-stretch ``wav_path`` in place by ``speed`` (pitch preserved).

    Used by engines whose upstream library has no native speed parameter
    (pocket today). Engines with a native knob — Piper length_scale,
    Matcha length_scale, Kokoro --speed, Kitten speed=, Coqui
    tts_to_file(speed=) — should pass it through directly; this helper is
    the documented fallback when none exists. See ENGINE-GUIDE.md
    "Honoring --speed" for the convention.

    No-op when ``speed`` is 1.0 (or falsy). If sox is missing, prints a
    warning to stderr and leaves the file untouched — the audio still
    plays, just at the original speed.
    """
    if not speed or speed == 1.0:
        return
    if not shutil.which("sox"):
        print(
            "[marmalade-tts] Note: sox not installed — --speed was ignored.\n"
            "  Install: apt install sox  /  brew install sox",
            file=sys.stderr,
        )
        return

    # sox tempo factor: >1 = faster, <1 = slower. Same convention as our
    # --speed flag, so pass through verbatim.
    fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="marmalade-sox-")
    os.close(fd)
    try:
        proc = subprocess.run(
            ["sox", wav_path, tmp, "tempo", str(float(speed))],
            capture_output=True,
        )
        if proc.returncode != 0:
            print(
                f"[marmalade-tts] sox tempo failed (speed left unchanged):\n"
                f"  {proc.stderr.decode(errors='replace').strip()}",
                file=sys.stderr,
            )
            return
        os.replace(tmp, wav_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
