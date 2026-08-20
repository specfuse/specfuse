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
what lets all three overlay the same repo without fighting. So the question a
repo answers is not "which one am I" but "which ones am I", and this module
answers it by looking for each upgrader's own footprint rather than assuming.

Detection is filesystem-only and side-effect free — the same read an upgrader
would do first anyway. A repo with none of the footprints is a fresh one; the
caller decides what a fresh repo gets (`specfuse init` defaults to the loop,
which is the historical behaviour and the common case).
"""

from __future__ import annotations

import sys
from pathlib import Path

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


def upgrade_orchestrator(target: Path, *, dry_run: bool, sync_labels: bool = True) -> int:
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
    """
    import yaml
    from specfuse.orchestrator import init as orchestrator_init

    doc = yaml.safe_load(orchestrator_init.MANIFEST.read_text(encoding="utf-8"))
    if not sync_labels:
        doc = {**doc, "labels": []}
    orchestrator_init.install_into(orchestrator_kind(target), target.resolve(),
                                   doc, True, dry_run)
    return 0
