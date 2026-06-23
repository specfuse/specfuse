#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""The umbrella must expose all three console scripts.

pipx only surfaces the installed package's OWN entry points, not its
dependencies'. So `pip install specfuse` must declare specfuse-loop and
specfuse-lint itself (re-exporting the driver's mains) or a `pipx install
specfuse` leaves them off PATH and the driver/lint commands appear missing.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

_EXPECTED = {
    "specfuse": "specfuse.cli:main",
    "specfuse-loop": "specfuse.loop.loop:main",
    "specfuse-lint": "specfuse.loop.lint_plan:main",
}


def _scripts() -> dict[str, str]:
    text = PYPROJECT.read_text(encoding="utf-8")
    block = text.split("[project.scripts]", 1)[1]
    # stop at the next [section]
    block = re.split(r"^\[", block, maxsplit=1, flags=re.MULTILINE)[0]
    out = {}
    for m in re.finditer(r'(?m)^([A-Za-z0-9_-]+)\s*=\s*"([^"]+)"', block):
        out[m.group(1)] = m.group(2)
    return out


class TestEntryPoints(unittest.TestCase):

    def test_all_three_console_scripts_declared(self):
        scripts = _scripts()
        for name, target in _EXPECTED.items():
            self.assertIn(name, scripts,
                          f"{name} must be declared so pipx exposes it on PATH")
            self.assertEqual(scripts[name], target)


if __name__ == "__main__":
    unittest.main()
