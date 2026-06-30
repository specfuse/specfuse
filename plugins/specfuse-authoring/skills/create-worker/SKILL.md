---
name: create-worker
description: "Create an event-handler worker (on-* operation) that subscribes to an existing or new domain event and does the work directly, optionally AI-powered and optionally emitting completion events. Use when adding an async subscriber to the v2 pub-sub architecture; enforces AsyncAPI handbook rules, snapshot payloads, x-subscription/x-emits wiring, and validation."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Create an event-handler worker (`on-*` operation) that subscribes to an existing or new domain event.

*Enforces: .specfuse/authoring/handbooks/AsyncAPI_Handbook.md*

**Before writing any files**, read and internalize the authoritative rules:
1. Read `.specfuse/authoring/handbooks/AsyncAPI_Handbook.md` — Sections 0.4, 4.3, 5.1
2. Read `api/specs/CLAUDE.md` — Section 10 (AsyncAPI Files — Critical Rules)
3. Read `.specfuse/authoring/samples/message-samples.yaml` — samples 5 (event handler) and 7 (emit declaration)

## What this skill creates

An `on-*` event handler worker — a subscriber that reacts to a domain event and does work directly. No intermediate command dispatch.

This skill does NOT create scheduled jobs — use `/create-job` for cron-triggered dispatchers.

## Inputs to clarify with the user

1. **Which domain** does this worker belong to?
2. **Which event** does it react to? (existing message, or a new one to create)
3. **What does the handler do?** (brief description of the work)
4. **Does the handler publish events on completion?** If yes, which ones?
5. **Is this an AI-powered worker?** If yes, what task? Which entities does it read/write?
6. **Concurrency and timeout** — how many parallel handlers, how long can one take?
7. **Criticality** — what happens if this worker fails? (critical/high/medium/low)

## Creation process

### Step 1: Verify the triggering event exists

Check if the event message already exists in `domains/{domain}/messages/`. If not, create it:

- File: `domains/{domain}/messages/{EventName}.yaml` (PascalCase, past tense)
- Required: `x-message-category: event`, `x-label` (entity + past-tense action), `x-version`
- **Action class is inferred from the suffix** (handbook §2.2):
  - `*Created` → payload `[<aggregateId>, after]`
  - `*Updated` → payload `[<aggregateId>, before, after]`
  - `*Deleted` → payload `[<aggregateId>, before]`
  - anything else → payload `[<aggregateId>, before, after, context?]` AND `x-trigger-when` is REQUIRED
- Payload uses snapshot `$ref`s into `domains/{domain}/events/{Entity}Snapshot.yaml` — NEVER raw entity types. One snapshot per entity, reused across all of its events.
- Use `$ref` to existing OpenAPI models for shared types (enums, value objects) — never duplicate schemas
- Add to the shared event topic in `async-common/channels/application-events.yaml`

### Step 2: Create the `on-*` operation

File: `domains/{domain}/async-operations/on-{event-description}.yaml`

```yaml
action: receive
channel:
  $ref: '../channels/{aggregate}-events.yaml'
tags:
  - name: {Domain}                                  # PascalCase, exactly one
summary: {Brief description}
description: |
  {Detailed description of what the handler does.}

  This handler does the work directly — no intermediate command dispatch.
traits:
  - $ref: '../../../async-common/operation-traits/common.yaml#/reliableDelivery'
messages:
  - $ref: '../messages/{EventName}.yaml'
x-worker:                                           # REQUIRED on on-* operations
  idempotent: true
  inboxDedup: true                                  # default true; set false ONLY for side-effect-free handlers
  concurrency: {n}
  timeout: {duration}
x-observability:
  criticality: {level}                              # low | medium | high | critical (legacy 'normal' rejected)
  sla:
    maxProcessingTime: {duration}
  alertOnDlq: true
x-subscription:                                     # REQUIRED on event-topic receivers
  name: on-{event-description}                      # MUST equal the operation file stem
  # NO 'filter' field — filters are derived from messages: above.
  # Generator emits: Label = '{Entity}.{Action}'  (or OR-chain for multi-message subscribers)
  # AND-merge tenant/channel scoping via requiredHeaders:
  #   requiredHeaders: { tenantId: '<guid>' }      → AND user.tenantId = '<guid>'
  #   requiredHeaders: { channel: email }          → AND user.channel = 'email' (requires x-envelope-promote on snapshot field)
```

