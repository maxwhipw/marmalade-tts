"""Hands-off engine + state UNinstaller for marmalade-tts.

The mirror image of ``installer.py``. Removes only state the CLI itself
manages (engine venvs, daemon scripts, systemd user units, sockets/pids/logs,
config and pronunciations dict). Never removes:

  - the CLI binary or its Python package — at the end of ``--purge`` we
    print the install-method-specific removal command instead;
  - the HuggingFace cache (shared with other tools);
  - any user voice file that lives outside our managed directories.

This module deletes files, so every code path errs HEAVILY toward
refusing rather than risking unwanted removal:

  1. A path whitelist gates every delete. The user can never supply
     a raw path — only the engine name or the tier flag.
  2. Symlinks are refused (they can escape the intended directory).
  3. Each directory is verified by a marker file (``pyvenv.cfg`` for a
     venv, ``daemon/_common.py`` for the daemon dir, ``config.yaml`` for
     the config dir) before deletion.
  4. The path's resolved abspath must live under ~/.local or ~/.config
     and have at least 4 path components — no chance of nuking $HOME.
  5. Each failed/refused delete prints a clear WARN; the command exits
     non-zero if any path failed.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from .installer import INSTALL_RECIPES

# ── Layout ───────────────────────────────────────────────────────────────────

BASE_DIR = "~/.local/share/marmalade-tts"
CONFIG_DIR = "~/.config/marmalade-tts"
SYSTEMD_USER_DIR = "~/.config/systemd/user"

# Engine-owned model dirs OUTSIDE the venv. (kitten/kokoro/pocket use the
# HuggingFace cache; matcha/emojivoice keep their checkpoints inside their
# venvs.) Removed by ``uninstall_engine(<eng>)`` and ``--engines``.
ENGINE_MODEL_DIRS = {
    "piper": "~/.local/share/piper",
    "coqui": "~/.local/share/tts",
}

# Required marker files. A directory we know by path is only deleted if its
# marker exists (or the dir is empty — see _is_empty_dir). Better to leave a
# weird directory than wipe the wrong one.
_DIR_MARKERS = {
    # venvs
    **{os.path.expanduser(r["venv"]): "pyvenv.cfg" for r in INSTALL_RECIPES.values()},
    os.path.expanduser(BASE_DIR): os.path.join("daemon", "_common.py"),
    os.path.expanduser(CONFIG_DIR): "config.yaml",
}

# ── Install-method detection (for the --purge end-of-run hint) ───────────────

REMOVAL_HINTS = {
    "apt": "sudo apt remove marmalade-tts    # 'apt purge' also drops /etc/marmalade-tts defaults if any",
    "rpm": "sudo dnf remove marmalade-tts",
    "pacman": "sudo pacman -R marmalade-tts",
    "pipx": "pipx uninstall marmalade-tts",
    "manual": "rm ~/.local/bin/marmalade-tts && rm -rf ~/.local/lib/marmalade-tts",
    "unknown": "(Couldn't determine your install method — find the marmalade-tts "
               "binary on your $PATH and remove it however you installed it.)",
}


def detect_install_method() -> str:
    """Return 'apt', 'rpm', 'pacman', 'pipx', 'manual', or 'unknown'."""
    bin_path = shutil.which("marmalade-tts")
    if not bin_path:
        return "unknown"
    real = os.path.realpath(bin_path)
    if real.startswith("/usr/"):
        for cmd, ret in (
            (["dpkg", "-S", bin_path], "apt"),
            (["rpm", "-q", "marmalade-tts"], "rpm"),
            (["pacman", "-Q", "marmalade-tts"], "pacman"),
        ):
            try:
                subprocess.run(cmd, capture_output=True, check=True)
                return ret
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        return "unknown"
    if "/pipx/" in real:
        return "pipx"
    home = os.path.expanduser("~")
    if real.startswith(home + "/.local/bin"):
        lib = os.path.join(home, ".local/lib/marmalade-tts")
        if os.path.isdir(lib):
            return "manual"
    return "unknown"


def print_removal_hint(method: str) -> None:
    print()
    print("[uninstall] The CLI binary itself is NOT removed by this command.")
    print("[uninstall] To remove marmalade-tts itself, run:")
    print(f"  {REMOVAL_HINTS.get(method, REMOVAL_HINTS['unknown'])}")
    print()
    print("[uninstall] HuggingFace cache (shared with other tools — NEVER touched):")
    print("  ~/.cache/huggingface/hub/  contains downloaded weights for kitten/")
    print("    kokoro/pocket. Clean manually with `huggingface-cli scan-cache` if")
    print("    you want them gone.")


# ── Safety ──────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _safe_paths() -> frozenset[str]:
    """All paths the uninstaller is ever allowed to touch.

    Anything not in this set is refused at runtime — the user can never
    supply a path, but defense in depth catches future bugs. Cached for the
    process lifetime; tests that monkeypatch INSTALL_RECIPES / BASE_DIR /
    CONFIG_DIR etc. must call ``_safe_paths.cache_clear()`` after the patch.
    """
    paths: set[str] = set()
    for recipe in INSTALL_RECIPES.values():
        paths.add(os.path.expanduser(recipe["venv"]))
    paths.update(os.path.expanduser(p) for p in (
        BASE_DIR,
        CONFIG_DIR,
        *ENGINE_MODEL_DIRS.values(),
    ))
    # Per-engine systemd units (exact filenames).
    for eng in INSTALL_RECIPES:
        paths.add(os.path.expanduser(
            f"{SYSTEMD_USER_DIR}/marmalade-{eng}.service"))
    # Per-engine sockets / pids / logs.
    for eng in INSTALL_RECIPES:
        for suffix in (".sock", ".pid", ".log"):
            paths.add(os.path.expanduser(f"{BASE_DIR}/{eng}{suffix}"))
    return frozenset(paths)


def _is_under_managed_root(path: str) -> bool:
    """The resolved abspath must sit under ~/.local or ~/.config and have at
    least 4 path components. Guarantees we never delete a top-level dir like
    ``$HOME`` or ``~/.local`` even if a future refactor adds a buggy entry to
    the whitelist."""
    abs_p = os.path.abspath(path)
    home = os.path.abspath(os.path.expanduser("~"))
    if not (abs_p.startswith(home + "/.local")
            or abs_p.startswith(home + "/.config")):
        return False
    # /home/user/.config/marmalade-tts splits to 5 elements counting the
    # empty leading element from the leading '/'. Threshold of 5 means the
    # path must sit at least two directories below home — qualifies
    # ~/.config/marmalade-tts and ~/.local/share/x; rejects ~/.local,
    # ~/.config, and $HOME itself.
    return len(abs_p.rstrip("/").split(os.sep)) >= 5


def _is_empty_dir(path: str) -> bool:
    try:
        return os.path.isdir(path) and not os.listdir(path)
    except OSError:
        return False


def _check_marker(path: str) -> tuple[bool, str]:
    """Verify the marker file is present (or the dir is empty).

    Returns ``(ok, reason)``. ``reason`` is filled when ``ok`` is False.
    Marker check applies only to directories we have a marker for; files
    and unmarked dirs pass through.
    """
    marker = _DIR_MARKERS.get(os.path.abspath(path))
    if marker is None:
        return True, ""
    if not os.path.isdir(path):
        # Not a dir — nothing to verify (e.g. it's gone already).
        return True, ""
    if _is_empty_dir(path):
        # Idempotent: a post-cleanup empty shell is safe to remove.
        return True, ""
    marker_path = os.path.join(path, marker)
    if os.path.islink(marker_path):
        # A symlinked marker could point anywhere — refuse rather than trust it.
        return False, f"marker file {marker!r} in {path} is a symlink (refused)"
    if os.path.exists(marker_path):
        return True, ""
    return False, f"missing marker file {marker!r} in {path}"


# ── Report ──────────────────────────────────────────────────────────────────

@dataclass
class Report:
    removed: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    install_method: str | None = None  # set on --purge

    def merge(self, other: "Report") -> None:
        self.removed.extend(other.removed)
        self.skipped.extend(other.skipped)
        self.failed.extend(other.failed)

    @property
    def ok(self) -> bool:
        return not self.failed


# ── Deletion primitives ─────────────────────────────────────────────────────

def _path_size(path: str) -> int:
    """Best-effort size on disk in bytes. Never raises."""
    try:
        if os.path.islink(path):
            return os.lstat(path).st_size
        if os.path.isfile(path):
            return os.path.getsize(path)
        if os.path.isdir(path):
            total = 0
            for root, _, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        continue
            return total
    except OSError:
        return 0
    return 0


def _fmt_size(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def _safe_remove(path: str, *, dry_run: bool, report: Report) -> None:
    """Remove a single whitelisted path, with every safety check applied.

    Order:
      1. Whitelist check.
      2. Managed-root + depth check.
      3. Existence check — missing is idempotent (skipped, not failed).
      4. Symlink refusal.
      5. Marker-file verification.
      6. Dry-run short-circuit.
      7. shutil.rmtree / os.unlink.
    """
    whitelist = _safe_paths()
    abs_p = os.path.abspath(path)
    if abs_p not in {os.path.abspath(p) for p in whitelist}:
        msg = f"refused (not in whitelist): {path}"
        print(f"[uninstall] WARN: {msg}", file=sys.stderr)
        report.failed.append((path, "not in whitelist"))
        return

    if not _is_under_managed_root(path):
        msg = f"refused (path outside ~/.local or ~/.config, or too shallow): {path}"
        print(f"[uninstall] WARN: {msg}", file=sys.stderr)
        report.failed.append((path, "outside managed root"))
        return

    if not os.path.exists(path) and not os.path.islink(path):
        report.skipped.append((path, "already gone"))
        return

    if os.path.islink(path):
        # Symlinks can escape the intended dir — refuse, never follow.
        msg = f"refused (symlink): {path}"
        print(f"[uninstall] WARN: {msg}", file=sys.stderr)
        report.failed.append((path, "symlink"))
        return

    ok, reason = _check_marker(path)
    if not ok:
        print(f"[uninstall] WARN: refused — {reason}", file=sys.stderr)
        report.failed.append((path, reason))
        return

    if dry_run:
        report.removed.append(path)
        return

    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)
        report.removed.append(path)
    except OSError as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"[uninstall] WARN: {path}: {msg}", file=sys.stderr)
        report.failed.append((path, msg))


# ── systemd integration ─────────────────────────────────────────────────────

def _systemctl_user(*args: str) -> None:
    """Best-effort `systemctl --user` call. Never raises."""
    try:
        subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True, check=False, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _stop_and_disable_unit(engine: str, *, dry_run: bool) -> None:
    """Stop + disable the systemd user unit for an engine. No-op if missing."""
    unit = f"marmalade-{engine}.service"
    if dry_run:
        print(f"[uninstall]   would stop + disable {unit}")
        return
    _systemctl_user("stop", unit)
    _systemctl_user("disable", unit)


def _stop_daemon(engine: str, *, dry_run: bool) -> None:
    """Stop the daemon if it's running. Must run BEFORE removing its socket."""
    # Imported lazily so test patches on ``marmalade_tts.uninstaller.daemon``
    # work without importing the live module on collection.
    from . import daemon as daemon_mod
    if dry_run:
        if daemon_mod.is_running(engine):
            print(f"[uninstall]   would stop daemon: {engine}")
        return
    try:
        if daemon_mod.is_running(engine):
            daemon_mod.stop(engine)
    except Exception as e:  # noqa: BLE001 — daemon stop is best-effort
        print(f"[uninstall] WARN: failed to stop {engine} daemon: {e}",
              file=sys.stderr)


