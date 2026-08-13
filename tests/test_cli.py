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
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from specfuse import cli


class _Tty(io.StringIO):
    """A capture buffer that claims to be a terminal, so the interactive-only
    deprecation notice fires under redirect_stderr."""

    def isatty(self):
        return True


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
    kw.setdefault("plugins", None)
    kw.setdefault("no_self_upgrade", False)
    kw.setdefault("fix", False)
    # Defaults to True here while the CLI defaults it to False: `doctor` reaches
    # pypi.org for the staleness advisory, and no test may depend on the network.
    # TestOutdatedComponents drives that path explicitly with an injected fetch.
    kw.setdefault("no_network", True)
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

    def test_second_init_upgrades_instead_of_refusing(self):
        """init used to refuse on an existing .specfuse/ and tell the user to run
        `upgrade` — a decision the tool can make itself by reading VERSION. The two
        are now one idempotent operation, so neither name is ever the wrong one."""
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                cli.cmd_init(_args(target=d))
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_init(_args(target=d), runner=_ok_runner(0))
            self.assertEqual(rc, 0)
            self.assertIn("upgrading it", out.getvalue())

    def test_upgrade_on_a_bare_repo_scaffolds(self):
        """The other direction: `upgrade` on a repo with no .specfuse/ scaffolds it
        rather than erroring."""
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_upgrade(_args(target=d), runner=_ok_runner(0))
            self.assertEqual(rc, 0)
            self.assertIn("scaffolding it", out.getvalue())
            self.assertTrue((Path(d) / ".specfuse" / "VERSION").is_file())

    def test_target_defaults_to_the_cwd(self):
        ns = cli.build_parser().parse_args(["init"])
        self.assertEqual(ns.target, ".")

    def test_init_dry_run_writes_nothing(self):
        # Red test for T05.
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_init(_args(target=d, dry_run=True))
            self.assertEqual(rc, 0)
            self.assertFalse((Path(d) / ".specfuse").exists())
            self.assertIn("dry-run", out.getvalue())

    def test_init_dry_run_on_existing_scaffold_previews_the_upgrade(self):
        """Was a refusal; now it routes to the upgrade preview — and still writes
        nothing."""
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                cli.cmd_init(_args(target=d))
            before = _tree(Path(d) / ".specfuse")
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_init(_args(target=d, dry_run=True), runner=_ok_runner(0))
            self.assertEqual(rc, 0)
            self.assertEqual(before, _tree(Path(d) / ".specfuse"))
            self.assertIn("dry-run", out.getvalue())

    def test_init_enables_requested_plugins(self):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_init(_args(target=d, plugins=["authoring", "orchestrator"]))
            self.assertEqual(rc, 0)
            settings = json.loads(
                (Path(d) / ".claude" / "settings.json").read_text(encoding="utf-8"))
            enabled = settings["enabledPlugins"]
            self.assertIs(enabled["specfuse-authoring@specfuse"], True)
            self.assertIs(enabled["specfuse-orchestrator@specfuse"], True)
            # The scaffold's own wiring survives the merge.
            self.assertIs(enabled["specfuse@specfuse"], True)
            self.assertIn("specfuse", settings["extraKnownMarketplaces"])

    def test_init_without_plugins_flag_enables_only_the_scaffold_default(self):
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                cli.cmd_init(_args(target=d))
            settings = json.loads(
                (Path(d) / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(list(settings["enabledPlugins"]), ["specfuse@specfuse"])

    def test_plugins_flag_rejects_unknown_names(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            cli.build_parser().parse_args(["init", "/tmp/x", "--plugins", "nope"])

    def test_plugins_flag_parses_a_comma_list(self):
        ns = cli.build_parser().parse_args(
            ["init", "/tmp/x", "--plugins", "authoring, orchestrator"])
        self.assertEqual(ns.plugins, ["authoring", "orchestrator"])


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

    def test_upgrade_carries_components_up_eagerly(self):
        """The upgrade names the umbrella ONLY — its components are hard deps and
        come with it, whereas naming today's components would pin the upgrade to
        today's list. `--upgrade-strategy eager` states the intent that every
        component moves; on current pip the default behaves the same way, so this
        asserts the contract, not a workaround (see cli._pip_install)."""
        with tempfile.TemporaryDirectory() as d:
            self._init(d)
            self._make_stale(d)
            runner = _ok_runner(0)
            with redirect_stdout(io.StringIO()):
                cli.cmd_upgrade(_args(target=d), runner=runner)
            cmd = runner.calls[0]
            self.assertIn("--upgrade-strategy", cmd)
            self.assertEqual(cmd[cmd.index("--upgrade-strategy") + 1], "eager")
            self.assertEqual(cmd[-1], "specfuse")

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
    """`diagnose_shims` is the collision detector: the umbrella install and a
    standalone `pipx install specfuse-authoring` compete for one name in
    ~/.local/bin, and the loser's package upgrades without changing what the
    command runs. Machines that ran the retired `specfuse[all]` extras path also
    carry dangling shims from a venv that no longer provides those scripts.

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
        """A console script this environment does not ship belongs to another
        package — not ours to police."""
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
        """The command is shipped by this venv but absent from PATH. Since the
        umbrella declares every suite command as its own entry point, this is a
        broken install — the fix is a reinstall, never --include-deps."""
        (self.venv_bin / "specfuse-authoring").write_text("#!/bin/sh\n")
        problems = self._run()
        self.assertEqual(len(problems), 1)
        self.assertIn("not on PATH", problems[0][1])
        self.assertIn("--force specfuse", problems[0][2])
        self.assertNotIn("--include-deps", problems[0][2])
        self.assertEqual(problems[0][3], "unlinked")

    def test_only_suite_distributions_are_policed(self):
        """Bundling the suite pulled transitive deps that ship their own console
        scripts (jsonschema, via the orchestrator). doctor reported `jsonschema`
        as a broken suite command until _console_scripts() filtered to
        SUITE_DISTS."""
        cli._console_scripts = self._orig_scripts   # exercise the real filter
        self.assertNotIn("jsonschema", cli._console_scripts())
        for _command, dist in cli._console_scripts().items():
            self.assertIn(dist, cli.SUITE_DISTS)

    def test_orphaned_shim_for_a_command_this_install_dropped(self):
        """The wreckage of the retired extras path: a shim for a command the venv
        no longer provides. The main loop cannot see it — its exists() guard skips
        any command this venv does not ship — so a second pass looks for it."""
        (self.shims / "specfuse-poller").symlink_to(self.other_bin / "gone")
        problems = self._run()
        self.assertEqual(len(problems), 1)
        command, problem, _fix, kind = problems[0]
        self.assertEqual(command, "specfuse-poller")
        self.assertIn("orphaned shim", problem)
        self.assertEqual(kind, "orphan")

    def test_unrelated_dangling_shim_is_not_ours_to_report(self):
        (self.shims / "some-other-tool").symlink_to(self.other_bin / "gone")
        self.assertEqual(self._run(), [])

    def test_no_fix_string_mentions_the_retired_extras(self):
        """The extras are gone; a fix that tells the user to reinstall
        `specfuse[all]` with --include-deps would send them back into the bug."""
        (self.venv_bin / "specfuse-authoring").write_text("#!/bin/sh\n")
        (self.other_bin / "specfuse-authoring").write_text("#!/bin/sh\n")
        (self.shims / "specfuse-authoring").symlink_to(
            self.other_bin / "specfuse-authoring")
        for _command, _problem, fix, _kind in self._run():
            self.assertNotIn("include-deps", fix)
            self.assertNotIn("with-executables-from", fix)
            self.assertNotIn("[all]", fix)


class TestUpgradeShimWarning(unittest.TestCase):
    """The upgrade-time advisory: every shim problem warns, and none of them ever
    fails the upgrade."""

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

    def test_unlinked_command_now_warns(self):
        """Was deliberately silent while the component commands were optional
        extras. Now the umbrella declares them all, so a suite command missing
        from PATH is a broken install and must be reported."""
        out = self._warn([("specfuse-stats", "not on PATH",
                           "pipx install --force specfuse", "unlinked")])
        self.assertIn("specfuse-stats", out)

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


class TestDelegation(unittest.TestCase):
    """`specfuse run ...` hands off to the component that implements it."""

    def setUp(self):
        self._orig_argv = list(sys.argv)

    def tearDown(self):
        sys.argv = self._orig_argv

    def _fake_component(self, rc=0, record=None):
        """A stand-in component main. Nine of the twelve real ones take NO
        arguments and read sys.argv themselves, so the dispatcher has to swap
        sys.argv — this asserts it does."""
        def main():
            if record is not None:
                record.append(list(sys.argv))
            return rc
        return main

    def _patch_target(self, func):
        module = types.ModuleType("fake_component")
        module.main = func
        orig = cli.importlib.import_module
        cli.importlib.import_module = lambda name: (
            module if name == "fake_component" else orig(name))
        self.addCleanup(setattr, cli.importlib, "import_module", orig)

    def test_argv_is_swapped_for_the_component_and_restored(self):
        seen = []
        self._patch_target(self._fake_component(record=seen))
        sys.argv = ["specfuse", "run", "--flag", "value"]
        rc = cli._delegate("fake_component:main", ["--flag", "value"],
                           prog="specfuse run")
        self.assertEqual(rc, 0)
        self.assertEqual(seen, [["specfuse run", "--flag", "value"]])
        self.assertEqual(sys.argv, ["specfuse", "run", "--flag", "value"],
                         "sys.argv must be restored")

    def test_argv_is_restored_even_when_the_component_raises(self):
        def boom():
            raise SystemExit(3)
        self._patch_target(boom)
        sys.argv = ["specfuse", "run"]
        with self.assertRaises(SystemExit):
            cli._delegate("fake_component:main", [], prog="specfuse run")
        self.assertEqual(sys.argv, ["specfuse", "run"])

    def test_none_return_becomes_zero(self):
        self._patch_target(lambda: None)
        self.assertEqual(cli._delegate("fake_component:main", [], prog="x"), 0)

    def test_component_return_code_propagates(self):
        self._patch_target(self._fake_component(rc=7))
        self.assertEqual(cli._delegate("fake_component:main", [], prog="x"), 7)

    def test_missing_component_reports_against_the_command_typed(self):
        orig = cli.importlib.import_module
        cli.importlib.import_module = lambda name: (_ for _ in ()).throw(
            ImportError("No module named 'specfuse.authoring'"))
        self.addCleanup(setattr, cli.importlib, "import_module", orig)
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli._delegate("specfuse.authoring.cli:_run", [],
                               prog="specfuse authoring")
        self.assertEqual(rc, 1)
        self.assertIn("specfuse authoring", err.getvalue())
        self.assertIn("--force specfuse", err.getvalue())

    def test_main_intercepts_before_argparse(self):
        """`specfuse lint --help` must print the LINTER's help. If argparse saw
        the subcommand it would interpret --help as its own."""
        seen = []
        self._patch_target(self._fake_component(record=seen))
        orig = dict(cli.DELEGATED_COMMANDS)
        cli.DELEGATED_COMMANDS["lint"] = ("fake_component:main", "specfuse-lint", "h")
        self.addCleanup(cli.DELEGATED_COMMANDS.update, orig)
        rc = cli.main(["lint", "--help", "--weird-flag"])
        self.assertEqual(rc, 0)
        self.assertEqual(seen, [["specfuse lint", "--help", "--weird-flag"]])

    def test_delegated_commands_appear_in_help(self):
        out = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(out):
            cli.main(["--help"])
        text = out.getvalue()
        for subcommand in cli.DELEGATED_COMMANDS:
            self.assertIn(subcommand, text)


class TestAliases(unittest.TestCase):
    """The deprecated flat `specfuse-*` commands. All twelve share one entry
    point, which recovers the invoked name from sys.argv[0]."""

    def setUp(self):
        self._orig_argv = list(sys.argv)
        self._orig_env = os.environ.get(cli.SUPPRESS_DEPRECATION_ENV)
        os.environ.pop(cli.SUPPRESS_DEPRECATION_ENV, None)
        self._calls = []
        orig = cli._delegate
        cli._delegate = lambda target, argv, *, prog: (
            self._calls.append((target, argv, prog)) or 0)
        self.addCleanup(setattr, cli, "_delegate", orig)

    def tearDown(self):
        sys.argv = self._orig_argv
        if self._orig_env is None:
            os.environ.pop(cli.SUPPRESS_DEPRECATION_ENV, None)
        else:
            os.environ[cli.SUPPRESS_DEPRECATION_ENV] = self._orig_env

    def test_alias_dispatches_to_the_right_subcommand(self):
        sys.argv = ["/usr/local/bin/specfuse-lint", "plan.md"]
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli.alias_main()
        self.assertEqual(rc, 0)
        target, argv, prog = self._calls[0]
        self.assertEqual(target, cli.DELEGATED_COMMANDS["lint"][0])
        self.assertEqual(argv, ["plan.md"])
        self.assertEqual(prog, "specfuse-lint")

    def test_alias_warns_and_names_the_replacement(self):
        sys.argv = ["specfuse-orchestrator"]
        err = _Tty()
        with redirect_stderr(err):
            cli.alias_main()
        text = err.getvalue()
        self.assertIn("deprecated", text)
        self.assertIn("specfuse pm", text)
        self.assertIn("1.0.0", text)

    def test_notice_is_silent_when_stderr_is_not_a_terminal(self):
        """Scaffold hooks and verification.yml call the flat commands on every
        gate. A line per call is noise in a CI log nobody can act on from there —
        and `specfuse doctor` reports migration status deterministically anyway."""
        sys.argv = ["specfuse-loop"]
        err = io.StringIO()          # not a tty
        with redirect_stderr(err):
            cli.alias_main()
        self.assertEqual(err.getvalue(), "")

    def test_warning_is_suppressible_even_interactively(self):
        sys.argv = ["specfuse-loop"]
        os.environ[cli.SUPPRESS_DEPRECATION_ENV] = "1"
        err = _Tty()
        with redirect_stderr(err):
            cli.alias_main()
        self.assertEqual(err.getvalue(), "")

    def test_windows_exe_suffix_is_stripped(self):
        sys.argv = [r"C:\Users\x\.local\bin\specfuse-stats.exe", "--json"]
        with redirect_stderr(io.StringIO()):
            cli.alias_main()
        self.assertEqual(self._calls[0][0], cli.DELEGATED_COMMANDS["stats"][0])

    def test_unknown_invocation_name_is_an_error(self):
        sys.argv = ["specfuse-nonsense"]
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli.alias_main()
        self.assertEqual(rc, 2)
        self.assertIn("specfuse --help", err.getvalue())
        self.assertEqual(self._calls, [])


class TestSelfUpgrade(unittest.TestCase):
    """`specfuse upgrade` runs the right installer instead of printing it."""

    def setUp(self):
        self._orig_installer = cli._installer
        self._orig_which = cli.shutil.which
        cli.shutil.which = lambda name: f"/usr/bin/{name}"
        self.addCleanup(setattr, cli.shutil, "which", self._orig_which)
        self.addCleanup(setattr, cli, "_installer", self._orig_installer)

    def test_pipx_install_runs_a_bare_pipx_upgrade(self):
        """No extra flags. Passing `--pip-args=--upgrade-strategy=eager` broke the
        upgrade outright on pipx 1.8+, which can use uv as its backend — `uv pip`
        rejects that pip-only flag. It was redundant anyway."""
        cli._installer = lambda: "pipx"
        runner = _ok_runner(0)
        with redirect_stdout(io.StringIO()):
            rc = cli._self_upgrade(runner)
        self.assertEqual(rc, 0)
        self.assertEqual(runner.calls[0], ["/usr/bin/pipx", "upgrade", "specfuse"])
        self.assertNotIn("--pip-args", " ".join(runner.calls[0]))

    def test_uv_install_runs_uv_tool_upgrade(self):
        cli._installer = lambda: "uv"
        runner = _ok_runner(0)
        with redirect_stdout(io.StringIO()):
            cli._self_upgrade(runner)
        self.assertEqual(runner.calls[0],
                         ["/usr/bin/uv", "tool", "upgrade", "specfuse"])

    def test_installer_failure_propagates(self):
        cli._installer = lambda: "uv"
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            rc = cli._self_upgrade(_ok_runner(4))
        self.assertEqual(rc, 4)
        self.assertIn("failed", err.getvalue())

    def test_installer_missing_from_path_advises_instead_of_failing(self):
        cli._installer = lambda: "pipx"
        cli.shutil.which = lambda name: None
        runner = _ok_runner(0)
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli._self_upgrade(runner)
        self.assertEqual(rc, 0)
        self.assertEqual(runner.calls, [])
        self.assertIn("pipx upgrade specfuse", err.getvalue())

    def test_plain_venv_still_uses_pip(self):
        cli._installer = lambda: None
        runner = _ok_runner(0)
        with redirect_stdout(io.StringIO()):
            cli._self_upgrade(runner)
        self.assertIn("-m", runner.calls[0])
        self.assertEqual(runner.calls[0][-1], "specfuse")

    def test_no_self_upgrade_flag_skips_it_entirely(self):
        cli._installer = lambda: "uv"
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                cli.cmd_init(_args(target=d))
            runner = _ok_runner(0)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_upgrade(_args(target=d, no_self_upgrade=True),
                                     runner=runner)
            self.assertEqual(rc, 0)
            self.assertEqual(runner.calls, [])
            self.assertIn("--no-self-upgrade", out.getvalue())


class TestManagedByTool(unittest.TestCase):
    """Whether a shim check applies at all. Getting this wrong is silent: a false
    negative makes `doctor` report "nothing to check" on an install that has
    shims, so a foreign or missing one is never found."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_env = {k: os.environ.get(k) for k in ("PIPX_HOME", "UV_TOOL_DIR")}
        self._orig_root = cli._venv_root
        for key in self._orig_env:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._orig_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cli._venv_root = self._orig_root
        self._tmp.cleanup()

    def _fake_venv(self, *parts) -> Path:
        """Stand in for sys.prefix — the venv ROOT, which is what the check reads.
        Patching sys.executable would not exercise the real code path: in a pipx/uv
        venv, bin/python is a symlink to the base interpreter, so a resolved
        sys.executable points outside the venv entirely."""
        root = Path(self._tmp.name).joinpath(*parts)
        root.mkdir(parents=True, exist_ok=True)
        cli._venv_root = lambda: root
        return root

    def test_default_pipx_and_uv_paths_are_detected(self):
        for parts in (("pipx", "venvs", "specfuse"), ("uv", "tools", "specfuse")):
            with self.subTest(path=parts):
                self._fake_venv(*parts)
                self.assertTrue(cli._managed_by_tool())

    def test_relocated_uv_tool_dir_is_detected(self):
        """Regression: a real `uv tool install` under an overridden UV_TOOL_DIR
        matched neither default substring, so `doctor` skipped the check."""
        self._fake_venv("custom-tools", "specfuse")
        os.environ["UV_TOOL_DIR"] = str(Path(self._tmp.name) / "custom-tools")
        self.assertTrue(cli._managed_by_tool())

    def test_relocated_pipx_home_is_detected(self):
        self._fake_venv("custom-pipx", "venvs", "specfuse")
        os.environ["PIPX_HOME"] = str(Path(self._tmp.name) / "custom-pipx")
        self.assertTrue(cli._managed_by_tool())

    def test_plain_venv_is_not_managed(self):
        self._fake_venv("some", "venv")
        self.assertFalse(cli._managed_by_tool())

    def test_env_var_pointing_elsewhere_does_not_false_positive(self):
        self._fake_venv("some", "venv")
        os.environ["UV_TOOL_DIR"] = str(Path(self._tmp.name) / "unrelated")
        self.assertFalse(cli._managed_by_tool())

    def test_venv_root_does_not_follow_the_python_symlink(self):
        """The bug this replaced: `Path(sys.executable).resolve()` follows
        bin/python out to the BASE interpreter, so no pipx/uv install was ever
        recognised. sys.prefix must stay inside the venv."""
        venv = Path(self._tmp.name) / "uv" / "tools" / "specfuse"
        (venv / "bin").mkdir(parents=True)
        base = Path(self._tmp.name) / "managed-cpython" / "bin"
        base.mkdir(parents=True)
        (base / "python").write_text("")
        (venv / "bin" / "python").symlink_to(base / "python")
        cli._venv_root = lambda: venv
        self.assertTrue(cli._managed_by_tool())
        self.assertNotIn("managed-cpython", str(cli._venv_root()))


class TestShimDir(unittest.TestCase):
    """Which bin dir this install's shims live in."""

    def setUp(self):
        self._orig_env = {k: os.environ.get(k)
                          for k in ("PIPX_BIN_DIR", "UV_TOOL_BIN_DIR")}
        self._orig_installer = cli._installer
        for key in self._orig_env:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._orig_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cli._installer = self._orig_installer

    def test_uv_install_prefers_uv_bin_dir_even_when_pipx_var_is_set(self):
        """Regression: with both vars exported, a fixed PIPX-then-UV order pointed a
        uv install at pipx's bin dir, and doctor called all twelve commands
        foreign."""
        os.environ["PIPX_BIN_DIR"] = "/pipx/bin"
        os.environ["UV_TOOL_BIN_DIR"] = "/uv/bin"
        cli._installer = lambda: "uv"
        self.assertEqual(cli._shim_dir(), Path("/uv/bin"))

    def test_pipx_install_prefers_pipx_bin_dir(self):
        os.environ["PIPX_BIN_DIR"] = "/pipx/bin"
        os.environ["UV_TOOL_BIN_DIR"] = "/uv/bin"
        cli._installer = lambda: "pipx"
        self.assertEqual(cli._shim_dir(), Path("/pipx/bin"))

    def test_unmanaged_env_falls_back_to_either_var_then_local_bin(self):
        cli._installer = lambda: None
        self.assertEqual(cli._shim_dir(), Path.home() / ".local" / "bin")
        os.environ["UV_TOOL_BIN_DIR"] = "/uv/bin"
        self.assertEqual(cli._shim_dir(), Path("/uv/bin"))


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

    def test_fix_removes_dead_shims_and_then_exits_zero(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        shims = Path(tmp.name) / "bin"
        shims.mkdir()
        (shims / "specfuse-poller").symlink_to(Path(tmp.name) / "gone")
        (shims / "specfuse-stats").symlink_to(Path(tmp.name) / "gone")

        state = {"problems": [
            ("specfuse-poller", "orphaned shim: x", "rm x", "orphan"),
            ("specfuse-stats", "stale shim: y", "rm y", "stale"),
        ]}
        orig_managed, orig_diag, orig_shim_dir = (
            cli._managed_by_tool, cli.diagnose_shims, cli._shim_dir)
        cli._managed_by_tool = lambda: True
        cli._shim_dir = lambda: shims
        # Second call reflects the removals, as the real diagnosis would.
        def diagnose():
            found = [p for p in state["problems"] if (shims / p[0]).is_symlink()]
            return found
        cli.diagnose_shims = diagnose
        out = io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                rc = cli.cmd_doctor(_args(fix=True))
        finally:
            (cli._managed_by_tool, cli.diagnose_shims,
             cli._shim_dir) = orig_managed, orig_diag, orig_shim_dir
        self.assertEqual(rc, 0, "nothing should remain after the removals")
        self.assertFalse((shims / "specfuse-poller").is_symlink())
        self.assertFalse((shims / "specfuse-stats").is_symlink())
        self.assertIn("removed dead shim", out.getvalue())

    def test_fix_leaves_a_foreign_shim_alone(self):
        """A foreign shim WORKS — it just belongs to another install. Deleting
        another install's property is the user's call, not ours."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        shims = Path(tmp.name) / "bin"
        other = Path(tmp.name) / "other"
        shims.mkdir()
        other.mkdir()
        (other / "specfuse-authoring").write_text("")
        (shims / "specfuse-authoring").symlink_to(other / "specfuse-authoring")

        problems = [("specfuse-authoring", "shim points at another install",
                     "pick ONE owner", "foreign")]
        orig_managed, orig_diag, orig_shim_dir = (
            cli._managed_by_tool, cli.diagnose_shims, cli._shim_dir)
        cli._managed_by_tool = lambda: True
        cli.diagnose_shims = lambda: problems
        cli._shim_dir = lambda: shims
        err = io.StringIO()
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                rc = cli.cmd_doctor(_args(fix=True))
        finally:
            (cli._managed_by_tool, cli.diagnose_shims,
             cli._shim_dir) = orig_managed, orig_diag, orig_shim_dir
        self.assertEqual(rc, 1)
        self.assertTrue((shims / "specfuse-authoring").is_symlink())
        self.assertIn("another install", err.getvalue())

    def test_report_points_at_fix_when_dead_shims_are_present(self):
        orig_managed, orig_diag = cli._managed_by_tool, cli.diagnose_shims
        cli._managed_by_tool = lambda: True
        cli.diagnose_shims = lambda: [
            ("specfuse-poller", "orphaned shim: x", "rm x", "orphan")]
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                cli.cmd_doctor(_args())
        finally:
            cli._managed_by_tool, cli.diagnose_shims = orig_managed, orig_diag
        self.assertIn("doctor --fix", err.getvalue())

    def test_deprecated_commands_are_reported_without_failing(self):
        """Migration status has to be deterministic: a component's own console
        script can win the flat name inside the venv (installer-dependent), so the
        per-invocation notice in alias_main may never fire. Listing what is still
        on PATH does not care who provides it — and never changes the exit code."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        shims = Path(tmp.name) / "bin"
        shims.mkdir()
        (shims / "specfuse-loop").write_text("")
        (shims / "specfuse-authoring").write_text("")

        orig_managed, orig_diag, orig_shim_dir = (
            cli._managed_by_tool, cli.diagnose_shims, cli._shim_dir)
        cli._managed_by_tool = lambda: True
        cli.diagnose_shims = lambda: []
        cli._shim_dir = lambda: shims
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                rc = cli.cmd_doctor(_args())
        finally:
            (cli._managed_by_tool, cli.diagnose_shims,
             cli._shim_dir) = orig_managed, orig_diag, orig_shim_dir
        self.assertEqual(rc, 0, "deprecated-but-working commands are not a failure")
        text = out.getvalue()
        self.assertIn("specfuse-loop -> specfuse run", text)
        self.assertIn("specfuse-authoring -> specfuse authoring", text)
        self.assertIn("1.0.0", text)

    def test_no_deprecated_commands_reports_nothing(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        shims = Path(tmp.name) / "bin"
        shims.mkdir()
        (shims / "specfuse").write_text("")
        self.assertEqual(cli.deprecated_shims_present(shims), [])

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


class TestOutdatedComponents(unittest.TestCase):
    """The staleness advisory: the only thing in the suite that tells a user a
    component moved. Since #125 the floors are minimums, so a component release
    reaches users on their next upgrade and never prompts one — every other path
    is pull. Every test injects the fetch; none touches the network."""

    def test_release_key_orders_versions_and_tolerates_suffixes(self):
        self.assertLess(cli._release_key("0.9.3"), cli._release_key("0.10.0"))
        self.assertLess(cli._release_key("0.5.6"), cli._release_key("0.6.0"))
        self.assertEqual(cli._release_key("1.2.3rc1"), (1, 2, 3))
        self.assertIsNone(cli._release_key("not-a-version"))

    def test_reports_only_the_components_that_are_behind(self):
        installed = [("specfuse-loop", "0.10.0"),
                     ("specfuse-authoring", "0.5.6"),
                     ("specfuse-orchestrator", "0.5.0")]
        latest = {"specfuse-loop": "0.10.0", "specfuse-authoring": "0.6.0",
                  "specfuse-orchestrator": "0.5.0"}
        self.assertEqual(
            [("specfuse-authoring", "0.5.6", "0.6.0")],
            cli.outdated_components(installed=installed, fetch=latest.get))

    def test_a_local_build_ahead_of_the_index_is_not_reported(self):
        # A maintainer on an unreleased build must not be told to "upgrade" to an
        # older version.
        self.assertEqual([], cli.outdated_components(
            installed=[("specfuse-loop", "0.11.0")],
            fetch=lambda _d: "0.10.0"))

    def test_uninstalled_component_is_skipped(self):
        self.assertEqual([], cli.outdated_components(
            installed=[("specfuse-loop", "not installed")],
            fetch=lambda _d: "9.9.9"))

    def test_unreachable_index_is_silent_rather_than_an_error(self):
        # Offline, proxied, rate-limited, private index: an advisory must never
        # become the reason a diagnostic fails.
        self.assertEqual([], cli.outdated_components(
            installed=[("specfuse-loop", "0.1.0")], fetch=lambda _d: None))

    def test_unparsable_version_is_skipped_not_guessed(self):
        self.assertEqual([], cli.outdated_components(
            installed=[("specfuse-loop", "0.1.0")], fetch=lambda _d: "mystery"))

    def test_report_names_the_upgrade_path_and_the_pip_caveat(self):
        lines: list[str] = []
        behind = cli.report_outdated_components(
            fetch=lambda d: "9.9.9" if d == "specfuse-loop" else None,
            log=lines.append)
        text = "\n".join(lines)
        self.assertEqual(1, len(behind))
        self.assertIn("specfuse upgrade", text)
        # The whole reason this advisory exists: `pip install -U specfuse` looks
        # like it works, exits 0, and leaves components behind.
        self.assertIn("pip install -U specfuse", text)

    def test_report_is_silent_when_everything_is_current(self):
        lines: list[str] = []
        cli.report_outdated_components(fetch=lambda _d: None, log=lines.append)
        self.assertEqual([], lines)

    def test_doctor_runs_the_advisory_on_a_plain_venv_install(self):
        # The not-tool-managed branch returns early, and it is exactly the
        # environment where plain pip strands components — the advisory must come
        # first or the users who most need it never see it.
        seen: list[str] = []
        orig_managed = cli._managed_by_tool
        orig_report = cli.report_outdated_components
        cli._managed_by_tool = lambda: False
        cli.report_outdated_components = lambda **kw: seen.append("ran") or []
        try:
            with redirect_stdout(io.StringIO()):
                rc = cli.cmd_doctor(_args(no_network=False))
        finally:
            cli._managed_by_tool = orig_managed
            cli.report_outdated_components = orig_report
        self.assertEqual(rc, 0)
        self.assertEqual(["ran"], seen)

    def test_no_network_flag_attempts_nothing(self):
        orig_managed = cli._managed_by_tool
        orig_report = cli.report_outdated_components
        cli._managed_by_tool = lambda: False

        def _boom(**kw):
            raise AssertionError("--no-network must not reach the network")

        cli.report_outdated_components = _boom
        try:
            with redirect_stdout(io.StringIO()):
                rc = cli.cmd_doctor(_args(no_network=True))
        finally:
            cli._managed_by_tool = orig_managed
            cli.report_outdated_components = orig_report
        self.assertEqual(rc, 0)

    def test_advisory_never_changes_the_exit_code(self):
        # Being a release behind is not a broken install; `doctor` exits non-zero
        # only for things CI should gate on.
        orig_managed, orig_diag = cli._managed_by_tool, cli.diagnose_shims
        orig_report = cli.report_outdated_components
        cli._managed_by_tool = lambda: True
        cli.diagnose_shims = lambda: []
        cli.report_outdated_components = lambda **kw: [
            ("specfuse-loop", "0.1.0", "9.9.9")]
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                rc = cli.cmd_doctor(_args(no_network=False))
        finally:
            cli._managed_by_tool, cli.diagnose_shims = orig_managed, orig_diag
            cli.report_outdated_components = orig_report
        self.assertEqual(rc, 0)


class TestParser(unittest.TestCase):

    def test_version_flag_exits_zero(self):
        with self.assertRaises(SystemExit) as cm, redirect_stdout(io.StringIO()):
            cli.main(["--version"])
        self.assertEqual(cm.exception.code, 0)

    def test_version_prints_one_line_per_component_unwrapped(self):
        """argparse's built-in `action="version"` runs the string through
        HelpFormatter, which re-wrapped the component table to terminal width and
        split names across lines ("specfuse-\\nauthoring 0.5.9"). The custom action
        must emit it verbatim: one line per component, none of them broken."""
        out = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(out):
            cli.main(["--version"])
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1 + len(cli.COMPONENTS))
        for component, line in zip(cli.COMPONENTS, lines[1:], strict=True):
            self.assertTrue(line.strip().startswith(component), line)

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
