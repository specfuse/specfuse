---
name: design-async
description: "Design or add async specifications (events, scheduled jobs, handlers) for a domain in the v2 pub-sub architecture. Use when modeling an event-driven flow -- API-triggered events, fan-out jobs, or workers; enforces the AsyncAPI handbook's three allowed patterns, message/snapshot/operation shapes, x-emits cross-links, and full validation."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Design or add async specifications (events, scheduled jobs) for a domain in the v2 pub-sub architecture.

*Enforces: .specfuse/authoring/handbooks/AsyncAPI_Handbook.md*

**Before writing any files**, read and internalize the authoritative rules:
1. Read `.specfuse/authoring/handbooks/AsyncAPI_Handbook.md` — the full handbook, especially Section 1 (Architectural Principles)
2. Read `api/specs/CLAUDE.md` — Section 10 (AsyncAPI Files — Critical Rules)
3. Read `.specfuse/authoring/samples/message-samples.yaml` — canonical templates to copy from

## Architectural constraints — ALWAYS adopt these

The v2 async architecture is deliberately minimal. Adopt these by default on every design task. If a scenario seems to require deviation, **stop and ask the user before proceeding** — explain what you want to introduce and why the simpler model is insufficient.

1. **Pub-sub only.** Every message is published to a topic. Every consumer subscribes. There are no command queues, no point-to-point sends, no request/reply.
2. **The handler reacting to an event does the actual work directly.** No intermediate command dispatch for the same domain.
3. **Scheduled jobs are thin fan-out dispatchers.** Query DB → publish one event per work item → subscribers handle each independently with per-item retry and DLQ. The job itself does NO heavy processing. The narrow exception (single-output jobs with no per-item semantics) must be obvious — ask if uncertain.
4. **Events carry IDs + changed state only.** Never embed the full aggregate.
5. **No language-specific fields in specs.** No class names, namespaces, or package paths — the generator derives them.

**When you want to deviate:** STOP. Tell the user you think the v2 model is insufficient for this specific scenario. Explain the tradeoff. Wait for explicit approval before introducing anything new.

## Inputs

The user will describe the async process they want to spec. Clarify:
- Which domain does this belong to?
- What triggers the process? (API operation, cron schedule, another event)
- What is the expected outcome?
- If fan-out is involved, confirm the per-item semantics (identifies that thin dispatcher is the right choice)

## Design Process

### Step 1: Identify the pattern

In v2, there are three patterns (and only three). If you find yourself wanting something else, stop and ask.

- **API-triggered event → handler**: An API write operation emits an event; one or more subscribers react and do the work.
- **Scheduled job fan-out**: A cron-triggered thin dispatcher queries the DB and publishes one event per work item; separate subscribers handle each independently.
- **Scheduled job direct (narrow exception)**: A cron job produces a single output with no per-item semantics and does the work directly. Must be justified — when in doubt, default to fan-out.

### Step 2: Design the message flow

Map out the full chain before writing any files. Example (API-triggered):

```
[API] POST /orders/{id}/finalize
  └─ emits → OrderFinalized (event-topic)
       ├─ handler 1 → generates the fulfillment plan (does the work directly)
       ├─ handler 2 → sends notifications
       └─ handler 3 → updates dashboard metrics
```

Example (scheduled job fan-out):

```
CRON trigger → {Job}Job message (run-* operation, action: send, x-worker required)
  └─ dispatcher → queries DB for work items
       └─ publishes N × {SomeEvent} (to relevant event-topic)
            └─ subscriber (on-* operation, action: receive) → processes each item independently (with retry + DLQ)
```

Present the flow to the user and confirm before creating files.

### Step 3: Create the files

For each element in the flow, create the required files in order:

**Messages first** (in `domains/{domain}/messages/`):
- Event: `{EventName}.yaml` — past tense, with `x-message-category: event`, `x-label`, `x-version`
- Scheduled job trigger: `{JobName}Job.yaml` — with `x-message-category: scheduledJob`, `x-label`, `x-version`, `x-scheduled-job`
- Reuse existing OpenAPI models via `$ref: '../models/{Model}.yaml'` — NEVER duplicate schemas

**Channels** (in `domains/{domain}/channels/`):
- Add new messages to existing channels if appropriate
- Create new event-topic channels only for new aggregates
- Each domain has exactly one scheduled-trigger channel (`{domain}-jobs.yaml`)
- Every channel needs: `address`, `description`, `messages`, `x-domain`, `x-channel-type` (`event-topic` or `scheduled-trigger`)

**Async operations** (in `domains/{domain}/async-operations/`):
- Verb prefixes and their rules:
  - `on-*` (`action: receive`, `x-worker` required) — event handlers. These are workers.
  - `run-*` (`action: send`, `x-worker` required) — scheduled job dispatchers. Cron-triggered publishers that query DB and fan out events. These are workers.
  - `emit-*` (`action: send`, NO `x-worker`) — publishing declarations owned by `on-*` workers. These are NOT workers.
- Every `on-*` and `run-*` operation needs: `action`, `channel`, `tags` (one tag), `messages`, `x-worker`
- Every `emit-*` operation needs: `action`, `channel`, `tags` (one tag), `messages` — but NO `x-worker`
- Event-topic receivers (`on-*`) need: `x-subscription` with `name` (MUST equal the operation file stem). Filters are derived from the `messages:` list — DO NOT author a `filter` field. AND-merge tenant/channel scoping via `x-subscription.requiredHeaders` (e.g., `{ tenantId: '<guid>' }` or `{ channel: email }`). Use `x-subscription.filterOverride` only as a justified escape hatch with `description` ≥ 40 chars.
- `on-*` workers that publish events need: (1) a separate `emit-*` operation referencing the emitted message, AND (2) `x-emits` on the `on-*` operation listing the events in `{Entity}.{Action}` format (two-segment label — tenancy lives in envelope ApplicationProperties)
- `run-*` scheduled jobs publish directly via their channel — they do NOT use `emit-*`, `x-emits`, or `x-subscription`
- `x-worker` fields: `idempotent`, `inboxDedup` (default `true`), `concurrency`, `timeout` — NO `type`, `handlerName`, or `namespace`