# ── Per-engine cleanup ──────────────────────────────────────────────────────

def _engine_targets(engine: str) -> list[str]:
    """Paths owned by a single engine, in deletion order:
      systemd unit → venv → per-engine model dir → socket → pid → log.
    """
    recipe = INSTALL_RECIPES[engine]
    targets = [
        os.path.expanduser(f"{SYSTEMD_USER_DIR}/marmalade-{engine}.service"),
        os.path.expanduser(recipe["venv"]),
    ]
    if engine in ENGINE_MODEL_DIRS:
        targets.append(os.path.expanduser(ENGINE_MODEL_DIRS[engine]))
    for suffix in (".sock", ".pid", ".log"):
        targets.append(os.path.expanduser(f"{BASE_DIR}/{engine}{suffix}"))
    return targets


def uninstall_engine(name: str, *, dry_run: bool) -> Report:
    """Tear down a single engine: stop daemon → drop unit → remove venv /
    models / sockets / pids / logs. Leaves the shared daemon scripts dir
    and config alone.
    """
    if name not in INSTALL_RECIPES:
        raise SystemExit(
            f"[uninstall] unknown engine: {name!r} "
            f"(known: {', '.join(INSTALL_RECIPES)})")

    report = Report()
    print(f"\n[uninstall] ━━ {name} ━━")

    # 1. Stop daemon (so the socket file is unlocked before we unlink it).
    _stop_daemon(name, dry_run=dry_run)
    # 2. Stop + disable the systemd unit (so it doesn't get re-spawned).
    _stop_and_disable_unit(name, dry_run=dry_run)

    # 3. Walk the per-engine targets, in order.
    for path in _engine_targets(name):
        _safe_remove(path, dry_run=dry_run, report=report)

    return report


