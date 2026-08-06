#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""`specfuse` umbrella CLI — the bridge between the pip-installed driver and the
Claude Code plugin.

This module is a contribution to the SHARED `specfuse` PEP 420 namespace package
(there is intentionally no `specfuse/__init__.py`), so it composes with
`specfuse.loop` from the specfuse-loop distribution rather than shadowing it.

Subcommands:
  specfuse init DIR      scaffold a repo's .specfuse/ + .claude wiring from the
                         pip package (via specfuse.loop.scaffold.init)
  specfuse upgrade DIR   overlay the versioned scaffold (never downgrades), then
                         pip-upgrade the driver + CLI and point at /plugin update
  specfuse doctor        report suite commands whose PATH shim is missing, stale,
                         or owned by another install

init/upgrade accept --dry-run (preview, writes nothing). The scaffolding itself
lives in the driver package (`specfuse.loop.scaffold`, FEAT-2026-0026); this CLI
is the thin user-facing bridge over it.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from specfuse.loop import scaffold

__version__ = "0.9.4"

MARKETPLACE = "specfuse/specfuse"
PLUGIN = "specfuse@specfuse"
PLUGIN_UPDATE_HINT = (
    f"In Claude Code, run `/plugin update {PLUGIN}` (or, first time, "
    f"`/plugin marketplace add {MARKETPLACE}` then `/plugin install {PLUGIN}`)."
)


def _pip_install(packages: list[str], *, upgrade: bool, runner=None) -> int:
    """Install/upgrade packages with the current interpreter's pip. `runner` is
    injectable for testing; resolved at call time (not bound as a default) so
    `mock.patch(cli.subprocess.run)` is honored. Returns the subprocess return code."""
    runner = runner or subprocess.run
    cmd = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        cmd.append("--upgrade")
    cmd += packages
    proc = runner(cmd)
    return getattr(proc, "returncode", 0)


def _scaffold_is_current(target: Path) -> tuple[bool, str]:
    """Return (already_current, installed_seed_version).

    already_current is True when the target's .specfuse/VERSION equals the
    installed seed version — i.e. there is nothing newer to overlay.
    """
    installed = scaffold.scaffold_version()
    vpath = target / ".specfuse" / "VERSION"
    if not vpath.exists():
        return (False, installed)
    current = vpath.read_text(encoding="utf-8").strip()
    try:
        same = scaffold._parse_version(current) == scaffold._parse_version(installed)
    except ValueError:
        return (False, installed)
    return (same, installed)


def _pip_upgrade_or_advise(runner=None) -> int:
    """Pip-upgrade the driver + CLI, unless this is a pipx-managed or pip-less
    install — pipx owns its venv (and may ship no pip), so `python -m pip` either
    fails ('No module named pip') or fights pipx. In that case skip and advise
    the right command instead of erroring. Returns a process-style rc (0 = ok or
    cleanly skipped)."""
    pipx_managed = "/pipx/venvs/" in Path(sys.executable).as_posix()
    pip_missing = importlib.util.find_spec("pip") is None
    if pipx_managed or pip_missing:
        why = "pipx-managed install" if pipx_managed else "no pip in this environment"
        print(
            f"specfuse: skipping automatic package upgrade ({why}). Update the "
            f"driver + CLI with:\n"
            f"  pipx upgrade specfuse                 # if installed via pipx\n"
            f"  python3 -m pip install -U specfuse    # if installed in a venv",
            file=sys.stderr,
        )
        return 0
    rc = _pip_install(["specfuse-loop", "specfuse"], upgrade=True, runner=runner)
    if rc != 0:
        print(f"specfuse: pip upgrade failed (exit {rc}).", file=sys.stderr)
    else:
        print("specfuse: pip packages upgraded (specfuse-loop, specfuse).")
    return rc


def _shim_dir() -> Path:
    """The directory pipx/uv expose console scripts in. Both default to
    ~/.local/bin and both let the user move it, so honor the env vars first."""
    for var in ("PIPX_BIN_DIR", "UV_TOOL_BIN_DIR"):
        override = os.environ.get(var)
        if override:
            return Path(override).expanduser()
    return Path.home() / ".local" / "bin"


def _console_scripts() -> dict[str, str]:
    """Map console-script name -> distribution name for everything installed in
    THIS environment. Read off `distributions()` rather than
    `entry_points(group=...)` because `EntryPoint.dist` — the only way to
    attribute a script back to its package — is not available on 3.10/3.11, and
    requires-python allows those."""
    scripts: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if name is None:
            continue
        for ep in dist.entry_points:
            if ep.group == "console_scripts":
                scripts[ep.name] = name
    return scripts


