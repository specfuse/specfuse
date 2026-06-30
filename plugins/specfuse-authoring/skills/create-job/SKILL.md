---
name: create-job
description: "Create a scheduled job (run-* operation) -- a cron-triggered thin fan-out dispatcher that queries the database and publishes one event per work item for independent per-item processing with retry and DLQ isolation. Use when adding a cron-driven background job to the v2 async architecture; enforces the AsyncAPI handbook's fan-out pattern, message and operation shapes, and validation."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Create a scheduled job (`run-*` operation) — a cron-triggered thin fan-out dispatcher that queries the database and publishes events for per-item processing.

*Enforces: .specfuse/authoring/handbooks/AsyncAPI_Handbook.md*

**Before writing any files**, read and internalize the authoritative rules:
1. Read `.specfuse/authoring/handbooks/AsyncAPI_Handbook.md` — Sections 0.4, 1.3, 4.3, 5.2
2. Read `api/specs/CLAUDE.md` — Section 10 (AsyncAPI Files — Critical Rules)
3. Read `.specfuse/authoring/samples/message-samples.yaml` — samples 2 (scheduled job message), 4 (scheduled-trigger channel), 6 (job operation)

## What this skill creates

A `run-*` scheduled job — a cron-triggered worker that queries the database for work items and publishes one event per item. Separate `on-*` subscribers handle each item independently with per-item retry and DLQ isolation.

This is the **thin fan-out dispatcher** pattern. The job itself does NO heavy processing.

**Narrow exception:** jobs producing a single output (snapshot, materialized view refresh) with no per-item semantics may do the work directly. If the user describes such a scenario, confirm it fits the exception before proceeding. When in doubt, default to fan-out.

This skill does NOT create standalone event handlers — use `/create-worker` for those.

## Inputs to clarify with the user

1. **Which domain** does this job belong to?
2. **What entity/aggregate** does the job query? (e.g., orders, compliance items)
3. **What criteria** selects work items? (e.g., "draft orders older than 12 weeks")
4. **What should happen per item?** (e.g., "archive the order", "send a reminder")
5. **Cron schedule** — how often? (e.g., weekly Monday 2 AM, daily at midnight)
6. **Scope** — global, perTenant, or perCustomer?
7. **Does a subscriber already exist** for the per-item event, or do we need to create one?

## The fan-out pattern

```
CRON: '{schedule}'
  └─ run-{job-name} (action: send, x-worker required)
       ├─ queries DB → finds N items matching criteria
       └─ publishes N × {ItemEvent} (to event-topic)
            └─ on-{item-event} subscriber (action: receive)
                 ├─ processes one item
                 ├─ success → done (optionally emits completion event)
                 └─ failure → DLQ (isolated, individually retryable)
```

## Creation process

### Step 1: Create the scheduled job message

File: `domains/{domain}/messages/{ActionDescription}Job.yaml`

```yaml
name: {ActionDescription}Job                        # PascalCase, verb phrase + Job suffix
title: {Human-Readable Title} Job
summary: {Brief description of what the job does}
contentType: application/json
traits:
  - $ref: '../../../async-common/message-traits/common.yaml#/commonHeaders'
x-message-category: scheduledJob                    # REQUIRED
x-label:                                            # REQUIRED
  entity: {Entity}                                  # PascalCase — must match x-entity in OpenAPI
  action: {ActionVerb}                              # PascalCase
x-version:                                          # REQUIRED
  current: 1
  status: draft
x-scheduled-job:                                    # REQUIRED
  cron: '{cron-expression}'
  scope: {global|perTenant|perCustomer}
  overlap: skip                                     # skip | queue | cancelPrevious
payload:
  type: object
  required: [{scope-dependent-ids}]
  properties:
    tenantId:                                       # Required for perTenant/perCustomer scope
      type: string
      format: uuid
    # Add job-specific config parameters (thresholds, etc.)
```

### Step 2: Create the per-item event message

File: `domains/{domain}/messages/{ItemActionEvent}.yaml`

```yaml
name: {ItemActionEvent}                             # PascalCase, past tense or action-requested
title: {Human-Readable Title}
summary: {Brief description — one per work item}
contentType: application/json
traits:
  - $ref: '../../../async-common/message-traits/common.yaml#/auditableEvent'
x-message-category: event                           # REQUIRED
x-label:                                            # REQUIRED
  entity: {Entity}
  action: {Action}
x-version:
  current: 1
  status: draft
payload:
  type: object
  # Per-item event payload follows action-class rules (handbook §2.2):
  #   *Created  → required: [{entityId}, after]
  #   *Updated  → required: [{entityId}, before, after]
  #   *Deleted  → required: [{entityId}, before]
  #   transition → required: [{entityId}, before, after, context?] AND x-trigger-when
  required: [{entityId}, before]
  properties:
    {entityId}:
      type: string
      format: uuid
    before:
      $ref: '../events/{Entity}Snapshot.yaml'        # Snapshot $ref — NEVER raw entity model
```

If the per-item event is a state transition (e.g. `*ArchiveRequested` is a transition action), add `x-trigger-when` and follow the transition payload shape with both `before` and `after`. See `.specfuse/authoring/samples/message-samples.yaml` §1c.

### Step 3: Set up channels

- **Scheduled-trigger channel**: check if `domains/{domain}/channels/{domain}-jobs.yaml` exists. If not, create it. Add the job message to its `messages` map.
- **Event-topic channel**: check if an appropriate event-topic exists for the per-item event. If not, create one. Add the per-item event to its `messages` map.

