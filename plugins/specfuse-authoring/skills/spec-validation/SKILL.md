---
name: spec-validation
description: "Invoke Specfuse validation on drafted specs, interpret the output into actionable failure feedback (via a common-error interpretation table), and own the drafting → validating → planning state transitions that hand the initiative to the PM agent. Use when the human requests validation during or after a drafting session; emits spec_validated and feature_state_changed events with idempotence guards, and never self-validates, fixes specs, or transitions on a failed run."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Spec validation — v1.1

> **Reframe note (Model B; docs/naming-convention.md).** The unit being validated is an
> **initiative** (`INIT-YYYY-NNNN`). The `drafting → validating → planning` transitions are on the
> initiative; the `validating → planning` handoff hands the **initiative** to the PM agent, whose
> **`feature-decomposition`** skill (reframed from `task-decomposition`) decomposes it into a
> `feature_graph`. Map feature→initiative / `FEAT-`→`INIT-` for the orchestrator-unit references
> below; generic "spec"/product wording is unchanged.

Invokes Specfuse validation on drafted specs, interprets the output, presents actionable feedback on failures, and owns the `drafting → validating → planning` state transitions that hand the **initiative** off to the PM agent. This is the gating skill between the specs agent's conversational work and the PM agent's structured planning work: when this skill emits `feature_state_changed(validating → planning)`, the PM agent's `feature-decomposition` skill is the next actor (it decomposes the initiative into features).

When this file and the specs agent role config disagree, **the role config wins and this file is wrong.** Raise an escalation rather than reconciling silently.

## Trigger

The human says something like "run validation on INIT-2026-NNNN" or "validate the specs" during a drafting session (first-pass validation) or after fixing issues surfaced by a prior run (re-validation). The trigger is conversational — there is no structured-event trigger.

**Precondition.** A valid initiative registry entry must exist at `/features/INIT-YYYY-NNNN.md` with `state: drafting` (first-pass) or `state: validating` (re-validation after a failed pass). The `## Related specs` section must contain at least one spec file link — validation against zero files is a configuration error, not a pass. If the feature is in any state other than `drafting` or `validating`, the skill does not proceed — it informs the human and suggests the appropriate entry point.

## Inputs

The skill reads, in order:

1. The initiative registry entry at `/features/INIT-YYYY-NNNN.md` — its frontmatter (`correlation_id`, `state`, `involved_repos`) and its `## Related specs` body section (which lists the spec file paths to validate).
2. This skill file and the specs agent role config — reloaded per `/shared/rules/role-switch-hygiene.md`.
3. The feature's event log at `/events/INIT-YYYY-NNNN.jsonl` — read to determine whether prior `spec_validated` and `feature_state_changed` events exist for this feature (required for idempotence guards in Steps 3 and 8).
4. Each spec file listed in `## Related specs` — read and passed to the Specfuse validator.

## Procedure

### Step 1 — Read the initiative registry and confirm preconditions

Read `/features/INIT-YYYY-NNNN.md`. Extract the `state` from frontmatter and the spec file paths from the `## Related specs` section.

**Extracting spec file paths.** The `## Related specs` section contains markdown list items linking to spec files. Each item follows the convention:

```markdown
- `product/specs/<feature-slug>.yaml` — description...
- `product/features/INIT-YYYY-NNNN.md` — description...
```

Extract the path from the backtick-enclosed segment of each list item. The paths are relative to the product specs repo root.

**Precondition checks:**

| Condition | Action |
|---|---|
| `state` is `drafting` | First-pass validation. Proceed to Step 2. |
| `state` is `validating` | Re-validation. Skip Step 2 (the `drafting → validating` transition has already occurred). Proceed to Step 3. |
| `state` is any other value | Do not proceed. Inform the human: "Feature INIT-YYYY-NNNN is in state `<state>` — validation requires `drafting` or `validating`. If you need to re-draft, use the spec-drafting skill. If the feature is already in `planning` or beyond, the PM agent has taken over." |
| `## Related specs` has zero file links | Do not proceed. Inform the human: "No spec files found in the initiative registry's Related specs section. Use the spec-drafting skill to create at least one spec file before running validation." |

### Step 2 — Emit `drafting → validating` transition (first-pass only)

This step runs only when the feature's current state is `drafting`. On re-validation (state is already `validating`), this step is skipped — no duplicate state-transition event is emitted.

**2a.** Update the initiative registry frontmatter: change `state: drafting` to `state: validating`.