def diagnose_shims(*, shim_dir: Path | None = None,
                   venv_bin: Path | None = None) -> list[tuple[str, str, str, str]]:
    """Find suite commands whose PATH shim does not lead back to this venv.

    The failure this catches: `specfuse-authoring` (and the orchestrator's
    commands) are console scripts of OPTIONAL extras, so two supported install
    paths compete for one name in ~/.local/bin — `pipx install --include-deps
    'specfuse[all]'`, which links them out of the umbrella venv, and a
    standalone `pipx install specfuse-authoring`, which links them out of its
    own. Whichever runs second loses: pipx refuses to overwrite a shim another
    venv owns ("File exists at ... and points to ... Not modifying") and warns
    on stderr, so the command silently keeps resolving to the OTHER install and
    upgrading one package changes nothing about what runs. A shim can also be
    left dangling when the venv that owned it is reinstalled without the extra.

    Returns (command, problem, fix, kind) tuples, kind one of "unlinked",
    "stale", "foreign"; empty means every script this venv provides resolves to
    this venv. Non-symlink shims are skipped: pipx uses symlinks on POSIX, and a
    Windows launcher .exe cannot be attributed by reading the filesystem.
    """
    shim_dir = shim_dir or _shim_dir()
    # Resolve: the comparison below is against shim.resolve(), and on macOS the
    # two sides disagree over /tmp vs /private/tmp (and over any symlinked venv
    # path) unless both are fully resolved — which would report every healthy
    # shim as foreign.
    venv_bin = (venv_bin or Path(sys.executable).parent).resolve()
    problems: list[tuple[str, str, str, str]] = []
    for command, dist in sorted(_console_scripts().items()):
        # Only scripts this venv actually ships: a dependency's entry point that
        # was never linked (no --include-deps) is a real finding, but a script
        # belonging to some unrelated package is not ours to police.
        if not (venv_bin / command).exists():
            continue
        shim = shim_dir / command
        if not shim.is_symlink() and not shim.exists():
            problems.append((
                command,
                f"provided by {dist} in this venv but not on PATH ({shim_dir})",
                f"pipx install --force --include-deps 'specfuse[all]'  "
                f"# or: uv tool install --with-executables-from {dist} 'specfuse[all]'",
                "unlinked",
            ))
            continue
        if not shim.is_symlink():
            continue
        if not shim.exists():
            problems.append((
                command,
                f"stale shim: {shim} -> {os.readlink(shim)} (target is gone)",
                f"rm {shim} && pipx install --force --include-deps 'specfuse[all]'",
                "stale",
            ))
            continue
        owner = shim.resolve().parent
        if owner != venv_bin:
            problems.append((
                command,
                f"shim points at another install: {shim} -> {shim.resolve()}",
                f"pick ONE owner — keep that install, or `pipx uninstall {dist}` "
                f"and reinstall the umbrella with --include-deps",
                "foreign",
            ))
    return problems


def _managed_by_tool() -> bool:
    """True when a tool installer (pipx / uv tool) owns this environment, i.e.
    when a PATH shim is expected to exist at all. A plain venv or a system pip
    install puts its scripts on PATH directly, so the shim check does not
    apply."""
    where = Path(sys.executable).resolve().as_posix()
    return "/pipx/venvs/" in where or "/uv/tools/" in where


def _warn_about_shims() -> None:
    """Advisory half of `specfuse doctor`, run at the end of an upgrade: report
    shim problems without failing the command that found them.

    Only the two BROKEN kinds. "unlinked" is left to `specfuse doctor`: an
    install without --include-deps legitimately leaves the driver's optional
    commands (specfuse-monitor, specfuse-stats, …) off PATH, so warning about it
    on every upgrade is noise, not a finding. A stale or foreign shim is always
    a bug — the command resolves somewhere other than what was just upgraded.
    """
    if not _managed_by_tool():
        return
    for command, problem, fix, kind in diagnose_shims():
        if kind == "unlinked":
            continue
        print(f"specfuse: warning: `{command}` — {problem}\n  fix: {fix}",
              file=sys.stderr)


def cmd_doctor(args: argparse.Namespace, *, runner=None) -> int:
    """Report suite commands whose PATH shim is missing, stale, or owned by a
    different install. Exits 1 when anything is wrong so CI can gate on it."""
    if not _managed_by_tool():
        print("specfuse: not a pipx/uv-managed install — this environment puts "
              "its scripts on PATH directly, so there are no shims to check.")
        return 0
    problems = diagnose_shims()
    if not problems:
        print(f"specfuse: all suite commands resolve to this install "
              f"({Path(sys.executable).resolve().parent}).")
        return 0
    print(f"specfuse: {len(problems)} command(s) do not resolve to this install:",
          file=sys.stderr)
    for command, problem, fix, _kind in problems:
        print(f"  {command}: {problem}\n    fix: {fix}", file=sys.stderr)
    return 1


