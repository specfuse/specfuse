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


class TestProvision(unittest.TestCase):

    def test_writes_every_file_under_its_own_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            written = methodology.provision(target)
            self.assertEqual(len(written), len(methodology.substrate_files()))
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
            self.assertEqual(len(written), len(methodology.substrate_files()))
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
