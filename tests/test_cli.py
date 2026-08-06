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
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from specfuse import cli


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

    def _make_stale(self, d):
        """Force the target's scaffold VERSION older than the seed so upgrade
        actually overlays (a freshly-init'd target is already current)."""
        (Path(d) / ".specfuse" / "VERSION").write_text("0.1.0\n", encoding="utf-8")

    def test_upgrade_overlays_then_pip(self):
        # Red test for T04: overlay precedes pip; both happen.
        with tempfile.TemporaryDirectory() as d:
            self._init(d)
            self._make_stale(d)
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
            self._make_stale(d)  # force an actual overlay so the copytree runs
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

    def test_upgrade_dry_run_reports_already_latest(self):
        """A freshly-init'd target is at the seed version; --dry-run must say so,
        not dump the full versioned-file list."""
        with tempfile.TemporaryDirectory() as d:
            self._init(d)  # VERSION == installed seed
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_upgrade(_args(target=d, dry_run=True), runner=_ok_runner(0))
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("already at the latest", text)
            self.assertNotIn("would overlay", text)
            self.assertNotIn("  .specfuse/", text)  # no file list

    def test_upgrade_real_reports_already_latest(self):
        """Real upgrade on a current target reports 'already at latest', not a
        misleading 'overlaid N file(s)'."""
        with tempfile.TemporaryDirectory() as d:
            self._init(d)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_upgrade(_args(target=d), runner=_ok_runner(0))
            self.assertEqual(rc, 0)
            self.assertIn("already at the latest", out.getvalue())

    def test_pip_step_skipped_when_pip_unavailable(self):
        """In a pip-less (e.g. pipx-managed) environment, the upgrade skips the
        auto pip-install with guidance rather than erroring, and does not call
        the runner."""
        import importlib.util as _ilu
        real_find_spec = _ilu.find_spec

        def _no_pip(name, *a, **k):
            return None if name == "pip" else real_find_spec(name, *a, **k)

        runner = _ok_runner(0)
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            self._init(d)
            self._make_stale(d)
            orig = cli.importlib.util.find_spec
            cli.importlib.util.find_spec = _no_pip
            try:
                with redirect_stderr(err):
                    rc = cli.cmd_upgrade(_args(target=d), runner=runner)
            finally:
                cli.importlib.util.find_spec = orig
            self.assertEqual(rc, 0, "pip-less env must not fail the upgrade")
            self.assertEqual(runner.calls, [], "must not attempt pip when pip absent")
            self.assertIn("pipx upgrade specfuse", err.getvalue())


class TestDiagnoseShims(unittest.TestCase):
    """`diagnose_shims` is the collision detector: two supported install paths
    (`pipx install --include-deps 'specfuse[all]'` and a standalone
    `pipx install specfuse-authoring`) compete for one name in ~/.local/bin, and
    the loser's package upgrades without changing what the command runs.

    The venv bin dir and shim dir are injected, so these build the four states on
    a real tmpdir instead of touching the caller's ~/.local/bin.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.venv_bin = root / "venvs" / "specfuse" / "bin"
        self.other_bin = root / "venvs" / "specfuse-authoring" / "bin"
        self.shims = root / "bin"
        for d in (self.venv_bin, self.other_bin, self.shims):
            d.mkdir(parents=True)
        # Attribute every script to a real distribution name; the fix strings
        # quote it back at the user.
        self._orig_scripts = cli._console_scripts
        cli._console_scripts = lambda: {"specfuse-authoring": "specfuse-authoring"}

    def tearDown(self):
        cli._console_scripts = self._orig_scripts
        self._tmp.cleanup()

    def _run(self):
        return cli.diagnose_shims(shim_dir=self.shims, venv_bin=self.venv_bin)

    def test_healthy_shim_is_not_reported(self):
        (self.venv_bin / "specfuse-authoring").write_text("#!/bin/sh\n")
        (self.shims / "specfuse-authoring").symlink_to(
            self.venv_bin / "specfuse-authoring")
        self.assertEqual(self._run(), [])

    def test_script_not_provided_by_this_venv_is_ignored(self):
        """A console script the venv does not actually ship (extra not installed)
        is another package's business, not a finding."""
        (self.shims / "specfuse-authoring").symlink_to(
            self.other_bin / "specfuse-authoring")
        self.assertEqual(self._run(), [])

    def test_stale_dangling_shim_is_reported_with_rm(self):
        (self.venv_bin / "specfuse-authoring").write_text("#!/bin/sh\n")
        (self.shims / "specfuse-authoring").symlink_to(
            self.other_bin / "gone")  # target never created
        problems = self._run()
        self.assertEqual(len(problems), 1)
        command, problem, fix, kind = problems[0]
        self.assertEqual(command, "specfuse-authoring")
        self.assertIn("stale shim", problem)
        self.assertIn("rm ", fix)
        self.assertEqual(kind, "stale")

    def test_shim_owned_by_another_install_is_reported(self):
        (self.venv_bin / "specfuse-authoring").write_text("#!/bin/sh\n")
        (self.other_bin / "specfuse-authoring").write_text("#!/bin/sh\n")
        (self.shims / "specfuse-authoring").symlink_to(
            self.other_bin / "specfuse-authoring")
        problems = self._run()
        self.assertEqual(len(problems), 1)
        self.assertIn("another install", problems[0][1])
        self.assertEqual(problems[0][3], "foreign")

    def test_installed_but_unlinked_script_is_reported(self):
        """The --include-deps omission: the extra is installed, its command is
        not on PATH at all."""
        (self.venv_bin / "specfuse-authoring").write_text("#!/bin/sh\n")
        problems = self._run()
        self.assertEqual(len(problems), 1)
        self.assertIn("not on PATH", problems[0][1])
        self.assertIn("--include-deps", problems[0][2])
        self.assertEqual(problems[0][3], "unlinked")


