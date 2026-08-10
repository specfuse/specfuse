#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""Tests for the release's PyPI propagation gate (specfuse/await_pypi.py).

The gate exists because the umbrella's build-test resolves component floors from
PyPI immediately after those components publish, and "publish job finished" is
not "pip can resolve it" (#111). Everything here injects the probe and the sleep,
so the retry behaviour is exercised with no network and no wall-clock cost — a
test that really waited 30 x 10s would be the same unattended hang the gate is
meant to prevent.

What is deliberately NOT tested: `pip_can_resolve` itself. Its whole content is
one subprocess call to pip against the live index; a test could only assert the
argv it builds, restating the source. The argv is reviewed, not asserted.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from specfuse import await_pypi as ap

ROOT = Path(__file__).resolve().parent.parent


def _pyproject(tmp: Path, deps: str) -> Path:
    path = tmp / "pyproject.toml"
    path.write_text(textwrap.dedent(f"""\
        [project]
        name = "specfuse"
        version = "0.0.0"
        dependencies = [{deps}]
        """), encoding="utf-8")
    return path


class _Probe:
    """A probe reporting unresolvable for the first `misses` calls per package."""

    def __init__(self, misses: int = 0, never: set[str] | None = None):
        self.misses = misses
        self.never = never or set()
        self.calls: list[tuple[str, str]] = []

    def __call__(self, name: str, version: str) -> bool:
        self.calls.append((name, version))
        if name in self.never:
            return False
        return sum(1 for n, _ in self.calls if n == name) > self.misses


class TestComponentFloors(unittest.TestCase):

    def test_reads_floors_from_the_real_pyproject(self):
        # The gate is worthless if it silently parses nothing out of the file it
        # actually runs against, so anchor on the shipped pyproject, not only on
        # fixtures. This also fails if the dependency set is ever restructured.
        floors = ap.component_floors(ROOT / "pyproject.toml")
        for expected in ("specfuse-loop", "specfuse-orchestrator", "specfuse-authoring"):
            self.assertIn(expected, floors)
        for name, version in floors.items():
            self.assertRegex(version, r"^\d+\.\d+", f"{name} floor looks unparsed")

    def test_ignores_dependencies_that_are_not_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _pyproject(Path(tmp), '"specfuse-loop>=1.2.3", "pytest>=8.0"')
            self.assertEqual({"specfuse-loop": "1.2.3"}, ap.component_floors(path))

    def test_skips_a_component_with_no_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _pyproject(Path(tmp), '"specfuse-loop", "specfuse-authoring>=2.0"')
            # No `>=` means no single version to wait for; inventing one would
            # gate the release on a number this module made up.
            self.assertEqual({"specfuse-authoring": "2.0"}, ap.component_floors(path))

    def test_parses_around_extras_and_upper_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _pyproject(Path(tmp), '"specfuse-loop[extra]>=0.9.3,<1.0"')
            self.assertEqual({"specfuse-loop": "0.9.3"}, ap.component_floors(path))


class TestAwaitResolvable(unittest.TestCase):

    def test_passes_immediately_when_already_on_the_index(self):
        probe, slept = _Probe(), []
        unresolved = ap.await_resolvable(
            {"specfuse-loop": "1.0.0"}, probe=probe, sleep=slept.append,
            log=lambda _: None)
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(probe.calls), "must not poll again after a hit")
        self.assertEqual([], slept, "must not sleep when the first probe succeeds")

    def test_retries_until_the_index_catches_up(self):
        # The v0.9.2 case: resolvable a few polls after the publish job finished.
        probe, slept = _Probe(misses=3), []
        unresolved = ap.await_resolvable(
            {"specfuse-loop": "1.0.0"}, probe=probe, delay=10,
            sleep=slept.append, log=lambda _: None)
        self.assertEqual([], unresolved)
        self.assertEqual(4, len(probe.calls))
        self.assertEqual([10, 10, 10], slept,
                         "one sleep between retries, none after the hit")

    def test_gives_up_after_the_bounded_number_of_attempts(self):
        probe, slept = _Probe(never={"specfuse-loop"}), []
        unresolved = ap.await_resolvable(
            {"specfuse-loop": "1.0.0"}, probe=probe, attempts=5, delay=2,
            sleep=slept.append, log=lambda _: None)
        self.assertEqual(["specfuse-loop==1.0.0"], unresolved)
        self.assertEqual(5, len(probe.calls), "must stop at the bound, not hang")
        self.assertEqual(4, len(slept), "no sleep after the final failed attempt")

    def test_waits_on_every_component_and_reports_each_failure(self):
        probe = _Probe(never={"specfuse-authoring", "specfuse-loop"})
        unresolved = ap.await_resolvable(
            {"specfuse-loop": "1.0.0", "specfuse-authoring": "2.0.0",
             "specfuse-orchestrator": "3.0.0"},
            probe=probe, attempts=2, delay=0, sleep=lambda _: None,
            log=lambda _: None)
        # Every component is gated, not just the driver the issue named — all
        # three became hard dependencies in #125.
        self.assertEqual(["specfuse-authoring==2.0.0", "specfuse-loop==1.0.0"],
                         unresolved)
        self.assertIn(("specfuse-orchestrator", "3.0.0"), probe.calls)

    def test_logs_each_wait_so_the_job_does_not_look_hung(self):
        lines: list[str] = []
        ap.await_resolvable({"specfuse-loop": "1.0.0"}, probe=_Probe(misses=2),
                            attempts=5, delay=10, sleep=lambda _: None,
                            log=lines.append)
        self.assertEqual(2, sum("not on the index yet" in ln for ln in lines))
        self.assertTrue(any("resolvable" in ln for ln in lines))


class TestMain(unittest.TestCase):

    def test_fails_loudly_when_no_component_floors_are_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _pyproject(Path(tmp), '"pytest>=8.0"')
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ap.main([str(path)])
        self.assertEqual(1, rc, "a gate that finds nothing to check must not pass")
        self.assertIn("::error::", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
