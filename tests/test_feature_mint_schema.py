#
# Copyright 2026 Specfuse contributors
# Licensed under the Apache License, Version 2.0. See LICENSE.
#
"""`methodology/schemas/feature-mint.schema.json` — the core half of the
feature-frontmatter split (#179).

The mint schema holds the four fields the specs agent writes when it mints a
registry entry. The orchestrator keeps the planning fields and is meant to build
its schema on top of this one (`allOf` + `$ref`, closed with
`unevaluatedProperties: false`). That arrangement holds only while the mint
schema is a STRICT WEAKENING of the orchestrator's: anything the orchestrator
accepts, core must accept. If core ever tightens a constraint, a registry entry
that validated yesterday stops validating in a consumer.

So the weakening is asserted, not claimed, against the INSTALLED orchestrator
package — the same "read the defining artifact" discipline as
test_substrate_drift. The nightly component-compat run executes this file against
the latest orchestrator release, so a change on either side fails core CI rather
than a consumer. It handles both shapes the orchestrator's schema can take, and
skips neither:

  * today: a self-contained schema. The four mint fields must carry identical
    constraints there, and nothing in the mint schema may reject more.
  * after specfuse/orchestrator#87: an extension that `$ref`s this file by `$id`.
    The composition must resolve and accept every fixture.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from specfuse import methodology

ROOT = Path(__file__).resolve().parent.parent
MINT_PATH = ROOT / "methodology" / "schemas" / "feature-mint.schema.json"
GLOSSARY = ROOT / "methodology" / "glossary.md"
MINT_ID = "https://specfuse.dev/methodology/schemas/feature-mint.schema.json"
MINT_FIELDS = ("correlation_id", "state", "involved_repos", "autonomy_default")

# Keywords that describe rather than constrain. Two schemas that differ only in
# these accept exactly the same documents.
ANNOTATIONS = frozenset({"title", "description", "$comment", "examples"})

# The only top-level keywords the mint schema may use. Each of these either
# annotates or is matched by the orchestrator (same `type`, a subset of its
# `required`, identical `properties`); any other keyword could reject a document
# the orchestrator accepts, which is the one thing a strict weakening may not do.
WEAKENING_SAFE = frozenset(
    {"$schema", "$id", "title", "$comment", "description",
     "type", "required", "properties"})


def _mint() -> dict:
    return json.loads(MINT_PATH.read_text(encoding="utf-8"))


def _orchestrator_schema() -> dict:
    spec = importlib.util.find_spec("specfuse.orchestrator")
    if spec is None or not spec.origin:
        raise AssertionError(
            "specfuse-orchestrator is a hard dependency and must be importable")
    path = (Path(spec.origin).parent / "_substrate" / "schemas"
            / "feature-frontmatter.schema.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _constraints(node):
    """*node* with every annotation keyword removed, recursively."""
    if isinstance(node, dict):
        return {k: _constraints(v) for k, v in node.items() if k not in ANNOTATIONS}
    if isinstance(node, list):
        return [_constraints(v) for v in node]
    return node


def _refs(node) -> set[str]:
    """Every `$ref` value anywhere in *node*."""
    found: set[str] = set()
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            found.add(node["$ref"])
        for value in node.values():
            found |= _refs(value)
    elif isinstance(node, list):
        for value in node:
            found |= _refs(value)
    return found


def _orchestrator_validator() -> Draft202012Validator:
    """The orchestrator's schema, able to resolve the mint schema by `$id` —
    locally, never over the network."""
    mint = _mint()
    registry = Registry().with_resource(MINT_ID, Resource.from_contents(mint))
    return Draft202012Validator(_orchestrator_schema(), registry=registry)


_NEXT_STEP = {"summary": "Review the task graph.", "owner": "human",
              "updated": "2026-09-16"}

# Registry frontmatter the orchestrator accepts today, one per shape that
# matters. Not the orchestrator's shipped `examples/feature-frontmatter.json`:
# that example is `state: in_progress` with no `next_step`, so it fails the
# orchestrator's own schema and would prove nothing here.
# `test_every_fixture_is_valid_for_the_orchestrator` keeps these honest.
FIXTURES = {
    "minted (drafting, empty task graph)": {
        "correlation_id": "FEAT-2026-0042", "state": "drafting",
        "involved_repos": ["specfuse/api"], "autonomy_default": "review",
        "task_graph": [],
    },
    "legacy feature mid-lifecycle": {
        "correlation_id": "FEAT-2026-0042", "state": "in_progress",
        "involved_repos": ["specfuse/api", "specfuse/persistence"],
        "autonomy_default": "review",
        "task_graph": [
            {"id": "T01", "type": "implementation", "depends_on": [],
             "assigned_repo": "specfuse/persistence"},
            {"id": "T02", "type": "qa_execution", "depends_on": ["T01"],
             "assigned_repo": "specfuse/api", "autonomy": "supervised"},
        ],
        "next_step": _NEXT_STEP,
    },
    "blocked initiative with a feature graph": {
        "correlation_id": "INIT-2026-0011", "state": "blocked",
        "involved_repos": ["specfuse/api"], "autonomy_default": "auto",
        "feature_graph": [
            {"id": "F01", "type": "implementation", "depends_on": [],
             "assigned_repo": "specfuse/api"},
        ],
        "next_step": {**_NEXT_STEP, "owner": "component-loop",
                      "owner_repo": "specfuse/api", "blocking_on": "PR #290 merge"},
    },
    "terminal state (no next_step required)": {
        "correlation_id": "INIT-2026-0011", "state": "done",
        "involved_repos": ["specfuse/api"], "autonomy_default": "supervised",
        "feature_graph": [],
    },
}


class TestTheMintSchemaItself(unittest.TestCase):

    def test_is_a_valid_draft_2020_12_schema(self):
        mint = _mint()
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", mint["$schema"])
        Draft202012Validator.check_schema(mint)

    def test_id_names_core_as_the_owner(self):
        # Constraint 3: stable, and what the orchestrator's `$ref` will name.
        self.assertEqual(MINT_ID, _mint()["$id"])

    def test_requires_exactly_the_four_mint_fields(self):
        mint = _mint()
        self.assertEqual(set(MINT_FIELDS), set(mint["required"]))
        self.assertEqual(set(MINT_FIELDS), set(mint["properties"]))

    def test_is_open_so_an_extension_can_add_planning_fields(self):
        # Constraint 1. Under `allOf`, a closed base rejects task_graph before the
        # orchestrator's extension is consulted.
        mint = _mint()
        self.assertNotIn("additionalProperties", mint)
        self.assertNotIn("unevaluatedProperties", mint)
        doc = {**FIXTURES["minted (drafting, empty task graph)"], "unknown_key": 1}
        self.assertTrue(Draft202012Validator(mint).is_valid(doc))

    def test_does_not_own_the_planning_fields(self):
        # Constraint 2: the graphs and next_step are pm's.
        text = MINT_PATH.read_text(encoding="utf-8")
        mint = _mint()
        for field in ("task_graph", "feature_graph", "next_step"):
            self.assertNotIn(field, mint["properties"])
            self.assertNotIn(field, mint["required"])
        self.assertNotIn('"oneOf"', text)
        self.assertNotIn('"allOf"', text)

    def test_declares_nothing_that_could_reject_what_the_orchestrator_accepts(self):
        extra = set(_mint()) - WEAKENING_SAFE
        self.assertEqual(set(), extra,
                         "keywords outside the weakening-safe set could reject a "
                         f"document the orchestrator accepts: {sorted(extra)}")

    def test_state_is_the_glossary_lifecycle_spine(self):
        # glossary.md §"Lifecycle states" is where the states are defined; the
        # schema must neither invent one nor drop one.
        text = GLOSSARY.read_text(encoding="utf-8")
        section = text.split("### Initiative / feature level", 1)[1].split("| ", 1)[0]
        spans = re.findall(r"`([^`]+)`", section)
        spine = {token for span in spans for token in re.findall(r"[a-z_]+", span)}
        self.assertEqual(9, len(spine), f"could not read the spine from glossary: {spine}")
        self.assertEqual(spine, set(_mint()["properties"]["state"]["enum"]))

    def test_is_provisioned_into_consumer_repos(self):
        names = {rel.as_posix() for rel in methodology.provisioned_files()}
        self.assertIn("schemas/feature-mint.schema.json", names)


class TestTheMintSchemaRejects(unittest.TestCase):
    """Open is not the same as permissive: the four fields are still checked."""

    def setUp(self):
        self.validator = Draft202012Validator(_mint())
        self.valid = FIXTURES["minted (drafting, empty task graph)"]

    def _invalid(self, **changes):
        doc = copy.deepcopy(self.valid)
        for key, value in changes.items():
            if value is None:
                doc.pop(key)
            else:
                doc[key] = value
        return doc

    def test_the_valid_baseline_passes(self):
        self.assertTrue(self.validator.is_valid(self.valid))

    def test_each_constraint_bites(self):
        cases = {
            "sub-unit correlation id": self._invalid(correlation_id="FEAT-2026-0042/T01"),
            "unknown namespace": self._invalid(correlation_id="BUG-2026-0042"),
            "unknown state": self._invalid(state="paused"),
            "task-level state": self._invalid(state="in_review"),
            "no repos": self._invalid(involved_repos=[]),
            "duplicate repos": self._invalid(involved_repos=["a/b", "a/b"]),
            "empty repo name": self._invalid(involved_repos=[""]),
            "unknown autonomy": self._invalid(autonomy_default="manual"),
        }
        for field in MINT_FIELDS:
            cases[f"missing {field}"] = self._invalid(**{field: None})
        for name, doc in cases.items():
            with self.subTest(case=name):
                self.assertFalse(self.validator.is_valid(doc))


class TestStrictWeakeningOfTheOrchestrator(unittest.TestCase):

    def test_every_fixture_is_valid_for_the_orchestrator(self):
        # Keeps FIXTURES honest: a fixture the orchestrator rejects proves nothing.
        validator = _orchestrator_validator()
        for name, doc in FIXTURES.items():
            with self.subTest(fixture=name):
                errors = [e.message for e in validator.iter_errors(doc)]
                self.assertEqual([], errors)

    def test_everything_the_orchestrator_accepts_is_accepted_here(self):
        mint = Draft202012Validator(_mint())
        for name, doc in FIXTURES.items():
            with self.subTest(fixture=name):
                errors = [e.message for e in mint.iter_errors(doc)]
                self.assertEqual([], errors)

    def test_the_orchestrator_schema_still_agrees(self):
        """Whichever shape the installed orchestrator schema has, it must agree.

        Self-contained (today): the mint fields carry identical constraints there,
        and are all required there. Together with
        `test_declares_nothing_that_could_reject_what_the_orchestrator_accepts`,
        that makes the weakening hold for every document, not just the fixtures.

        Extension (after orchestrator#87): it `$ref`s this file, and the
        constraints live here — so the composition must resolve, which
        `test_every_fixture_is_valid_for_the_orchestrator` exercises.
        """
        orchestrator = _orchestrator_schema()
        if MINT_ID in _refs(orchestrator):
            # The fields should no longer be restated; restating them is a second
            # home for one fact, which is the drift this split exists to end.
            restated = set(orchestrator.get("properties", {})) & set(MINT_FIELDS)
            self.assertEqual(set(), restated,
                             "the orchestrator extension restates mint fields; they "
                             "belong to core now")
            return
        mint = _mint()
        self.assertEqual("object", orchestrator.get("type"))
        self.assertLessEqual(set(mint["required"]), set(orchestrator["required"]),
                             "core requires a field the orchestrator does not")
        for field in MINT_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(
                    _constraints(orchestrator["properties"][field]),
                    _constraints(mint["properties"][field]),
                    f"`{field}` constraints differ between core and the installed "
                    "orchestrator; the mint schema must not be stricter, and "
                    "should not silently be looser")


if __name__ == "__main__":
    unittest.main()
