#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""`specfuse` umbrella CLI — the suite's entry point and the bridge to the Claude
Code plugin.

The umbrella IS the suite: its hard dependencies (specfuse-loop,
specfuse-orchestrator, specfuse-authoring) mean one `pipx install specfuse` /
`uv tool install specfuse` installs and upgrades every script component, with no
extras and no installer flags. Plugins stay separate and per-repo — that is the
toolset choice a repository makes.

This module is a contribution to the SHARED `specfuse` PEP 420 namespace package
(there is intentionally no `specfuse/__init__.py`), so it composes with
`specfuse.loop` from the specfuse-loop distribution rather than shadowing it.

Own subcommands:
  specfuse init [DIR]    scaffold a repo's .specfuse/ + .claude wiring, or
                         upgrade it if one is already there — idempotent
  specfuse upgrade [DIR] the same operation, named for what it does to an
                         existing scaffold
  specfuse doctor        report suite commands whose PATH shim is missing, stale,
                         or owned by another install (--fix clears dead shims)
  specfuse --version     the umbrella version plus the resolved component table

init/upgrade accept --dry-run (preview, writes nothing). The scaffolding itself
lives in the driver package (`specfuse.loop.scaffold`, FEAT-2026-0026); this CLI
is the thin user-facing bridge over it.

Delegating subcommands (DELEGATED_COMMANDS): `specfuse run`, `lint`, `monitor`,
`stats`, `authoring`, `pm`, … hand off to the component that implements them.
They replace the flat `specfuse-*` commands, which remain as deprecated aliases —
one name on PATH is what makes a shim collision between two installs structurally
impossible.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from specfuse.loop import scaffold

from specfuse import methodology

__version__ = "0.11.0"

MARKETPLACE = "specfuse/specfuse"
PLUGIN = "specfuse@specfuse"
PLUGIN_UPDATE_HINT = (
    f"In Claude Code, run `/plugin update {PLUGIN}` (or, first time, "
    f"`/plugin marketplace add {MARKETPLACE}` then `/plugin install {PLUGIN}`)."
)

# The suite's components, in the order `specfuse --version` reports them. These
# are HARD dependencies of the umbrella (not extras), so a missing one means a
# broken install, not an opt-out the user declined.
COMPONENTS = ("specfuse-loop", "specfuse-orchestrator", "specfuse-authoring")

# Distributions whose console scripts `specfuse doctor` is responsible for: the
# umbrella plus its components. Bundling the suite pulled transitive deps that
# ship scripts of their own (jsonschema, via the orchestrator), and without this
# filter doctor reported `jsonschema` as a broken suite command.
SUITE_DISTS = ("specfuse", *COMPONENTS)

# The plugins this marketplace catalogs, as `enabledPlugins` keys. `specfuse` is
# asserted by the scaffold itself; the other two are opt-in per repo via
# `--plugins`, because which Claude assets a repo enables is its own decision.
PLUGIN_KEYS = {
    "specfuse": "specfuse@specfuse",
    "authoring": "specfuse-authoring@specfuse",
    "orchestrator": "specfuse-orchestrator@specfuse",
}

# subcommand -> (entry target, the flat command it replaces, help text)
#
# Each target is a component's console-script main. The umbrella dispatches to
# them so the suite needs ONE name on PATH: the flat `specfuse-*` commands share
# their names with the standalone packages' scripts, so two installs can fight
# over them and the loser's upgrades silently change nothing about what runs. A
# single `specfuse` shim cannot collide with anything.
DELEGATED_COMMANDS: dict[str, tuple[str, str, str]] = {
    "run": ("specfuse.loop.loop:main", "specfuse-loop",
            "run the gate-cycle driver"),
    "lint": ("specfuse.loop.lint_plan:main", "specfuse-lint",
             "lint a feature plan"),
    "monitor": ("specfuse.monitor.cli:main", "specfuse-monitor",
                "the monitoring CLI"),
    "monitor-lint": ("specfuse.loop.lint_monitoring:main", "specfuse-monitor-lint",
                     "lint a monitoring config"),
    "stats": ("specfuse.loop.events_stats:main", "specfuse-stats",
              "event statistics for a repo's loop"),
    "authoring": ("specfuse.authoring.cli:_run", "specfuse-authoring",
                  "the spec-authoring kit (design/validate/bundle)"),
    "pm": ("specfuse.orchestrator.cli:main", "specfuse-orchestrator",
           "multi-repo initiative coordination"),
    "poller": ("specfuse.orchestrator.poller:main", "specfuse-poller",
               "the orchestrator's inbox poller"),
    "runner": ("specfuse.orchestrator.runner:main", "specfuse-runner",
               "the orchestrator's agent runner"),
    "validate-event": ("specfuse.orchestrator.validate_event:main",
                       "specfuse-validate-event", "validate an orchestrator event"),
    "validate-frontmatter": ("specfuse.orchestrator.validate_frontmatter:main",
                             "specfuse-validate-frontmatter",
                             "validate a document's frontmatter"),
}

# The reverse map, used by `alias_main` to turn the invoked shim name back into a
# subcommand. Built from one table so the two can never drift.
ALIAS_TO_SUBCOMMAND: dict[str, str] = {
    flat: sub for sub, (_target, flat, _help) in DELEGATED_COMMANDS.items()
}