**Root asyncapi.yaml**:
- Add new channels and operations under the correct domain section
- Add new tags to `info.tags` if this is a new domain

**OpenAPI operations (x-emits)**:
- For events triggered by API operations, update the triggering OpenAPI operation file
- Add `x-emits` with the event's `{Entity}.{Action}` label (must match the message's `x-label`)
- This creates the bidirectional link — the AsyncAPI side has NO reverse pointer; the validator computes it
- Cross-spec validation will fail if the OpenAPI `x-emits.event` has no matching AsyncAPI message

### Step 4: Add recommended extensions

For each message, consider:
- `x-partition-key` if the message requires ordered delivery (events for the same aggregate that must be applied in sequence)

For each operation, add:
- `x-observability` with at least `criticality` chosen from `low | medium | high | critical` (legacy `normal` is rejected — migrate to `medium`); add `sla`, `metrics`, `alertOnDlq` as appropriate

For each entity field carrying PII, sensitive, or encrypted data, declare:
- `x-classification: [pii | sensitive | encrypted]` on the property schema (Vendor_Extensions §1.5). This drives snapshot inclusion review (`x-snapshot-pii-acknowledged` justification required) and AI access shaping.

For each event message, infer the action class from the suffix (handbook §2.2) and shape the payload accordingly:
- `*Created` / `*Updated` / `*Deleted` — payload = `<aggregateId>` + the appropriate `before`/`after` snapshot `$ref`s
- State-transition (anything else) — payload = `<aggregateId>` + `before` + `after` (+ optional `context`) AND `x-trigger-when` predicate over `Before.*`/`After.*` snapshot fields

Snapshots live in `domains/{domain}/events/{Entity}Snapshot.yaml` — one per event-emitting entity, reused across all of its events. See `.specfuse/authoring/samples/message-samples.yaml` §1 for canonical examples of every action class.

### Step 5: Validate

Run the full async validation:
```bash
./scripts/validate-async-structure.sh
./scripts/validate-async-spectral.sh
```

Fix any errors before presenting the result.

### Step 6: Create or update flow documentation

This step is MANDATORY — do not skip it.

1. Check if a flow doc exists in `api/docs/flows/{domain}/` that covers this process
2. If yes: update it to reflect the new/changed operations and messages
3. If no: create a new flow doc following the template in `api/docs/flows/README.md`

The flow doc must include:
- Mermaid sequence diagram showing the complete message flow
- Messages and Operations tables
- Error handling at each step
- Monitoring section based on x-observability values

## Checklist (verify before finishing)

- [ ] Confirmed the design fits the v2 pub-sub architecture — no commands, no sagas, no point-to-point queues
- [ ] Scheduled jobs are thin fan-out dispatchers (or the narrow exception is explicitly justified)
- [ ] Every message has `x-message-category` (`event` or `scheduledJob`), `x-label`, `x-version`
- [ ] `x-label.entity` matches a schema with `x-entity` in OpenAPI
- [ ] Every `on-*` and `run-*` operation has `tags`, `x-worker` (slim form), `action`, `channel`
- [ ] Every `emit-*` operation has `tags`, `action`, `channel`, `messages` — but NO `x-worker`
- [ ] Every operation has `x-observability` with `criticality` from `low | medium | high | critical` (NOT legacy `normal`)
- [ ] Event topic receivers have `x-subscription` with `name` (= operation file stem); filters are derived from `messages:` (no authored `filter` field); use `requiredHeaders` for tenant/channel scoping when needed
- [ ] `on-*` workers that publish events have a separate `emit-*` send operation AND `x-emits` on the `on-*` operation
- [ ] `run-*` scheduled jobs use `action: send` with `x-worker` — they publish directly, no `emit-*` or `x-subscription` needed
- [ ] `emit-*` operations have NO `x-worker` (they are declarations, not workers)
- [ ] Message payloads use `$ref` to existing OpenAPI models for shared types (enums, value objects); event payloads use snapshot `$ref`s into `events/{Entity}Snapshot.yaml` (never raw entity types)
- [ ] Action class shape is correct per name suffix: `*Created` (after) / `*Updated` (before+after) / `*Deleted` (before) / state-transition (before+after, REQUIRES `x-trigger-when`)
- [ ] State-transition events have `x-trigger-when` predicate; `*Created`/`*Updated`/`*Deleted` do NOT
- [ ] Snapshots include scalar columns + owned VOs only (no navigation, no child collections); declare `x-snapshot-pii-acknowledged` per-field if any source entity field is `x-classification: [pii \| sensitive]`
- [ ] Labels are exactly two segments (`{Entity}.{Action}`); tenancy lives in envelope ApplicationProperties
- [ ] Files follow naming conventions (PascalCase messages and snapshots, kebab-case operations/channels)
- [ ] Root `asyncapi.yaml` updated with new channels and operations
- [ ] Flow documentation created/updated in `api/docs/flows/{domain}/`
- [ ] OpenAPI operations updated with `x-emits` for events they trigger
- [ ] No removed/forbidden extensions used (`x-source-aggregate`, `x-target-aggregate`, `x-event`, `x-command`, `x-saga`, `x-dispatches`, `x-worker.type/handlerName/namespace`, `x-action-class`, `x-pii`/`x-sensitive` booleans, three-segment labels, authored `x-subscription.filter`)
- [ ] Validation passes with 0 errors
