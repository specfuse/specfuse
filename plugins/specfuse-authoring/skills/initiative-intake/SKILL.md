---
name: initiative-intake
description: "Create a new initiative's registry entry in the orchestration repo, mint its INIT-YYYY-NNNN correlation ID, emit the initiative_created event, and set state to drafting. The entry point for every initiative's lifecycle -- no downstream skill (drafting, validation, planning) can operate until a valid registry entry exists. Use when a human starts a new initiative (renamed from feature-intake in the Model-B reframe)."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Initiative intake — v1.0

Creates a new **initiative's** registry entry in the orchestration repo, mints the initiative
correlation ID (`INIT-YYYY-NNNN`), emits the `initiative_created` event, and sets the state to
`drafting`. This is the entry point for every initiative's lifecycle — no downstream skill (spec
drafting, validation, planning) can operate until a valid registry entry exists.

> **Reframe note (docs/naming-convention.md, Model B).** The orchestrator's top unit is the
> **initiative** (`INIT-YYYY-NNNN`): cross-repo, spec-driven product value. The PM later
> decomposes it into **features** (`INIT-YYYY-NNNN/FNN`), each dispatched to one component repo's
> loop. This skill mints the *initiative*; it does not create features (that is the PM's
> `task-decomposition`). This skill was `feature-intake` before the reframe.

When this file and the specs agent role config disagree, **the role config wins and this
file is wrong.** Raise an escalation rather than reconciling silently.

## Trigger

The human opens a Claude Code session and says they want to start a new initiative. There is no
structured-event trigger — this is a session-driven, conversational entry point.

## Inputs from the human

Three required pieces of information; the skill does not assume defaults for title or repos.

1. **Initiative title** (string) — free-form prose describing the initiative. Used in the
   registry Description heading and the `initiative_created` event payload. Not a machine identifier.
2. **Involved repos** (array of `owner/repo` strings) — the component repositories this initiative
   spans. At least one required; each must match `owner/repo` (e.g. `acme/api-sample`).
3. **Autonomy default** (enum: `auto`, `review`, `supervised`) — the initiative-level autonomy
   setting governing downstream latitude (inherited by features/gates, tightening-only per gate).
   If unspecified, prompt explicitly — do not silently default to `review`.

## Procedure

### Step 1 — Determine the next available ordinal

Read all existing initiative registry files matching `/features/INIT-YYYY-*.md` for the current
year (`YYYY` = the four-digit current year at execution time). Extract the four-digit ordinal
`NNNN` from each filename matching `INIT-YYYY-NNNN.md` *exactly* (exclude `INIT-YYYY-NNNN-*.md`
sidecars like `-plan.md` / `-issues-dryrun.md`). Identify the largest, `max_NNNN`.

`candidate = max_NNNN + 1` (or `1` if none exist). Zero-pad to four digits (`printf '%04d'`). The
candidate correlation ID is `INIT-YYYY-NNNN`.

> Legacy note: pre-reframe registries use the `FEAT-YYYY-NNNN` root. Initiatives mint under the
> `INIT-` root; the two ordinal spaces are independent (different roots, no collision). Scan only
> `INIT-YYYY-*.md` for the initiative ordinal.

### Step 2 — Handle ordinal collision

Check whether `/features/INIT-YYYY-NNNN.md` already exists at the computed path (a file created
between listing and write, or a sidecar inflating the max without occupying the ordinal).

```
while /features/INIT-{YYYY}-{NNNN}.md exists:
    NNNN = NNNN + 1   (re-pad to four digits)
```

The loop terminates at a free ordinal — the minted `INIT-YYYY-NNNN`. Two invocations on the same
directory state cannot collide: the first creates the file, the second's existence check finds it
occupied and increments.

### Step 3 — Create the initiative registry file

Create `/features/INIT-YYYY-NNNN.md` from the `feature-registry.md`
template. Frontmatter:

```yaml
---
correlation_id: INIT-YYYY-NNNN
state: drafting
involved_repos:
  - <each repo the human provided, one per line>
autonomy_default: <the human's choice>
feature_graph: []
---
```

`feature_graph` is an empty array — decomposing the initiative into dispatched features is the PM
agent's concern after `planning`. (The frontmatter schema accepts `feature_graph` as the
initiative form of the unit graph; `task_graph` is the legacy feature form.)

**Body sections** carry honest placeholders — intake does not draft spec content (that is the
spec-drafting skill, WU 4.3):

```markdown
## Description

To be drafted during spec authoring.

## Scope

- To be drafted during spec authoring.

## Out of scope

- To be drafted during spec authoring.

## Related specs

- To be drafted during spec authoring.
```

### Step 4 — Validate the frontmatter

Before writing to the registry, validate against `feature-frontmatter.schema.json`
via `scripts/validate-frontmatter.py`. Write the
complete file (frontmatter + body) to a temp path first, then:

```sh
python3 scripts/validate-frontmatter.py --file /tmp/initiative-registry-candidate.md
```

**Exit 0:** valid — copy the temp file to `/features/INIT-YYYY-NNNN.md`.
**Exit 1/2:** invalid — do not write; diagnose, correct, re-validate (one corrective cycle per
`verify-before-report.md`; three failures →
`spinning_detected`).

### Step 5 — Emit the `initiative_created` event

