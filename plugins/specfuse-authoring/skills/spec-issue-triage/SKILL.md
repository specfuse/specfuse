---
name: spec-issue-triage
description: "Triage spec issues raised by downstream agents (GitHub issues labelled specfuse:spec-issue) -- deciding, via a four-case decision tree, whether the fix belongs in /product/ (a spec-content correction the specs agent makes and re-validates) or in the generator project (a template issue to file), then resolving or routing accordingly. The specs agent's monitor-driven skill; reads the upstream spec to distinguish a genuine template bug from a spec error propagated through generation, and escalates ambiguous cases rather than guessing."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Spec-issue triage — v1.0

Handles spec issues raised by downstream actors (component, QA, PM, or a general session) as **GitHub issues labelled `specfuse:spec-issue`** in the product specs repo, assessing whether the fix belongs in `/product/` (a spec-content correction the specs agent can make) or in the generator project (a template issue to be filed against the generator), and executing accordingly. This is the specs agent's monitor-driven skill — it picks open `specfuse:spec-issue` issues, not a conversational prompt. (Legacy: the same triage runs on a filled template dropped into `/inbox/spec-issue/`; see "Legacy inbox path" below.)

When this file and the specs agent role config disagree, **the role config wins and this file is wrong.** Raise an escalation rather than reconciling silently.

## Trigger

An open GitHub issue labelled `specfuse:spec-issue` exists in the product specs repo. List the open spec-issues with `gh`:

```sh
gh issue list --label specfuse:spec-issue --state open   # this repo's origin
# or add: --repo <owner>/<repo>
```

(A deploying project may wrap this in a small helper script of its own; the skill only needs the list of open `specfuse:spec-issue`-labelled issues.)

The issue **body** follows the `spec-issue.md` template: `## Observation`, `## Location`, `## Triggering task`, `## Suggested resolution`. It was filed by `scripts/raise-spec-issue.py` (orchestrator side) when a downstream actor hit a spec-level problem it could not resolve inside its own task. The `initiative:INIT-…` label (when present) threads it to its initiative.

**This is the specs agent's monitor-driven skill** rather than the session-driven pattern of the drafting skills: it picks an open `specfuse:spec-issue` issue and triages it. The human does not need to be in an active session for triage to begin — although the escalation path (case d) requires human input before the issue can be resolved.

**Precondition.** The picked issue must:

1. Be open and carry the `specfuse:spec-issue` label.
2. Have a body with all four mandatory sections from the `spec-issue.md` template: `## Observation`, `## Location`, `## Triggering task`, and `## Suggested resolution`.
3. Have a well-formed correlation ID in the `## Triggering task` section (pattern: `(FEAT|INIT)-YYYY-NNNN[/FNN][/TNN]`).

If any precondition fails, the skill does not proceed with triage — it comments on the issue describing the parsing failure, leaves it open, and escalates with `spec_level_blocker`.

**Legacy inbox path.** A filled template dropped into `/inbox/spec-issue/` still works: the same triage runs, reading the file instead of the issue body and archiving it to `/inbox/spec-issue/processed/` on completion (the original behavior). New issues should be filed via the producer (GitHub) path.

## Inputs

The skill reads, in order:

1. The GitHub issue body (via `gh issue view <N> --repo <specs> --json number,title,body,labels,url`) — its four sections provide the observation, the file locations where the issue surfaces, the triggering task's correlation ID, and the filing actor's suggested resolution. (Legacy: the inbox file under `/inbox/spec-issue/`.)
2. This skill file and the specs agent role config — reloaded per `/shared/rules/role-switch-hygiene.md`.
3. The file(s) named in the `## Location` section — read to determine whether the issue surfaces in a spec file under `/product/`, a generated file under `_generated/` (or equivalent generated directory), or both.
4. The relevant spec file(s) under `/product/` — even when the issue names a generated file, the skill reads the upstream spec to determine whether the generated output's problem traces back to a spec-content error (case c in the triage decision tree).
5. The feature's event log at `/events/FEAT-YYYY-NNNN.jsonl` — read to confirm the original `spec_issue_raised` event exists and to avoid duplicate resolution/routing events.

