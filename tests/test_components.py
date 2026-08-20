#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""Tests for component detection and for init/upgrade honouring it.

The bug these pin: `specfuse init` / `specfuse upgrade` ran the loop's scaffold
on every repo. Pointing them at an authoring (specs) repo dropped a whole
gate-cycle driver scaffold into a repo that runs no driver.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from specfuse import cli, components


def _args(**kw):
    kw.setdefault("dry_run", False)
    kw.setdefault("ci_check", None)
    kw.setdefault("plugins", None)
    kw.setdefault("components", None)
    kw.setdefault("no_self_upgrade", True)
    return SimpleNamespace(**kw)


def _ok_runner(rc=0):
    calls = []

    def runner(cmd):
        calls.append(cmd)
        return SimpleNamespace(returncode=rc)

    runner.calls = calls
    return runner


def _touch(root: Path, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


class TestDetect(unittest.TestCase):

    def test_empty_repo_detects_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(components.detect(d), [])

    def test_loop_scaffold_detects_loop_only(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(Path(d), ".specfuse/VERSION")
            self.assertEqual(components.detect(d), [components.LOOP])

    def test_legacy_loop_tree_without_a_version_stamp_still_detects(self):
        """A pre-stamp init.sh scaffold must not read as a fresh repo — that
        would re-init it rather than overlay it."""
        with tempfile.TemporaryDirectory() as d:
            _touch(Path(d), ".specfuse/templates/PLAN.template.md")
            self.assertEqual(components.detect(d), [components.LOOP])

    def test_authoring_kit_detects_authoring_only(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(Path(d), ".specfuse/authoring/VERSION")
            self.assertEqual(components.detect(d), [components.AUTHORING])

    def test_pre_overlay_authoring_project_detects_authoring(self):
        """A project created before the kit moved under `.specfuse/authoring/`
        has only the project skeleton. Both halves are needed: `api/specs` alone
        is not an authoring repo, and neither is a stray *-project.json."""
        with tempfile.TemporaryDirectory() as d:
            _touch(Path(d), "api/specs/v1/openapi.yaml")
            self.assertEqual(components.detect(d), [])
            _touch(Path(d), "widget-project.json")
            self.assertEqual(components.detect(d), [components.AUTHORING])

    def test_orchestrator_substrate_detects_orchestrator_only(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(Path(d), ".specfuse/templates.yaml")
            self.assertEqual(components.detect(d), [components.ORCHESTRATOR])

    def test_loop_templates_dir_and_orchestrator_templates_yaml_do_not_collide(self):
        """`.specfuse/templates` (loop, a dir) vs `.specfuse/templates.yaml`
        (orchestrator, a file) — one must never be read as the other."""
        with tempfile.TemporaryDirectory() as d:
            _touch(Path(d), ".specfuse/templates.yaml")
            self.assertNotIn(components.LOOP, components.detect(d))

    def test_a_repo_can_have_several_components(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(Path(d), ".specfuse/VERSION")
            _touch(Path(d), ".specfuse/authoring/VERSION")
            _touch(Path(d), ".specfuse/issue-templates/spec-issue.md")
            self.assertEqual(
                components.detect(d),
                [components.LOOP, components.AUTHORING, components.ORCHESTRATOR])

    def test_detection_is_reported_in_install_order(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(Path(d), ".specfuse/authoring/VERSION")
            _touch(Path(d), ".specfuse/VERSION")
            self.assertEqual(components.detect(d)[0], components.LOOP)

    def test_orchestrator_kind_follows_the_role_config_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(components.orchestrator_kind(d), "component")
            _touch(Path(d), ".specfuse/agents/specs/CLAUDE.md")
            self.assertEqual(components.orchestrator_kind(d), "specs")

    def test_detect_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            components.detect(d)
            self.assertEqual(list(Path(d).iterdir()), [])


class TestComponentsFlag(unittest.TestCase):

    def test_parses_a_comma_list_into_install_order(self):
        ns = cli.build_parser().parse_args(
            ["upgrade", "/tmp/x", "--components", "orchestrator, loop"])
        self.assertEqual(ns.components, ["loop", "orchestrator"])

    def test_rejects_unknown_names(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            cli.build_parser().parse_args(["init", "/tmp/x", "--components", "nope"])

    def test_defaults_to_none(self):
        self.assertIsNone(cli.build_parser().parse_args(["init"]).components)


class TestSelection(unittest.TestCase):

    def test_flag_wins_over_detection(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(Path(d), ".specfuse/VERSION")
            selected, why = cli._selected_components(
                _args(target=d, components=["authoring"]), Path(d))
            self.assertEqual(selected, ["authoring"])
            self.assertIn("--components", why)

    def test_detection_wins_over_the_default(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(Path(d), ".specfuse/authoring/VERSION")
            selected, why = cli._selected_components(_args(target=d), Path(d))
            self.assertEqual(selected, ["authoring"])
            self.assertIn("detected", why)

    def test_fresh_repo_defaults_to_the_loop(self):
        with tempfile.TemporaryDirectory() as d:
            selected, why = cli._selected_components(_args(target=d), Path(d))
            self.assertEqual(selected, [components.LOOP])
            self.assertIn("--components", why)

    def test_selected_components_imply_their_plugins(self):
        args = _args(target=".", plugins=["orchestrator"])
        self.assertEqual(sorted(cli._plugins_for(args, ["loop", "authoring"])),
                         ["authoring", "orchestrator", "specfuse"])


class TestUpgradeRespectsDetection(unittest.TestCase):
    """The regression itself, at the command level."""

    def _authoring_repo(self, d):
        root = Path(d)
        (root / ".specfuse" / "authoring").mkdir(parents=True)
        (root / ".specfuse" / "authoring" / "VERSION").write_text(
            "0.0.1\n", encoding="utf-8")
        return root

    def test_authoring_repo_gets_no_loop_scaffold(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._authoring_repo(d)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                rc = cli.cmd_upgrade(_args(target=d), runner=_ok_runner(0))
            self.assertEqual(rc, 0)
            # The loop's own stamp and its scaffold dirs must be absent.
            self.assertFalse((root / ".specfuse" / "VERSION").exists())
            self.assertFalse((root / ".specfuse" / "templates").exists())
            self.assertFalse((root / ".specfuse" / "rules").exists())
            # The authoring kit did get refreshed.
            self.assertTrue((root / ".specfuse" / "authoring" / "handbooks").is_dir())

    def test_authoring_repo_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._authoring_repo(d)
            before = sorted(p.relative_to(root).as_posix()
                            for p in root.rglob("*"))
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                rc = cli.cmd_upgrade(_args(target=d, dry_run=True),
                                     runner=_ok_runner(0))
            self.assertEqual(rc, 0)
            self.assertEqual(
                before,
                sorted(p.relative_to(root).as_posix() for p in root.rglob("*")))
            self.assertIn("detected", out.getvalue())

    def test_authoring_repo_enables_the_authoring_plugin(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._authoring_repo(d)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                cli.cmd_upgrade(_args(target=d), runner=_ok_runner(0))
            settings = json.loads(
                (root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertIs(settings["enabledPlugins"]["specfuse-authoring@specfuse"],
                          True)

    def test_loop_repo_still_gets_the_loop_scaffold(self):
        """The default path must not regress: a driver repo upgrades as before."""
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                cli.cmd_init(_args(target=d))
            root = Path(d)
            self.assertTrue((root / ".specfuse" / "VERSION").is_file())
            self.assertFalse((root / ".specfuse" / "authoring").exists())
            with redirect_stdout(io.StringIO()):
                rc = cli.cmd_upgrade(_args(target=d), runner=_ok_runner(0))
            self.assertEqual(rc, 0)
            self.assertFalse((root / ".specfuse" / "authoring").exists())

    def test_components_flag_forces_the_authoring_kit_onto_a_fresh_repo(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                rc = cli.cmd_init(_args(target=d, components=["authoring"]))
            self.assertEqual(rc, 0)
            self.assertTrue((root / ".specfuse" / "authoring" / "VERSION").is_file())
            self.assertFalse((root / ".specfuse" / "VERSION").exists())


if __name__ == "__main__":
    unittest.main()
