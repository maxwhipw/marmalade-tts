"""WAV playback utilities."""

import os
import shutil
import subprocess
import tempfile
import wave


def wav_duration(path: str) -> float:
    """Return the duration in seconds of a PCM WAV file.

    Used to time subtitle cues; we read the file the engine just wrote
    (after any sox effects, which can change length via tempo/speed/fade),
    so the cue lines up with the audio the user will actually hear.
    """
    with wave.open(path, "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate()
        if rate <= 0:
            return 0.0
        return frames / float(rate)


def play_wav(path: str):
    """Play a WAV file via the first available player."""
    for player in ("paplay", "aplay", "ffplay"):
        if shutil.which(player):
            cmd = [player, path]
            if player == "ffplay":
                cmd += ["-nodisp", "-autoexit", "-loglevel", "quiet"]
            subprocess.run(cmd, check=False)
            return
    print(f"[marmalade-tts] No audio player found. File saved: {path}")


def make_tmp_wav() -> str:
    """Create a temp WAV file path (caller must clean up)."""
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    return path