### Step 4: Create the `run-*` operation (the dispatcher)

File: `domains/{domain}/async-operations/run-{job-description}.yaml`

```yaml
action: send                                        # Scheduled jobs are senders (cron-triggered publishers)
channel:
  $ref: '../channels/{aggregate}-events.yaml'       # Where the per-item events are published
tags:
  - name: {Domain}
summary: {Brief description of the fan-out}
description: |
  Cron-triggered thin fan-out dispatcher. Queries the database for
  {work items matching criteria}, then publishes one {EventName} event
  per item for independent downstream processing.

  Uses action: send because this is a cron-triggered publisher, not a
  message receiver. The cron schedule is defined in x-scheduled-job on
  the {JobName}Job message.
traits:
  - $ref: '../../../async-common/operation-traits/common.yaml#/standardDelivery'
messages:
  - $ref: '../messages/{JobName}Job.yaml'
x-worker:                                           # REQUIRED on run-* operations
  idempotent: true
  inboxDedup: true                                  # default true
  concurrency: 1                                    # Typically 1 for dispatchers
  timeout: {duration}                               # Short — query + publish only, no processing
x-observability:
  criticality: {level}                              # low | medium | high | critical (legacy 'normal' rejected)
  sla:
    maxProcessingTime: {duration}
  metrics:
    - {itemsFound}
    - {eventsPublished}
  alertOnDlq: true
```

**Note:** `run-*` operations publish directly via their channel. They do NOT use `emit-*` declarations, `x-emits`, or `x-subscription` (cron-triggered, not subscribers).

### Step 5: Create the `on-*` subscriber (per-item handler)

If a subscriber doesn't already exist for the per-item event, create one using the same pattern as `/create-worker`:

File: `domains/{domain}/async-operations/on-{item-event}.yaml`

```yaml
action: receive
channel:
  $ref: '../channels/{aggregate}-events.yaml'
tags:
  - name: {Domain}
summary: {Process one item}
description: |
  Handles one {EventName} event independently. {Description of work.}
  Per-item retry and DLQ isolation — failure on one item does not
  affect others.
traits:
  - $ref: '../../../async-common/operation-traits/common.yaml#/reliableDelivery'
messages:
  - $ref: '../messages/{ItemActionEvent}.yaml'
x-worker:                                           # REQUIRED on on-* operations
  idempotent: true
  inboxDedup: true                                  # default true; false ONLY for side-effect-free handlers
  concurrency: {n}                                  # Can be high — items are independent
  timeout: {duration}
x-observability:
  criticality: {level}                              # low | medium | high | critical
  sla:
    maxProcessingTime: {duration}
  alertOnDlq: true
x-subscription:                                     # REQUIRED on event-topic receivers
  name: on-{item-event-description}                 # MUST equal the operation file stem
  # NO 'filter' — derived from messages: → Label = '{Entity}.{Action}'
  # AND-merge tenant scoping via requiredHeaders: { tenantId: '<guid>' } if needed
```

### Step 6: Register in asyncapi.yaml

Add under the correct domain section:
- New channels (if created)
- The `run-*` operation
- The `on-*` subscriber operation (if created)
- New domain tag to `info.tags` if this is a new async domain

### Step 7: Validate

```bash
./scripts/validate-async-structure.sh
./scripts/validate-async-spectral.sh
```

Fix any errors before presenting the result.

### Step 8: Create or update flow documentation

This step is MANDATORY — scheduled job fan-out flows are especially important to document.

1. Check if a flow doc exists in `api/docs/flows/{domain}/` covering this process
2. If yes: update it
3. If no: create one using the template in `api/docs/flows/README.md`

The flow doc must include:
- Mermaid sequence diagram showing: CRON → dispatcher → N events → subscriber
- Messages and Operations tables
- Error handling (what happens when per-item processing fails)
- Monitoring section (metrics from both dispatcher and subscriber)

## Checklist (verify before finishing)

- [ ] Job message has `x-message-category: scheduledJob`, `x-label`, `x-version`, `x-scheduled-job`
- [ ] Per-item event message has `x-message-category: event`, `x-label`, `x-version`
- [ ] `x-label.entity` on both messages matches a schema with `x-entity` in OpenAPI
- [ ] `run-*` operation has `action: send` and `x-worker` (it IS a worker)
- [ ] `run-*` operation does NOT use `emit-*` or `x-emits` — it publishes directly
- [ ] `on-*` subscriber has `action: receive`, `x-worker` (with `inboxDedup`), `x-subscription` (name = file stem, NO authored `filter`)
- [ ] Both operations have `x-observability` with at least `criticality` from `low | medium | high | critical` (NOT legacy `normal`)
- [ ] Payloads use `$ref` to OpenAPI models — no duplication
- [ ] Per-item event payloads use snapshot `$ref`s into `events/{Entity}Snapshot.yaml` per action class — never raw entity types
- [ ] State-transition per-item events declare `x-trigger-when`; `*Created`/`*Updated`/`*Deleted` do not
- [ ] Scheduled-trigger channel exists for the domain
- [ ] Files follow naming conventions (PascalCase messages, kebab-case operations/channels)
- [ ] Root `asyncapi.yaml` updated with new channels and operations
- [ ] Flow documentation created/updated
- [ ] No removed v1 extensions used
- [ ] Validation passes with 0 errors
