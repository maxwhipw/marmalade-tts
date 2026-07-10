"""Kitten TTS engine — daemon client with subprocess fallback."""

import os

from . import Engine, run_in_venv
from .. import daemon as dmgr

KITTEN_VENV   = os.path.expanduser("~/.local/share/kittentts-venv")
KITTEN_PYTHON = os.path.join(KITTEN_VENV, "bin", "python")
DAEMON_SCRIPT = os.path.expanduser("~/.local/share/marmalade-tts/kitten-daemon.py")

MODEL_REPOS = {
    "nano":  "KittenML/kitten-tts-nano-0.8",
    "micro": "KittenML/kitten-tts-micro-0.8",
    "mini":  "KittenML/kitten-tts-mini-0.8",
}

VOICES = ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"]


class KittenEngine(Engine):
    name = "kitten"
    MAX_CHARS = 500  # conservative — kitten's small CPU model degrades on long inputs

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.voice = cfg.get("voice", "Kiki")
        self.model_size = cfg.get("model_size", "micro")
        self.use_daemon = cfg.get("daemon", True)

    def _repo(self) -> str:
        return MODEL_REPOS.get(self.model_size, self.model_size)

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, **kwargs):
        v = voice or self.voice

        if self.use_daemon:
            # "model" lets the daemon verify it has this size loaded (it
            # loads one model at startup and refuses mismatches).
            request = {"text": text, "voice": v, "speed": speed,
                       "model": self._repo(), "out": out_path}
            dmgr.synthesize("kitten", request, auto_start=True)
            return

        # Fallback: direct subprocess (slow cold start)
        cmd = [
            KITTEN_PYTHON, "-c",
            f"from kittentts import KittenTTS; "
            f"m = KittenTTS('{self._repo()}'); "
            f"m.generate_to_file({text!r}, {out_path!r}, voice={v!r}, speed={speed})",
        ]
        run_in_venv(KITTEN_PYTHON, cmd,
                    env_extra={"CUDA_VISIBLE_DEVICES": "", "HF_HUB_OFFLINE": "1"},
                    engine_name="kitten")

    def list_voices(self):
        print(f"Kitten TTS voices: {', '.join(VOICES)}")
        print("Model sizes: nano (~23MB)  micro (~41MB)  mini (~80MB)")
        for size, repo in MODEL_REPOS.items():
            print(f"  {size}: {repo}")