### Step 3: If the handler publishes events, create `emit-*` declaration(s)

For each event the handler emits on completion:

**3a. Create the emitted event message** (if it doesn't exist):
- File: `domains/{domain}/messages/{EmittedEvent}.yaml`
- Same rules as Step 1

**3b. Create the `emit-*` operation:**

File: `domains/{domain}/async-operations/emit-{event-description}.yaml`

```yaml
action: send
channel:
  $ref: '../channels/{aggregate}-events.yaml'
tags:
  - name: {Domain}
summary: Publish {EventName} after {description}
description: |
  Publishing declaration for the on-{handler} worker.
  {Brief description of when/why this event is published.}

  This is NOT a worker — the code generator wires this publish call
  into the on-{handler} handler class via x-emits.
messages:
  - $ref: '../messages/{EmittedEvent}.yaml'
```

**Important:** `emit-*` operations must NOT have `x-worker` or `x-observability`. They are declarations, not workers.

**3c. Add `x-emits` to the `on-*` operation:**

```yaml
x-emits:
  - event: {Entity}.{Action}                        # Matches emitted message's x-label
    description: {When/why this event is published}
```

### Step 4: Register in asyncapi.yaml

- Add new channels under the correct domain section (if created)
- Add the `on-*` operation under the correct domain section
- Add the `emit-*` operation(s) under the correct domain section (if created)
- Add new domain tag to `info.tags` if this is a new async domain

### Step 5: If AI-powered, add x-ai and cross-check entities

If the handler uses AI/LLM:

```yaml
x-ai:
  enabled: true
  task: {generation|classification|extraction|...}
  entities:
    reads: [{Entity1}, {Entity2}]
    creates: [{Entity3}]
    updates: [{Entity4}]
```

**MANDATORY cross-check:** every entity listed must have the corresponding `aiAccess.operations` in its OpenAPI `x-entity`. If not, stop and flag to the user before proceeding.

### Step 6: Update OpenAPI operations (if event is API-triggered)

If the triggering event comes from a REST write operation, ensure that operation has `x-emits` listing the event.

### Step 7: Validate

```bash
./scripts/validate-async-structure.sh
./scripts/validate-async-spectral.sh
```

Fix any errors before presenting the result.

### Step 8: Update flow documentation

1. Check if a flow doc exists in `api/docs/flows/{domain}/` covering this process
2. If yes: update it to reflect the new worker
3. If no: create one using the template in `api/docs/flows/README.md`

## Checklist (verify before finishing)

- [ ] `on-*` operation has `action: receive`, `x-worker` (with `inboxDedup`), `x-subscription` (name = file stem, NO authored `filter`), `x-observability` (criticality from low/medium/high/critical)
- [ ] `emit-*` declarations (if any) have `action: send` and NO `x-worker`
- [ ] `on-*` operation has `x-emits` linking to each `emit-*` declaration (if any)
- [ ] Message(s) have `x-message-category: event`, `x-label`, `x-version`
- [ ] `x-label.entity` matches a schema with `x-entity` in OpenAPI
- [ ] Payloads use `$ref` to OpenAPI models — no duplication
- [ ] Event payloads use snapshot `$ref`s into `events/{Entity}Snapshot.yaml` per action class (`*Created`/`*Updated`/`*Deleted`/transition); never raw entity types
- [ ] State-transition events carry `x-trigger-when` predicate; `*Created`/`*Updated`/`*Deleted` do not
- [ ] If snapshot includes a property whose source entity field is `x-classification: [pii \| sensitive]`, snapshot file declares `x-snapshot-pii-acknowledged.{property}` with justification ≥ 20 chars
- [ ] Files follow naming conventions (PascalCase messages, kebab-case operations/channels)
- [ ] Root `asyncapi.yaml` updated with new channels and operations
- [ ] Flow documentation created/updated
- [ ] AI workers have `x-ai.entities` cross-checked against `aiAccess`
- [ ] No removed v1 extensions used
- [ ] Validation passes with 0 errors
