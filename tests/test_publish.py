# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
"""Tests for the marketplace publish step (specfuse/publish.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from specfuse import publish as pub


def _make_source(root: Path, name: str, *, version: str = "0.1.0",
                 skill_body: str = "# do a thing\n") -> Path:
    """Create a minimal source-repo checkout holding plugins/<name>/."""
    plugin = root / "plugins" / name
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": name, "version": version, "description": "d"}, indent=2) + "\n")
    (plugin / "skills" / "do-thing").mkdir(parents=True)
    (plugin / "skills" / "do-thing" / "SKILL.md").write_text(skill_body)
    return root


def _make_marketplace(root: Path, *names: str) -> Path:
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": "specfuse",
        "plugins": [{"name": n, "source": f"./plugins/{n}", "source_repo": f"specfuse/{n}"}
                    for n in names],
    }, indent=2) + "\n")
    return root


def test_publish_creates_and_stamps_version(tmp_path):
    src = _make_source(tmp_path / "src", "p")
    mkt = _make_marketplace(tmp_path / "mkt", "p")

    changed = pub.publish("p", src, "1.2.3", mkt)

    assert changed is True
    pj = json.loads((mkt / "plugins" / "p" / ".claude-plugin" / "plugin.json").read_text())
    assert pj["version"] == "1.2.3"  # stamped, not the source's 0.1.0
    assert (mkt / "plugins" / "p" / "skills" / "do-thing" / "SKILL.md").is_file()


def test_publish_is_idempotent(tmp_path):
    src = _make_source(tmp_path / "src", "p")
    mkt = _make_marketplace(tmp_path / "mkt", "p")

    assert pub.publish("p", src, "1.2.3", mkt) is True
    # second run with identical inputs writes nothing
    assert pub.publish("p", src, "1.2.3", mkt) is False


def test_publish_detects_content_change(tmp_path):
    src = _make_source(tmp_path / "src", "p")
    mkt = _make_marketplace(tmp_path / "mkt", "p")
    pub.publish("p", src, "1.2.3", mkt)

    # change the source skill body → next publish must re-write
    (src / "plugins" / "p" / "skills" / "do-thing" / "SKILL.md").write_text("# changed\n")
    assert pub.publish("p", src, "1.2.3", mkt) is True


def test_publish_version_only_change(tmp_path):
    src = _make_source(tmp_path / "src", "p")
    mkt = _make_marketplace(tmp_path / "mkt", "p")
    pub.publish("p", src, "1.2.3", mkt)
    # same content, new version → the stamp differs, so it is a real change
    assert pub.publish("p", src, "1.3.0", mkt) is True


def test_publish_unlisted_plugin_raises(tmp_path):
    src = _make_source(tmp_path / "src", "p")
    mkt = _make_marketplace(tmp_path / "mkt", "other")
    with pytest.raises(KeyError):
        pub.publish("p", src, "1.2.3", mkt)


def test_publish_missing_source_raises(tmp_path):
    _make_source(tmp_path / "src", "p")
    mkt = _make_marketplace(tmp_path / "mkt", "q")
    with pytest.raises(FileNotFoundError):
        pub.publish("q", tmp_path / "src", "1.2.3", mkt)
