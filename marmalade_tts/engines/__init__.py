"""Engine base class, registry, and shared helpers."""

import os
import shutil
import subprocess
import sys
import tempfile


class Engine:
    """Base class for TTS engines."""

    name: str = ""

    def synthesize(self, text: str, out_path: str, **kwargs):
        """Synthesize text to a WAV file. Subclasses must implement."""
        raise NotImplementedError

    def list_voices(self):
        """Print available voices/models. Subclasses should override."""
        print(f"[{self.name}] No voice listing available.")


# ── Shared helpers ──────────────────────────────────────────────────────────


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