| Field | Value |
|---|---|
| `timestamp` | `date -u +%Y-%m-%dT%H:%M:%SZ` — at emission time, never synthesized |
| `correlation_id` | The minted `INIT-YYYY-NNNN` |
| `event_type` | `initiative_created` |
| `source` | `specs` |
| `source_version` | `scripts/read-agent-version.sh specs` — never eye-cached |
| `payload.initiative_title` | The human-provided title |
| `payload.involved_repos` | The human-provided repo array |
| `payload.autonomy_default` | The human-provided autonomy choice |
| `payload.correlation_id` | The minted `INIT-YYYY-NNNN` (duplicated for payload self-containment) |

Write minified single-line JSON to `/tmp/event.json`, validate, then safe-append:

```sh
python3 scripts/validate-event.py --file /tmp/event.json
printf '%s\n' "$(cat /tmp/event.json)" >> events/INIT-YYYY-NNNN.jsonl
```

**Exit 1/2:** do not append; diagnose, correct, re-validate; three failures → `spinning_detected`.

### Step 6 — Verify

Per `verify-before-report.md`, re-read and confirm:

1. `/features/INIT-YYYY-NNNN.md` exists and round-trips through `validate-frontmatter.py` (exit 0).
2. `/events/INIT-YYYY-NNNN.jsonl` exists, has exactly one line, round-trips through `validate-event.py` (exit 0).
3. Correlation ID matches across filename, frontmatter `correlation_id`, event envelope, and `payload.correlation_id`.
4. State is `drafting`.
5. No written path is in `never-touch.md`.

Only after all checks pass does the skill report completion.

## Worked example

**Human input:** title "Weekly roster generation"; repos `acme/backend`,
`acme/ai-service`; autonomy `review`.

**Step 1–2 — Ordinal:** list `/features/INIT-2026-*.md` → finds `INIT-2026-0001.md` (+ its
`-plan.md` / `-issues-dryrun.md` sidecars, excluded). `max_NNNN` = 0001 → candidate 0002.
`/features/INIT-2026-0002.md` does not exist → minted `INIT-2026-0002`.

**Step 3 — Registry at `/features/INIT-2026-0002.md`:**

```yaml
---
correlation_id: INIT-2026-0002
state: drafting
involved_repos:
  - acme/backend
  - acme/ai-service
autonomy_default: review
feature_graph: []
---
```

**Step 5 — Event:**

```sh
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SOURCE_VERSION=$(scripts/read-agent-version.sh specs)
cat > /tmp/event.json << EOF
{"timestamp":"${TIMESTAMP}","correlation_id":"INIT-2026-0002","event_type":"initiative_created","source":"specs","source_version":"${SOURCE_VERSION}","payload":{"initiative_title":"Weekly roster generation","involved_repos":["acme/backend","acme/ai-service"],"autonomy_default":"review","correlation_id":"INIT-2026-0002"}}
EOF
python3 scripts/validate-event.py --file /tmp/event.json   # exit 0
printf '%s\n' "$(cat /tmp/event.json)" >> events/INIT-2026-0002.jsonl
```

Intake complete. The initiative is in `drafting` with a valid registry entry and a validated
`initiative_created` event. The spec-drafting skill can proceed; the PM decomposes it into
features after `planning`.

## Artifacts produced

| Artifact | Path | Validated against |
|---|---|---|
| Initiative registry entry | `/features/INIT-YYYY-NNNN.md` | `feature-frontmatter.schema.json` via `validate-frontmatter.py` |
| Initiative event log | `/events/INIT-YYYY-NNNN.jsonl` | `event.schema.json` + `initiative_created.schema.json` via `validate-event.py` |

## Schemas consumed

- `shared/schemas/feature-frontmatter.schema.json` — frontmatter validation (accepts `INIT-` + `feature_graph`).
- `shared/schemas/event.schema.json` — event envelope validation.
- `shared/schemas/events/initiative_created.schema.json` — per-type payload validation.

## Rules absorbed

- `shared/rules/correlation-ids.md` — ID format, minting, uniqueness; the `INIT-`/`FEAT-` root distinction (docs/naming-convention.md).
- `shared/rules/verify-before-report.md` — four-step cycle, emission discipline, corrective-cycle limit.
- `shared/rules/never-touch.md` — path prohibition check on every write.
- `shared/rules/state-vocabulary.md` — `drafting` is the initial state; no transition during intake.
- `shared/rules/escalation-protocol.md` — `spinning_detected` after three consecutive validation failures.

## Anti-patterns

1. **Skipping the collision check.** The existence check at the computed path is mandatory even with an apparent ordinal gap.
2. **Defaulting autonomy without asking.** Never silently assume `review`; the human's choice is load-bearing downstream.
3. **Drafting body content.** Placeholders only — spec content is the spec-drafting skill's concern.
4. **Populating `feature_graph`.** It is `[]` at intake. Decomposing the initiative into dispatched features is the PM agent's job after `planning`.
5. **Minting under the wrong root.** Initiatives are `INIT-YYYY-NNNN`. Do not mint `FEAT-` (the legacy feature root / component-local loop root) for an initiative.
6. **Eye-caching `source_version`.** Read at emission time via `scripts/read-agent-version.sh specs`.
7. **Appending the event before validation**, or using `cat >>` instead of the safe `printf '%s\n'` append.