def uninstall_all_engines(*, dry_run: bool) -> Report:
    """``--engines``: tear down every engine. Keeps the daemon scripts dir +
    config dir intact."""
    report = Report()
    for name in INSTALL_RECIPES:
        report.merge(uninstall_engine(name, dry_run=dry_run))
    return report


def purge(*, dry_run: bool) -> Report:
    """``--purge``: ``--engines`` + remove the daemon scripts dir + config dir.
    Sets ``report.install_method`` so the caller can print the right hint."""
    report = uninstall_all_engines(dry_run=dry_run)

    print("\n[uninstall] ━━ shared state ━━")
    for path in (
        os.path.expanduser(BASE_DIR),    # daemon scripts + remaining logs
        os.path.expanduser(CONFIG_DIR),  # config.yaml + pronunciations.yaml
    ):
        _safe_remove(path, dry_run=dry_run, report=report)

    # Skip detection on dry-run — it forks dpkg/rpm/pacman subprocesses, and
    # dry-run promises no side effects. The hint isn't printed on dry-run
    # anyway (cmd_uninstall returns before print_removal_hint).
    if not dry_run:
        report.install_method = detect_install_method()
    return report


# ── Planning / printing ─────────────────────────────────────────────────────

def plan_for_engine(name: str) -> list[str]:
    """Return the list of paths an ``uninstall <engine>`` would touch."""
    return _engine_targets(name)


def plan_for_all_engines() -> list[str]:
    out: list[str] = []
    for name in INSTALL_RECIPES:
        out.extend(_engine_targets(name))
    return out


def plan_for_purge() -> list[str]:
    return plan_for_all_engines() + [
        os.path.expanduser(BASE_DIR),
        os.path.expanduser(CONFIG_DIR),
    ]


def print_plan(paths: list[str], header: str) -> None:
    """Print the planned-removal list with per-path size."""
    print(f"\n[uninstall] {header}")
    if not paths:
        print("  (nothing to do)")
        return
    total = 0
    for p in paths:
        if not os.path.lexists(p):
            note = "(already gone)"
        elif os.path.islink(p):
            # Symlinks get refused at delete time, so don't count their size
            # against the reclaimable total — that number would mislead.
            note = "(symlink — will be REFUSED)"
        else:
            size = _path_size(p)
            total += size
            note = f"~ {_fmt_size(size)}"
        print(f"  - {p}  {note}")
    print(f"  Total reclaimable: ~ {_fmt_size(total)}")