# Set to silence the deprecation notice explicitly.
SUPPRESS_DEPRECATION_ENV = "SPECFUSE_NO_DEPRECATION_WARNING"


def _deprecation_notice_enabled() -> bool:
    """Whether a flat command should print its replacement.

    Interactive use only, by default. The people who can act on the notice are
    reading a terminal; the flat commands are meanwhile invoked constantly by
    scaffold hooks and verification.yml, where a line per call is pure noise in
    somebody's CI log and cannot be acted on from there anyway. `specfuse doctor`
    is the deterministic report of what still needs migrating, so nothing is lost
    by staying quiet when nobody is watching.
    """
    if os.environ.get(SUPPRESS_DEPRECATION_ENV):
        return False
    return bool(getattr(sys.stderr, "isatty", lambda: False)())


def _delegate(target: str, argv: list[str], *, prog: str) -> int:
    """Run a component's console-script main with `argv`, as if it were invoked
    directly.

    Nine of the eleven component mains take no arguments and read `sys.argv`
    themselves, so passing argv is not an option — sys.argv is swapped for the
    duration and restored in a finally. argv[0] is set to `prog` ("specfuse run")
    so the component's own --help and error messages name the way the user
    actually invoked it.

    The import is deferred to call time: a component is a hard dependency, so a
    missing one is a broken install, and reporting it against the command the user
    typed beats an ImportError at CLI startup for every other command too.
    """
    module_name, _, func_name = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        print(f"specfuse: `{prog}` needs {module_name}, which is not importable "
              f"({exc}). The suite's components are hard dependencies — reinstall "
              f"with `pipx install --force specfuse` (or `uv tool install --force "
              f"specfuse`).", file=sys.stderr)
        return 1
    func = getattr(module, func_name)
    saved = sys.argv
    sys.argv = [prog, *argv]
    try:
        rc = func()
    finally:
        sys.argv = saved
    return 0 if rc is None else rc


def alias_main() -> int:
    """Entry point for every deprecated flat `specfuse-*` command.

    One function serves all eleven: the invoked name comes from `sys.argv[0]`, so
    the console-script table stays a single line per command and cannot drift from
    DELEGATED_COMMANDS. Prints the replacement once per invocation (each is its own
    process), interactively only — see `_deprecation_notice_enabled`.

    The notice is BEST-EFFORT, by construction. Each component also declares its
    own console script under the same flat name, and inside a single venv the last
    distribution installed wins the file — measured, that is installer-dependent
    (pip/pipx left `specfuse-loop` and `specfuse-lint` pointing straight at the
    driver; uv routed all eleven here). The command works identically either way,
    only the notice is skipped, so `specfuse doctor` reports migration status
    deterministically instead of relying on this path being taken.
    """
    # Both separators, not `Path(...).name`: that is platform-dependent, so a
    # Windows launcher path is one long "filename" when the same code is exercised
    # on POSIX (as the tests do) and the alias is never recognised.
    invoked = os.path.basename(sys.argv[0].replace("\\", "/"))
    if invoked.endswith(".exe"):        # Windows launcher
        invoked = invoked[:-4]
    subcommand = ALIAS_TO_SUBCOMMAND.get(invoked)
    if subcommand is None:
        print(f"specfuse: `{invoked}` is not a Specfuse command. Suite commands "
              f"are subcommands of `specfuse` — try `specfuse --help`.",
              file=sys.stderr)
        return 2
    if _deprecation_notice_enabled():
        print(f"specfuse: `{invoked}` is deprecated and will be removed in 1.0.0 "
              f"— use `specfuse {subcommand}` instead. "
              f"(set {SUPPRESS_DEPRECATION_ENV}=1 to silence)", file=sys.stderr)
    target, _flat, _help = DELEGATED_COMMANDS[subcommand]
    return _delegate(target, sys.argv[1:], prog=invoked)


def _component_versions() -> list[tuple[str, str]]:
    """(distribution, version) for each suite component, "not installed" when
    absent. Only the umbrella's version is advertised in the docs; this table is
    what makes a support question one command instead of four."""
    out: list[tuple[str, str]] = []
    for name in COMPONENTS:
        try:
            out.append((name, importlib.metadata.version(name)))
        except importlib.metadata.PackageNotFoundError:
            out.append((name, "not installed"))
    return out


def _release_key(version: str) -> tuple[int, ...] | None:
    """The numeric release segment as a comparable tuple, or None if unparsable.

    Deliberately not a full PEP 440 implementation: `packaging` is not a
    dependency of this package, and the only decision made here is whether to
    print one advisory line. Anything with a pre/post/dev suffix parses down to
    its release numbers, which is close enough to answer "is there something
    newer" and never wrong in a way that matters — the fallback is silence.
    """
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", version)
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def _latest_on_pypi(dist: str, *, timeout: float = 2.0) -> str | None:
    """The newest published version of `dist`, or None if it cannot be learned.

    The JSON API, not the simple index. #111 established that the two are
    independently eventually-consistent and that only the simple index decides
    whether pip can *resolve* — but the question here is not resolvability, it
    is "is the user behind", and the cost of a lagging answer is one delayed
    nudge rather than a failed release. The JSON API gives the answer in one
    request with no parsing of index HTML.

    Every failure returns None: no network, a proxy, PyPI down, a rate limit, a
    private index. An advisory must never become the reason a diagnostic command
    fails.
    """
    try:
        with urllib.request.urlopen(  # noqa: S310 — fixed https host, not user input
            f"https://pypi.org/pypi/{dist}/json", timeout=timeout
        ) as response:
            return json.load(response)["info"]["version"]
    except Exception:  # noqa: BLE001 — deliberately total; see below
        # Blind on purpose, not laziness. An enumerated list (URLError, OSError,
        # TimeoutError, JSONDecodeError, KeyError...) fails the one way that
        # matters: the type nobody predicted crashes `doctor` for a user whose
        # only sin was being behind a proxy. The advisory has no value worth an
        # exception, so every failure means "unknown", which means silence.
        return None


