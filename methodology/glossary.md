<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Specfuse glossary — units of work

The canonical definitions of every unit of work in the Specfuse methodology, and
how those units differ between the two execution surfaces. This file is core
substrate: loop, authoring, and orchestrator all vendor it. When a role
definition and this glossary disagree on what a unit *is*, this file wins.

Two facts resolve most confusion up front:

1. **The same word can name units at different altitudes.** "Feature" is the
   *top* grind unit on the loop surface but a *mid-level* unit under an initiative
   on the orchestrator surface. The correlation-ID namespace disambiguates —
   always read the ID root.
2. **Origin is read from the ID root.** `INIT-…` = orchestrated (belongs to an
   initiative). `FEAT-…` = component-local (standalone). Collisions between the
   two namespaces are structurally impossible.

---

## The two execution surfaces

| Surface | Scope | Unit hierarchy | State home |
| --- | --- | --- | --- |
| **Loop** | single repo | Roadmap → **Feature** → Gate → Work Unit | files (`.specfuse/`) |
| **Orchestrator** | many repos | **Initiative** → **Feature** → Task | registry + GitHub labels |

They share one machinery. An orchestrated feature (`INIT-…/FNN`) dispatched to a
component repo is ground there by the loop **exactly as** a standalone
`FEAT-YYYY-NNNN` — the loop treats both as "a feature to grind." The orchestrator
adds the cross-repo layer *above* the loop; it does not replace it.

---

## Units

### Initiative — `INIT-YYYY-NNNN`
The top, cross-repo, spec-driven unit: the whole thing a deploy decision turns
on. Minted by the specs agent (authoring plane) when an idea is picked for
deployment. Owned by specs through `drafting → validating → planning`, then handed
to the pm agent (execution plane) at `planning`. Decomposed by the pm's
feature-decomposition into features.

- `YYYY` = creation year; `NNNN` = zero-padded 4-digit ordinal.
- A **bare `INIT-YYYY-NNNN` is an initiative ID, not a feature ID.** Using it
  where a loop feature ID is expected is malformed and must be rejected.
- Exists only on the orchestrator surface. The loop has no initiatives.

### Feature
A spec-driven *or directly-authored* unit of value. Owns an ordered list of
gates. Two namespaces:

- **Orchestrated:** `INIT-YYYY-NNNN/FNN` — a feature *within* an initiative
  (`FNN` = 2-digit ordinal within the initiative). Produced by the pm decomposing
  an initiative; assigned to a component repo.
- **Component-local:** `FEAT-YYYY-NNNN` — a standalone feature in one repo's
  roadmap. The loop's native top unit; no initiative above it.

On the loop surface the feature is the **top** unit (Roadmap → Feature → …). On
the orchestrator surface it is a **mid-level** unit (Initiative → Feature → Task).
Same concept, different altitude; the ID root tells you which.

### Gate
A milestone partition of a feature: an ordered batch of substantive work units
followed by a mandatory closing sequence and a human review-and-arm checkpoint.
Numbered within a feature (`G1`, `G2`, …). A loop concept; the orchestrator's
task graph is the multi-repo analogue.

### Work Unit (WU) — loop surface
A single, self-contained unit of work crafted to be completed in one focused
agent session. Carries its own prompt; it is the contract between planner and
executor. Task-level correlation IDs:

- Substantive: `FEAT-YYYY-NNNN/TNN` (or `INIT-…/FNN/TNN` when orchestrated).
- Hygiene (precursor to a target WU): `FEAT-…/TNNH[N…]`.
- Closing sequence: `FEAT-…/G<n>-CLOSE` (terminal), `G<n>-CLOSE-INTERMEDIATE` +
  `G<n>-PLAN` (non-terminal two-WU), or the legacy `G<n>-(RETRO|LESSONS|DOCS|PLAN)`
  four-WU form (accepted, emits WARN).

### Task — orchestrator surface
The orchestrator's executable unit under a feature: `INIT-…/FNN/TNN` (or
`FEAT-…/TNN` for a component-local dispatch). Materialized as a GitHub issue,
picked up by a component or QA agent, closed by the merge watcher on PR merge. A
task dispatched into a component repo is executed by that repo's loop as one or
more work units — task (orchestrator view) and WU (loop view) are the same work
seen from the two surfaces.

---

## Lifecycle states

### Initiative / feature level
`drafting → validating → planning → plan_review → generating → in_progress → done`
(plus `blocked`, `abandoned`).

| Transition | Owner |
| --- | --- |
| `drafting → validating`, `validating → planning` | **specs** (definition plane) |
| `planning → plan_review`, `generating → in_progress`, `in_progress → done` | **pm** (execution plane) |
| `generating` (approval gate) | **human** |
| `* → blocked` | any agent (on escalation) |
| `* → abandoned` | human (or pm cascading) |

The `validating → planning` transition is the **plane handoff**: specs (authoring)
→ pm (orchestrator). See `decision-authoring-execution-boundary.md`.

### Task level
`pending → ready → in_progress → in_review → done` (plus `blocked_spec`,
`blocked_human`, `abandoned`).

| Transition | Owner |
| --- | --- |
| `pending` (mint), every `pending → ready` (dependency recomputation) | **pm** |
| `ready → in_progress`, `in_progress → in_review`, `* → blocked_*` | **component / qa** |
| `done` (PR merged) | **merge watcher** |
| `* → abandoned` | human or pm |

### Loop-native status enums
Where the loop tracks state in files rather than the registry:

- **WU status:** `pending`, `draft`, `ready`, `in_progress`, `in_review`, `done`,
  `blocked_human`, `abandoned`.
- **Gate status:** `open`, `awaiting_review`, `passed`.
- **Feature (roadmap) status:** `planned`, `active`, `done`, `abandoned`,
  `deferred` (parked pending an external decision; resumable, unlike `abandoned`).

---

## Correlation-ID quick reference

```
Component-local:   FEAT-YYYY-NNNN[/(TNN[H[N…]] | G<n>-(RETRO|LESSONS|DOCS|PLAN|CLOSE-INTERMEDIATE|CLOSE))]
Orchestrated:      INIT-YYYY-NNNN/FNN[/(TNN[H[N…]] | G<n>-(…))]
Initiative (bare): INIT-YYYY-NNNN        # an initiative, NOT a feature — reject where a feature ID is required
```

The full regex and minting rules are in `rules/correlation-ids.md` (core). This
glossary defines the *concepts*; that rule defines the *format*.
