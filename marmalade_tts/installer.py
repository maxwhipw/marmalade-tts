"""Hands-off engine + model installer for marmalade-tts.

marmalade-tts *owns* the install path. `marmalade-tts init` and
`marmalade-tts install <engine>` both route through here: each engine gets
its own venv at ``~/.local/share/<engine>-venv`` (created with uv), its pip
packages, any system deps (espeak-ng, via sudo with an explicit prompt),
its models (from ``models.json``), and a post-install self-test that
synthesizes one phrase through the exact same code path the CLI uses.

uv is a hard dependency — it manages per-engine Python versions and venvs
cross-distro. matcha and emojivoice *require* Python 3.11 (matcha-tts does
not build on 3.12: an old numpy pin uses the removed ``pkgutil.ImpImporter``).
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

# ── Recipes ──────────────────────────────────────────────────────────────────
#
# One declarative recipe per engine, mirroring init.ENGINE_INFO. Fields:
#   python         required Python version for the venv ("3.11"), or None to
#                  let uv pick a system-compatible interpreter.
#   venv           venv path — MUST match the venv constant in the engine
#                  module and ENGINE_PYTHON in daemon.py.
#   pip            packages / wheel URLs for the initial `uv pip install`.
#   pip_post       extra `uv pip install` invocations (each a list of args),
#                  run after the main install.
#   system_deps    system packages (installed via the distro package manager
#                  with sudo, after an explicit prompt).
#   models         model-ids to fetch from models.json, or None when the
#                  engine auto-downloads its own model on first run.
#   warm_cache     Python snippet run inside the venv to pre-download
#                  auto-fetched models so the first real run is offline-safe.
#   selftest_text  phrase synthesized for the post-install self-test.

INSTALL_RECIPES = {
    "kitten": {
        "python": "3.11",
        "venv": "~/.local/share/kittentts-venv",
        "pip": [
            "https://github.com/KittenML/KittenTTS/releases/download/0.8.1/"
            "kittentts-0.8.1-py3-none-any.whl",
        ],
        "pip_post": [],
        "system_deps": [],
        "models": None,  # auto-downloads from HuggingFace
        "warm_cache": (
            "from kittentts import KittenTTS\n"
            "for r in ('nano', 'micro', 'mini'):\n"
            "    KittenTTS(f'KittenML/kitten-tts-{r}-0.8')\n"
            "print('kitten models cached')\n"
        ),
        "selftest_text": "Marmalade kitten self test.",
    },
    "kokoro": {
        "python": None,
        "venv": "~/.local/share/kokoro-venv",
        "pip": ["kokoro", "soundfile"],
        "pip_post": [],
        "system_deps": [],
        "models": None,  # auto-downloads from HuggingFace
        "warm_cache": (
            "from kokoro import KPipeline\n"
            "p = KPipeline(lang_code='a', device='cpu')\n"
            "list(p('warm up', voice='af_heart'))\n"
            "print('kokoro model + voice cached')\n"
        ),
        "selftest_text": "Marmalade kokoro self test.",
    },
    "piper": {
        "python": None,
        "venv": "~/.local/share/piper-venv",
        "pip": ["piper-tts"],
        "pip_post": [],
        "system_deps": ["espeak-ng"],
        "models": ["piper-en_US-lessac-medium"],
        "warm_cache": None,
        "selftest_text": "Marmalade piper self test.",
    },
    "coqui": {
        "python": None,
        "venv": "~/.local/share/coqui-venv",
        "pip": ["coqui-tts"],
        # The modern `coqui-tts` fork (idiap/coqui-ai-TTS) pins its own torch
        # and transformers, so the torch-injection / transformers-patch dance
        # from the old unmaintained `TTS` package is no longer needed. If the
        # self-test ever fails on a transformers mismatch, add the pin here.
        "pip_post": [],
        "system_deps": [],
        "models": None,  # coqui downloads the model on first use
        "warm_cache": None,
        "selftest_text": "Marmalade coqui self test.",
    },
    "pocket": {
        "python": None,
        "venv": "~/.local/share/pocket-tts-venv",
        "pip": ["pocket-tts", "scipy"],
        "pip_post": [],
        "system_deps": [],
        "models": None,  # auto-downloads from HuggingFace
        "warm_cache": (
            "from pocket_tts import TTSModel\n"
            "m = TTSModel.load_model()\n"
            "m.get_state_for_audio_prompt('alba')\n"
            "print('pocket model cached')\n"
        ),
        "selftest_text": "Marmalade pocket self test.",
    },
    "matcha": {
        # Python 3.11 REQUIRED — matcha-tts does not build on 3.12.
        "python": "3.11",
        "venv": "~/.local/share/matcha-tts-venv",
        # matcha-tts pinned to 0.0.7.x — the cold path now calls the
        # matcha-tts Python API directly (load_matcha / load_vocoder /
        # process_text / to_waveform), which is less stable than the CLI,
        # so we pin to the range we've actually verified against.
        # torch < 2.6 REQUIRED — PyTorch 2.6 flipped torch.load's weights_only
        # default to True, and matcha-tts checkpoints embed an
        # omegaconf.DictConfig that isn't an allowed global, so checkpoint
        # loading raises UnpicklingError on torch >= 2.6. Pinning torch and
        # torchaudio together keeps uv's resolver from pulling a mismatched pair.
        "pip": ["matcha-tts>=0.0.7,<0.1", "torch<2.6", "torchaudio<2.6"],
        "pip_post": [],
        "system_deps": ["espeak-ng"],
        "models": None,  # matcha-tts auto-downloads via its own MATCHA_URLS
        "warm_cache": None,
        "selftest_text": "Marmalade matcha self test.",
    },
    "emojivoice": {
        # Python 3.11 REQUIRED — runs on matcha-tts (same 3.12 build failure).
        # matcha-tts pinned — see the matcha recipe above for why.
        # torch < 2.6 REQUIRED — same matcha-tts checkpoint-load issue (see
        # the matcha recipe); emojivoice loads its paige .ckpt the same way.
        "python": "3.11",
        "venv": "~/.local/share/emojivoice-venv",
        "pip": ["matcha-tts>=0.0.7,<0.1", "torch<2.6", "torchaudio<2.6"],
        "pip_post": [],
        "system_deps": ["espeak-ng"],
        "models": ["emojivoice-paige"],
        "warm_cache": None,
        "selftest_text": "Marmalade emojivoice self test \U0001f642",
    },
}


# ── uv ───────────────────────────────────────────────────────────────────────

def uv_bin() -> str:
    """Locate the uv binary. uv is a hard dependency — exit clearly if absent."""
    found = shutil.which("uv")
    if found:
        return found
    for cand in ("~/.local/bin/uv", "~/.cargo/bin/uv"):
        p = os.path.expanduser(cand)
        if os.path.exists(p):
            return p
    sys.exit(
        "[install] uv not found — it is a hard dependency of marmalade-tts.\n"
        "  Install it with:  curl -LsSf https://astral.sh/uv/install.sh | sh\n"
        "  or:               pipx install uv"
    )


def _run(cmd, **kwargs):
    """Run a command, raising CalledProcessError on failure."""
    kwargs.setdefault("check", True)
    return subprocess.run(cmd, **kwargs)


def uv_python_install(version: str):
    """Ensure a given Python version is available to uv."""
    _run([uv_bin(), "python", "install", version])


def uv_venv(venv_path: str, python: str = None):
    """Create (or recreate, --clear) a venv at venv_path."""
    cmd = [uv_bin(), "venv", "--clear"]
    if python:
        cmd += ["--python", python]
    cmd += [venv_path]
    _run(cmd)


def uv_pip_install(venv_path: str, packages):
    """Install packages into venv_path with uv."""
    venv_python = os.path.join(venv_path, "bin", "python")
    _run([uv_bin(), "pip", "install", "--python", venv_python, *packages])


# ── System dependencies ──────────────────────────────────────────────────────

# distro package manager → the sudo install command prefix
_PKG_INSTALL = {
    "apt-get": ["sudo", "apt-get", "install", "-y"],
    "dnf": ["sudo", "dnf", "install", "-y"],
    "pacman": ["sudo", "pacman", "-S", "--noconfirm"],
}

def _has_espeak_ng() -> bool:
    """espeak-ng is 'present' if EITHER the CLI binary OR the shared library is
    loadable. matcha-tts / emojivoice / piper-phonemize call libespeak-ng via
    `phonemizer` (ctypes), so the shared library alone is sufficient — and
    Debian/Ubuntu often install `libespeak-ng1` (e.g. via speech-dispatcher)
    without the `espeak-ng` CLI package. Checking only the binary causes a
    spurious sudo prompt on those systems.
    """
    if shutil.which("espeak-ng"):
        return True
    import ctypes
    for soname in ("libespeak-ng.so.1", "libespeak-ng.so"):
        try:
            ctypes.CDLL(soname)
            return True
        except OSError:
            continue
    return False


# system package name → callable that returns True if the dep is satisfied.
# Default (when no entry): `shutil.which(name)`.
_DEP_PRESENT = {"espeak-ng": _has_espeak_ng}


def _dep_present(dep: str) -> bool:
    check = _DEP_PRESENT.get(dep)
    if check is not None:
        return check()
    return shutil.which(dep) is not None


def detect_distro() -> str | None:
    """Return the system package manager name, or None if unrecognized."""
    for mgr in ("apt-get", "dnf", "pacman"):
        if shutil.which(mgr):
            return mgr
    return None


def ensure_system_deps(deps, allow_sudo: bool, interactive: bool):
    """Install any missing system packages. Returns [(dep, status), ...].

    Already-present packages are skipped. Missing ones are announced up
    front; in interactive mode the user confirms the sudo command, in
    non-interactive mode they are only installed when allow_sudo is set
    (otherwise skipped with a clear warning).
    """
    results = [(d, "present") for d in deps if _dep_present(d)]
    missing = [d for d in deps if not _dep_present(d)]
    if not missing:
        return results

    mgr = detect_distro()
    if not mgr:
        print(f"[install] No supported package manager found — install manually: "
              f"{', '.join(missing)}")
        return results + [(d, "skipped-no-pkgmgr") for d in missing]

    install_cmd = _PKG_INSTALL[mgr] + missing
    print(f"[install] marmalade-tts needs system package(s): {', '.join(missing)}")
    print(f"          It will run:  {' '.join(install_cmd)}")

    if interactive:
        try:
            resp = input("          Proceed with sudo? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            resp = "n"
        proceed = resp in ("", "y", "yes")
    else:
        proceed = allow_sudo
        if not proceed:
            print("          Skipped — non-interactive without --allow-sudo. "
                  "Install the package(s) above manually, or re-run with --allow-sudo.")

    if not proceed:
        return results + [(d, "skipped") for d in missing]

    try:
        _run(install_cmd)
        return results + [(d, "installed") for d in missing]
    except subprocess.CalledProcessError as e:
        print(f"[install] system package install failed: {e}")
        return results + [(d, "failed") for d in missing]


# ── Model manifest + fetching ────────────────────────────────────────────────

def manifest_path() -> str:
    return os.path.join(os.path.dirname(__file__), "models.json")


def load_manifest() -> dict:
    with open(manifest_path(), encoding="utf-8") as f:
        return json.load(f)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _http_download(url: str, dest: str):
    # Download to a .part file and rename on success — so an interrupted or
    # error-page (e.g. a 200 HTML rate-limit notice) download never leaves a
    # truncated/garbage file sitting at `dest`.
    req = urllib.request.Request(url, headers={"User-Agent": "marmalade-tts-installer"})
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _gdrive_download(src: dict, dest: str):
    """Download a single file out of a public Google Drive folder via gdown.

    gdown is run through `uv tool run` so it never has to be a marmalade-tts
    dependency. We only have the folder id (no per-file id), so the whole
    folder is fetched to a temp dir and the target filename is moved out.
    """
    tmp = tempfile.mkdtemp(prefix="marmalade-gdrive-")
    try:
        print(f"[install]   fetching {src['filename']} from Google Drive via "
              f"gdown — the first run also installs gdown, this can take a while…")
        folder_url = f"https://drive.google.com/drive/folders/{src['folder_id']}"
        _run([uv_bin(), "tool", "run", "gdown", "--folder", folder_url, "-O", tmp])
        for root, _, files in os.walk(tmp):
            if src["filename"] in files:
                shutil.move(os.path.join(root, src["filename"]), dest)
                return
        raise RuntimeError(f"{src['filename']!r} not found in Drive folder")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _fetch_file(fspec: dict, model_id: str) -> str:
    """Fetch one file of a model. Returns a status string."""
    dest = os.path.expanduser(fspec["dest"])
    sha = fspec.get("sha256")
    if os.path.exists(dest) and (not sha or _sha256(dest) == sha):
        return "present"

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    last_err = None
    for src in fspec["sources"]:
        try:
            if src["type"] == "gdrive":
                _gdrive_download(src, dest)
            else:
                _http_download(src["url"], dest)
            if sha:
                got = _sha256(dest)
                if got != sha:
                    last_err = f"sha256 mismatch (expected {sha}, got {got})"
                    os.remove(dest)
                    continue
            return "downloaded"
        except Exception as e:  # noqa: BLE001 — try the next source on any error
            last_err = f"{type(e).__name__}: {e}"
            if os.path.exists(dest):
                os.remove(dest)
            continue
    # Raised (not sys.exit) so a batch install can record it per-engine and
    # carry on with the next engine.
    raise RuntimeError(f"failed to fetch {model_id} → {dest}: {last_err}")


def fetch_model(model_id: str, manifest: dict):
    """Fetch every file of a model-id. Returns [(dest, status), ...]."""
    entry = manifest["models"].get(model_id)
    if not entry:
        sys.exit(f"[install] unknown model id in manifest: {model_id}")
    out = []
    for fspec in entry["files"]:
        status = _fetch_file(fspec, model_id)
        out.append((os.path.expanduser(fspec["dest"]), status))
    return out


# ── Self-test ────────────────────────────────────────────────────────────────

def selftest(engine_name: str, text: str):
    """Synthesize one phrase via the engine's real subprocess path.

    Returns (ok: bool, message: str). Builds the engine exactly the way the
    CLI does (daemon disabled) so a PASS means the installed engine works.
    """
    import wave

    from .cli import ENGINE_CLASSES

    tmp = os.path.join(tempfile.gettempdir(),
                       f"marmalade-selftest-{engine_name}-{os.getpid()}.wav")
    try:
        engine = ENGINE_CLASSES[engine_name]({"device": "cpu", "daemon": False})
        engine.synthesize(text, tmp, speed=1.0)
        if not os.path.exists(tmp):
            return False, "no output file produced"
        if os.path.getsize(tmp) < 1024:
            return False, f"output WAV suspiciously small ({os.path.getsize(tmp)} bytes)"
        with wave.open(tmp) as w:
            frames = w.getnframes()
        if frames <= 0:
            return False, "WAV has no audio frames"
        return True, f"{frames} frames, {os.path.getsize(tmp)} bytes"
    except SystemExit as e:
        return False, f"engine exited: {e}"
    except Exception as e:  # noqa: BLE001 — any failure is a failed self-test
        return False, f"{type(e).__name__}: {e}"
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# ── Orchestration ────────────────────────────────────────────────────────────

def install_engine(name: str, allow_sudo: bool = False, reinstall: bool = False,
                    skip_selftest: bool = False, interactive: bool = True) -> dict:
    """Install one engine end-to-end: python → venv → pip → pip_post →
    system deps → models → warm_cache → self-test.

    Returns a result dict. Raises nothing for engine-level failures other
    than truly fatal ones (unknown engine, missing uv) — recoverable
    problems are captured in the returned dict so a batch install can
    continue with the next engine.
    """
    if name not in INSTALL_RECIPES:
        sys.exit(f"[install] unknown engine: {name!r} "
                 f"(known: {', '.join(INSTALL_RECIPES)})")

    recipe = INSTALL_RECIPES[name]
    venv = os.path.expanduser(recipe["venv"])
    result = {"engine": name, "venv": venv, "system_deps": [],
              "models": [], "selftest": None, "error": None}

    print(f"\n[install] ━━ {name} ━━")
    try:
        # 1. Python version
        if recipe["python"]:
            print(f"[install] {name}: ensuring Python {recipe['python']} (uv)")
            uv_python_install(recipe["python"])

        # 2. venv — recreate it if missing, incomplete (a prior install was
        # interrupted before the interpreter landed), or --reinstall.
        venv_python = os.path.join(venv, "bin", "python")
        if os.path.exists(venv_python) and not reinstall:
            print(f"[install] {name}: venv exists at {venv} "
                  f"(pass --reinstall to recreate)")
        else:
            if os.path.isdir(venv) and not reinstall:
                print(f"[install] {name}: venv at {venv} looks incomplete — recreating")
            else:
                print(f"[install] {name}: creating venv at {venv}")
            uv_venv(venv, recipe["python"])

        # 3. pip
        print(f"[install] {name}: installing {', '.join(recipe['pip'])}")
        uv_pip_install(venv, recipe["pip"])

        # 4. pip_post
        for step in recipe["pip_post"]:
            print(f"[install] {name}: extra pip install — {', '.join(step)}")
            uv_pip_install(venv, step)

        # 5. system deps
        if recipe["system_deps"]:
            result["system_deps"] = ensure_system_deps(
                recipe["system_deps"], allow_sudo, interactive)

        # 6. models
        if recipe["models"]:
            manifest = load_manifest()
            for model_id in recipe["models"]:
                print(f"[install] {name}: fetching model {model_id}")
                result["models"].append((model_id, fetch_model(model_id, manifest)))

        # 7. warm cache
        if recipe["warm_cache"]:
            print(f"[install] {name}: warming model cache (first-run download)")
            venv_python = os.path.join(venv, "bin", "python")
            env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
            try:
                _run([venv_python, "-c", recipe["warm_cache"]], env=env)
            except subprocess.CalledProcessError as e:
                print(f"[install] {name}: warm-cache step failed (non-fatal, the "
                      f"model will download on first use): {e}")

    except (subprocess.CalledProcessError, RuntimeError, OSError) as e:
        result["error"] = f"{type(e).__name__}: {e}"
        print(f"[install] {name}: FAILED — {result['error']}")
        return result

    # 8. self-test
    if skip_selftest:
        print(f"[install] {name}: self-test skipped")
    else:
        print(f"[install] {name}: self-test — synthesizing a phrase…")
        ok, msg = selftest(name, recipe["selftest_text"])
        result["selftest"] = (ok, msg)
        print(f"[install] {name}: self-test {'PASS ✓' if ok else 'FAIL ✗'} — {msg}")

    return result


def install_engines(names, allow_sudo: bool = False, reinstall: bool = False,
                     skip_selftest: bool = False, interactive: bool = True) -> list:
    """Install several engines, then print a summary. Returns the result list."""
    results = []
    for name in names:
        results.append(install_engine(
            name, allow_sudo=allow_sudo, reinstall=reinstall,
            skip_selftest=skip_selftest, interactive=interactive))

    print("\n[install] ━━ summary ━━")
    all_ok = True
    for r in results:
        if r["error"]:
            all_ok = False
            print(f"  ✗ {r['engine']}: {r['error']}")
        elif r["selftest"] is None:
            print(f"  • {r['engine']}: installed (self-test skipped)")
        else:
            ok, msg = r["selftest"]
            if not ok:
                all_ok = False
            mark = "✓" if ok else "✗"
            print(f"  {mark} {r['engine']}: self-test {'PASS' if ok else 'FAIL'} — {msg}")
    return results
