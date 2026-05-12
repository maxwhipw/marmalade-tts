"""WAV playback utilities."""

import os
import shutil
import subprocess
import tempfile


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
