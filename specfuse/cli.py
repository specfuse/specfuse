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

Both accept --dry-run (preview, writes nothing). The scaffolding itself lives in
the driver package (`specfuse.loop.scaffold`, FEAT-2026-0026); this CLI is the
thin user-facing bridge over it.
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from specfuse.loop import scaffold

__version__ = "0.2.5"

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

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
