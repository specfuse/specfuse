---
name: backlog-groom
description: "Periodically triage the whole initiative ideation backlog -- surfacing ready-to-mint ideas, parking stale ones, and flagging internal dupes, items overtaken by minted work, under-shaped entries, bundle drift, and orphaned dossiers. The backlog analog of the PM's roadmap-sync: report-first, read-mostly (orchestrator registries/roadmap read-only), writing only the backlog index and never deleting a row or dossier."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Specs agent — backlog-groom skill (v0.1)

> **Model B (docs/naming-convention.md).** Periodic triage of the initiative
> ideation backlog. The backlog analog of the PM's `roadmap-sync`: keeps the
> pre-intake list honest and surfaces what's ready to mint. Read-mostly; the sole
> writer is `docs/product/INITIATIVE_BACKLOG.md`.

When this file and the specs agent role config disagree, **the role config
wins and this file is wrong.** Raise an escalation rather than reconciling silently.

## Purpose

Walk the whole backlog and produce a triage report: which items are `ready` to mint,
which are stale, which duplicate each other or already-minted initiatives, and which
should be `parked` or `dropped`. On accept, apply the low-risk hygiene fixes
(reprioritize order, merge obvious dupes, park stale items). Surfacing `ready` items
for `initiative-intake` is the skill's highest-value output.

## Scope

In scope:

- Reading every backlog item + the orchestrator `roadmap.md` and `features/INIT-*.md`
  (to detect items overtaken by already-minted work).
- Reporting the triage classes below.
- On accept: reordering by priority, flipping stale items to `parked`, recording
  `dropped` decisions with a one-line why, and fixing unambiguous bundle-drift.

Out of scope:

- **Minting / intake** — `ready` items are *surfaced*, not minted. Graduation is the
  human running the `initiative-intake` skill.
- **Shaping an item** — that is the `ideation-shape` skill;
  groom points at it for under-shaped items, doesn't do the shaping.
- **Touching the orchestrator repo** — registries and roadmap are read-only here.
- **Deleting an item.** `dropped` keeps the row + reason so it isn't re-proposed.

## Triage classes

| Class | Condition | Resolution |
|-------|-----------|------------|
| **ready-to-mint** | item state `ready` | surface prominently; recommend `/initiative-intake` |
| **stale** | `idea`/`shaping`, untouched a long while, no momentum | recommend `parked` (auto on accept) |
| **dupe-internal** | two ideas describe the same initiative | recommend they **bundle** (set lead `bundles:`) or merge — route to `/ideation-shape` |
| **overtaken** | idea overlaps an already-minted `INIT-` (roadmap/registry) | recommend `dropped` with a link to the INIT |
| **under-shaped** | `ready` box checked but dossier thin/unsupported | revert to `shaping`; point at `/ideation-shape` |
| **bundle-drift** | dossier `bundles:`/`bundled_into:` inconsistent (lead missing a follower, follower points at non-lead, states out of step) | report; fix the row/frontmatter mismatch on accept |
| **orphan-dossier** | dossier file with no index row, or row with no dossier | report; do **not** delete — needs human/`ideation-capture` |
| **unsorted** | rows not in priority order | reorder on accept |

## Inputs

1. `docs/product/INITIATIVE_BACKLOG.md` (index) + `docs/product/backlog/*.md` (dossiers).
2. Orchestrator `roadmap.md` + `features/INIT-*.md` (read-only, for overtaken/dupe checks).

## Procedure

### 1. Gather

State intent: "I will groom the initiative backlog (N ideas)." Read every index row,
every dossier (state, `bundles`/`bundled_into`), and the orchestrator
roadmap/registries.

### 2. Classify and report

Sort every item into the triage table. Produce the report first — the human sees
what will change, and which items are ready to mint, before any write.

### 3. Apply hygiene on accept

Reorder by priority, flip stale → `parked`, record `dropped` with its one-line
reason, and fix unambiguous `bundle-drift` (row/frontmatter mismatch). Leave
`ready-to-mint`, `dupe-internal` (bundling is `ideation-shape`'s call), `overtaken`,
`under-shaped`, and `orphan-dossier` for the human / sibling skill. Preserve the
header, table integrity, dossier files, and Notes. **Never delete a row or dossier.**

### 4. Result

Emit the RESULT block. `status: complete` = report delivered and accepted hygiene
applied. Lead the report with the `ready-to-mint` list — that is the backlog's
purpose realized.

## Version

**v0.1.** Seven triage classes. Staleness is judgment-based at v1 (no timestamp
field); if the backlog grows enough to need it, add a `touched` field to the dossier
frontmatter and make `stale` mechanical.
