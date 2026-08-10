#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""`methodology/schemas/` is core-canonical — prove the consumers still agree.

The orchestrator's `shared/distribution/ownership-manifest.yaml` entry
`schemas-methodology` names this repo canonical for the event envelope and the
definition-plane payload schemas, and states the invariant outright:

    the orchestrator and loop both vendor them byte-identical

Nothing checked, and it stopped being true. Core's copies had not changed since
they landed in #22; the orchestrator widened the correlation-ID patterns to admit
hygiene (`TNNH[N...]`) and closing-sequence (`G<n>-<NAME>`) work-unit IDs — its
`$comment` cites 288 envelope-validation failures across 39 feature folders — and
the canonical copy never followed. Core, the owner, shipped the pattern that
*rejects* those IDs, and the loop vendored the stale copy faithfully.

That is `methodology/rules/borrowed-vocabularies.md` on this repo's own
vocabulary, and it names why memory was never going to hold: the consumer that
discovers the gap fixes it locally, because that is where the failure appears,
and nothing tells the owner.

This check does what that rule requires of the party who closes over a set:

- **Reads the defining artifact, not a description of it.** It compares against
  the schemas inside the INSTALLED component packages. Both are hard
  dependencies (#125), so `pip install -e '.[dev]'` resolves them from PyPI and
  CI compares against what those components actually ship.
- **Discovers the set structurally.** It walks `methodology/schemas/`, so a new
  core schema is covered the day it is added, with no list to update in turn.
- **Never skips silently.** A divergence is either a failure or a WAIVER with a
  reason, and a waiver that no longer corresponds to a real divergence fails too
  — an exception that outlives its cause is how the next drift hides.

A consumer that does not vendor a given file is not drift: the loop carries a
subset, plus `driver-event.schema.json` of its own, which core does not own.
"""

from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_SCHEMAS = ROOT / "methodology" / "schemas"

# (distribution, import name, path to its vendored copy within the package).
CONSUMERS = (
    ("specfuse-orchestrator", "specfuse.orchestrator", "_substrate/schemas"),
    ("specfuse-loop", "specfuse.loop", "data/schemas"),
)

# (distribution, path relative to methodology/schemas/) -> why it may differ.
#
# A waiver is a debt, not a dispensation. Each one must name the direction and
# what clears it, and `test_no_waiver_outlives_its_cause` deletes the excuse the
# moment the files agree again.
KNOWN_DIVERGENCES: dict[tuple[str, str], str] = {
    ("specfuse-loop", "event.schema.json"):
        "Core moved ahead: adopted the orchestrator's widened correlation-ID "
        "pattern. Clears when specfuse/loop re-vendors and releases — see "
        "specfuse/loop#1433.",
    ("specfuse-loop", "events/spec_issue_routed.schema.json"):
        "Same widening as the envelope; clears with specfuse/loop#1433.",
    ("specfuse-loop", "events/spec_issue_resolved.schema.json"):
        "Same widening as the envelope; clears with specfuse/loop#1433.",
}


def _vendored_dir(import_name: str, subpath: str) -> Path | None:
    spec = importlib.util.find_spec(import_name)
    if spec is None or not spec.origin:
        return None
    path = Path(spec.origin).parent / subpath
    return path if path.is_dir() else None


def _core_schemas() -> list[Path]:
    """Every schema this repo owns, discovered structurally."""
    return sorted(CORE_SCHEMAS.rglob("*.json"))


def _divergences() -> tuple[list[tuple[str, str]], list[str]]:
    """(diverging (dist, relpath) pairs, names of consumers that could not be read)."""
    diverging: list[tuple[str, str]] = []
    unreadable: list[str] = []
    for dist, import_name, subpath in CONSUMERS:
        vendored = _vendored_dir(import_name, subpath)
        if vendored is None:
            unreadable.append(dist)
            continue
        for schema in _core_schemas():
            rel = schema.relative_to(CORE_SCHEMAS).as_posix()
            theirs = vendored / rel
            # Not vendoring a file is not drift — consumers carry subsets.
            if theirs.is_file() and theirs.read_bytes() != schema.read_bytes():
                diverging.append((dist, rel))
    return diverging, unreadable


class TestSubstrateDrift(unittest.TestCase):

    def test_core_actually_owns_schemas_to_check(self):
        # A structural walk that finds nothing passes forever.
        found = _core_schemas()
        self.assertGreater(len(found), 1, "no schemas discovered under methodology/schemas/")
        names = {p.relative_to(CORE_SCHEMAS).as_posix() for p in found}
        self.assertIn("event.schema.json", names)

    def test_both_consumers_are_readable(self):
        # Not a skip. Both components are HARD dependencies, so being unable to
        # read them means the environment is wrong, and silently passing here
        # would turn the whole check into a no-op exactly when it is needed.
        _diverging, unreadable = _divergences()
        self.assertEqual([], unreadable,
                         "could not read vendored schemas from: " + ", ".join(unreadable))

    def test_no_unwaived_drift_from_the_canonical_copies(self):
        diverging, _unreadable = _divergences()
        unwaived = [pair for pair in diverging if pair not in KNOWN_DIVERGENCES]
        self.assertEqual(
            [], unwaived,
            "these consumers no longer match core, which owns them:\n  "
            + "\n  ".join(f"{dist}: {rel}" for dist, rel in unwaived)
            + "\nEither re-vendor the consumer, or land the change in core and "
              "add a KNOWN_DIVERGENCES entry naming what clears it.")

    def test_no_waiver_outlives_its_cause(self):
        # An exception that survives the condition it was written for is how the
        # next drift passes unnoticed.
        diverging, _unreadable = _divergences()
        stale = [pair for pair in KNOWN_DIVERGENCES if pair not in diverging]
        self.assertEqual(
            [], stale,
            "these waivers no longer describe a real divergence — delete them:\n  "
            + "\n  ".join(f"{dist}: {rel}" for dist, rel in stale))

    def test_every_waiver_states_what_clears_it(self):
        for (dist, rel), reason in KNOWN_DIVERGENCES.items():
            self.assertRegex(
                reason, r"[Cc]lears",
                f"waiver for {dist}:{rel} must name what clears it")


class TestCorrelationIdWideningIsAdditive(unittest.TestCase):
    """The widening core just adopted must accept everything the old pattern did.

    The orchestrator's `$comment` claims the change is strictly additive. Core is
    now the canonical home for that claim, so it is asserted here rather than
    trusted: a correlation ID that validated before this change must still
    validate, or the "additive" framing is wrong and consumers break on upgrade.
    """

    LEGACY_IDS = (
        "FEAT-2026-0042",
        "FEAT-2026-0042/T09",
        "INIT-2026-0011",
        "INIT-2026-0011/F02",
        "INIT-2026-0011/F02/T03",
    )
    NEWLY_ADMITTED = (
        "FEAT-2026-0042/T09H",
        "FEAT-2026-0042/T09H2",
        "FEAT-2026-0042/G1-RETRO",
        "FEAT-2026-0042/G2-CLOSE-INTERMEDIATE",
    )
    STILL_REFUSED = (
        "FEAT-2026-0042/G1-FOO",      # undocumented closing name
        "FEAT-26-0042",               # short year
        "BUG-2026-0042",              # unknown namespace
    )

    def setUp(self):
        import json
        schema = json.loads((CORE_SCHEMAS / "event.schema.json").read_text())
        self.pattern = re.compile(
            schema["properties"]["correlation_id"]["pattern"])

    def test_every_legacy_id_still_validates(self):
        for cid in self.LEGACY_IDS:
            with self.subTest(cid=cid):
                self.assertRegex(cid, self.pattern)

    def test_the_hygiene_and_closing_shapes_are_admitted(self):
        for cid in self.NEWLY_ADMITTED:
            with self.subTest(cid=cid):
                self.assertRegex(cid, self.pattern)

    def test_the_widening_did_not_open_the_gate(self):
        for cid in self.STILL_REFUSED:
            with self.subTest(cid=cid):
                self.assertNotRegex(cid, self.pattern)


if __name__ == "__main__":
    unittest.main()