class TestUpgradeShimWarning(unittest.TestCase):
    """The upgrade-time advisory: broken shims warn, an unlinked optional command
    stays quiet, and neither ever fails the upgrade."""

    def _warn(self, problems):
        orig_managed, orig_diag = cli._managed_by_tool, cli.diagnose_shims
        cli._managed_by_tool = lambda: True
        cli.diagnose_shims = lambda: problems
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                cli._warn_about_shims()
        finally:
            cli._managed_by_tool, cli.diagnose_shims = orig_managed, orig_diag
        return err.getvalue()

    def test_foreign_shim_warns(self):
        out = self._warn([("specfuse-authoring", "shim points at another install",
                           "pick ONE owner", "foreign")])
        self.assertIn("specfuse-authoring", out)

    def test_unlinked_command_is_silent(self):
        out = self._warn([("specfuse-stats", "not on PATH", "--include-deps",
                           "unlinked")])
        self.assertEqual(out, "")

    def test_plain_venv_skips_the_check_entirely(self):
        orig_managed, orig_diag = cli._managed_by_tool, cli.diagnose_shims
        called = []
        cli._managed_by_tool = lambda: False
        cli.diagnose_shims = lambda: called.append(1) or []
        try:
            cli._warn_about_shims()
        finally:
            cli._managed_by_tool, cli.diagnose_shims = orig_managed, orig_diag
        self.assertEqual(called, [], "no shims exist to check outside pipx/uv")


class TestDoctor(unittest.TestCase):

    def test_non_tool_install_reports_nothing_to_check(self):
        orig = cli._managed_by_tool
        cli._managed_by_tool = lambda: False
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                rc = cli.cmd_doctor(_args())
        finally:
            cli._managed_by_tool = orig
        self.assertEqual(rc, 0)
        self.assertIn("no shims to check", out.getvalue())

    def test_problems_exit_nonzero_and_name_the_command(self):
        orig_managed, orig_diag = cli._managed_by_tool, cli.diagnose_shims
        cli._managed_by_tool = lambda: True
        cli.diagnose_shims = lambda: [
            ("specfuse-authoring", "stale shim: x", "rm x", "stale")]
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                rc = cli.cmd_doctor(_args())
        finally:
            cli._managed_by_tool, cli.diagnose_shims = orig_managed, orig_diag
        self.assertEqual(rc, 1)
        self.assertIn("specfuse-authoring", err.getvalue())
        self.assertIn("rm x", err.getvalue())

    def test_clean_install_exits_zero(self):
        orig_managed, orig_diag = cli._managed_by_tool, cli.diagnose_shims
        cli._managed_by_tool = lambda: True
        cli.diagnose_shims = lambda: []
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                rc = cli.cmd_doctor(_args())
        finally:
            cli._managed_by_tool, cli.diagnose_shims = orig_managed, orig_diag
        self.assertEqual(rc, 0)
        self.assertIn("resolve to this install", out.getvalue())


class TestParser(unittest.TestCase):

    def test_version_flag_exits_zero(self):
        with self.assertRaises(SystemExit) as cm, redirect_stdout(io.StringIO()):
            cli.main(["--version"])
        self.assertEqual(cm.exception.code, 0)

    def test_no_subcommand_errors(self):
        with self.assertRaises(SystemExit) as cm, redirect_stderr(io.StringIO()):
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
