#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""Every relative link in this repo's own markdown resolves to something on disk.

Relative links rot silently. The docs that cross-reference each other are written
in separate PRs, and a link to a file that has not merged yet — or to one that was
later renamed — reads exactly like a link that works until someone clicks it.
Nothing in CI noticed: `ci` runs pytest and ruff, neither of which reads markdown.

Two near-misses in one afternoon prompted this. `methodology/overview.md` and
`docs/ways-of-working.md` each link to the other and merged as separate PRs, so
whichever landed first left main carrying a dangling link until the second did;
and the same overview's `rules/` row enumerated five rules while the directory it
points at had grown a sixth. Both were caught by a human reading the diff, which
is the reviewing practice that had already failed elsewhere in this repo (see
`methodology/rules/borrowed-vocabularies.md` on why memory is not enough).

Scope — `plugins/` is deliberately NOT scanned. Those copies are publish output
(see `docs/plan-unify-plugin-sourcing.md`); `plugin-drift-guard` fails CI on any
hand-edit, so a broken link inside one can only be fixed in the source repo and
re-published. Gating on something this repo cannot fix would leave PRs blocked
with no in-repo remedy. Links *pointing into* `plugins/` are still checked — only
the scanning of files under it is skipped.

Not covered: anchor fragments (`#section`) and external URLs. Anchors would mean
reimplementing GitHub's heading slugification, and external URLs would make CI
fail on someone else's outage.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

# Directories whose markdown this repo does not author. See the module docstring.
# Anything dot-prefixed is skipped too — .pytest_cache and .venv ship READMEs of
# their own, and failing CI over a link inside a build artifact would be noise.
#
# `_methodology/` is the build backend's generated mirror of `methodology/`. Its
# links are authored relative to the canonical location and only resolve there, so
# scanning the copy reports breakage that does not exist. The canonical tree IS
# scanned, which is what the links are written against.
SKIPPED_DIRS = {"plugins", "node_modules", "__pycache__", "build", "dist",
                "_methodology"}

# Targets that name somewhere other than this working tree.
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)

# ``` or ~~~ fenced blocks: examples in them are illustrations, not real links.
FENCE = re.compile(r"^(?P<fence>```|~~~).*?^(?P=fence)", re.MULTILINE | re.DOTALL)

# Inline code spans. Stripped so a documented *example* of link syntax does not
# register as a link. Labels like [`glossary.md`](glossary.md) survive this — the
# backticks sit inside the label, and the `](target)` half is what gets matched.
CODE_SPAN = re.compile(r"`[^`\n]*`")

# [label](target), ![alt](target), and an optional "title" after the target.
INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)>\s]+)>?(?:\s+\"[^\"]*\")?\s*\)")

# Reference definitions: [label]: target "optional title"
REF_LINK = re.compile(r"(?m)^[ \t]{0,3}\[[^\]]+\]:[ \t]+<?([^>\s]+)>?")


def _markdown_files() -> list[Path]:
    out = []
    for path in ROOT.rglob("*.md"):
        rel = path.relative_to(ROOT)
        if SKIPPED_DIRS.isdisjoint(rel.parts) and not any(
            part.startswith(".") for part in rel.parts
        ):
            out.append(path)
    return sorted(out)


def _targets(text: str) -> list[str]:
    """Every link target in `text`, fenced blocks and code spans removed."""
    stripped = CODE_SPAN.sub("", FENCE.sub("", text))
    return INLINE_LINK.findall(stripped) + REF_LINK.findall(stripped)


def _is_relative(target: str) -> bool:
    return bool(target) and not target.startswith("#") and not EXTERNAL.match(target)


class TestDocLinks(unittest.TestCase):

    def test_repo_has_markdown_to_check(self):
        # A scanner that silently matches nothing passes forever. Anchor it: the
        # skip list or the glob breaking should fail here, not go unnoticed.
        files = _markdown_files()
        self.assertGreater(len(files), 5,
                           "found almost no markdown — the walk or SKIPPED_DIRS is wrong")
        names = {f.relative_to(ROOT).as_posix() for f in files}
        for expected in ("README.md", "methodology/methodology.md"):
            self.assertIn(expected, names, f"{expected} must be among the scanned files")

    def test_every_relative_link_resolves(self):
        broken = []
        for path in _markdown_files():
            rel = path.relative_to(ROOT).as_posix()
            for target in _targets(path.read_text(encoding="utf-8")):
                if not _is_relative(target):
                    continue
                # Strip the anchor: the file must exist, the fragment is not checked.
                resolved = (path.parent / unquote(target.split("#", 1)[0])).resolve()
                if not resolved.exists():
                    broken.append(f"{rel} -> {target}")

        self.assertEqual([], broken,
                         "relative links pointing at nothing:\n  " + "\n  ".join(broken))

    def test_no_link_escapes_the_repository(self):
        # A `../../` that climbs out of the tree resolves on the author's machine
        # and nowhere else. exists() alone would not catch it.
        escaping = []
        for path in _markdown_files():
            rel = path.relative_to(ROOT).as_posix()
            for target in _targets(path.read_text(encoding="utf-8")):
                if not _is_relative(target):
                    continue
                resolved = (path.parent / unquote(target.split("#", 1)[0])).resolve()
                if not resolved.is_relative_to(ROOT):
                    escaping.append(f"{rel} -> {target}")

        self.assertEqual([], escaping,
                         "links resolving outside the repository:\n  " + "\n  ".join(escaping))


if __name__ == "__main__":
    unittest.main()
