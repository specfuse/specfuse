#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""Block until every component floor this package pins is installable from PyPI.

Closes #111. The umbrella's `release` build-test installs the built wheel WITH
deps, so it must resolve `specfuse-loop`, `specfuse-orchestrator` and
`specfuse-authoring` from PyPI. The coordinated order publishes the components
first, and the workflow assumed that made them resolvable. It does not: a
component's publish job finishing and pip being able to resolve it are different
moments. At v0.9.2 the umbrella's build-test failed three minutes after a
successful component publish with

    ERROR: Could not find a version that satisfies the requirement
    specfuse-loop>=0.9.2 (from specfuse)

and an unchanged `gh run rerun --failed` went green 20s later.

**Only the simple index decides whether pip can resolve.** The obvious probe --
PyPI's JSON API -- is what made the release look ready when it was not, and its
lag is not even directionally reliable: at v0.9.2 the JSON API led, at v0.9.3 it
trailed the simple index in both directions on two different packages. The two
surfaces are independently eventually-consistent, not ordered, so gating on
anything except the surface pip actually resolves against is guesswork.

So the probe here is an install, not a lookup: `pip download --no-deps` against
the real index. It is the only check that answers the question the release
actually asks. `pip index versions` would be cheaper but is an experimental
command whose output shape is not a contract.

Floors are read from `pyproject.toml`, never hardcoded -- a second copy of a
version another repo owns is precisely the drift
`methodology/rules/borrowed-vocabularies.md` exists to prevent, and this module
would be the copy that goes stale.

Waiting is bounded and fails loudly, naming propagation: a component that was
never published must still surface as a red release rather than a hang, and the
raw pip error ("could not find a version") reads as a bad pin or a failed
component release, which invites the wrong fix.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterable

import tomllib

# Only the suite's own components are gated. Any other dependency is an ordinary
# third-party pin that was on the index long before this release started.
COMPONENT_PREFIX = "specfuse-"

# A dependency's lower bound: `specfuse-loop>=0.9.3`. Extras, environment
# markers and upper bounds may follow; only the name and the floor matter here.
_FLOOR = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*>=\s*"
    r"(?P<version>[^,;\s\]]+)"
)

DEFAULT_ATTEMPTS = 30
DEFAULT_DELAY_SECONDS = 10


def component_floors(pyproject: Path) -> dict[str, str]:
    """`{'specfuse-loop': '0.9.3', ...}` from `[project].dependencies`.

    A component pinned without a `>=` floor is skipped rather than guessed at:
    there is no single version to wait for, and inventing one would gate the
    release on a number this file made up.
    """
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    floors: dict[str, str] = {}
    for raw in data.get("project", {}).get("dependencies", []):
        m = _FLOOR.match(str(raw))
        if m and m.group("name").lower().startswith(COMPONENT_PREFIX):
            floors[m.group("name")] = m.group("version")
    return floors


def pip_can_resolve(name: str, version: str) -> bool:
    """True when pip can actually fetch `name==version` from the index.

    A download, not a lookup — see the module docstring on why the JSON API is
    not a usable signal. `--no-deps` keeps this to one artifact, and
    `--no-cache-dir` stops a previous attempt in the same job from answering
    from cache and reporting a stale yes.
    """
    with tempfile.TemporaryDirectory() as dest:
        return subprocess.run(
            [sys.executable, "-m", "pip", "download", "--no-deps",
             "--no-cache-dir", "--quiet", "--dest", dest, f"{name}=={version}"],
            capture_output=True,
            # A non-zero exit is the expected answer while the index catches up,
            # not an error to raise on — the return code IS the signal.
            check=False,
        ).returncode == 0


def await_resolvable(
    floors: dict[str, str],
    *,
    probe: Callable[[str, str], bool] = pip_can_resolve,
    attempts: int = DEFAULT_ATTEMPTS,
    delay: float = DEFAULT_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> list[str]:
    """Poll until every floor resolves. Returns the ones that never did.

    Each component is waited on in turn rather than in parallel: they publish in
    a fixed order, the whole budget is available to whichever is slowest, and a
    serial log says plainly which one the release is waiting on.
    """
    unresolved: list[str] = []
    for name, version in sorted(floors.items()):
        for attempt in range(1, attempts + 1):
            if probe(name, version):
                log(f"{name}=={version} resolvable (attempt {attempt})")
                break
            if attempt == attempts:
                unresolved.append(f"{name}=={version}")
                break
            # Logged every attempt: a silent wait is indistinguishable from a
            # hung job in the Actions UI.
            log(f"{name}=={version} not on the index yet "
                f"(attempt {attempt}/{attempts}), retrying in {delay:g}s")
            sleep(delay)
    return unresolved


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    pyproject = Path(args[0]) if args else Path("pyproject.toml")

    floors = component_floors(pyproject)
    if not floors:
        # Not a pass: this gate exists because the umbrella pins components. If
        # it finds none, the parse is wrong or the dependency set moved, and
        # staying quiet would report coverage while checking nothing.
        print(f"::error::no {COMPONENT_PREFIX}* floors found in {pyproject} — "
              "the release gate parsed no components to wait for")
        return 1

    print("waiting for component floors: "
          + ", ".join(f"{n}=={v}" for n, v in sorted(floors.items())))
    unresolved = await_resolvable(floors)
    if unresolved:
        window = DEFAULT_ATTEMPTS * DEFAULT_DELAY_SECONDS
        print(f"::error::not installable from PyPI after {window}s: "
              f"{', '.join(unresolved)} — either the component release never "
              "published, or index propagation is slower than this gate's "
              "window. This is NOT a bad pin: the floor is read from pyproject.")
        return 1

    print("all component floors resolvable — proceeding to build-test")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
