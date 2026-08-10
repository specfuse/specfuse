#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""Provision the core methodology substrate from the installed package into a repo.

The umbrella owns `methodology/` and, as of the in-tree build backend, ships it —
so core is now both the author and the distributor of its own contracts. That
combination is the point. Before this, `methodology/` shipped nowhere: consumers
obtained it by copying out of git, which is how core's event schema came to sit two
releases behind the orchestrator's while claiming to be canonical (#135), and why
the one working authoring deployment resolved its contracts through a **sibling
checkout** of the orchestrator.

The decision this implements (`decision-authoring-execution-boundary.md`,
follow-up #3) requires the substrate to ship from core so that neither plane
imports the other. Shipping it from any component would relocate the inversion
rather than remove it: the authoring plane would depend on the loop for contracts
the loop does not own.

**Filesystem, not import.** The consumers are agent skills that read files, and the
components are dependencies of the umbrella — a component importing the umbrella
would be a cycle. Provisioning into the repo sidesteps that entirely, and gives the
skills a stable path to cite instead of the unqualified `shared/rules/...` that
only ever resolved inside an orchestrator checkout.

**Its own slot.** Files land in `.specfuse/methodology/`, not in `.specfuse/rules/`
or `.specfuse/schemas/`, which the loop's scaffold writes. The ownership manifest's
one-upgrader invariant is that every `(target, install path)` pair has exactly one
writer; a separate slot keeps this upgrader and `loop-init` from fighting, and lets
the loop's copies be retired later without a flag day.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# The directory the build mirrors `methodology/` into. See _build/backend.py.
MIRROR_DIRNAME = "_methodology"

# Where it lands in a target repo. Deliberately distinct from the loop scaffold's
# .specfuse/rules/ and .specfuse/schemas/ — see the module docstring.
INSTALL_SUBPATH = Path(".specfuse") / "methodology"

# Which subtrees are provisioned into a repo. The wheel carries the WHOLE
# substrate; only these are laid down.
#
# The machine contract ships; the prose does not, yet. `rules/` and `schemas/` are
# what consumers actually cite — the authoring skills reference
# `shared/rules/...` and `shared/schemas/...` and never the prose — and every
# file in them is either byte-identical to the loop's scaffold copy or absent
# from it, so provisioning them adds no contradiction.
#
# `glossary.md`, `methodology.md` and `overview.md` are held back because the loop
# scaffold ships its own `.specfuse/docs/` versions that have genuinely diverged,
# and not as stale copies:
#
#   * glossary.md   — a DIFFERENT document. Core's is a cross-surface unit
#     reference; the loop's is onboarding prose for loop users. Both legitimate.
#   * methodology.md — diverged in both directions. Core is ahead on the roadmap
#     status vocabulary (the blocked/deferred split, #117); the loop is ahead on
#     loop-surface detail core deliberately does not carry (auto_close_disabled,
#     hedged met_locally verdicts, driver version floors).
#
# Provisioning those today would put two files with the same name and
# contradictory status vocabulary in one repo, and an agent reading both would
# have no way to know which wins. That is an editorial decision about surface
# expressions, not a packaging one — tracked in #137, and this tuple is what
# changes when it lands.
PROVISIONED_SUBTREES = ("rules", "schemas")


class MethodologyMissingError(RuntimeError):
    """The installed package carries no substrate — a broken or partial install."""


def packaged_root() -> Path:
    """The substrate directory inside the installed umbrella package.

    Resolved as a sibling of this module rather than through
    `importlib.resources.files("specfuse")`: `specfuse` is a PEP 420 namespace
    shared with `specfuse.loop`, `specfuse.authoring` and `specfuse.orchestrator`,
    so `files()` returns a MultiplexedPath spanning every installed component's
    portion. Anchoring on this module's own location names the umbrella's portion
    exactly, with no dependence on which portion a traversal happens to search first.
    """
    return Path(__file__).resolve().parent / MIRROR_DIRNAME


def is_available() -> bool:
    return packaged_root().is_dir()


def substrate_files() -> list[Path]:
    """Every file in the packaged substrate, sorted, relative to its root."""
    root = packaged_root()
    if not root.is_dir():
        raise MethodologyMissingError(
            f"no methodology substrate at {root} — the installed `specfuse` package "
            "was built without it (see _build/backend.py), so there is nothing to "
            "provision")
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())


def provisioned_files() -> list[Path]:
    """The subset of the packaged substrate that is laid into a repo.

    Distinct from `substrate_files()` on purpose: the wheel carries everything, so
    releasing the prose later is a change to `PROVISIONED_SUBTREES` rather than to
    packaging, and the mirror-integrity tests keep checking the whole tree.
    """
    return [rel for rel in substrate_files()
            if rel.parts and rel.parts[0] in PROVISIONED_SUBTREES]


def provision(target: Path, *, dry_run: bool = False) -> list[str]:
    """Copy the packaged substrate into `<target>/.specfuse/methodology/`.

    Returns the repo-relative paths written (or that would be, under `dry_run`).

    Overwrites rather than merges. These files are core's, not the repo's: a local
    edit is drift by definition, and preserving it would recreate exactly the
    silent divergence this mechanism exists to end. Repo-local additions belong in
    the loop scaffold's `rules-local/`, which this never touches.
    """
    root = packaged_root()
    written: list[str] = []
    for rel in provisioned_files():
        dest = target / INSTALL_SUBPATH / rel
        written.append((INSTALL_SUBPATH / rel).as_posix())
        if dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dest)
    return written