The skill does **not** read component-repo source code beyond the paths named in the issue's `## Location` section. It does not read test harnesses, CI logs, or generated directories in bulk.

## Triage decision tree

The skill's core judgment: is this a spec problem or a generator template problem? The decision tree has four cases. The skill evaluates them in order; the first match wins.

---

### Case (a) — Spec-content fix

**Criteria.** The issue names a file under `/product/` **and** the fix is a spec-content change: wrong endpoint path, missing field, incorrect type, wrong status code, mismatched enum value, contradictory description, or any other factual error in the spec document itself.

**Signal words in the issue.** The `## Observation` describes a discrepancy between the spec's declared behavior and the expected behavior. The `## Location` points to a path under `/product/`. The `## Suggested resolution` proposes a concrete change to the spec content.

**Action.** Route to the [spec-fix path](#spec-fix-path).

---

### Case (b) — Generator-template fix

**Criteria.** The issue names a file under `_generated/` (or equivalent generated directory per architecture §9.1) **and** the problem is in the generated code's shape: missing boilerplate, wrong template output, incorrect scaffolding structure, missing imports, wrong file naming convention, or any other problem that would persist even if the spec were correct.

**Signal words in the issue.** The `## Observation` describes a structural problem in generated output (missing class, wrong method signature shape, absent boilerplate). The `## Location` points to a path under `_generated/`. The `## Suggested resolution` proposes a template or generator change, not a spec change. Reading the upstream spec confirms the spec is correct — the generated output does not match what the spec prescribes.

**Action.** Route to the [generator-routing path](#generator-routing-path).

---

### Case (c) — Spec error propagated through generation

**Criteria.** The issue names a file under `_generated/` (or equivalent) **but** the root cause is a spec error that propagated through the generator. The generated code is wrong because the spec fed it wrong input — fix the spec, regenerate, and the generated output will be correct.

**This is the subtlest case.** The filing agent sees the symptom in generated code and correctly identifies the file path, but the root cause is upstream in `/product/`. The triage skill must read both the generated file and the spec file to make this determination.

**Signal words in the issue.** The `## Observation` describes generated output that does not match expected behavior. The `## Location` points to a generated file. But when the skill reads the upstream spec, it finds the same error there — the spec prescribes the wrong behavior, and the generator faithfully reproduced it.

**Action.** Route to the [spec-fix path](#spec-fix-path) — **not** the generator-routing path. The fix is in `/product/`; regeneration after the spec fix will correct the generated output. The skill documents this reasoning in the resolution summary so the filing agent understands why a generated-file issue was resolved by a spec change.

**Worked example for case (c).**

A component agent files a spec issue: "The generated controller at `_generated/Controllers/OrdersController.cs:47` routes `POST /orders` to `/order` (singular) instead of `/orders` (plural)." The `## Location` points to `_generated/Controllers/OrdersController.cs:47`. At first glance, this looks like a generator template problem (case b).

But the triage skill reads the upstream OpenAPI spec at `product/specs/orders-api.yaml` and finds:

```yaml
paths:
  /order:          # <-- typo: should be /orders
    post:
      operationId: createOrder
```

The spec has a typo — `/order` instead of `/orders`. The generator faithfully reproduced the spec's path. The fix is to correct the spec (`/order` -> `/orders`), not to change the generator template. After the spec fix, regeneration will produce the correct route.

This is case (c): a spec error that propagated through generation. The skill routes it to the spec-fix path, not the generator-routing path.

---

### Case (d) — Ambiguous classification

**Criteria.** After reading the issue, the affected files, and the upstream spec, the skill cannot confidently determine whether the problem is a spec-content error or a generator-template error. Common ambiguity signals:

- The issue describes a behavior that could result from either a spec omission or a template gap.
- The spec is silent on the behavior in question — neither prescribing it nor excluding it — so it is unclear whether the generator should have inferred it or the spec should have stated it.
- The fix would require coordinated changes in both the spec and the generator template, and the correct sequencing is unclear.

**Action.** Route to the [escalation path](#escalation-path). The specs agent does not guess.

---

### Decision summary

| Case | Issue location | Root cause | Action |
|---|---|---|---|
| (a) | `/product/` | Spec content error | Spec-fix path |
| (b) | `_generated/` | Generator template error | Generator-routing path |
| (c) | `_generated/` | Spec error propagated through generation | Spec-fix path |
| (d) | Any | Ambiguous | Escalation path |

## Spec-fix path

When the triage decision is case (a) or case (c), the specs agent fixes the spec content in `/product/` and resolves the issue.

### Step 1 — Identify the fix

Read the affected spec file(s) under `/product/`. Using the issue's `## Observation`, `## Location`, and `## Suggested resolution`, identify the concrete change needed. For case (c), trace the generated-file symptom back to the spec-level root cause.

### Step 2 — Apply the fix

Edit the spec file(s) under `/product/` in the product specs repo. The edit is scoped to the issue's root cause — do not refactor surrounding content, do not add features, do not change unrelated fields. The fix is a surgical correction.

**Write surface.** The spec-fix path writes only to `/product/` in the product specs repo. It does **not** write to `/business/` (`never-touch.md` §4), does not write to `_generated/` directories (architecture §9.1 — fix the spec, regenerate), does not write to `/product/test-plans/` (QA agent's surface), and does not modify generated code in component repos.

### Step 3 — Re-validate

Run the spec-validation skill's validation procedure on the affected spec file(s):

```sh
specfuse validate <affected-spec-file>
```

The fix must produce a clean validation pass on the affected file(s). If validation fails, correct the fix and re-validate. Three consecutive failures trigger `spinning_detected` escalation per `escalation-protocol.md`.

### Step 4 — Emit `spec_issue_resolved` event

Construct the event:

| Field | Value |
|---|---|
| `timestamp` | `date -u +%Y-%m-%dT%H:%M:%SZ` — captured at emission time |
| `correlation_id` | `FEAT-YYYY-NNNN` (feature-level, extracted from the triggering task's correlation ID) |
| `event_type` | `spec_issue_resolved` |
| `source` | `specs` |
| `source_version` | Output of `scripts/read-agent-version.sh specs` |
| `payload.original_issue_correlation_id` | The task-level correlation ID from the inbox file's `## Triggering task` (e.g. `FEAT-2026-0042/T09`) |
| `payload.affected_files` | Array of spec file paths edited (relative to product specs repo root) |
| `payload.resolution_summary` | One-sentence description of what was fixed and why |

Write to `/tmp/event.json`, validate, and append:

```sh
python3 scripts/validate-event.py --file /tmp/event.json
# Exit 0 → append
printf '%s\n' "$(cat /tmp/event.json)" >> events/FEAT-YYYY-NNNN.jsonl
```

Three consecutive validation failures on the event itself → `spinning_detected` escalation.

### Step 5 — Close the spec-issue GitHub issue

Close the issue with a comment linking the resolution (the `/product/` commit/PR for a spec-content fix, or the generator issue reference for a routing), so the thread records the outcome:

```sh
gh issue close <N> --repo <specs-repo> --reason completed \
  --comment "Resolved: <one-line summary>. <PR/commit or generator-issue ref>."
```

The issue is the audit record (alongside the `spec_issue_resolved`/`spec_issue_routed` event); closing it — not deleting — preserves history. **Legacy inbox path:** instead, move the file from `/inbox/spec-issue/` to `/inbox/spec-issue/processed/` (`mv`, never delete).

### Step 6 — Verify

Per `verify-before-report.md`:

1. Re-read the edited spec file(s) and confirm the fix landed as intended.
2. Re-read the event log and confirm the `spec_issue_resolved` event round-trips through `scripts/validate-event.py` with exit 0.
3. Confirm the spec-issue GitHub issue is closed (legacy: the inbox file is in `/inbox/spec-issue/processed/`).
4. Confirm no written path is in `never-touch.md`.

Three consecutive re-read failures → `spinning_detected` escalation.

## Generator-routing path

When the triage decision is case (b), the specs agent files a GitHub issue against the generator project and archives the inbox file.

### Step 1 — Compose the generator issue

Using the inbox file's content, compose a GitHub issue against the generator project. The issue body carries:

- **Title:** A concise description of the template problem (e.g. "Generated test fixture missing required `metadata` field").
- **Body:** The `## Observation` and `## Location` from the inbox file (adapted to reference the generator template, not the generated output). The `## Suggested resolution` from the inbox file, if it proposes a template change. A link back to the triggering task's correlation ID for traceability.

The specs agent uses `gh issue create` to file the issue:

```sh
gh issue create --repo <generator-project> --title "<title>" --body "<body>"
```

The `<generator-project>` is the `owner/repo` of the Specfuse generator project. This is read from the feature's `involved_repos` frontmatter or from the inbox file's context — the generator project is the repo that owns the templates producing the generated output.

### Step 2 — Emit `spec_issue_routed` event

Construct the event:

| Field | Value |
|---|---|
| `timestamp` | `date -u +%Y-%m-%dT%H:%M:%SZ` — captured at emission time |
| `correlation_id` | `FEAT-YYYY-NNNN` (feature-level) |
| `event_type` | `spec_issue_routed` |
| `source` | `specs` |
| `source_version` | Output of `scripts/read-agent-version.sh specs` |
| `payload.original_issue_correlation_id` | The task-level correlation ID from the inbox file's `## Triggering task` |
| `payload.target_project` | The `owner/repo` of the generator project |
| `payload.filed_issue_reference` | The GitHub issue reference returned by `gh issue create` (e.g. `acme/specfuse-generator#42`) |

Write to `/tmp/event.json`, validate, and append:

```sh
python3 scripts/validate-event.py --file /tmp/event.json
# Exit 0 → append
printf '%s\n' "$(cat /tmp/event.json)" >> events/FEAT-YYYY-NNNN.jsonl
```

### Step 3 — Archive the inbox file

Move the inbox file to `/inbox/spec-issue/processed/`. Never delete.

### Step 4 — Verify

Per `verify-before-report.md`:

1. Confirm the GitHub issue was created (re-read via `gh issue view`).
2. Re-read the event log and confirm the `spec_issue_routed` event round-trips through `scripts/validate-event.py` with exit 0.
3. Confirm the inbox file is in `/inbox/spec-issue/processed/`.
4. Confirm no spec files under `/product/` were modified (the generator-routing path does not touch specs).
5. Confirm no generated code was modified (the specs agent files an issue, it does not fix generated code).

## Escalation path

When the triage decision is case (d) — ambiguous classification — the specs agent escalates to the human with structured context.

### Step 1 — Write the escalation file

Write a `human-escalation.md` at `/inbox/human-escalation/<correlation-id>-spec-triage.md` per `escalation-protocol.md`:

- **Correlation ID:** The feature-level correlation ID from the triggering task.
- **Reason:** `spec_level_blocker`.
- **Agent state:** "specs agent, triaging spec issue from `<inbox-filename>`. The issue describes `<one-sentence observation>`. Location: `<paths>`. I cannot determine whether this is a spec-content problem (fix in `/product/`) or a generator-template problem (file against generator). The ambiguity is: `<specific description of what makes the classification unclear>`."
- **Decision requested:** "(a) This is a spec-content problem — I should fix the spec under `/product/`; (b) this is a generator-template problem — I should file against the generator project; (c) this requires coordinated changes in both — provide sequencing guidance; (d) abandon triage and reassign."

### Step 2 — Emit `human_escalation` event

Per the escalation protocol, append a `human_escalation` event to the feature's event log with the reason, inbox filename, and one-sentence summary.

### Step 3 — Stop

The specs agent does not continue triage. The inbox file remains in `/inbox/spec-issue/` (it is **not** archived until the issue is resolved). The human's response will direct the specs agent to one of the two resolution paths or to abandonment.

## Inbox lifecycle

The inbox file follows a strict lifecycle. The skill never deletes inbox files.

```
/inbox/spec-issue/<filename>.md          ← Filed by downstream agent
        │
        ├── Read by triage skill
        ├── Triage decision made
        ├── Action taken (spec fix, generator issue, or escalation)
        │
        └── Archived to:
            /inbox/spec-issue/processed/<filename>.md
```

**States:**

1. **Pending** — the file is in `/inbox/spec-issue/`. The triage skill has not yet processed it.
2. **Processing** — the triage skill is actively reading and assessing the file. The file remains in `/inbox/spec-issue/` during processing.
3. **Archived** — the file has been moved to `/inbox/spec-issue/processed/`. Triage is complete (either resolved via spec fix, routed to generator, or escalated and later resolved by human).

**On escalation (case d):** the inbox file stays in `/inbox/spec-issue/` until the human responds and the issue is subsequently resolved or routed. Only then is it archived.

**On malformed input:** the file is moved to `/inbox/spec-issue/processed/` with a `_malformed` suffix appended before the `.md` extension (e.g. `FEAT-2026-0042-T09-spec_malformed.md`).

**Concurrency.** If multiple spec issues arrive simultaneously, the skill processes them sequentially — one file at a time. Each file's triage is independent; the decision for one issue does not influence the decision for another.

## Worked examples

### Example 1 — Spec fix (case a): wrong status code in OpenAPI spec

**Context.** The component agent working on `FEAT-2026-0042/T09` files a spec issue because the generated controller returns HTTP 200 on bookmark creation, but the acceptance criterion AC-1 expects HTTP 201. The component agent cannot resolve this inside its task because the generated code faithfully implements the spec, and the spec appears to be wrong.

**Inbox file** at `/inbox/spec-issue/FEAT-2026-0042-T09-wrong-status.md`:

```markdown
## Observation

The generated bookmark creation endpoint returns HTTP 200 on first
creation. AC-1 in the feature narrative expects HTTP 201 on first
creation and HTTP 200 only on idempotent repeat. The OpenAPI spec
declares only a "200" response for the POST operation, with no "201"
response defined.

## Location

- product/specs/inventory-api-bookmarks.yaml:32

## Triggering task

- Task issue: acme/inventory-api#18
- Correlation ID: FEAT-2026-0042/T09

## Suggested resolution

Add a "201" response to the POST /users/{user_id}/bookmarks operation
in the OpenAPI spec, with description "Bookmark created". Move the
current "200" response description to "Bookmark already exists
(idempotent repeat)".
```

**Triage decision.** The skill reads the inbox file. The `## Location` points to `product/specs/inventory-api-bookmarks.yaml:32` — a path under `/product/`. The `## Observation` describes a factual error in the spec (missing 201 response). This is case (a): a spec-content fix.

**Spec-fix path execution:**

1. **Identify the fix.** Read `product/specs/inventory-api-bookmarks.yaml`. At line 32, the POST operation's `responses` section has only `"200"`. The fix: add `"201"` as the primary success response, keep `"200"` for the idempotent repeat case. This matches the feature narrative's AC-1 and AC-2.

2. **Apply the fix.** Edit `product/specs/inventory-api-bookmarks.yaml`:

   ```yaml
   responses:
     "201":
       description: Bookmark created
       content:
         application/json:
           schema:
             $ref: "#/components/schemas/Bookmark"
     "200":
       description: Bookmark already exists (idempotent repeat)
       content:
         application/json:
           schema:
             $ref: "#/components/schemas/Bookmark"
   ```

3. **Re-validate.** `specfuse validate product/specs/inventory-api-bookmarks.yaml` exits 0.

4. **Emit `spec_issue_resolved` event:**

   ```json
   {"timestamp":"2026-04-25T14:30:00Z","correlation_id":"FEAT-2026-0042","event_type":"spec_issue_resolved","source":"specs","source_version":"1.0.0","payload":{"original_issue_correlation_id":"FEAT-2026-0042/T09","affected_files":["product/specs/inventory-api-bookmarks.yaml"],"resolution_summary":"Added HTTP 201 response to POST /users/{user_id}/bookmarks for first-creation case; HTTP 200 retained for idempotent repeat. Fixes missing status code that caused generated controller to return 200 on all creations."}}
   ```

   Validated through `scripts/validate-event.py` with exit 0. Appended to `events/FEAT-2026-0042.jsonl`.

5. **Archive.** `mv inbox/spec-issue/FEAT-2026-0042-T09-wrong-status.md inbox/spec-issue/processed/FEAT-2026-0042-T09-wrong-status.md`

6. **Verify.** Re-read the spec file — 201 response present. Event validates. Inbox file in processed/. No generated code touched. No `/business/` paths touched.

**Result.** The spec is corrected. The component agent's task (`FEAT-2026-0042/T09`) can be unblocked — regeneration from the corrected spec will produce a controller that returns 201 on first creation.

---

### Example 2 — Generator routing (case b): missing field in generated test fixture

**Context.** The QA agent working on `FEAT-2026-0042/T12` files a spec issue because a generated test fixture for the bookmarks API is missing the `created_at` field. The QA agent's test plan expects every bookmark object in the fixture to have `created_at`, but the generated fixture only includes `item_id`.

**Inbox file** at `/inbox/spec-issue/FEAT-2026-0042-T12-fixture-field.md`:

```markdown
## Observation

The generated test fixture at _generated/fixtures/bookmarks.json
contains bookmark objects with only an `item_id` field. The Bookmark
schema in the OpenAPI spec requires both `item_id` and `created_at`.
The fixture generator appears to omit `created_at` (a datetime field)
from its output.

## Location

- _generated/fixtures/bookmarks.json:1

## Triggering task

- Task issue: acme/inventory-api#22
- Correlation ID: FEAT-2026-0042/T12

## Suggested resolution

Update the fixture generation template to include all required fields
from the referenced schema, including datetime fields like `created_at`.
The template currently appears to skip `format: date-time` fields.
```

**Triage decision.** The skill reads the inbox file. The `## Location` points to `_generated/fixtures/bookmarks.json` — a generated directory. The skill then reads the upstream spec at `product/specs/inventory-api-bookmarks.yaml` to check whether the spec correctly declares the `created_at` field:

```yaml
components:
  schemas:
    Bookmark:
      type: object
      required: [item_id, created_at]
      properties:
        item_id:
          type: string
        created_at:
          type: string
          format: date-time
```

The spec is correct — `created_at` is required and properly typed. The generated fixture is wrong because the fixture-generation template skips `format: date-time` fields. This is case (b): a generator-template fix.

**Generator-routing path execution:**

1. **Compose the generator issue.** File against the generator project:

   ```
   Title: Fixture generation template omits `format: date-time` fields

   Body:
   ## Observation

   The fixture generation template produces bookmark objects with only
   `item_id`, omitting the required `created_at` field (type: string,
   format: date-time). The upstream OpenAPI spec correctly declares
   `created_at` as required.

   ## Location

   Fixture generation template (datetime field handling).

   ## Triggering context

   Correlation ID: FEAT-2026-0042/T12
   Spec file: product/specs/inventory-api-bookmarks.yaml
   Schema: Bookmark (components/schemas/Bookmark)

   ## Suggested resolution

   Update the fixture generation template to include all required fields
   from the referenced schema, including those with `format: date-time`.
   Generate a valid ISO-8601 datetime value for such fields.
   ```

   Filed via `gh issue create --repo acme/specfuse-generator --title "..." --body "..."` — returns `acme/specfuse-generator#42`.

2. **Emit `spec_issue_routed` event:**

   ```json
   {"timestamp":"2026-04-25T15:10:00Z","correlation_id":"FEAT-2026-0042","event_type":"spec_issue_routed","source":"specs","source_version":"1.0.0","payload":{"original_issue_correlation_id":"FEAT-2026-0042/T12","target_project":"acme/specfuse-generator","filed_issue_reference":"acme/specfuse-generator#42"}}
   ```

   Validated through `scripts/validate-event.py` with exit 0. Appended to `events/FEAT-2026-0042.jsonl`.

3. **Archive.** `mv inbox/spec-issue/FEAT-2026-0042-T12-fixture-field.md inbox/spec-issue/processed/FEAT-2026-0042-T12-fixture-field.md`

4. **Verify.** GitHub issue exists (`gh issue view acme/specfuse-generator#42`). Event validates. Inbox file in processed/. No spec files under `/product/` were modified. No generated code was modified.

**Result.** The generator issue is filed. The QA agent's task (`FEAT-2026-0042/T12`) remains blocked on the generator fix — the generator feedback loop (Phase 5) will handle the template correction. The specs agent's work on this issue is complete.

## Event types

This skill emits two event types, both new in Phase 4 WU 4.5:

### `spec_issue_resolved`

Emitted when the skill resolves a spec issue by fixing spec content under `/product/`. Per-type payload schema: `spec_issue_resolved.schema.json`.

| Payload field | Type | Description |
|---|---|---|
| `original_issue_correlation_id` | `string` | Task-level correlation ID from the triggering task (`FEAT-YYYY-NNNN/TNN`) |
| `affected_files` | `string[]` | Spec file paths edited under `/product/` |
| `resolution_summary` | `string` | What was fixed and why |

### `spec_issue_routed`

Emitted when the skill routes a spec issue to the generator project by filing a GitHub issue. Per-type payload schema: `spec_issue_routed.schema.json`.

| Payload field | Type | Description |
|---|---|---|
| `original_issue_correlation_id` | `string` | Task-level correlation ID from the triggering task (`FEAT-YYYY-NNNN/TNN`) |
| `target_project` | `string` | `owner/repo` of the generator project |
| `filed_issue_reference` | `string` | GitHub issue reference (`owner/repo#N`) |

Both event types follow the standard event envelope schema at `event.schema.json`. The `source` is always `specs`; the `source_version` is read at emission time via `scripts/read-agent-version.sh specs`.

## Artifacts produced

| Artifact | Path | Validated against |
|---|---|---|
| Spec file edits (spec-fix path) | `/product/` in product specs repo | Specfuse validator (`specfuse validate <file>`) |
| Generator issue (generator-routing path) | GitHub issue on generator project | `gh issue view` confirmation |
| `spec_issue_resolved` event | `/events/FEAT-YYYY-NNNN.jsonl` | `event.schema.json` + `spec_issue_resolved.schema.json` via `validate-event.py` |
| `spec_issue_routed` event | `/events/FEAT-YYYY-NNNN.jsonl` | `event.schema.json` + `spec_issue_routed.schema.json` via `validate-event.py` |
| Archived inbox file | `/inbox/spec-issue/processed/` | Presence check |
| Human-escalation file (case d only) | `/inbox/human-escalation/` | `human-escalation.md` template |

## Schemas consumed

- `shared/schemas/event.schema.json` — event envelope validation.
- `shared/schemas/events/spec_issue_resolved.schema.json` — per-type payload validation for resolution events (authored in this WU).
- `shared/schemas/events/spec_issue_routed.schema.json` — per-type payload validation for routing events (authored in this WU).
- `shared/schemas/events/human_escalation.schema.json` — per-type payload validation for escalation events (case d).

## Rules absorbed

- `shared/rules/correlation-ids.md` — task-level and feature-level ID formats used in events and inbox files.
- `shared/rules/verify-before-report.md` — four-step cycle, event-emission operational discipline (timestamps at emission time, canonical `--file /tmp/event.json` invocation, JSONL single-line requirement, safe append pattern), corrective cycle limit.
- `shared/rules/never-touch.md` — path prohibition check on every write. In particular: generated directories are never edited (file a spec issue or generator issue instead), `/business/` is off-limits, `/product/test-plans/` belongs to the QA agent.
- `shared/rules/escalation-protocol.md` — `spinning_detected` escalation after three consecutive failures; `spec_level_blocker` for ambiguous triage (case d).
- `shared/rules/role-switch-hygiene.md` — re-read shared rules unconditionally at the start of every task.

## Anti-patterns

1. **Editing generated code.** The specs agent files issues, it does not fix generated code. The spec-fix path edits specs under `/product/`; the generator-routing path files a GitHub issue. Neither path touches `_generated/` or equivalent.
2. **Guessing on case (d).** When the classification is ambiguous, the skill escalates. A wrong classification — routing a spec error to the generator or fixing a template problem in the spec — creates a false resolution that the downstream agent will re-discover, wasting a full task cycle.
3. **Deleting inbox files.** Inbox files are archived to `/inbox/spec-issue/processed/`, never deleted. The processed directory is the audit trail.
4. **Routing case (c) to the generator.** The most common triage error. When a spec error propagates through generation, the fix is in the spec — not the generator template. The generator is working correctly; the input it received was wrong. The skill must read the upstream spec to distinguish case (b) from case (c).
5. **Applying the fix without re-validation.** The spec-fix path requires `specfuse validate` to pass after the edit. A spec fix that introduces new validation errors is worse than the original issue.
6. **Emitting events before validation.** Events must pass `validate-event.py` with exit 0 before append. An invalid event in the log corrupts the audit trail.
7. **Implementing the generator feedback loop.** This skill files issues against the generator project. It does not fix generator templates, run the generator, or verify generator output. The generator feedback loop is Phase 5.
8. **Modifying the filing agent's behavior.** The component and QA agents' spec-issue filing behavior is their own — this skill consumes their output, it does not modify how they produce it.
9. **Writing to `/product/test-plans/`.** Test plans belong to the QA agent. A write there from the specs agent crosses role boundaries.
10. **Writing to `/business/`.** Off-limits per `never-touch.md` §4.

## What this skill does not do

- It does **not** draft specs from scratch. That is the spec-drafting skill's concern. This skill makes surgical corrections to existing specs based on issues filed by downstream agents.
- It does **not** run full feature validation. It runs `specfuse validate` on the affected file(s) only, to confirm the fix is clean. Full-feature validation (all spec files, state transitions) is the spec-validation skill's concern.
- It does **not** fix generator templates. It files issues against the generator project. The generator feedback loop (Phase 5) will own template fixes.
- It does **not** modify generated code. Generated code is the generator's output; the specs agent's only influence on it is through the spec content it owns and the issues it files.
- It does **not** unblock downstream tasks. After resolving or routing an issue, the downstream agent's task remains in whatever state it was in (`blocked_spec`, typically). Unblocking is the human's or PM agent's responsibility.
- It does **not** modify the component or QA agents' spec-issue filing behavior. Those agents' escalation skills define how and when spec issues are filed; this skill consumes the result.
- It does **not** emit `feature_state_changed` events. Spec-issue triage does not change feature state — the feature may be in any state when a spec issue arrives.
- It does **not** modify the feature registry frontmatter. Feature state transitions during triage (if any) are the human's or PM agent's responsibility.

## Deferred integration

### Phase 5 — Generator feedback loop

Phase 5 introduces the generator feedback loop, which will:

1. **Consume `spec_issue_routed` events** to track generator issues filed by this skill.
2. **Close the loop** when generator template fixes land — re-running generation, verifying the fix resolved the original issue, and notifying the downstream agent.
3. **Enable case (c) prevention** — when the generator feedback loop detects that spec changes cause generated-output regressions, it can proactively flag the spec change before it propagates.

Phase 4 does **not** introduce this loop. The v1.0 spec-issue-triage skill files generator issues and stops. The generator feedback loop will pick up from where this skill leaves off.

## References

- `/docs/orchestrator-architecture.md` §7.4 (inbox flow), §9.1 (generated code rules).
- `/agents/specs/CLAUDE.md` — the specs agent role config that orchestrates this skill.
- `/agents/specs/skills/spec-drafting/SKILL.md` — the skill that originally drafted the specs this skill may correct.
- `/agents/specs/skills/spec-validation/SKILL.md` — the validation procedure this skill invokes after a spec fix.
- `/agents/component/skills/escalation/SKILL.md` — the component agent's spec-issue filing behavior (the incoming contract for this skill).
- `/shared/templates/spec-issue.md` — the template downstream agents use to file spec issues (the inbox file format).
- `/shared/templates/human-escalation.md` — the template for case (d) escalations.
- `/shared/schemas/event.schema.json` — event envelope schema.
- `/shared/schemas/events/spec_issue_resolved.schema.json` — per-type schema for resolution events (authored in this WU).
- `/shared/schemas/events/spec_issue_routed.schema.json` — per-type schema for routing events (authored in this WU).
- `/shared/rules/verify-before-report.md` — re-read discipline and event-emission operational discipline.
- `/shared/rules/never-touch.md` — path prohibition.
- `/shared/rules/escalation-protocol.md` — escalation for ambiguous triage (case d) and spinning detection.