def cmd_init(args: argparse.Namespace, *, runner=None) -> int:
    """Scaffold a repo's .specfuse/ + .claude wiring from the package (no pip,
    no curl-bash). Refuses if .specfuse/ already exists (points at `upgrade`)."""
    target = Path(args.target)
    if not target.is_dir():
        print(f"specfuse: target '{target}' is not a directory.", file=sys.stderr)
        return 2
    ci_check = getattr(args, "ci_check", None)

    if getattr(args, "dry_run", False):
        # Preview without touching the target: scaffold into a throwaway dir and
        # report the real written set. The exists-refusal is NOT bypassed.
        if (target / ".specfuse").exists():
            print(
                f"specfuse: {target}/.specfuse already exists — run `specfuse upgrade "
                f"{target}` instead (dry-run).",
                file=sys.stderr,
            )
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            written = scaffold.init(tmp, ci_check=ci_check)
        print(f"specfuse: [dry-run] would scaffold {len(written)} file(s) under "
              f"{target}/.specfuse/:")
        for rel in written:
            print(f"  .specfuse/{rel}")
        return 0

    try:
        written = scaffold.init(target, ci_check=ci_check)
    except scaffold.ScaffoldExistsError:
        print(
            f"specfuse: {target}/.specfuse already exists — refusing to re-init. "
            f"Run `specfuse upgrade {target}` to update an existing scaffold.",
            file=sys.stderr,
        )
        return 1
    print(f"specfuse: scaffolded {len(written)} file(s) under {target}/.specfuse/ "
          f"(+ .claude wiring).")
    print(PLUGIN_UPDATE_HINT)
    return 0


def cmd_upgrade(args: argparse.Namespace, *, runner=None) -> int:
    """Overlay the versioned scaffold onto an existing .specfuse/ (never downgrades),
    then pip-upgrade the driver + CLI and point at /plugin update."""
    target = Path(args.target)
    if not target.is_dir():
        print(f"specfuse: target '{target}' is not a directory.", file=sys.stderr)
        return 2
    ci_check = getattr(args, "ci_check", None)
    current, installed = _scaffold_is_current(target)

    if getattr(args, "dry_run", False):
        if current:
            print(f"specfuse: [dry-run] .specfuse/ is already at the latest "
                  f"scaffold version ({installed}); nothing to overlay.")
            return 0
        # Preview the overlay against a faithful copy of the target's .specfuse/;
        # the target is never touched and no pip runs.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_target = Path(tmp) / "repo"
            tmp_target.mkdir()
            src = target / ".specfuse"
            if src.exists():
                # symlinks=True copies links as links (don't follow); without it,
                # a legacy init.sh scaffold's dangling .specfuse/skills/* symlinks
                # make copytree raise on the missing targets. ignore_dangling_symlinks
                # is belt-and-suspenders for the same case.
                shutil.copytree(src, tmp_target / ".specfuse",
                                symlinks=True, ignore_dangling_symlinks=True)
            try:
                written = scaffold.upgrade_specfuse(tmp_target, ci_check=ci_check)
            except scaffold.ScaffoldDowngradeError as exc:
                print(f"specfuse: [dry-run] {exc}", file=sys.stderr)
                return 1
        print(f"specfuse: [dry-run] would overlay {len(written)} file(s) onto "
              f"{target}/.specfuse/ (no pip-upgrade in dry-run):")
        for rel in written:
            print(f"  .specfuse/{rel}")
        return 0

    # Overlay the scaffold BEFORE the pip-upgrade. The scaffold version is the one
    # this CLI's installed specfuse-loop carries; pip then catches the env up.
    try:
        written = scaffold.upgrade_specfuse(target, ci_check=ci_check)
    except scaffold.ScaffoldDowngradeError as exc:
        print(f"specfuse: {exc}", file=sys.stderr)
        return 1
    if current:
        print(f"specfuse: .specfuse/ already at the latest scaffold version "
              f"({installed}); .claude wiring refreshed.")
    else:
        print(f"specfuse: overlaid {len(written)} versioned file(s) onto "
              f"{target}/.specfuse/.")

    rc = _pip_upgrade_or_advise(runner)
    if rc != 0:
        return rc
    # After the upgrade, not before: an upgrade is exactly when a shim owned by
    # a competing install turns into a silent wrong-version bug — the package is
    # updated, the command on PATH still runs the other venv's copy.
    _warn_about_shims()
    print(PLUGIN_UPDATE_HINT)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="specfuse", description=__doc__.splitlines()[0])
    ap.add_argument("--version", action="version", version=f"specfuse {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    ini = sub.add_parser("init", help="scaffold a repo's .specfuse/ + .claude from the package")
    ini.add_argument("target", help="path to the repo to scaffold")
    ini.add_argument("--dry-run", action="store_true", help="preview; write nothing")
    ini.add_argument("--ci-check", default=None,
                     help="path to a CI check script to delegate verification.yml to")
    ini.set_defaults(func=cmd_init)

    up = sub.add_parser("upgrade", help="overlay the scaffold, then pip-upgrade + /plugin update")
    up.add_argument("target", help="path to the repo to upgrade")
    up.add_argument("--dry-run", action="store_true", help="preview; write nothing, no pip")
    up.add_argument("--ci-check", default=None,
                    help="path to a CI check script to delegate verification.yml to")
    up.set_defaults(func=cmd_upgrade)

    doc = sub.add_parser("doctor", help="check that suite commands on PATH resolve here")
    doc.set_defaults(func=cmd_doctor)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
