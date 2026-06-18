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
  specfuse upgrade   pip-upgrade the driver + this CLI, then point at /plugin update
  specfuse init DIR  ensure the driver is installed and print the bootstrap steps

Scope note: a fully pip-native `specfuse init` that lays down templates/rules from
package data is deferred (see specfuse/loop FEAT-2026-0019 retrospective) — until
then, scaffolding a NEW repo still uses the loop's `init.sh`. This CLI owns the
pip <-> plugin bridge; it does not yet own scaffold-data delivery.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

__version__ = "0.1.0"

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


def cmd_upgrade(args: argparse.Namespace, *, runner=None) -> int:
    """Upgrade the driver + umbrella via pip, then point at the plugin update."""
    rc = _pip_install(["specfuse-loop", "specfuse"], upgrade=True, runner=runner)
    if rc != 0:
        print(f"specfuse: pip upgrade failed (exit {rc}).", file=sys.stderr)
        return rc
    print("specfuse: pip packages upgraded (specfuse-loop, specfuse).")
    print(PLUGIN_UPDATE_HINT)
    return 0


def cmd_init(args: argparse.Namespace, *, runner=None) -> int:
    """Bootstrap: ensure the driver is installed and print the next steps. Full
    pip-native scaffolding is deferred; if the loop's init.sh is reachable we point
    at it, otherwise we print the documented bootstrap path."""
    target = Path(args.target)
    if not target.is_dir():
        print(f"specfuse: target '{target}' is not a directory.", file=sys.stderr)
        return 2
    rc = _pip_install(["specfuse-loop"], upgrade=False, runner=runner)
    if rc != 0:
        print(f"specfuse: could not install specfuse-loop (exit {rc}).", file=sys.stderr)
        return rc
    print("specfuse: specfuse-loop installed; `specfuse-loop` is on PATH.")
    print(
        "specfuse: to scaffold this repo's `.specfuse/` (templates, rules, "
        "verification.yml), run the loop's init.sh until pip-native scaffolding "
        "ships:\n"
        "  curl -fsSL https://raw.githubusercontent.com/specfuse/loop/main/init.sh "
        f"| bash -s -- {target}"
    )
    print(PLUGIN_UPDATE_HINT)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="specfuse", description=__doc__.splitlines()[0])
    ap.add_argument("--version", action="version", version=f"specfuse {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    up = sub.add_parser("upgrade", help="pip-upgrade driver + CLI, then /plugin update")
    up.set_defaults(func=cmd_upgrade)

    ini = sub.add_parser("init", help="ensure the driver is installed; print bootstrap steps")
    ini.add_argument("target", help="path to the repo to bootstrap")
    ini.set_defaults(func=cmd_init)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