**2b.** Construct the `feature_state_changed` event:

| Field | Value |
|---|---|
| `timestamp` | `date -u +%Y-%m-%dT%H:%M:%SZ` — captured at emission time |
| `correlation_id` | `INIT-YYYY-NNNN` |
| `event_type` | `feature_state_changed` |
| `source` | `specs` |
| `source_version` | The literal `"n/a"` — the specs agent is a session-driven external actor across the plane seam, not a versioned orchestrator role |
| `payload.from_state` | `drafting` |
| `payload.to_state` | `validating` |
| `payload.trigger` | `validation_requested` |

**2c.** Write the event to `/tmp/event.json`. Validate through `scripts/validate-event.py`:

```sh
python3 scripts/validate-event.py --file /tmp/event.json
```

Exit 0: append to the event log using the safe append pattern:

```sh
printf '%s\n' "$(cat /tmp/event.json)" >> events/INIT-YYYY-NNNN.jsonl
```

Exit 1 or 2: diagnose, correct, re-validate. Three consecutive failures → escalate with `spinning_detected`.

### Step 3 — Invoke the Specfuse validator

For each spec file path extracted in Step 1, invoke the Specfuse validator:

```sh
specfuse validate <spec-file-path>
```

The validator is invoked once per spec file. Capture:

- The exit code (0 = pass, non-zero = at least one error).
- The structured output (JSON array of error objects, each with `file`, `line`, `message`, `severity` fields).
- The validator version (`specfuse --version`), captured once at the start of the validation run — not per-file.

**Collecting results.** Aggregate the per-file results into a single validation result:

- `pass`: `true` if every file's exit code is 0; `false` if any file produces a non-zero exit code.
- `spec_files_checked`: the ordered list of paths that were validated.
- `errors`: the union of all error objects across all files (empty when `pass` is `true`).
- `validator_version`: the captured version string.

### Step 4 — Emit the `spec_validated` event

Construct the `spec_validated` event with the aggregated results:

| Field | Value |
|---|---|
| `timestamp` | `date -u +%Y-%m-%dT%H:%M:%SZ` — captured at emission time |
| `correlation_id` | `INIT-YYYY-NNNN` |
| `event_type` | `spec_validated` |
| `source` | `specs` |
| `source_version` | The literal `"n/a"` — the specs agent is a session-driven external actor across the plane seam, not a versioned orchestrator role |
| `payload.feature_correlation_id` | `INIT-YYYY-NNNN` |
| `payload.pass` | `true` or `false` |
| `payload.spec_files_checked` | Array of paths from Step 3 |
| `payload.errors` | Array of error objects from Step 3 (empty on pass) |
| `payload.validator_version` | Captured version string |

Write to `/tmp/event.json`, validate, and append:

```sh
python3 scripts/validate-event.py --file /tmp/event.json
# Exit 0 → append
printf '%s\n' "$(cat /tmp/event.json)" >> events/INIT-YYYY-NNNN.jsonl
```

Three consecutive validation failures → `spinning_detected` escalation.

### Step 5 — Branch on validation result

**If `pass` is `false`:** proceed to Step 6 (present failure feedback). The feature stays in `validating`.

**If `pass` is `true`:** proceed to Step 7 (present success summary), then Step 8 (emit `validating → planning` transition).

### Step 6 — Present actionable failure feedback

The skill does **not** dump raw validator output. For each error in the `errors` array, the skill:

1. Looks up the error in the [interpretation table](#interpretation-table-for-common-specfuse-validation-errors) below.
2. If a match is found: presents the interpreted guidance — the specific file and line, what went wrong in plain language, and a concrete suggestion for fixing it.
3. If no match is found: presents the raw error with a caveat: "This error is not in my interpretation table — please review the raw validator output below."

**Presentation format:**

```
Validation failed for INIT-YYYY-NNNN — N error(s) across M file(s).

──────────────────────────────────────────────────────────────────

File: product/specs/<feature-slug>.yaml
Line: 42

  Error: <plain-language description of what went wrong>

  Fix:   <concrete remediation step>

  Raw:   <original validator message, for reference>

──────────────────────────────────────────────────────────────────

File: product/specs/<feature-slug>.yaml
Line: 78

  ...

──────────────────────────────────────────────────────────────────

The feature remains in `validating`. Fix the issues above and ask me
to re-validate when ready.
```

After presenting the feedback, the skill's work for this run is complete. The human works with the spec-drafting skill to fix the issues, then triggers re-validation by returning to this skill.

### Step 7 — Present success summary

On a clean pass:

```
Validation passed for INIT-YYYY-NNNN — N file(s) checked, 0 errors.

Files validated:
  - product/specs/<feature-slug>.yaml  ✓
  - product/features/INIT-YYYY-NNNN.md ✓

Proceeding to hand off to the PM agent for task decomposition.
```

### Step 8 — Emit `validating → planning` transition (clean pass only)

This step runs only on a clean validation pass (`pass` is `true`).

**8a. Idempotence guard.** Read the event log at `/events/INIT-YYYY-NNNN.jsonl`. Scan for a prior `feature_state_changed` event where `payload.from_state` is `validating` and `payload.to_state` is `planning`. If found, the transition has already been emitted (e.g., the human ran validation again after a prior clean pass without any intervening changes) — skip the rest of this step and report:

```
Feature INIT-YYYY-NNNN has already transitioned to `planning`.
The PM agent can pick up the feature for task decomposition.
```

**8b.** Update the initiative registry frontmatter: change `state: validating` to `state: planning`.

**8c.** Construct the `feature_state_changed` event:

| Field | Value |
|---|---|
| `timestamp` | `date -u +%Y-%m-%dT%H:%M:%SZ` — captured at emission time |
| `correlation_id` | `INIT-YYYY-NNNN` |
| `event_type` | `feature_state_changed` |
| `source` | `specs` |
| `source_version` | The literal `"n/a"` — the specs agent is a session-driven external actor across the plane seam, not a versioned orchestrator role |
| `payload.from_state` | `validating` |
| `payload.to_state` | `planning` |
| `payload.trigger` | `validation_passed` |

**8d.** Write to `/tmp/event.json`, validate, and append:

```sh
python3 scripts/validate-event.py --file /tmp/event.json
# Exit 0 → append
printf '%s\n' "$(cat /tmp/event.json)" >> events/INIT-YYYY-NNNN.jsonl
```

**8e.** Report completion:

```
Feature INIT-YYYY-NNNN is ready for PM planning.

State: validating → planning
Trigger: validation_passed
PM handoff: the PM agent's task-decomposition skill can now pick up
this feature.
```

This is the last action the specs agent takes on this feature's forward path. After the handoff, the PM agent is the next actor.

### Step 9 — Verify

Per `verify-before-report.md`:

1. Re-read `/features/INIT-YYYY-NNNN.md` and confirm the `state` field matches the expected value (`validating` on failure, `planning` on success).
2. Re-read `/events/INIT-YYYY-NNNN.jsonl` and round-trip the most recent event(s) through `validate-event.py` with exit 0.
3. If the `validating → planning` transition was emitted: confirm no written path is in `never-touch.md`.

Three consecutive re-read failures → `spinning_detected` escalation per `escalation-protocol.md`.

## State transition discipline

The skill owns two feature-level transitions. Both are emitted as `feature_state_changed` events with structured payloads per `feature_state_changed.schema.json`.

### `drafting → validating`

- **When:** the human requests validation and the feature is currently in `drafting`.
- **Timing:** emitted **before** the validator runs (Step 2), so that the event log records the intent to validate even if the validator invocation fails.
- **Trigger:** `validation_requested`.
- **Idempotence:** if the feature is already in `validating` (re-validation), the transition is skipped entirely — no duplicate event is emitted. The `validating` state means "validation in progress or awaiting fix + re-validation."
- **Registry update:** `state: drafting` → `state: validating` in the feature's frontmatter.

### `validating → planning`

- **When:** all spec files pass validation with zero errors.
- **Timing:** emitted **after** the `spec_validated(pass: true)` event (Step 8), as the last action of the skill.
- **Trigger:** `validation_passed`.
- **Idempotence:** guarded by scanning the event log for a prior `feature_state_changed` event with `from_state: validating` and `to_state: planning`. If found, the transition is skipped. This prevents duplicate handoffs if the human runs validation again on unchanged, already-validated specs.
- **Registry update:** `state: validating` → `state: planning` in the feature's frontmatter.
- **PM handoff:** this transition is what releases the PM agent's task-decomposition skill. Once emitted, the PM agent can pick up the feature. On a failed validation, the feature stays in `validating` — the skill does **not** transition back to `drafting` on failure, because that would require the human to re-trigger the `drafting → validating` transition unnecessarily.

## Validation output structure

Every validation run (pass or fail) produces a `spec_validated` event. The per-type payload schema is `spec_validated.schema.json`, with fields:

| Field | Type | Description |
|---|---|---|
| `feature_correlation_id` | `string` | `INIT-YYYY-NNNN` — duplicated from envelope for payload self-containment |
| `pass` | `boolean` | `true` if all files pass; `false` if any file has errors |
| `spec_files_checked` | `string[]` | Paths checked, relative to product specs repo root |
| `errors` | `object[]` | Structured error objects (empty on pass) |
| `errors[].file` | `string` | Spec file path that produced the error |
| `errors[].line` | `integer` | Line number (0 if not reported) |
| `errors[].message` | `string` | Validator's raw error message |
| `errors[].severity` | `string` | `error` (blocks) or `warning` (advisory) |
| `validator_version` | `string` | Specfuse validator version used |

The event log is append-only. A re-validation after a fix produces a **new** `spec_validated` event — prior failures are preserved for audit. Consumers that need the current validation status read the most recent `spec_validated` event for the feature.

## Interpretation table for common Specfuse validation errors

The skill translates raw validator errors into actionable remediation. For each error encountered during a validation run, the skill looks up the error's message pattern in this table and presents the corresponding plain-language explanation and fix.

| Error pattern | Plain-language explanation | Remediation |
|---|---|---|
| `missing required property: operationId` | An API operation is missing its `operationId` field. Every OpenAPI operation must have a unique `operationId` — it is the stable identifier that downstream skills (QA, component) use to reference specific endpoints. | Add an `operationId` field to the operation. Use a camelCase name that describes the action: e.g., `operationId: listWidgets` for `GET /widgets`. |
| `missing required property: summary` | An API operation is missing its `summary` field. While not always schema-required, the Specfuse validator enforces `summary` for spec readability. | Add a `summary` field with a brief description of what the operation does: e.g., `summary: List all widgets`. |
| `duplicate operationId: <id>` | Two or more operations share the same `operationId`. Operation IDs must be unique across the entire spec document. | Rename one of the duplicate operations. Use a more specific name that distinguishes the two: e.g., `listWidgets` vs. `listArchivedWidgets`. |
| `invalid \$ref: <path>` | A `$ref` JSON reference points to a schema or component that does not exist in the document. | Check the `$ref` path for typos. Verify the target schema exists under `components/schemas/` (or the appropriate section). Common mistakes: wrong casing, missing the leading `#/`. |
| `missing required property: info` | The spec document is missing the top-level `info` object, which is required by the OpenAPI specification. | Add an `info` object with at least `title` and `version` fields at the top level of the spec. |
| `missing required property: paths` | The spec document has no `paths` object. At least one path is required for the validator to consider the spec meaningful. | Add a `paths` object containing at least one path definition with at least one operation. |
| `invalid response status code: <code>` | A response is declared with an HTTP status code that is not a valid three-digit code or a valid range pattern (`2XX`, `3XX`, etc.). | Correct the status code. Use standard HTTP status codes: `200`, `201`, `204`, `400`, `404`, `409`, `500`. Range patterns: `2XX`, `3XX`, `4XX`, `5XX`. |
| `path parameter .* not found in path template` | A parameter declared with `in: path` does not appear as a `{placeholder}` in the URL path template. | Either add `{<param_name>}` to the path string, or change the parameter's `in` value to `query` or `header` if it is not a path segment. |
| `schema type mismatch` | A schema declares a `type` that conflicts with the surrounding context or a `$ref` target's type. | Review the schema definition. Common cause: a `$ref` points to an object schema but the enclosing context expects an array (or vice versa). Wrap with `type: array` + `items: {$ref: ...}` if an array of objects is intended. |
| `YAML syntax error at line <N>` | The spec file is not valid YAML. The parser cannot proceed beyond the indicated line. | Open the file and check line N for common YAML mistakes: incorrect indentation, unquoted special characters (`:`, `#`, `@`), missing colons after keys, tabs mixed with spaces. |
| `JSON syntax error` | The spec file is not valid JSON. | Run the file through a JSON linter. Common causes: trailing commas, unquoted keys, single-quoted strings (JSON requires double quotes). |
| `unknown spec format` | The validator cannot determine whether the file is OpenAPI, AsyncAPI, or Arazzo. | Ensure the file has the correct top-level discriminator: `openapi: "3.x.x"` for OpenAPI, `asyncapi: "2.x.x"` or `asyncapi: "3.x.x"` for AsyncAPI, `arazzo: "1.0"` for Arazzo. |
| `missing channel` or `missing channels` | An AsyncAPI document is missing the `channels` section. | Add a `channels` object with at least one channel definition. Each channel must have a name and at least one operation (publish/subscribe). |
| `invalid sourceDescription reference` | An Arazzo workflow references a `sourceDescription` that does not exist in the document's `sourceDescriptions` array. | Check the `sourceDescriptions` array at the top level of the Arazzo document. Add the missing entry, ensuring the `name` matches what the workflow step references and the `url` points to a valid OpenAPI or AsyncAPI document. |
| `acceptance criterion .* not testable` | A feature narrative's acceptance criterion does not map to a testable behavior — it is too vague, describes multiple behaviors, or lacks an observable outcome. | Rewrite the criterion to describe a single, observable behavior. Each criterion should answer: "What input triggers this behavior? What observable outcome does it produce?" See the spec-drafting skill's §"Writing acceptance criteria that the QA agent can consume" for examples. |

**Errors not in the table.** For any error whose message does not match a pattern in the table above, the skill presents the raw error with:

```
This error is not in my interpretation table — please review the raw
validator output below.

  File: <file>
  Line: <line>
  Raw:  <original message>
  Severity: <severity>

If this error recurs across features, consider filing an issue to
expand the interpretation table.
```

## Idempotence under re-validation

The skill handles two modes — first-pass and re-validation — and must be idempotent: running validation twice on unchanged specs produces the same result without duplicate state-transition events.

**State transitions are guarded, not events.** The event log is append-only: every validation run produces a new `spec_validated` event, even if the result is identical to a prior run. This is correct — the append-only log records that validation was invoked, not just its outcome. State transitions, however, are **not** append-only: each transition happens at most once per feature per direction.

**Guards:**

1. **`drafting → validating` guard (Step 2).** Before emitting, check the registry's `state` field. If it is already `validating`, the transition has been emitted in a prior run — skip Step 2 entirely. This covers the re-validation case: the human fixed issues and is asking for another pass without needing to re-enter `drafting`.

2. **`validating → planning` guard (Step 8a).** Before emitting, scan the event log for a prior `feature_state_changed` event with `payload.from_state: "validating"` and `payload.to_state: "planning"` on this feature's correlation ID. If found, the handoff has already occurred — skip the transition. This covers the case where the human runs validation a second time after a prior clean pass.

**Prior failures are preserved.** A re-validation after a fix produces a new `spec_validated` event. The event log therefore contains the full history: prior failed runs followed by the successful run. No events are deleted or overwritten.

## Worked example

A realistic validation session for a feature with two spec files, demonstrating both failure and success paths, the interpretation of errors, and the state transitions.

---

**Context.** The human has drafted specs for `INIT-2026-0042` (Inventory API bookmarks). The initiative registry at `/features/INIT-2026-0042.md` has `state: drafting` and the following `## Related specs` section:

```markdown
## Related specs

- `product/features/INIT-2026-0042.md` — feature narrative with acceptance
  criteria (AC-1 through AC-5).
- `product/specs/inventory-api-bookmarks.yaml` — OpenAPI spec for the
  bookmarks endpoints.
```

---

### First validation run — failure

**Human:** "Run validation on INIT-2026-0042."

**Step 1 — Precondition check:**

The skill reads `/features/INIT-2026-0042.md`. State is `drafting`. Two spec files found in `## Related specs`. Preconditions pass.

**Step 2 — Emit `drafting → validating`:**

```sh
# Update registry frontmatter
# state: drafting → state: validating

# Capture timestamp and version
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SOURCE_VERSION="n/a"   # session-driven external actor; not a versioned orchestrator role

# Construct event
cat > /tmp/event.json << EOF
{"timestamp":"${TIMESTAMP}","correlation_id":"INIT-2026-0042","event_type":"feature_state_changed","source":"specs","source_version":"${SOURCE_VERSION}","payload":{"from_state":"drafting","to_state":"validating","trigger":"validation_requested"}}
EOF

# Validate and append
python3 scripts/validate-event.py --file /tmp/event.json
# Exit 0
printf '%s\n' "$(cat /tmp/event.json)" >> events/INIT-2026-0042.jsonl
```

**Step 3 — Invoke Specfuse validator:**

```sh
VALIDATOR_VERSION=$(specfuse --version)
# → "1.0.0"

specfuse validate product/features/INIT-2026-0042.md
# Exit 0 — narrative spec passes

specfuse validate product/specs/inventory-api-bookmarks.yaml
# Exit 1 — one error
```

Validator output for `inventory-api-bookmarks.yaml`:

```json
[
  {
    "file": "product/specs/inventory-api-bookmarks.yaml",
    "line": 18,
    "message": "missing required property: operationId",
    "severity": "error"
  }
]
```

Aggregated result: `pass: false`, 1 error across 2 files.

**Step 4 — Emit `spec_validated` event:**

```sh
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SOURCE_VERSION="n/a"   # session-driven external actor; not a versioned orchestrator role

cat > /tmp/event.json << EOF
{"timestamp":"${TIMESTAMP}","correlation_id":"INIT-2026-0042","event_type":"spec_validated","source":"specs","source_version":"${SOURCE_VERSION}","payload":{"feature_correlation_id":"INIT-2026-0042","pass":false,"spec_files_checked":["product/features/INIT-2026-0042.md","product/specs/inventory-api-bookmarks.yaml"],"errors":[{"file":"product/specs/inventory-api-bookmarks.yaml","line":18,"message":"missing required property: operationId","severity":"error"}],"validator_version":"1.0.0"}}
EOF

python3 scripts/validate-event.py --file /tmp/event.json
# Exit 0
printf '%s\n' "$(cat /tmp/event.json)" >> events/INIT-2026-0042.jsonl
```

**Step 5 — Branch:** `pass` is `false` → proceed to Step 6.

**Step 6 — Actionable failure feedback:**

The skill looks up `missing required property: operationId` in the interpretation table. Match found. Presents:

```
Validation failed for INIT-2026-0042 — 1 error across 2 files.

──────────────────────────────────────────────────────────────────

File: product/specs/inventory-api-bookmarks.yaml
Line: 18

  Error: An API operation is missing its `operationId` field. Every
         OpenAPI operation must have a unique `operationId` — it is
         the stable identifier that downstream skills (QA, component)
         use to reference specific endpoints.

  Fix:   Add an `operationId` field to the operation at line 18.
         Use a camelCase name that describes the action: e.g.,
         `operationId: listBookmarks` for the GET /bookmarks
         endpoint.

  Raw:   missing required property: operationId

──────────────────────────────────────────────────────────────────

The feature remains in `validating`. Fix the issue above and ask me
to re-validate when ready.
```

**Verification (Step 9):** registry state is `validating` ✓. Event log has two entries (`feature_state_changed` + `spec_validated`), both validate ✓.

---

### Re-validation after fix — success

The human opens the OpenAPI spec and adds `operationId: listBookmarks` to the `GET /users/{user_id}/bookmarks` operation at line 18.

**Human:** "I've added the operationId. Re-validate."

**Step 1 — Precondition check:**

Registry state is `validating`. Two spec files in `## Related specs`. Preconditions pass.

**Step 2 — Skipped.** State is `validating`, not `drafting`. No `drafting → validating` transition is emitted. Idempotence: the transition from the first run is preserved.

**Step 3 — Invoke Specfuse validator:**

```sh
VALIDATOR_VERSION=$(specfuse --version)
# → "1.0.0"

specfuse validate product/features/INIT-2026-0042.md
# Exit 0

specfuse validate product/specs/inventory-api-bookmarks.yaml
# Exit 0
```

Aggregated result: `pass: true`, 0 errors across 2 files.

**Step 4 — Emit `spec_validated` event:**

```sh
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SOURCE_VERSION="n/a"   # session-driven external actor; not a versioned orchestrator role

cat > /tmp/event.json << EOF
{"timestamp":"${TIMESTAMP}","correlation_id":"INIT-2026-0042","event_type":"spec_validated","source":"specs","source_version":"${SOURCE_VERSION}","payload":{"feature_correlation_id":"INIT-2026-0042","pass":true,"spec_files_checked":["product/features/INIT-2026-0042.md","product/specs/inventory-api-bookmarks.yaml"],"errors":[],"validator_version":"1.0.0"}}
EOF

python3 scripts/validate-event.py --file /tmp/event.json
# Exit 0
printf '%s\n' "$(cat /tmp/event.json)" >> events/INIT-2026-0042.jsonl
```

**Step 5 — Branch:** `pass` is `true` → proceed to Step 7, then Step 8.

**Step 7 — Success summary:**

```
Validation passed for INIT-2026-0042 — 2 files checked, 0 errors.

Files validated:
  - product/features/INIT-2026-0042.md            ✓
  - product/specs/inventory-api-bookmarks.yaml     ✓

Proceeding to hand off to the PM agent for task decomposition.
```

**Step 8 — Emit `validating → planning`:**

**8a.** Idempotence guard: scan event log for `feature_state_changed(validating → planning)` on INIT-2026-0042. Not found — this is the first clean pass. Proceed.

**8b.** Update registry frontmatter: `state: validating` → `state: planning`.

**8c–8d.** Construct, validate, and append the event:

```sh
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SOURCE_VERSION="n/a"   # session-driven external actor; not a versioned orchestrator role

cat > /tmp/event.json << EOF
{"timestamp":"${TIMESTAMP}","correlation_id":"INIT-2026-0042","event_type":"feature_state_changed","source":"specs","source_version":"${SOURCE_VERSION}","payload":{"from_state":"validating","to_state":"planning","trigger":"validation_passed"}}
EOF

python3 scripts/validate-event.py --file /tmp/event.json
# Exit 0
printf '%s\n' "$(cat /tmp/event.json)" >> events/INIT-2026-0042.jsonl
```

**8e.** Report:

```
Feature INIT-2026-0042 is ready for PM planning.

State: validating → planning
Trigger: validation_passed
PM handoff: the PM agent's task-decomposition skill can now pick up
this feature.
```

**Verification (Step 9):** registry state is `planning` ✓. Event log has four entries (`feature_state_changed(drafting→validating)`, `spec_validated(pass:false)`, `spec_validated(pass:true)`, `feature_state_changed(validating→planning)`), all validate ✓. No duplicate state transitions ✓.

---

### Event log after the worked example

The event log at `/events/INIT-2026-0042.jsonl` contains four entries (plus the `feature_created` from intake):

| # | `event_type` | Key payload fields |
|---|---|---|
| 1 | `feature_created` | (from intake — pre-existing) |
| 2 | `feature_state_changed` | `from_state: drafting`, `to_state: validating`, `trigger: validation_requested` |
| 3 | `spec_validated` | `pass: false`, 1 error (missing operationId) |
| 4 | `spec_validated` | `pass: true`, 0 errors |
| 5 | `feature_state_changed` | `from_state: validating`, `to_state: planning`, `trigger: validation_passed` |

**Confirming the acceptance criteria:**

- **(a)** First validation emits `drafting → validating` (entry 2) + `spec_validated(pass: false)` (entry 3). ✓
- **(b)** Re-validation emits `spec_validated(pass: true)` (entry 4) + `validating → planning` (entry 5). ✓
- **(c)** No duplicate state transitions: one `drafting → validating`, one `validating → planning`. ✓
- **(d)** The `validating → planning` transition is the last action — no further specs-agent work after the handoff. ✓

## Artifacts produced

| Artifact | Path | Validated against |
|---|---|---|
| Initiative registry entry (state update) | `/features/INIT-YYYY-NNNN.md` | `feature-frontmatter.schema.json` via `validate-frontmatter.py` |
| `feature_state_changed` event(s) | `/events/INIT-YYYY-NNNN.jsonl` | `event.schema.json` + `feature_state_changed.schema.json` via `validate-event.py` |
| `spec_validated` event | `/events/INIT-YYYY-NNNN.jsonl` | `event.schema.json` + `spec_validated.schema.json` via `validate-event.py` |

## Schemas consumed

- `shared/schemas/event.schema.json` — event envelope validation.
- `shared/schemas/events/feature_state_changed.schema.json` — per-type payload validation for state transition events.
- `shared/schemas/events/spec_validated.schema.json` — per-type payload validation for validation result events (authored in this WU).
- `shared/schemas/feature-frontmatter.schema.json` — frontmatter validation after registry state updates.

## Rules absorbed

- `shared/rules/correlation-ids.md` — feature-level ID used in event envelopes and payloads.
- `shared/rules/verify-before-report.md` — four-step cycle, event-emission operational discipline (timestamps at emission time, canonical `--file /tmp/event.json` invocation, JSONL single-line requirement, safe append pattern), corrective cycle limit.
- `shared/rules/never-touch.md` — path prohibition check on every write.
- `shared/rules/state-vocabulary.md` — `validating` and `planning` states, transition legality.
- `shared/rules/escalation-protocol.md` — `spinning_detected` escalation after three consecutive validation failures.
- `shared/rules/role-switch-hygiene.md` — re-read shared rules unconditionally at the start of every task.

## Anti-patterns

1. **Self-validating.** The skill runs the Specfuse validator — it does not judge whether the spec "looks correct." "The spec looks valid to me" is not validation; it must be `specfuse validate <file>` with exit 0.
2. **Emitting `validating → planning` on a failed run.** The transition is gated on `pass: true`. A false `validating → planning` transition releases task decomposition on an unvalidated spec — the single worst outcome this skill can produce.
3. **Emitting duplicate state transitions.** Running validation twice on unchanged specs must not produce two `drafting → validating` events or two `validating → planning` events. The guards in Steps 2 and 8a prevent this.
4. **Transitioning back to `drafting` on failure.** On a failed validation, the feature stays in `validating`. The `validating` state means "validation in progress or awaiting fix + re-validation." Transitioning back to `drafting` would force the human to re-trigger the `drafting → validating` transition unnecessarily.
5. **Dumping raw validator output without interpretation.** The skill's value is translating machine output into human-actionable guidance. Presenting raw JSON errors without context, specific file locations, and concrete fix suggestions fails the human.
6. **Skipping the `spec_validated` event on failure.** The `spec_validated` event is emitted on **every** run, pass or fail. The append-only log records the full validation history. Skipping the event on failure hides the failure from audit.
7. **Eye-caching `validator_version`.** It is captured at execution time via `specfuse --version`; a stale string produces a misleading audit trail. `source_version` is not read from anywhere — it is the constant `"n/a"` for this role (see the event-field tables above).
8. **Appending events before validation.** Events must pass `validate-event.py` with exit 0 before append. An invalid event in the log corrupts the audit trail.
9. **Modifying spec files.** The spec-validation skill does not fix specs. It reports what is wrong. The spec-drafting skill is the tool for fixing spec content.
10. **Performing work after the PM handoff.** The `validating → planning` transition is the last action. After emitting it, the specs agent has no further forward-path work on this feature. Any follow-up (spec-issue triage on routed issues) is a separate entry point, not a continuation of the validation session.

## What this skill does not do

- It does **not** draft or fix specs. That is the spec-drafting skill's concern. This skill reports what is wrong; the human and the spec-drafting skill fix it.
- It does **not** create the task graph or open issues. That is the PM agent's territory — specifically `task-decomposition/SKILL.md`, which is triggered by the `planning` state this skill produces.
- It does **not** author test plans. That is the QA agent's concern via `qa-authoring/SKILL.md`.
- It does **not** write to `/product/`. The validation skill reads spec files; it does not modify them.
- It does **not** write to `/business/`. That subtree is off-limits per `never-touch.md` §4.
- It does **not** modify `event.schema.json`'s enum. The `spec_validated` type already exists in the Phase 1 baseline. This WU adds only the per-type payload schema.
- It does **not** modify the PM agent's configuration or any downstream skill. The handoff is clean: emit the event, update the state, stop.

## References

- `/docs/orchestrator-architecture.md` §6.1 (feature state machine), §6.3 (transition ownership).
- `/agents/specs/CLAUDE.md` — the specs agent role config that orchestrates this skill.
- `/agents/specs/skills/spec-drafting/SKILL.md` — the preceding skill that produces the spec files this skill validates; also the skill the human returns to when fixing validation failures.
- `/agents/specs/skills/initiative-intake/SKILL.md` — the intake skill that creates the initiative registry entry this skill reads and updates.
- `/agents/pm/skills/task-decomposition/SKILL.md` — the downstream skill that consumes the `planning` state this skill produces; the PM handoff target.
- `/shared/schemas/event.schema.json` — event envelope schema.
- `/shared/schemas/events/feature_state_changed.schema.json` — per-type schema for state transitions.
- `/shared/schemas/events/spec_validated.schema.json` — per-type schema for validation results (authored in this WU).
- `/shared/schemas/feature-frontmatter.schema.json` — frontmatter validation for registry state updates.
- `/shared/rules/verify-before-report.md` — re-read discipline and event-emission operational discipline.
- `/shared/rules/never-touch.md` — path prohibition.
- `/shared/rules/state-vocabulary.md` — feature state machine states and transitions.
- `/shared/rules/escalation-protocol.md` — `spinning_detected` escalation.
- `/docs/walkthroughs/phase-3/retrospective.md` — WU 3.10 idempotence guard pattern.
