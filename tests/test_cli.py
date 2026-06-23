#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""Tests for the `specfuse` umbrella CLI (FEAT-2026-0028 gate 2).

These exercise the REAL scaffold API (`specfuse.loop.scaffold`, editable
specfuse-loop) — the FEAT-2026-0019 stub-era assertions (curl-bash / pip-only) are
gone. The pip runner is injected so no real install happens.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace

import specfuse.cli as cli


def _ok_runner(rc=0):
    calls = []
    def runner(cmd):
        calls.append(cmd)
        return SimpleNamespace(returncode=rc)
    runner.calls = calls
    return runner


def _args(**kw):
    kw.setdefault("dry_run", False)
    kw.setdefault("ci_check", None)
    return SimpleNamespace(**kw)


def _tree(root: Path) -> dict:
    """relpath -> bytes for every file under root (for before/after equality)."""
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


class TestInit(unittest.TestCase):

    def test_init_rejects_non_directory(self):
        with redirect_stderr(io.StringIO()):
            rc = cli.cmd_init(_args(target="/no/such/dir"))
        self.assertEqual(rc, 2)

    def test_init_scaffolds_specfuse_tree(self):
        # Red test for T03: the stub wrote no .specfuse/; the rewire must.
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                rc = cli.cmd_init(_args(target=d))
            self.assertEqual(rc, 0)
            sf = Path(d) / ".specfuse"
            self.assertTrue((sf / "VERSION").is_file())
            self.assertTrue((sf / "rules").is_dir())
            self.assertTrue((sf / "templates").is_dir())
            self.assertTrue((sf / "docs" / "methodology.md").is_file())

    def test_init_refusal_points_at_upgrade(self):
        # AC3: .specfuse exists → ScaffoldExistsError caught → non-zero + 'upgrade'.
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                cli.cmd_init(_args(target=d))           # first init succeeds
            err = io.StringIO()
            with redirect_stderr(err):
                rc = cli.cmd_init(_args(target=d))       # second refuses
            self.assertNotEqual(rc, 0)
            self.assertIn("upgrade", err.getvalue())

    def test_init_dry_run_writes_nothing(self):
        # Red test for T05.
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_init(_args(target=d, dry_run=True))
            self.assertEqual(rc, 0)
            self.assertFalse((Path(d) / ".specfuse").exists())
            self.assertIn("dry-run", out.getvalue())

    def test_init_dry_run_does_not_bypass_refusal(self):
        # AC4: dry-run on an existing .specfuse still refuses.
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                cli.cmd_init(_args(target=d))
            err = io.StringIO()
            with redirect_stderr(err):
                rc = cli.cmd_init(_args(target=d, dry_run=True))
            self.assertNotEqual(rc, 0)


class TestUpgrade(unittest.TestCase):

    def _init(self, d):
        with redirect_stdout(io.StringIO()):
            cli.cmd_init(_args(target=d))

    def test_upgrade_overlays_then_pip(self):
        # Red test for T04: overlay precedes pip; both happen.
        with tempfile.TemporaryDirectory() as d:
            self._init(d)
            runner = _ok_runner(0)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_upgrade(_args(target=d), runner=runner)
            self.assertEqual(rc, 0)
            self.assertTrue(runner.calls, "pip-upgrade must run after the overlay")
            self.assertIn("--upgrade", runner.calls[0])
            self.assertIn("overlaid", out.getvalue())
            self.assertIn("/plugin update", out.getvalue())

    def test_upgrade_pip_failure_propagates(self):
        with tempfile.TemporaryDirectory() as d:
            self._init(d)
            err = io.StringIO()
            with redirect_stderr(err):
                rc = cli.cmd_upgrade(_args(target=d), runner=_ok_runner(1))
            self.assertEqual(rc, 1)
            self.assertIn("failed", err.getvalue())

    def test_upgrade_dry_run_changes_nothing_and_skips_pip(self):
        with tempfile.TemporaryDirectory() as d:
            self._init(d)
            before = _tree(Path(d) / ".specfuse")
            runner = _ok_runner(0)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_upgrade(_args(target=d, dry_run=True), runner=runner)
            after = _tree(Path(d) / ".specfuse")
            self.assertEqual(rc, 0)
            self.assertEqual(before, after, "dry-run must not touch the target")
            self.assertEqual(runner.calls, [], "dry-run must not pip-upgrade")
            self.assertIn("dry-run", out.getvalue())

    def test_upgrade_dry_run_tolerates_dangling_symlinks(self):
        """A legacy init.sh scaffold leaves dangling .specfuse/skills/* symlinks.
        The dry-run copies .specfuse/ to a temp dir; copytree must not choke on
        them (regression: shutil.Error 'No such file or directory')."""
        with tempfile.TemporaryDirectory() as d:
            self._init(d)
            skills = Path(d) / ".specfuse" / "skills"
            skills.mkdir(parents=True, exist_ok=True)
            # Point at a target that does not exist → dangling symlink.
            (skills / "roadmap-add").symlink_to("../../nonexistent/roadmap-add")
            runner = _ok_runner(0)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_upgrade(_args(target=d, dry_run=True), runner=runner)
            self.assertEqual(rc, 0, "dry-run must survive dangling legacy symlinks")
            self.assertIn("dry-run", out.getvalue())


class TestParser(unittest.TestCase):

    def test_version_flag_exits_zero(self):
        with self.assertRaises(SystemExit) as cm:
            with redirect_stdout(io.StringIO()):
                cli.main(["--version"])
        self.assertEqual(cm.exception.code, 0)

    def test_no_subcommand_errors(self):
        with self.assertRaises(SystemExit) as cm:
            with redirect_stderr(io.StringIO()):
                cli.main([])
        self.assertNotEqual(cm.exception.code, 0)

    def test_init_and_upgrade_subparsers_accept_dry_run(self):
        ap = cli.build_parser()
        ns = ap.parse_args(["init", "/tmp/x", "--dry-run"])
        self.assertTrue(ns.dry_run)
        ns = ap.parse_args(["upgrade", "/tmp/x", "--dry-run"])
        self.assertTrue(ns.dry_run)


if __name__ == "__main__":
    unittest.main()
