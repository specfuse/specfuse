#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""Which suite components a repo is actually wired for, and how to overlay each.

`specfuse init` / `specfuse upgrade` used to be loop-shaped: whatever the target
repo was, they ran `specfuse.loop.scaffold` on it. That is correct for a
component repo running the gate-cycle driver and wrong everywhere else — an
authoring (specs) repo that ran `specfuse upgrade` to pick up a newer kit got a
whole driver scaffold dropped into its `.specfuse/`, complete with the driver's
rules, templates and verification workflow, none of which it runs.

The suite has three per-repo scaffolds, each with its own upgrader:

  loop          `specfuse.loop.scaffold`         .specfuse/ (the root itself)
  authoring     `specfuse.authoring.scaffold`    .specfuse/authoring/
  orchestrator  `specfuse.orchestrator.init`     .specfuse/rules|issue-templates,
                                                 .specfuse/templates.yaml, CI

They compose: the ownership manifest's one-upgrader-per-install-path invariant is
what lets all three overlay the same repo without fighting. The published packages
have broken that invariant, so `find_collisions` checks it instead of trusting it. So the question a
repo answers is not "which one am I" but "which ones am I", and this module
answers it by looking for each upgrader's own footprint rather than assuming.

Detection is filesystem-only and side-effect free — the same read an upgrader
would do first anyway. A repo with none of the footprints is a fresh one; the
caller decides what a fresh repo gets (`specfuse init` defaults to the loop,
which is the historical behaviour and the common case).
"""

from __future__ import annotations

import hashlib
import io
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

LOOP = "loop"
AUTHORING = "authoring"
ORCHESTRATOR = "orchestrator"

# Install order, and the order every report lists them in. The loop goes first
# because its scaffold owns the `.specfuse/` root the other two overlay into —
# an authoring or orchestrator overlay laid down first would still be there
# afterwards, but the loop's own `.claude` wiring is what the others extend.
ORDER: tuple[str, ...] = (LOOP, AUTHORING, ORCHESTRATOR)

# The per-component footprint. ANY of a component's entries matching means that
# component is installed. An entry is either one repo-relative path (a glob is
# allowed) or a tuple of them, which matches only when ALL of its paths exist —
# for the shapes no single path identifies on its own.
#
# Each entry names something only that upgrader produces:
#
#  * loop — `.specfuse/VERSION` and `.specfuse/.scaffold-manifest` are the
#    modern stamp; `templates/` and `scripts/` are listed for the legacy
#    `init.sh` trees that predate the stamp, which would otherwise read as
#    uninstalled and get re-inited.
#  * authoring — `.specfuse/authoring/` is the kit overlay. The `api/specs` +
#    `<project>-project.json` pair is the PROJECT skeleton, and is what a
#    pre-overlay project (created before the kit moved under `.specfuse/`) has
#    instead; neither half identifies an authoring repo alone, both together do.
#  * orchestrator — `templates.yaml` (a FILE; the loop's `templates/` is a
#    directory, so the two never collide), `issue-templates/`, the merge-watcher
#    workflow, and the per-role config dirs its `.claude` wiring reads.
#    `.specfuse/rules/` is deliberately NOT here: the manifest splits that
#    directory between three upgraders, so its presence proves nothing about
#    which of them wrote it.
_FOOTPRINTS: dict[str, tuple[object, ...]] = {
    LOOP: (
        ".specfuse/VERSION",
        ".specfuse/.scaffold-manifest",
        ".specfuse/templates",
        ".specfuse/scripts",
    ),
    AUTHORING: (
        ".specfuse/authoring",
        ("api/specs", "*-project.json"),
    ),
    ORCHESTRATOR: (
        ".specfuse/templates.yaml",
        ".specfuse/issue-templates",
        ".github/workflows/merge-watcher.yml",
        ".specfuse/agents/component",
        ".specfuse/agents/specs",
    ),
}

# The orchestrator installs per repo KIND; `.specfuse/agents/<kind>/` is where
# its `.claude` wiring puts that repo's role config, so the directory that
# exists names the kind. Component is the default — it is the kind the ownership
# manifest actually ships files for.
_ORCHESTRATOR_KINDS = ("specs", "component")


# Human-facing names for the report line.
LABELS = {
    LOOP: "loop (the gate-cycle driver)",
    AUTHORING: "authoring (the spec kit)",
    ORCHESTRATOR: "orchestrator (the multi-repo substrate)",
}


def _matches(root: Path, entry: object) -> bool:
    """Whether one footprint entry matches: all of a tuple, any of a glob."""
    if isinstance(entry, tuple):
        return all(_matches(root, part) for part in entry)
    rel = str(entry)
    if "*" in rel:
        return any(root.glob(rel))
    return (root / rel).exists()


def detect(target: str | Path) -> list[str]:
    """Return the components installed in *target*, in ORDER. [] on a fresh repo."""
    root = Path(target)
    return [name for name in ORDER
            if any(_matches(root, entry) for entry in _FOOTPRINTS[name])]


def footprint(target: str | Path, name: str) -> list[str]:
    """The entries that made `detect` report *name* — used to explain the verdict."""
    root = Path(target)
    return [str(entry) for entry in _FOOTPRINTS[name] if _matches(root, entry)]


def orchestrator_kind(target: str | Path) -> str:
    """Which repo kind the orchestrator installs into *target* as."""
    root = Path(target)
    for kind in _ORCHESTRATOR_KINDS:
        if (root / ".specfuse" / "agents" / kind).exists():
            return kind
    return "component"


# --------------------------------------------------------------------------- #
# Per-component overlays.
#
# Each returns a process exit code and does its own reporting, because the three
# upgraders genuinely report different things (a written-file list, a version
# transition, an install log) and flattening them into one shape would mean
# discarding two of them. Imports are deferred: a loop-only repo should not pay
# for pyyaml and the orchestrator's substrate just to be scaffolded.
# --------------------------------------------------------------------------- #


def upgrade_authoring(target: Path, *, dry_run: bool) -> int:
    """Overlay the authoring kit into *target* (`.specfuse/authoring/` + scripts/).

    This is the kit-content overlay only. Creating a NEW authoring project — its
    `api/` tree, CLAUDE.md and project file — stays `specfuse authoring init`,
    which needs a project name/token/domain this command has no way to ask for.
    Running it on a repo with no kit yet is still meaningful: it delivers the
    handbooks, samples and schemas and stamps the manifest, so the repo becomes
    upgradeable from then on.
    """
    from specfuse.authoring import bootstrap

    try:
        return bootstrap.upgrade(target, dry_run=dry_run)
    except SystemExit as exc:
        # bootstrap.upgrade sys.exit()s on a downgrade refusal or missing kit
        # content. Inside the umbrella that would take the whole command down
        # mid-way through a multi-component overlay, skipping the components
        # after it; turn it back into a return code the caller can weigh.
        code = exc.code
        if isinstance(code, str):
            print(f"specfuse: {code}", file=sys.stderr)
            return 1
        return int(code or 0)


def upgrade_orchestrator(target: Path, *, dry_run: bool, sync_labels: bool = True,
                         kind: str | None = None) -> int:
    """Overlay the orchestrator's frozen substrate into *target*.

    The repo kind comes from `orchestrator_kind` — a specs repo and a component
    repo take different slices of the ownership manifest, and installing one as
    the other is the same class of wrong assumption this module exists to remove.

    `upgrade=True` always: the umbrella only calls this for a repo that already
    has the substrate, or for one that explicitly asked for it via
    `--components`, and in both cases overlay-in-place is the intent. Init-mode's
    refuse-if-present guard exists for the standalone `python -m
    specfuse.orchestrator.init` entry point, where the caller may not know.

    `sync_labels=False` strips the manifest's label list, which is the only part
    of the install that leaves the machine (`gh label create` against the
    target's origin remote).

    `kind` defaults to the one *target* has. The collision check passes the real
    repo's kind while installing into an empty directory, which on its own would
    always read as a component repo.
    """
    import yaml
    from specfuse.orchestrator import init as orchestrator_init

    doc = yaml.safe_load(orchestrator_init.MANIFEST.read_text(encoding="utf-8"))
    if not sync_labels:
        doc = {**doc, "labels": []}
    orchestrator_init.install_into(kind or orchestrator_kind(target), target.resolve(),
                                   doc, True, dry_run)
    return 0


# --------------------------------------------------------------------------- #
# Collision guard.
#
# "They compose" rests on every install path having ONE writer, and nothing used
# to check it. Where two writers ship the same path they run in turn and the last
# one's copy is what lands — silently, in the run, in --dry-run, and in
# `.scaffold-manifest`, which keeps recording the first writer's hash. That is how
# the orchestrator's stale forks of four core-owned rules reached repos that run
# both it and the loop, and read as the loop's rules going backwards
# (specfuse/specfuse#176).
#
# The check asks each writer what it lays down by running it for real into its
# own empty temp dir: the same entry points the overlays use, so no component's
# layout is restated here, and a component that moves a file is measured where
# it moved it. The target is never touched.
# --------------------------------------------------------------------------- #

# The umbrella's own writer: core's substrate, provisioned after every component.
METHODOLOGY = "methodology"

# Files each writer EDITS rather than replaces — each merges its own block into
# whatever is already there. Their empty-dir payloads always differ, by design,
# so comparing them would warn on every run and bury the collisions that matter.
MERGED_PATHS = frozenset({".claude/CLAUDE.md", ".claude/settings.json", ".gitignore"})


@dataclass(frozen=True)
class Collision:
    """A path more than one writer ships: each writer and its sha256, in write order."""

    path: str
    writers: tuple[tuple[str, str], ...]

    @property
    def differs(self) -> bool:
        return len({sha for _, sha in self.writers}) > 1

    @property
    def lands(self) -> str:
        """The writer whose copy ends up on disk — the last one to write it."""
        return self.writers[-1][0]


def _writer(name: str, kind: str) -> Callable[[Path], object]:
    """The install entry point for one writer, aimed at whatever root it is given."""
    if name == LOOP:
        def write_loop(root: Path) -> object:
            from specfuse.loop import scaffold
            return scaffold.init(root, no_labels=True)
        return write_loop
    if name == AUTHORING:
        return lambda root: upgrade_authoring(root, dry_run=False)
    if name == ORCHESTRATOR:
        return lambda root: upgrade_orchestrator(root, dry_run=False,
                                                 sync_labels=False, kind=kind)
    from specfuse import methodology
    return methodology.provision


def payloads(target: str | Path, selected: list[str]
             ) -> tuple[dict[str, dict[str, str]], list[tuple[str, str]]]:
    """What each writer lays down, as `{writer: {repo-relative path: sha256}}`.

    Writers come in write order: the selected components in ORDER, then core's
    methodology, which the umbrella provisions last. A writer that cannot install
    into an empty directory is returned in the second list, with its error,
    rather than raised — the check is advisory and must not be what stops an
    upgrade.
    """
    kind = orchestrator_kind(target)
    found: dict[str, dict[str, str]] = {}
    failed: list[tuple[str, str]] = []
    for name in [*(n for n in ORDER if n in selected), METHODOLOGY]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result = _writer(name, kind)(root)
            # Blind on purpose: whatever a component raises while installing into
            # a scratch dir, the answer is "not measured", never a failed upgrade.
            except (Exception, SystemExit) as exc:  # noqa: BLE001
                failed.append((name, f"{type(exc).__name__}: {exc}"))
                continue
            if isinstance(result, int) and result != 0:
                failed.append((name, f"exited {result}"))
                continue
            found[name] = {
                p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file() and not p.is_symlink()}
    return found, failed


def find_collisions(payloads: dict[str, dict[str, str]]) -> list[Collision]:
    """Every path more than one writer ships, MERGED_PATHS aside, sorted by path."""
    writers: dict[str, list[tuple[str, str]]] = {}
    for name, files in payloads.items():
        for path, sha in files.items():
            if path not in MERGED_PATHS:
                writers.setdefault(path, []).append((name, sha))
    return [Collision(path, tuple(ws)) for path, ws in sorted(writers.items())
            if len(ws) > 1]
