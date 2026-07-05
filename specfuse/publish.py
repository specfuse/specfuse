#!/usr/bin/env python3
#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""Publish a plugin from its source repo into the marketplace `plugins/` tree.

This is the single, marketplace-owned publish step (see
docs/plan-unify-plugin-sourcing.md). Given a plugin name, a checkout of its
source repo, and the release version, it regenerates `plugins/<name>/` in the
marketplace from `<source_checkout>/plugins/<name>/` and stamps
`plugin.json.version` to the release version.

Design invariants:
  * **Near-pure copy.** The only transformation is the version stamp; the source
    plugin dir is otherwise reproduced verbatim.
  * **Idempotent.** If the regenerated tree is byte-identical to what is already
    committed, nothing is written and `publish()` returns False. A package-only
    release therefore produces no marketplace change.
  * **Uniform layout.** Every source repo holds its plugin at `plugins/<name>/`
    (the loop vendors its own `.specfuse/skills/` from there); this script makes
    no per-plugin special cases.

The version stamp couples `plugin.json.version` to the source package's released
version (`plugin@X == package@X == tag vX`).
"""
from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
import tempfile
from pathlib import Path

MARKETPLACE_MANIFEST = Path(".claude-plugin/marketplace.json")


def load_manifest(marketplace_root: Path) -> dict:
    path = marketplace_root / MARKETPLACE_MANIFEST
    return json.loads(path.read_text(encoding="utf-8"))


def plugin_entry(manifest: dict, name: str) -> dict:
    for entry in manifest.get("plugins", []):
        if entry.get("name") == name:
            return entry
    raise KeyError(f"plugin {name!r} not listed in {MARKETPLACE_MANIFEST}")


def _stamp_version(plugin_dir: Path, version: str) -> None:
    """Set plugin.json.version = version, preserving key order and formatting."""
    pj = plugin_dir / ".claude-plugin" / "plugin.json"
    if not pj.is_file():
        raise FileNotFoundError(f"source plugin has no {pj.relative_to(plugin_dir)}")
    data = json.loads(pj.read_text(encoding="utf-8"))
    data["version"] = version
    pj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _trees_equal(a: Path, b: Path) -> bool:
    """Recursively compare two directory trees by name and byte content."""
    if not a.exists() or not b.exists():
        return False
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(_trees_equal(a / d, b / d) for d in cmp.common_dirs)


def managed_plugins(manifest: dict) -> list[dict]:
    """Entries the publish mechanism owns (`managed: true`).

    A plugin becomes managed once its source repo has been onboarded to the
    uniform layout (holds plugins/<name>/). Un-onboarded plugins are skipped by
    the publish flow and the drift-guard until their onboarding gate lands.
    """
    return [e for e in manifest.get("plugins", []) if e.get("managed") is True]


def _source_dir(source_checkout: Path, name: str) -> Path:
    src = source_checkout / "plugins" / name
    if not src.is_dir():
        raise FileNotFoundError(
            f"source plugin not found at {src} — every source repo must hold its "
            f"plugin at plugins/<name>/ (see the unify-plugin-sourcing plan)")
    return src


def _stage(source_checkout: Path, name: str, version: str, tmp: Path) -> Path:
    """Copy the source plugin into tmp and stamp its version. Returns the dir."""
    staged = tmp / name
    shutil.copytree(_source_dir(source_checkout, name), staged)
    _stamp_version(staged, version)
    return staged


def publish(name: str, source_checkout: Path, version: str,
            marketplace_root: Path = Path(".")) -> bool:
    """Regenerate marketplace plugins/<name>/ from the source checkout.

    Returns True if the committed copy changed, False if it was already
    byte-identical (idempotent no-op).
    """
    plugin_entry(load_manifest(marketplace_root), name)  # validate it is declared
    dest = marketplace_root / "plugins" / name

    with tempfile.TemporaryDirectory() as tmp:
        staged = _stage(source_checkout, name, version, Path(tmp))
        if _trees_equal(staged, dest):
            return False
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(staged, dest)
        return True


def verify(name: str, source_checkout: Path, version: str,
           marketplace_root: Path = Path(".")) -> bool:
    """Drift-guard: is the committed marketplace copy a faithful publish?

    Regenerates the plugin from the source checkout (at `version`) into a temp
    dir and compares to the committed copy WITHOUT writing. Returns True when
    they match (no drift), False when the committed copy diverges — i.e. it was
    hand-edited, mis-merged, or produced by a different source state.
    """
    plugin_entry(load_manifest(marketplace_root), name)
    dest = marketplace_root / "plugins" / name
    with tempfile.TemporaryDirectory() as tmp:
        staged = _stage(source_checkout, name, version, Path(tmp))
        return _trees_equal(staged, dest)


def committed_version(name: str, marketplace_root: Path = Path(".")) -> str:
    """The version stamped in the committed plugin.json (the drift-guard's pin)."""
    pj = marketplace_root / "plugins" / name / ".claude-plugin" / "plugin.json"
    return json.loads(pj.read_text(encoding="utf-8"))["version"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Publish a plugin from its source repo into the marketplace.")
    ap.add_argument("name", help="plugin name, e.g. specfuse-orchestrator")
    ap.add_argument("--source", required=True, type=Path,
                    help="path to a checkout of the plugin's source repo")
    ap.add_argument("--version", required=True,
                    help="release version to stamp into plugin.json (= the PyPI package version)")
    ap.add_argument("--marketplace-root", type=Path, default=Path("."),
                    help="marketplace repo root (default: cwd)")
    ap.add_argument("--check", action="store_true",
                    help="drift-guard: verify the committed copy matches a fresh publish "
                         "WITHOUT writing; exit 1 on drift")
    args = ap.parse_args(argv)

    try:
        if args.check:
            if verify(args.name, args.source, args.version, args.marketplace_root):
                print(f"ok: {args.name} @ {args.version} matches source")
                return 0
            sys.stderr.write(
                f"DRIFT: plugins/{args.name} does not match a fresh publish of "
                f"{args.name} @ {args.version} from {args.source}. The marketplace "
                f"copy must only ever be publish output — edit the source repo and "
                f"re-publish, never hand-edit plugins/.\n")
            return 1
        changed = publish(args.name, args.source, args.version, args.marketplace_root)
    except (KeyError, FileNotFoundError) as e:
        sys.stderr.write(f"error: {e}\n")
        return 2

    print(f"{'published' if changed else 'no change'}: {args.name} @ {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