def outdated_components(
    *,
    installed: list[tuple[str, str]] | None = None,
    fetch: Callable[[str], str | None] | None = None,
) -> list[tuple[str, str, str]]:
    """`[(dist, installed, latest)]` for every component behind the index.

    A component that is not installed, whose latest cannot be learned, or whose
    version does not parse is skipped rather than guessed at. Equal or ahead is
    not reported — a maintainer running an unreleased local build should not be
    told to downgrade.
    """
    # Resolved at call time, not bound as a default, so `mock.patch` on the
    # module attribute is honored — same reason `_pip_install` resolves `runner`.
    fetch = fetch or _latest_on_pypi
    behind: list[tuple[str, str, str]] = []
    for dist, version in (installed if installed is not None else _component_versions()):
        if version == "not installed":
            continue
        latest = fetch(dist)
        if latest is None:
            continue
        have, newest = _release_key(version), _release_key(latest)
        if have is not None and newest is not None and have < newest:
            behind.append((dist, version, latest))
    return behind


def report_outdated_components(
    *,
    fetch: Callable[[str], str | None] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[tuple[str, str, str]]:
    """Advise when a component has moved. Returns what was reported.

    Nothing else in the suite notices this. Since #125 the components are hard
    dependencies with floors that are minimums, so a component release reaches
    users on their next upgrade and never prompts one — every path is pull. The
    nightly `component-compat` guard catches components that BREAK users, not
    components that merely moved.

    Advisory only: never changes the caller's exit code. Being a release behind
    is not a broken install, and `doctor` exits non-zero for things CI should
    gate on.
    """
    log = log or (lambda line: print(line, file=sys.stderr))
    behind = outdated_components(fetch=fetch)
    if not behind:
        return []
    log("specfuse: newer component releases are available:")
    width = max(len(dist) for dist, _, _ in behind)
    for dist, have, latest in behind:
        log(f"  {dist:<{width}}  {have} -> {latest}")
    log("specfuse: `specfuse upgrade` pulls them. Note that a plain "
        "`pip install -U specfuse` does NOT — see docs/releasing.md.")
    return behind


def version_report() -> str:
    """The `--version` text: umbrella version plus the resolved component table."""
    components = _component_versions()
    lines = [f"specfuse {__version__}"]
    width = max(len(name) for name, _ in components)
    for name, version in components:
        lines.append(f"  {name:<{width}}  {version}")
    return "\n".join(lines)


class _VersionAction(argparse.Action):
    """Print `version_report()` verbatim.

    NOT argparse's built-in `action="version"`: that routes the string through
    HelpFormatter, which re-wraps it to the terminal width and collapsed the
    component table into a ragged paragraph ("specfuse-\nauthoring 0.5.9").
    """

    def __init__(self, option_strings, dest, help=None):  # noqa: A002
        super().__init__(option_strings, dest, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        print(version_report())
        parser.exit()


def _pip_install(packages: list[str], *, upgrade: bool, runner=None) -> int:
    """Install/upgrade packages with the current interpreter's pip. `runner` is
    injectable for testing; resolved at call time (not bound as a default) so
    `mock.patch(cli.subprocess.run)` is honored. Returns the subprocess return code.

    An upgrade passes `--upgrade-strategy eager` to state the intent explicitly:
    every component moves to the newest version the floors allow.

    **The flag is load-bearing. Do not remove it.** An earlier version of this
    docstring recorded the opposite ("measured on pip 25, a plain
    `pip install --upgrade <pkg>` carries satisfied dependencies to the newest
    version anyway"). That does not hold on pip 26.1.2: with the umbrella already
    at its newest version and `specfuse-authoring>=0.5.6` satisfied by an
    installed 0.5.6, a plain `--upgrade` left it at 0.5.6 while 0.6.0 was on the
    index — twice, the second time on a clean venv. That is exactly what
    `--upgrade-strategy only-if-needed` is documented to do, and since #125 made
    the floors minimums rather than levers, a satisfied floor is the normal state
    of every component between umbrella releases. Without the flag, a plain-venv
    install stops receiving component releases entirely and says nothing.

    pipx and uv need no such flag — both re-resolve the environment (verified:
    `pipx upgrade specfuse` moved authoring 0.5.6 -> 0.6.0 while reporting the
    umbrella "already at latest version").
    """
    runner = runner or subprocess.run
    cmd = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        cmd += ["--upgrade", "--upgrade-strategy", "eager"]
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


def _installer_upgrade_command(installer: str, tool: str) -> list[str] | None:
    """The argv that upgrades this install, or None when the installer is not on
    PATH (installed via a different shell, a system package, …).

    Deliberately no extra flags. An earlier version passed
    `--pip-args=--upgrade-strategy=eager` to pipx, to state the intent that every
    component moves — but pipx 1.8+ can use **uv** as its install backend, and
    `uv pip` rejects that pip-only flag, so the upgrade failed outright:

        'uv pip install --python … --upgrade --upgrade-strategy=eager …' failed
        specfuse: pipx upgrade failed (exit 1).

    It was also unnecessary *here*: both installers do the right thing unaided —
    uv re-resolves a tool's whole environment, and pipx re-resolves the
    umbrella's dependency set, so each pulls a newer component with the umbrella
    version unchanged. That is specific to pipx/uv. Plain pip does NOT behave
    this way and still needs the eager flag `_pip_install` passes; see its
    docstring before concluding the flag is decorative there too.
    """
    exe = shutil.which(installer)
    if exe is None:
        return None
    if installer == "uv":
        return [exe, "tool", "upgrade", tool]
    return [exe, "upgrade", tool]


def _self_upgrade(runner=None) -> int:
    """Upgrade the installed suite, using whichever installer owns this
    environment. Returns a process-style rc (0 = upgraded, or cleanly skipped
    with advice).

    Previously this only ever ADVISED for pipx/uv installs — it detected the
    managed environment in order to skip, then printed the command for the user
    to copy. It has the detection; running the command is strictly better than
    describing it. A plain venv still goes through `python -m pip`, which is
    correct there and wrong for pipx (whose venv it owns, and which may ship no
    pip at all).
    """
    runner = runner or subprocess.run
    installer = _installer()
    if installer:
        cmd = _installer_upgrade_command(installer, "specfuse")
        if cmd is None:
            print(f"specfuse: this is a {installer}-managed install but `{installer}` "
                  f"is not on PATH. Upgrade the suite with:\n"
                  f"  {installer} {'tool ' if installer == 'uv' else ''}upgrade specfuse",
                  file=sys.stderr)
            return 0
        print(f"specfuse: upgrading the suite via {installer}...")
        proc = runner(cmd)
        rc = getattr(proc, "returncode", 0)
        if rc != 0:
            print(f"specfuse: {installer} upgrade failed (exit {rc}).", file=sys.stderr)
            return rc
        print("specfuse: suite upgraded (specfuse + " + ", ".join(COMPONENTS) + ").")
        return 0

    if importlib.util.find_spec("pip") is None:
        print(
            "specfuse: skipping automatic package upgrade (no pip in this "
            "environment). Upgrade the whole suite with:\n"
            "  uv tool upgrade specfuse              # if installed via uv\n"
            "  pipx upgrade specfuse                 # if installed via pipx\n"
            "  python3 -m pip install -U specfuse    # if installed in a venv",
            file=sys.stderr,
        )
        return 0
    # The umbrella alone: its components are hard dependencies, and the eager
    # strategy in _pip_install carries them up with it. Naming them here too
    # would only pin the upgrade to today's component list.
    rc = _pip_install(["specfuse"], upgrade=True, runner=runner)
    if rc != 0:
        print(f"specfuse: pip upgrade failed (exit {rc}).", file=sys.stderr)
    else:
        print("specfuse: suite upgraded (specfuse + "
              + ", ".join(COMPONENTS) + ").")
    return rc


def _venv_root() -> Path:
    """This environment's own root — `sys.prefix`, NOT a resolved sys.executable.

    In a pipx or uv-tool venv, `bin/python` is a symlink to the base interpreter,
    so `Path(sys.executable).resolve()` walks straight OUT of the venv (to
    /opt/homebrew/... or uv's managed cpython dir). Every caller that used it was
    therefore comparing against the wrong directory: `_managed_by_tool()` matched
    neither installer's path and reported "not a pipx/uv-managed install" on real
    pipx AND uv installs, so the whole shim check silently no-op'd. sys.prefix is
    the venv itself and follows no symlink.
    """
    return Path(sys.prefix)


def _venv_bin() -> Path:
    """The dir this environment puts its own console scripts in — resolved, since
    the shim comparison is against `shim.resolve()` and on macOS the two sides
    otherwise disagree over /tmp vs /private/tmp. Resolving the DIRECTORY is safe;
    it is resolving the python symlink that escaped the venv. `sysconfig` rather
    than a hardcoded "bin" so Windows' "Scripts" works."""
    return Path(sysconfig.get_path("scripts")).resolve()


def _shim_dir() -> Path:
    """The directory THIS install's console scripts are exposed in. pipx and uv
    both default to ~/.local/bin and both let the user move it, so the env vars
    come first.

    Which env var is asked first depends on the installer that owns this
    environment, not on a fixed order: a machine with both tools can have both
    PIPX_BIN_DIR and UV_TOOL_BIN_DIR exported, and a fixed
    PIPX_BIN_DIR-then-UV_TOOL_BIN_DIR order then pointed a uv install at pipx's bin
    dir — where every one of its commands is, correctly, someone else's. `doctor`
    reported all twelve as foreign.
    """
    installer = _installer()
    preferred = {"pipx": ("PIPX_BIN_DIR",), "uv": ("UV_TOOL_BIN_DIR",)}.get(
        installer, ("PIPX_BIN_DIR", "UV_TOOL_BIN_DIR"))
    for var in preferred:
        override = os.environ.get(var)
        if override:
            return Path(override).expanduser()
    return Path.home() / ".local" / "bin"


def _console_scripts() -> dict[str, str]:
    """Map console-script name -> distribution name for every SUITE script
    installed in this environment.

    Read off `distributions()` rather than `entry_points(group=...)` because
    `EntryPoint.dist` — the only way to attribute a script back to its package —
    is not available on 3.10/3.11, and requires-python allows those.

    Filtered to SUITE_DISTS: a transitive dependency's console script is not the
    suite's to police, and the orchestrator brings one (jsonschema).
    """
    scripts: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if name is None or name not in SUITE_DISTS:
            continue
        for ep in dist.entry_points:
            if ep.group == "console_scripts":
                scripts[ep.name] = name
    return scripts


def diagnose_shims(*, shim_dir: Path | None = None,
                   venv_bin: Path | None = None) -> list[tuple[str, str, str, str]]:
    """Find suite commands whose PATH shim does not lead back to this venv.

    The failure this catches: every suite command is also a console script of its
    own standalone PyPI package, so an umbrella install and a standalone
    `pipx install specfuse-authoring` compete for one name in ~/.local/bin.
    Whichever runs second loses — pipx refuses to overwrite a shim another venv
    owns ("File exists at ... and points to ... Not modifying") and warns once on
    stderr, so the command silently keeps resolving to the OTHER install and
    upgrading the package you think you are using changes nothing about what
    runs. Shims are also left dangling by machines that ran the retired
    `specfuse[all]` extras path, whose venv no longer provides those scripts.

    Since 0.10.0 the umbrella declares EVERY suite command as its own entry
    point, so an unlinked one is a broken install rather than the expected
    consequence of omitting --include-deps. The flat commands are deprecated
    aliases now; when 1.0.0 drops them this detector goes with them, because a
    single `specfuse` shim cannot collide with anything.

    Returns (command, problem, fix, kind) tuples, kind one of "unlinked",
    "stale", "foreign", "orphan"; empty means every script this venv provides
    resolves to this venv. Non-symlink shims are skipped: pipx uses symlinks on
    POSIX, and a Windows launcher .exe cannot be attributed by reading the
    filesystem.
    """
    shim_dir = shim_dir or _shim_dir()
    # Resolve: the comparison below is against shim.resolve(), and on macOS the
    # two sides disagree over /tmp vs /private/tmp (and over any symlinked venv
    # path) unless both are fully resolved — which would report every healthy
    # shim as foreign. `_venv_bin()` (sysconfig) rather than sys.executable's
    # parent: the latter, resolved, points at the BASE interpreter's bin in every
    # pipx/uv venv, where none of this venv's scripts exist — so every command was
    # skipped by the exists() guard below and nothing was ever reported.
    venv_bin = _venv_bin() if venv_bin is None else venv_bin.resolve()
    problems: list[tuple[str, str, str, str]] = []
    reinstall = "pipx install --force specfuse  # or: uv tool install --force specfuse"
    for command, dist in sorted(_console_scripts().items()):
        # Only scripts this venv actually ships. A name this environment does not
        # provide belongs to some other package and is not ours to police.
        if not (venv_bin / command).exists():
            continue
        shim = shim_dir / command
        if not shim.is_symlink() and not shim.exists():
            problems.append((
                command,
                f"provided by {dist} in this venv but not on PATH ({shim_dir})",
                reinstall,
                "unlinked",
            ))
            continue
        if not shim.is_symlink():
            continue
        if not shim.exists():
            problems.append((
                command,
                f"stale shim: {shim} -> {os.readlink(shim)} (target is gone)",
                f"rm {shim} && {reinstall}",
                "stale",
            ))
            continue
        owner = shim.resolve().parent
        if owner != venv_bin:
            problems.append((
                command,
                f"shim points at another install: {shim} -> {shim.resolve()}",
                f"the umbrella ships this command — `pipx uninstall {dist}` to "
                f"drop the competing standalone install, then: {reinstall}",
                "foreign",
            ))

    # Second pass: dangling shims for suite commands this venv no longer provides.
    # The loop above cannot see them — its exists() guard skips any command the
    # venv does not ship. That is exactly the wreckage the retired extras path
    # leaves behind (a `pipx install --force` without --include-deps drops the
    # orchestrator's five scripts from the venv and abandons their shims), and
    # what dropping the flat aliases in 1.0.0 will leave behind next.
    provided = set(_console_scripts())
    for command in sorted(_known_suite_commands() - provided):
        shim = shim_dir / command
        if shim.is_symlink() and not shim.exists():
            problems.append((
                command,
                f"orphaned shim: {shim} -> {os.readlink(shim)} (this install does "
                f"not provide `{command}`)",
                f"rm {shim}  # or: specfuse doctor --fix",
                "orphan",
            ))
    return problems


def _known_suite_commands() -> set[str]:
    """Every command name the suite has ever put on PATH: `specfuse` itself plus
    the flat aliases. Used to recognise an orphaned shim as ours to clean up
    rather than an unrelated program's."""
    return {"specfuse", *ALIAS_TO_SUBCOMMAND}


def _installer() -> str | None:
    """Which tool installer owns this environment: "pipx", "uv", or None.

    None means a plain venv or a system pip install, which puts its scripts on
    PATH directly — so there are no shims to check, and `python -m pip` is the
    right way to upgrade.

    Both installers let the user relocate their venv root, and the default-path
    substrings below then match nothing, so PIPX_HOME/UV_TOOL_DIR are honored
    first — the same way `_shim_dir()` honors PIPX_BIN_DIR/UV_TOOL_BIN_DIR.

    Uses `_venv_root()`; see there for why a resolved sys.executable cannot be
    used for this test.
    """
    where = _venv_root().resolve()
    for var, installer in (("PIPX_HOME", "pipx"), ("UV_TOOL_DIR", "uv")):
        root = os.environ.get(var)
        if root and where.is_relative_to(Path(root).expanduser().resolve()):
            return installer
    posix = where.as_posix()
    if "/pipx/venvs/" in posix:
        return "pipx"
    if "/uv/tools/" in posix:
        return "uv"
    return None


def _managed_by_tool() -> bool:
    """True when a PATH shim is expected to exist at all — i.e. pipx or uv owns
    this environment."""
    return _installer() is not None


def _warn_about_shims() -> None:
    """Advisory half of `specfuse doctor`, run at the end of an upgrade: report
    shim problems without failing the command that found them.

    All three kinds warn. "unlinked" used to be filtered out as expected noise —
    an install without --include-deps legitimately left the optional commands off
    PATH. Since 0.10.0 the umbrella declares every suite command as its own entry
    point, so a suite command missing from PATH is a broken install, in the same
    class as a stale or foreign shim: an upgrade is exactly when a wrongly-owned
    or missing shim turns into a silent wrong-version bug.
    """
    if not _managed_by_tool():
        return
    for command, problem, fix, _kind in diagnose_shims():
        print(f"specfuse: warning: `{command}` — {problem}\n  fix: {fix}",
              file=sys.stderr)


# The shim kinds `--fix` may delete. Both are DANGLING symlinks — the target does
# not exist, so the shim cannot run anything and removing it destroys nothing.
# "foreign" is deliberately excluded: that shim works, it just belongs to another
# install, and deleting another install's property is the user's call, not ours.
_REMOVABLE_KINDS = ("stale", "orphan")


def _remove_dead_shims(problems, *, shim_dir: Path | None = None) -> list[str]:
    """Delete the dangling shims in `problems`, returning the commands removed.

    Re-checks `is_symlink() and not exists()` immediately before unlinking rather
    than trusting the diagnosis: the two are separated by however long the user
    spent reading the report, and this deletes files.
    """
    shim_dir = shim_dir or _shim_dir()
    removed: list[str] = []
    for command, _problem, _fix, kind in problems:
        if kind not in _REMOVABLE_KINDS:
            continue
        shim = shim_dir / command
        if not (shim.is_symlink() and not shim.exists()):
            continue
        try:
            shim.unlink()
        except OSError as exc:
            print(f"specfuse: could not remove {shim}: {exc}", file=sys.stderr)
            continue
        removed.append(command)
        print(f"specfuse: removed dead shim {shim}")
    return removed


def deprecated_shims_present(shim_dir: Path | None = None) -> list[str]:
    """The flat `specfuse-*` commands still on PATH, sorted.

    Migration status, reported deterministically. The per-invocation notice in
    `alias_main` cannot be relied on — a component's own console script may win the
    name inside the venv, and which one does is installer-dependent (see there).
    Listing what is still installed does not care who provides it.
    """
    shim_dir = shim_dir or _shim_dir()
    return sorted(flat for flat in ALIAS_TO_SUBCOMMAND
                  if (shim_dir / flat).exists() or (shim_dir / flat).is_symlink())


def _report_deprecated(shim_dir: Path | None = None) -> None:
    """Advisory only — never changes an exit code. These commands still work."""
    present = deprecated_shims_present(shim_dir)
    if not present:
        return
    print(f"specfuse: {len(present)} deprecated command(s) still on PATH; they are "
          f"removed in 1.0.0. Migrate to the subcommand form:")
    for flat in present:
        print(f"  {flat} -> specfuse {ALIAS_TO_SUBCOMMAND[flat]}")


def cmd_doctor(args: argparse.Namespace, *, runner=None) -> int:
    """Report suite commands whose PATH shim is missing, stale, orphaned, or owned
    by a different install. Exits 1 when anything is still wrong so CI can gate on
    it.

    `--fix` deletes the dangling shims first (see _REMOVABLE_KINDS) and re-runs the
    diagnosis, so the exit code reflects what is left, not what was found.

    The component-staleness advisory runs BEFORE the not-tool-managed early
    return, deliberately. That branch is the plain-venv install — precisely the
    one where a plain `pip install -U specfuse` silently leaves components behind
    (see `_pip_install`), so it is the environment that most needs telling. It is
    advisory and never affects the exit code.
    """
    if not getattr(args, "no_network", False):
        report_outdated_components()

    if not _managed_by_tool():
        print("specfuse: not a pipx/uv-managed install — this environment puts "
              "its scripts on PATH directly, so there are no shims to check.")
        return 0
    problems = diagnose_shims()

    if getattr(args, "fix", False) and problems:
        removed = _remove_dead_shims(problems)
        if removed:
            # Re-diagnose so the exit code reflects what is LEFT. Removing a dead
            # shim for a command this venv still provides turns a "stale" finding
            # into an "unlinked" one — the garbage is gone, but nothing has put the
            # command back on PATH, and only a reinstall can.
            print(f"specfuse: removed {len(removed)} dead shim(s). Reinstall to put "
                  f"any command that lost its shim back on PATH: "
                  f"pipx install --force specfuse")
            problems = diagnose_shims()
        else:
            print("specfuse: nothing to remove — no dead shims among the findings.")

    if not problems:
        print(f"specfuse: all suite commands resolve to this install "
              f"({_venv_bin()}).")
        _report_deprecated()
        return 0
    print(f"specfuse: {len(problems)} command(s) do not resolve to this install:",
          file=sys.stderr)
    for command, problem, fix, _kind in problems:
        print(f"  {command}: {problem}\n    fix: {fix}", file=sys.stderr)
    if not getattr(args, "fix", False) and any(
            kind in _REMOVABLE_KINDS for *_rest, kind in problems):
        print("specfuse: `specfuse doctor --fix` removes the dead shims above.",
              file=sys.stderr)
    _report_deprecated()
    return 1


def _enable_plugins(target: Path, names: list[str], *, dry_run: bool) -> list[str]:
    """Set `enabledPlugins["<plugin>@specfuse"] = true` in .claude/settings.json for
    each requested plugin, returning the keys changed.

    The scaffold already asserts the marketplace entry and the `specfuse` plugin;
    this only adds the opt-in ones, so wiring a repo for a chosen toolset is a flag
    rather than a hand-edit. Every other settings key is preserved.
    """
    keys = [PLUGIN_KEYS[name] for name in names]
    settings_path = target / ".claude" / "settings.json"
    data: dict = {}
    if settings_path.exists():
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    plugins: dict = data.setdefault("enabledPlugins", {})
    changed = [key for key in keys if plugins.get(key) is not True]
    if not changed or dry_run:
        return changed
    for key in changed:
        plugins[key] = True
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    return changed


def _provision_methodology(target: Path, *, dry_run: bool) -> list[str]:
    """Lay the core substrate into `.specfuse/methodology/`, reporting what landed.

    Failure here is reported and swallowed rather than raised: the substrate is
    additive to the scaffold, and a repo that got its `.specfuse/` but not its
    methodology is in a worse state if the command also exits non-zero and leaves
    the caller thinking nothing was written. The message names the remedy.
    """
    try:
        written = methodology.provision(target, dry_run=dry_run)
    except methodology.MethodologyMissingError as exc:
        print(f"specfuse: {exc}", file=sys.stderr)
        print("specfuse: reinstall the package to restore it "
              "(`specfuse upgrade`, or pipx/uv install --force specfuse).",
              file=sys.stderr)
        return []
    prefix = "[dry-run] would provision" if dry_run else "provisioned"
    print(f"specfuse: {prefix} {len(written)} methodology file(s) under "
          f"{target}/{methodology.INSTALL_SUBPATH.as_posix()}/.")
    return written


def cmd_init(args: argparse.Namespace, *, runner=None) -> int:
    """Scaffold a repo's .specfuse/ + .claude wiring — or upgrade it if a scaffold
    is already there.

    Idempotent on purpose. This used to refuse on an existing `.specfuse/` and tell
    the user to run `upgrade` instead, which made them answer a question the tool
    can answer itself by reading `.specfuse/VERSION`. `init` and `upgrade` are now
    the same command under two names, so neither is ever the wrong one to run.
    """
    target = Path(args.target)
    if not target.is_dir():
        print(f"specfuse: target '{target}' is not a directory.", file=sys.stderr)
        return 2

    if (target / ".specfuse").exists():
        print(f"specfuse: {target}/.specfuse already exists — upgrading it.")
        return cmd_upgrade(args, runner=runner)

    ci_check = getattr(args, "ci_check", None)
    plugins = getattr(args, "plugins", None) or []

    if getattr(args, "dry_run", False):
        # Preview without touching the target: scaffold into a throwaway dir and
        # report the real written set.
        with tempfile.TemporaryDirectory() as tmp:
            written = scaffold.init(tmp, ci_check=ci_check)
        print(f"specfuse: [dry-run] would scaffold {len(written)} file(s) under "
              f"{target}/.specfuse/:")
        for rel in written:
            print(f"  .specfuse/{rel}")
        _provision_methodology(target, dry_run=True)
        for name in plugins:
            print(f"  [dry-run] would enable plugin {PLUGIN_KEYS[name]}")
        return 0

    written = scaffold.init(target, ci_check=ci_check)
    print(f"specfuse: scaffolded {len(written)} file(s) under {target}/.specfuse/ "
          f"(+ .claude wiring).")
    _provision_methodology(target, dry_run=False)
    for key in _enable_plugins(target, plugins, dry_run=False):
        print(f"specfuse: enabled plugin {key} in .claude/settings.json.")
    print(PLUGIN_UPDATE_HINT)
    return 0


def cmd_upgrade(args: argparse.Namespace, *, runner=None) -> int:
    """Overlay the versioned scaffold onto an existing .specfuse/ (never downgrades),
    then upgrade the suite (umbrella + components) and point at /plugin update.

    Scaffolds from scratch when there is nothing to overlay — `init` and `upgrade`
    are one idempotent operation under two names.
    """
    target = Path(args.target)
    if not target.is_dir():
        print(f"specfuse: target '{target}' is not a directory.", file=sys.stderr)
        return 2
    if not (target / ".specfuse").exists():
        print(f"specfuse: {target}/.specfuse does not exist yet — scaffolding it.")
        return cmd_init(args, runner=runner)
    ci_check = getattr(args, "ci_check", None)
    plugins = getattr(args, "plugins", None) or []
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
              f"{target}/.specfuse/ (no package upgrade in dry-run):")
        for rel in written:
            print(f"  .specfuse/{rel}")
        _provision_methodology(target, dry_run=True)
        for key in _enable_plugins(target, plugins, dry_run=True):
            print(f"  [dry-run] would enable plugin {key}")
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
    # Always, even when the loop scaffold was already current: the two move on
    # independent release cadences, so a repo whose scaffold has not changed can
    # still be behind on the substrate.
    _provision_methodology(target, dry_run=False)
    for key in _enable_plugins(target, plugins, dry_run=False):
        print(f"specfuse: enabled plugin {key} in .claude/settings.json.")

    if getattr(args, "no_self_upgrade", False):
        print("specfuse: skipping the package upgrade (--no-self-upgrade).")
        rc = 0
    else:
        rc = _self_upgrade(runner)
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
    # The component table, not a bare version string: the umbrella's version is
    # the only number advertised in the docs, so `--version` has to be where the
    # per-component versions are answerable.
    ap.add_argument("--version", action=_VersionAction,
                    help="show the umbrella version and the component table")
    sub = ap.add_subparsers(dest="command", required=True)

    def _scaffold_options(parser: argparse.ArgumentParser) -> None:
        """init and upgrade are the same operation under two names, so they take
        the same options — including `target`, which defaults to the cwd because
        the answer is almost always "this repo"."""
        parser.add_argument("target", nargs="?", default=".",
                            help="path to the repo (default: the current directory)")
        parser.add_argument("--dry-run", action="store_true",
                            help="preview; write nothing, upgrade nothing")
        parser.add_argument("--ci-check", default=None,
                            help="path to a CI check script to delegate verification.yml to")
        parser.add_argument("--plugins", default=None, type=_parse_plugins,
                            metavar="NAME[,NAME]",
                            help="also enable these plugins in .claude/settings.json "
                                 f"({', '.join(n for n in PLUGIN_KEYS if n != 'specfuse')})")
        parser.add_argument("--no-self-upgrade", action="store_true",
                            help="scaffold only; do not upgrade the installed packages")

    ini = sub.add_parser("init",
                         help="scaffold a repo's .specfuse/ + .claude (upgrades an existing one)")
    _scaffold_options(ini)
    ini.set_defaults(func=cmd_init)

    up = sub.add_parser("upgrade",
                        help="overlay the scaffold, then upgrade the suite + /plugin update")
    _scaffold_options(up)
    up.set_defaults(func=cmd_upgrade)

    doc = sub.add_parser("doctor", help="check that suite commands on PATH resolve here")
    doc.add_argument("--fix", action="store_true",
                     help="delete shims that point at nothing (leaves other installs alone)")
    # The staleness advisory already fails soft on any network error, so this is
    # for callers that want no outbound request attempted at all — an air-gapped
    # build, or CI that gates on `doctor` and should not depend on pypi.org.
    doc.add_argument("--no-network", action="store_true",
                     help="skip the check for newer component releases on PyPI")
    doc.set_defaults(func=cmd_doctor)

    # Registered so they appear in `specfuse --help` and in argparse's
    # invalid-choice list. They are never PARSED: main() intercepts them first and
    # hands the raw argv to the component, because argparse would otherwise try to
    # interpret the component's own flags. REMAINDER keeps them working as a
    # fallback if that interception is ever bypassed.
    for name, (target, flat, help_text) in DELEGATED_COMMANDS.items():
        delegated = sub.add_parser(name, help=f"{help_text} (was `{flat}`)",
                                   add_help=False)
        delegated.add_argument("rest", nargs=argparse.REMAINDER)
        delegated.set_defaults(
            func=lambda a, *, _t=target, _n=name, **kw: _delegate(
                _t, a.rest, prog=f"specfuse {_n}"))

    return ap


def _parse_plugins(value: str) -> list[str]:
    """`--plugins authoring,orchestrator` -> ["authoring", "orchestrator"]."""
    names = [part.strip() for part in value.split(",") if part.strip()]
    unknown = [name for name in names if name not in PLUGIN_KEYS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown plugin(s): {', '.join(unknown)}. "
            f"Choose from: {', '.join(PLUGIN_KEYS)}")
    return names


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Delegated subcommands are dispatched BEFORE argparse sees them: the
    # component owns everything after the subcommand name, and letting argparse
    # parse it would mean this CLI reinterpreting flags it knows nothing about
    # (`specfuse lint --help` must print the linter's help, not ours).
    if argv and argv[0] in DELEGATED_COMMANDS:
        target, _flat, _help = DELEGATED_COMMANDS[argv[0]]
        return _delegate(target, argv[1:], prog=f"specfuse {argv[0]}")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
