"""Matcha-TTS engine — daemon client with one-shot subprocess fallback.

Matcha-TTS is a fast flow-matching neural TTS by Shivam Mehta et al.
https://github.com/shivammehta25/Matcha-TTS  (MIT)

It lives in its own venv. The cold path runs `daemon/matcha-oneshot.py`
inside that venv via the venv's Python directly — calling matcha-tts's
Python API rather than its CLI. That avoids the upstream CLI's leak: it
always writes a `.png` mel-spectrogram next to each `.wav` (no flag
disables it). The one-shot writes only the WAV.

Install:  marmalade-tts install matcha
  (creates the Python 3.11 venv, installs matcha-tts + espeak-ng, and
  self-tests — matcha-tts does NOT build on Python 3.12, so the installer
  provisions 3.11 via uv. See marmalade_tts/installer.py.)
"""

import os

from . import Engine, EngineError, run_in_venv
from .. import daemon as dmgr

MATCHA_VENV = os.path.expanduser("~/.local/share/matcha-tts-venv")
VENV_PYTHON = os.path.join(MATCHA_VENV, "bin", "python")
ONESHOT_SCRIPT = "matcha-oneshot.py"

# Built-in model names that matcha-tts auto-downloads on first use.
MODELS = ["matcha_ljspeech", "matcha_vctk"]
DEFAULT_MODEL = "matcha_ljspeech"


def _is_checkpoint_path(model: str) -> bool:
    """A model spec is a checkpoint file path if it looks like one."""
    return model.endswith(".ckpt") or os.sep in model or model.startswith("~")


class MatchaEngine(Engine):
    name = "matcha"
    MAX_CHARS = 500

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = cfg.get("model", DEFAULT_MODEL)
        self.device = cfg.get("device", "cpu")
        self.use_daemon = cfg.get("daemon", False)
        # Optional speaker id for multi-speaker models (matcha_vctk: 0-107).
        self.spk = cfg.get("spk")
        # Quality knobs. `steps` (n_timesteps for matcha's ODE solver) is the
        # main quality lever — default 10 (matcha-tts's own default, tuned
        # for speed); 50 sounds noticeably better but takes 5x longer to
        # synthesize. None means "use the engine venv's default" (whatever
        # _matcha_synth.DEFAULT_STEPS / DEFAULT_TEMPERATURE are).
        self.steps = cfg.get("steps")
        self.temperature = cfg.get("temperature")

    def synthesize(self, text: str, out_path: str, voice: str = None,
                   speed: float = 1.0, speaker: str = None, **kwargs):
        # Matcha-TTS (via espeak) chokes on parentheses — strip them.
        text = text.replace("(", "").replace(")", "")
        # `voice` overrides the model spec; `speaker` overrides the speaker id.
        model = voice or self.model
        spk = speaker if speaker is not None else self.spk

        if self.use_daemon:
            request = {"text": text, "speed": speed, "out": out_path}
            if spk is not None:
                request["spk"] = int(spk)
            if self.steps is not None:
                request["steps"] = int(self.steps)
            if self.temperature is not None:
                request["temperature"] = float(self.temperature)
            dmgr.synthesize("matcha", request, auto_start=True, timeout=120.0)
            return

        # ── One-shot subprocess fallback ──
        if not os.path.exists(VENV_PYTHON):
            raise EngineError(
                f"[matcha] matcha-tts venv not found at {MATCHA_VENV}\n"
                f"  Run: marmalade-tts install matcha"
            )

        script = dmgr._find_daemon_script(ONESHOT_SCRIPT)
        if not os.path.exists(script):
            raise EngineError(
                f"[matcha] one-shot script not found: {script}\n"
                f"  Reinstall: bash install.sh"
            )

        env_extra = {}
        if self.device == "cpu":
            env_extra["CUDA_VISIBLE_DEVICES"] = ""

        # marmalade `speed` is a rate multiplier (1.4 = faster). Matcha's
        # length scale runs the other way (higher = slower), so invert.
        # When speed == 1.0, pass 1.0 explicitly — the one-shot defaults to
        # 1.0 too, so this is a no-op.
        length_scale = (1.0 / speed) if (speed and speed != 1.0) else 1.0

        cmd = [
            VENV_PYTHON, script,
            "--text", text,
            "--out", out_path,
            "--model", os.path.expanduser(model) if _is_checkpoint_path(model) else model,
            "--length-scale", str(length_scale),
        ]
        if spk is not None:
            cmd += ["--spk", str(int(spk))]
        if self.steps is not None:
            cmd += ["--steps", str(int(self.steps))]
        if self.temperature is not None:
            cmd += ["--temperature", str(float(self.temperature))]

        run_in_venv(VENV_PYTHON, cmd, env_extra=env_extra, engine_name="matcha")

    def list_voices(self):
        print("Matcha-TTS models (auto-download on first use):")
        for m in MODELS:
            marker = " (default)" if m == self.model else ""
            print(f"  {m}{marker}")
        print()
        print("  matcha_ljspeech — single female speaker (LJSpeech)")
        print("  matcha_vctk     — multi-speaker; pick a speaker with --speaker N (0-107)")
        print()
        print("Custom checkpoint: set engines.matcha.model to a .ckpt path,")
        print("or pass --voice /path/to/model.ckpt")
