#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""The umbrella ships the core substrate and lays it into a repo.

Follow-up #3 of `decision-authoring-execution-boundary.md` requires the shared
substrate contract to ship from core, so neither plane imports the other. Before
this it shipped from nowhere at all — a built wheel carried ten entries and not one
line of `methodology/` — which is why consumers hand-copied it out of git, why
core's event schema drifted two releases behind the orchestrator's (#135), and why
the working authoring deployment resolved contracts through a sibling checkout.

Two things are asserted here, and the first is the one that would rot silently:

1. **The package actually carries the substrate.** `packaged_root()` is a
   directory of real files that matches `methodology/`. A provisioning function
   that faithfully copies an empty directory would pass every behavioural test
   ever written about it.
2. **Provisioning writes into its own slot.** `.specfuse/methodology/`, never
   `.specfuse/rules/` or `.specfuse/schemas/`, which `loop-init` owns. The
   ownership manifest's invariant is one writer per `(target, install path)`, and
   two upgraders on one slot is the failure it exists to prevent.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from specfuse import cli, methodology

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "methodology"


class TestPackagedSubstrate(unittest.TestCase):

    def test_the_installed_package_carries_the_substrate(self):
        # If this fails, the build backend did not mirror. Everything else in this
        # file would still pass against an empty directory.
        self.assertTrue(
            methodology.is_available(),
            f"no substrate at {methodology.packaged_root()} — build backend did not "
            "mirror methodology/ (see _build/backend.py)")

    def test_the_mirror_matches_the_canonical_source(self):
        packaged = set(methodology.substrate_files())
        canonical = {p.relative_to(SOURCE) for p in SOURCE.rglob("*") if p.is_file()}
        self.assertEqual(canonical, packaged,
                         "the packaged mirror and methodology/ disagree on contents")

    def test_the_mirror_is_byte_identical(self):
        root = methodology.packaged_root()
        for rel in methodology.substrate_files():
            with self.subTest(rel=str(rel)):
                self.assertEqual((SOURCE / rel).read_bytes(), (root / rel).read_bytes())

    def test_the_substrate_carries_the_rules_and_schemas_consumers_cite(self):
        names = {p.as_posix() for p in methodology.substrate_files()}
        for expected in ("schemas/event.schema.json",
                         "rules/correlation-ids.md",
                         "rules/never-touch.md",
                         "glossary.md"):
            self.assertIn(expected, names)


class TestProvisionedSubset(unittest.TestCase):
    """Only the machine contract is laid into a repo; the prose is held back.

    The wheel carries the whole substrate — releasing the prose later is a change
    to `PROVISIONED_SUBTREES`, not to packaging. What ships now is `rules/` and
    `schemas/`: exactly what consumers cite, and every file in them is either
    byte-identical to the loop scaffold's copy or absent from it, so provisioning
    adds no contradiction to a repo.

    `glossary.md` and `methodology.md` are withheld because the loop ships its own
    diverged `.specfuse/docs/` versions — core is ahead on the roadmap status
    vocabulary while the loop is ahead on loop-surface detail — and laying core's
    beside them would put contradictory status vocabulary in one repo with nothing
    saying which wins (#137).
    """

    def test_only_the_machine_contract_is_provisioned(self):
        tops = {rel.parts[0] for rel in methodology.provisioned_files()}
        self.assertEqual({"rules", "schemas"}, tops)

    def test_the_diverged_prose_is_not_provisioned(self):
        names = {rel.as_posix() for rel in methodology.provisioned_files()}
        for withheld in ("glossary.md", "methodology.md", "overview.md"):
            self.assertNotIn(withheld, names)

    def test_the_wheel_still_carries_the_prose(self):
        # Withheld from provisioning, NOT from the package — otherwise releasing
        # it later means changing the build rather than one tuple.
        names = {rel.as_posix() for rel in methodology.substrate_files()}
        for present in ("glossary.md", "methodology.md", "overview.md"):
            self.assertIn(present, names)

    # Provisioned files that currently differ from the loop scaffold's copy.
    #
    # EMPTY, and that is the intended steady state: every provisioned file is
    # byte-identical to the loop's copy or absent from it, which is the premise
    # `methodology.py` provisions on at all. It held three schemas from
    # specfuse/loop#1433 — core adopted the widened correlation-ID patterns in
    # #135 and the loop had not re-vendored, so a scaffolded repo carried two
    # copies of one contract disagreeing on which work-unit IDs are legal. Loop
    # 0.12.1 re-vendored; the floor in pyproject.toml is what keeps it true.
    #
    # Re-adding an entry is allowed but held to a higher bar than "documented":
    # it must be a case where core is RIGHT and the loop is stale, with the fix
    # already filed — not an open editorial question. The prose is the opposite
    # (both sides legitimate) and is withheld from provisioning entirely rather
    # than waived here.
    KNOWN_SCAFFOLD_DIVERGENCES: set[str] = set()

    def _scaffold_seed(self) -> Path:
        try:
            from specfuse.loop import scaffold as loop_scaffold
        except ImportError:  # pragma: no cover - components are hard deps
            self.fail("specfuse-loop is a hard dependency and must be importable")
        return Path(loop_scaffold.__file__).resolve().parent / "data"

    def _diverged_from_scaffold(self) -> set[str]:
        seed, root = self._scaffold_seed(), methodology.packaged_root()
        return {rel.as_posix() for rel in methodology.provisioned_files()
                if (seed / rel).is_file()
                and (seed / rel).read_bytes() != (root / rel).read_bytes()}

    def test_nothing_unexpected_contradicts_the_loop_scaffold(self):
        # Why this subset is safe to provision: every file is absent from the
        # loop's scaffold, byte-identical to it, or a known stale-loop case.
        # Anything else would put two different truths in one repo unannounced.
        unexpected = self._diverged_from_scaffold() - self.KNOWN_SCAFFOLD_DIVERGENCES
        self.assertEqual(
            set(), unexpected,
            "these differ from the loop scaffold with no recorded reason:\n  "
            + "\n  ".join(sorted(unexpected)))

    def test_no_scaffold_waiver_outlives_its_cause(self):
        # Vacuous while the waiver set is empty, and kept for the next time it is
        # not. Same discipline as test_substrate_drift: an exception that survives
        # its condition is how the next divergence passes unnoticed.
        stale = self.KNOWN_SCAFFOLD_DIVERGENCES - self._diverged_from_scaffold()
        self.assertEqual(
            set(), stale,
            "the loop scaffold now agrees on these — delete them from "
            "KNOWN_SCAFFOLD_DIVERGENCES:\n  " + "\n  ".join(sorted(stale)))


class TestProvision(unittest.TestCase):

    def test_writes_every_file_under_its_own_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            written = methodology.provision(target)
            self.assertEqual(len(written), len(methodology.provisioned_files()))
            for rel in written:
                self.assertTrue(rel.startswith(".specfuse/methodology/"), rel)
                self.assertTrue((target / rel).is_file(), rel)

    def test_does_not_write_into_the_loop_scaffold_slots(self):
        # The one-upgrader invariant: `loop-init` owns .specfuse/rules/ and
        # .specfuse/schemas/. This upgrader must not touch them.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            methodology.provision(target)
            self.assertFalse((target / ".specfuse" / "rules").exists())
            self.assertFalse((target / ".specfuse" / "schemas").exists())

    def test_dry_run_reports_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            written = methodology.provision(target, dry_run=True)
            self.assertEqual(len(written), len(methodology.provisioned_files()))
            self.assertFalse((target / ".specfuse").exists())

    def test_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            first = methodology.provision(target)
            second = methodology.provision(target)
            self.assertEqual(first, second)

    def test_overwrites_a_locally_edited_copy(self):
        # These files are core's. A local edit is drift, and preserving it would
        # recreate the divergence this mechanism exists to end.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            methodology.provision(target)
            victim = target / ".specfuse" / "methodology" / "rules" / "never-touch.md"
            victim.write_text("tampered\n", encoding="utf-8")
            methodology.provision(target)
            self.assertNotEqual("tampered\n", victim.read_text(encoding="utf-8"))

    def test_a_package_without_the_substrate_raises_rather_than_writing_nothing(self):
        original = methodology.packaged_root
        methodology.packaged_root = lambda: Path("/nonexistent/_methodology")
        try:
            with self.assertRaises(methodology.MethodologyMissingError):
                methodology.substrate_files()
        finally:
            methodology.packaged_root = original


class TestCliIntegration(unittest.TestCase):

    def test_a_missing_substrate_is_reported_without_failing_the_command(self):
        # Additive to the scaffold: a repo that got .specfuse/ but not the
        # methodology is worse off if the command also exits non-zero and leaves
        # the caller believing nothing was written.
        original = methodology.provision

        def _boom(_target, **_kw):
            raise methodology.MethodologyMissingError("no substrate")

        methodology.provision = _boom
        err = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as tmp, redirect_stderr(err):
                written = cli._provision_methodology(Path(tmp), dry_run=False)
        finally:
            methodology.provision = original
        self.assertEqual([], written)
        self.assertIn("no substrate", err.getvalue())
        self.assertIn("reinstall", err.getvalue())

    def test_init_provisions_the_substrate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_init(_init_args(tmp))
            self.assertEqual(0, rc)
            laid = Path(tmp) / ".specfuse" / "methodology" / "rules" / "correlation-ids.md"
            self.assertTrue(laid.is_file(), "init did not provision the substrate")
            self.assertIn("methodology file(s)", out.getvalue())


def _init_args(target: str):
    from types import SimpleNamespace
    return SimpleNamespace(target=target, dry_run=False, ci_check=None,
                           plugins=None, no_self_upgrade=True, fix=False,
                           no_network=True)


if __name__ == "__main__":
    unittest.main()
