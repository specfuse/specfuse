#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""Tests for the `specfuse` umbrella CLI. The pip runner is injected/mocked so no
real install happens."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from types import SimpleNamespace

import specfuse.cli as cli


def _ok_runner(rc=0):
    return lambda cmd: SimpleNamespace(returncode=rc)


class TestUpgrade(unittest.TestCase):

    def test_upgrade_success_prints_plugin_hint(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli.cmd_upgrade(SimpleNamespace(), runner=_ok_runner(0))
        self.assertEqual(rc, 0)
        self.assertIn("/plugin update specfuse@specfuse", out.getvalue())

    def test_upgrade_pip_failure_propagates(self):
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli.cmd_upgrade(SimpleNamespace(), runner=_ok_runner(1))
        self.assertEqual(rc, 1)
        self.assertIn("failed", err.getvalue())

    def test_upgrade_invokes_pip_upgrade(self):
        seen = {}
        def runner(cmd):
            seen["cmd"] = cmd
            return SimpleNamespace(returncode=0)
        with redirect_stdout(io.StringIO()):
            cli.cmd_upgrade(SimpleNamespace(), runner=runner)
        self.assertIn("install", seen["cmd"])
        self.assertIn("--upgrade", seen["cmd"])
        self.assertIn("specfuse-loop", seen["cmd"])


class TestInit(unittest.TestCase):

    def test_init_rejects_non_directory(self):
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli.cmd_init(SimpleNamespace(target="/no/such/dir"), runner=_ok_runner(0))
        self.assertEqual(rc, 2)

    def test_init_valid_dir_installs_and_prints_steps(self):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.cmd_init(SimpleNamespace(target=d), runner=_ok_runner(0))
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("specfuse-loop", text)
            self.assertIn("init.sh", text)        # points at the scaffold bootstrap
            self.assertIn("/plugin", text)

    def test_init_pip_failure_propagates(self):
        with tempfile.TemporaryDirectory() as d:
            with redirect_stderr(io.StringIO()):
                rc = cli.cmd_init(SimpleNamespace(target=d), runner=_ok_runner(1))
            self.assertEqual(rc, 1)


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

    def test_main_dispatches_upgrade(self):
        from unittest import mock
        with mock.patch.object(cli.subprocess, "run",
                               return_value=SimpleNamespace(returncode=0)) as m:
            with redirect_stdout(io.StringIO()):
                rc = cli.main(["upgrade"])
        self.assertEqual(rc, 0)
        self.assertTrue(m.called)


if __name__ == "__main__":
    unittest.main()
