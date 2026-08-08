#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""The distribution's shape: one command, deprecated aliases, hard dependencies.

`specfuse` is the suite's single console script; every component command is a
subcommand of it. The flat `specfuse-*` names remain only as deprecated aliases
routed through `specfuse.cli:alias_main`, and all of them are the umbrella's OWN
entry points — pipx/uv surface only those, never a dependency's, so declaring
them here is what keeps `pipx install specfuse` flagless. Combined with hard
dependencies (not extras — those resolve once and never re-resolve), that is what
makes one install own and upgrade the whole suite.
"""

from __future__ import annotations

import importlib
import re
import unittest
from pathlib import Path

from specfuse import cli

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

_EXPECTED = {
    "specfuse": "specfuse.cli:main",
    # Deprecated aliases: all one function, which recovers the invoked name from
    # sys.argv[0]. Removed in 1.0.0.
    **{flat: "specfuse.cli:alias_main" for flat in cli.ALIAS_TO_SUBCOMMAND},
}


def _section(name: str) -> str:
    """The raw text of a pyproject `[name]` table, up to the next table."""
    text = PYPROJECT.read_text(encoding="utf-8")
    block = text.split(f"[{name}]", 1)[1]
    return re.split(r"^\[", block, maxsplit=1, flags=re.MULTILINE)[0]


def _scripts() -> dict[str, str]:
    out = {}
    for m in re.finditer(r'(?m)^([A-Za-z0-9_-]+)\s*=\s*"([^"]+)"',
                         _section("project.scripts")):
        out[m.group(1)] = m.group(2)
    return out


def _requirement_names(section: str) -> set[str]:
    return set(re.findall(r'"([A-Za-z0-9_.-]+?)(?:[><=~!]|")', section))


class TestEntryPoints(unittest.TestCase):

    def test_every_suite_console_script_is_declared(self):
        scripts = _scripts()
        for name, target in _EXPECTED.items():
            self.assertIn(name, scripts,
                          f"{name} must be declared so pipx/uv expose it on PATH")
            self.assertEqual(scripts[name], target)

    def test_no_undeclared_extra_scripts(self):
        """Every declared script is accounted for above — a new component command
        must be added to the expected map, not smuggled in."""
        self.assertEqual(set(_scripts()), set(_EXPECTED))

    def test_every_target_imports_and_is_callable(self):
        for name, target in sorted(_scripts().items()):
            module_name, _, func_name = target.partition(":")
            with self.subTest(script=name):
                module = importlib.import_module(module_name)
                self.assertTrue(callable(getattr(module, func_name, None)),
                                f"{target} is not a callable entry point")

    def test_every_delegated_target_imports_and_is_callable(self):
        """The cost of dispatching into the components: cli.py names eleven
        modules this repo does not own, and the dispatch is a deferred import — so
        a component that renames one produces a broken subcommand at RUN time, in
        a release that was green. Resolve them all here instead."""
        for subcommand, (target, _flat, _help) in sorted(cli.DELEGATED_COMMANDS.items()):
            module_name, _, func_name = target.partition(":")
            with self.subTest(subcommand=subcommand):
                module = importlib.import_module(module_name)
                self.assertTrue(callable(getattr(module, func_name, None)),
                                f"{target} is not a callable entry point")

    def test_every_alias_maps_back_to_a_subcommand(self):
        """The alias table is derived from DELEGATED_COMMANDS, so the two cannot
        drift — assert the property rather than the derivation."""
        self.assertEqual(len(cli.ALIAS_TO_SUBCOMMAND), len(cli.DELEGATED_COMMANDS))
        for flat, subcommand in cli.ALIAS_TO_SUBCOMMAND.items():
            self.assertEqual(cli.DELEGATED_COMMANDS[subcommand][1], flat)


class TestSuiteDependencies(unittest.TestCase):
    """The distribution shape: components are hard deps, extras are gone."""

    def test_all_components_are_hard_dependencies(self):
        deps = _requirement_names(_section("project").split("dependencies", 1)[1])
        for component in cli.COMPONENTS:
            self.assertIn(component, deps,
                          f"{component} must be a hard dependency so `pipx upgrade` "
                          f"re-resolves it")

    def test_suite_extras_are_removed(self):
        """`[orchestrator]`, `[authoring]` and `[all]` are what forced
        --include-deps and stranded installs on stale components. Only `dev`
        (developing this package) may remain."""
        extras = _section("project.optional-dependencies")
        keys = set(re.findall(r"(?m)^([A-Za-z0-9_-]+)\s*=", extras))
        self.assertEqual(keys, {"dev"})

    def test_cli_version_matches_pyproject(self):
        declared = re.search(r'(?m)^version\s*=\s*"([^"]+)"',
                             _section("project")).group(1)
        self.assertEqual(cli.__version__, declared)


class TestVersionReport(unittest.TestCase):

    def test_report_names_umbrella_and_every_component(self):
        report = cli.version_report()
        self.assertIn(f"specfuse {cli.__version__}", report)
        for component in cli.COMPONENTS:
            self.assertIn(component, report)


if __name__ == "__main__":
    unittest.main()
