#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""In-tree PEP 517 backend: mirror `methodology/` into the package before building.

`methodology/` is the canonical, human-authored home of the core substrate and
stays at the repo root — the orchestrator's ownership manifest names that exact
path as `canonical_source`, and every doc cross-link points at it. But a wheel can
only carry files that live inside a package directory, so before this the umbrella
shipped **none** of it: a freshly built wheel held 10 entries and not one line of
`methodology/`.

That is why the substrate reached consumers by hand-copying out of git, and why
core's own event schema sat two releases behind the orchestrator's until #135.
There was never a distribution mechanism, only a convention.

So the build mirrors `methodology/` to `specfuse/_methodology/`, which is
gitignored: generated, never committed, so there is no second copy for a reviewer
to edit by mistake. This is the same shape the orchestrator's `hatch_build.py`
already uses for `shared/` -> `specfuse/orchestrator/_substrate/`; the umbrella is
on setuptools rather than hatchling, so it wraps the backend instead of
registering a build hook. Wrapping keeps `setup.py` out of the tree.

Every hook mirrors, including `build_editable`: an editable install is what CI and
contributors run, and a resolver that works only after a wheel build is a resolver
that is broken exactly where it is developed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import build_meta as _orig

# Re-export the rest of the PEP 517 surface unchanged.
prepare_metadata_for_build_wheel = _orig.prepare_metadata_for_build_wheel
get_requires_for_build_wheel = _orig.get_requires_for_build_wheel
get_requires_for_build_sdist = _orig.get_requires_for_build_sdist

# Some setuptools versions expose the editable hooks only conditionally.
get_requires_for_build_editable = getattr(_orig, "get_requires_for_build_editable", None)
prepare_metadata_for_build_editable = getattr(
    _orig, "prepare_metadata_for_build_editable", None)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "methodology"
MIRROR = ROOT / "specfuse" / "_methodology"


def _mirror() -> None:
    """Replace `specfuse/_methodology/` with a fresh copy of `methodology/`.

    Removed first rather than merged: a file deleted from `methodology/` must
    disappear from the wheel too, and an additive copy would keep shipping it.
    """
    if not SOURCE.is_dir():
        # An sdist build unpacks a tree that must still contain methodology/ —
        # see [tool.setuptools.sdist]. Failing loudly beats shipping a wheel whose
        # substrate is silently empty, which is the exact failure this exists to end.
        raise RuntimeError(
            f"cannot build: {SOURCE} is missing, so the wheel would ship no "
            "methodology substrate")
    if MIRROR.exists():
        shutil.rmtree(MIRROR)
    shutil.copytree(SOURCE, MIRROR)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    _mirror()
    return _orig.build_wheel(wheel_directory, config_settings, metadata_directory)


def build_sdist(sdist_directory, config_settings=None):
    _mirror()
    return _orig.build_sdist(sdist_directory, config_settings)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    _mirror()
    return _orig.build_editable(wheel_directory, config_settings, metadata_directory)
