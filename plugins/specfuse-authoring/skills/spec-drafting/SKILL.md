---
name: spec-drafting
description: "Conversational three-phase guidance (feature scoping → spec drafting → pre-validation review) for drafting an initiative's OpenAPI/AsyncAPI/Arazzo specifications collaboratively with the human under /product/, keeping the human's product judgment primary while ensuring acceptance criteria are concrete, single-behavior, and QA-consumable. Use during the drafting state, after initiative intake and before spec validation; never runs the validator, modifies frontmatter, or writes test plans."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Spec drafting — v1.1

> **Reframe note (Model B; docs/naming-convention.md).** This skill drafts the specs for an
> **initiative** (`INIT-YYYY-NNNN`) — the orchestrator's top, cross-repo unit. The PM later
> decomposes the validated initiative into features. "Scoping" below scopes the initiative; where
> the text refers to the orchestrator's unit (registry, correlation ID, state machine), read
> initiative / `INIT-`. Generic product-"feature"/"behavior"/"user story" wording inside the
> specs themselves is unchanged — those are product concepts, not the orchestrator's feature unit.

Conversational guidance for drafting product specifications collaboratively with the human. The skill structures the interaction into three phases — initiative scoping, spec drafting, and pre-validation review — so that the output is concrete enough for Specfuse validation and QA consumption while preserving the human's product judgment as the primary driver.

When this file and the specs agent role config disagree, **the role config wins and this file is wrong.** Raise an escalation rather than reconciling silently.

## Trigger

The human has completed feature intake (a registry entry exists at `/features/FEAT-YYYY-NNNN.md` with `state: drafting`) and is ready to describe the feature's behavior in detail. The trigger is conversational: the human says something like "let's draft the spec for FEAT-2026-0008" or continues from a feature-intake session into spec authoring.

**Precondition.** A valid feature registry entry must exist for the feature being drafted. The skill reads the registry file and confirms `state: drafting` before proceeding. If the feature is in any other state, the skill does not proceed — it informs the human and suggests the appropriate entry point (feature-intake for a missing feature, spec-validation for an already-validated one).

## Inputs

The skill reads, in order:

1. The feature registry entry at `/features/FEAT-YYYY-NNNN.md` — its frontmatter (`correlation_id`, `state`, `involved_repos`, `autonomy_default`) and its body (placeholder sections from feature-intake or partially-drafted content from a prior session).
2. This skill file and the specs agent role config — reloaded per `/shared/rules/role-switch-hygiene.md`.
3. Any existing spec files under `/product/` in the product specs repo that the human references or that `## Related specs` already points to (for continuation sessions where drafting resumes on a partially-authored spec).
4. The `test-plan.schema.json` contract — not to author test plans (that is qa-authoring's concern), but to understand the shape acceptance criteria must map onto: `test_id`, `covers`, `commands`, `expected`.

The skill does **not** read component-repo source code, test harnesses, or generated directories. The spec is authored from the human's product intent, not reverse-engineered from an implementation.

## Conversational structure

The skill organizes the spec-drafting session into three phases. The phases are sequential — the agent does not jump ahead — but the human can revisit earlier phases at any point by saying so. The agent's role in each phase is to ask clarifying questions, surface structural requirements, and draft concrete prose the human can approve or revise.

---

### Phase 1 — Feature scoping

**Goal.** Help the human articulate what the feature does, which repos it touches, and what its boundaries are. By the end of this phase, the feature registry's body sections — `## Description`, `## Scope`, `## Out of scope`, and `## Related specs` — are populated with concrete, unambiguous content.

**How the agent guides the conversation:**

1. Read the feature registry entry. Note the `involved_repos` and `autonomy_default` from frontmatter; note whether the body sections carry placeholder text ("To be drafted during spec authoring") or have prior content.
2. Ask the human to describe the feature in a few sentences. Do not require a structured format — let the human express the idea naturally.
3. Based on the human's description, ask focused scoping questions. Good scoping questions isolate boundaries:
   - "Does this feature add new endpoints, or does it modify existing ones?"
   - "What happens when [edge-case input]? Is that in scope or out?"
   - "You mentioned [repo X] — does the feature also touch [repo Y], or is it single-repo?"
   - "Is there existing behavior this feature replaces, or is it purely additive?"
4. Draft the four body sections based on the human's answers. Present them for review.
5. Iterate until the human approves the scoped content.

**Output of Phase 1.** The feature registry's body sections are populated:

- `## Description` — one or two paragraphs in product language stating what the feature is and why it exists.
- `## Scope` — a bulleted list of capabilities the feature delivers. Each bullet is a concrete, prescriptive statement (see [§ Scope and cardinality conventions](#scope-and-cardinality-conventions) below). Each bullet maps to at least one acceptance criterion that will be drafted in Phase 2.
- `## Out of scope` — a bulleted list of adjacent concerns this feature explicitly does not cover.
- `## Related specs` — initially empty or carrying forward references; populated fully in Phase 2 as spec files are created.

The body sections are written to the feature registry file. **The frontmatter is not modified** — `state`, `correlation_id`, `task_graph`, and other frontmatter fields are owned by the intake and validation skills.

---

### Phase 2 — Spec drafting

**Goal.** Produce the specification documents under `/product/specs/` in the product specs repo and populate the feature registry's `## Related specs` section with links to every produced spec file.

**Choosing the right spec type:**

| Spec type | Use when | File extension |
|---|---|---|
| OpenAPI | The feature defines REST API endpoints — request/response shapes, status codes, query parameters, headers | `.yaml` or `.json` |
| AsyncAPI | The feature defines event-driven contracts — message brokers, pub/sub channels, event schemas | `.yaml` or `.json` |
| Arazzo | The feature defines multi-step workflows that chain multiple API calls or event sequences into a higher-order behavior | `.yaml` |
| Feature narrative | The feature's behavior is not fully captured by a machine-readable spec format (e.g., UI behavior, business rules, migration procedures) — use a structured markdown document with explicit acceptance criteria | `.md` |

When the feature spans multiple spec types (e.g., a REST API that also emits events), produce one file per spec type. Each file covers the behaviors relevant to that spec type; cross-references between files use relative paths.

**Structuring spec files for Specfuse validation:**

- OpenAPI documents must be valid per the OpenAPI 3.0 or 3.1 specification. Every operation in scope must have an `operationId`.
- AsyncAPI documents must be valid per the AsyncAPI 2.x or 3.x specification.
- Arazzo documents must be valid per the Arazzo 1.0 specification, with `sourceDescriptions` referencing the OpenAPI/AsyncAPI documents they orchestrate.
- Feature narratives must use the acceptance-criteria heading convention: `### Acceptance criteria` followed by numbered items (`AC-1`, `AC-2`, ...), each stating a single, testable behavior.

**File path conventions:**

- Spec documents: `/product/specs/<feature-slug>.yaml` (or `.json`). The `<feature-slug>` is a kebab-case, human-readable name derived from the feature title — not the correlation ID. Example: a feature titled "Widget Catalog API" produces `/product/specs/widget-catalog-api.yaml`.
- Feature descriptions (narratives with acceptance criteria): `/product/features/<correlation-id>.md`. Example: `/product/features/FEAT-2026-0008.md`.
- Avoid conflicts with existing files: before creating a file, check whether a file at the target path already exists. If it does, confirm with the human whether to overwrite (continuation of the same feature's drafting) or use an alternative path (different feature touching the same spec surface).

**Writing acceptance criteria that the QA agent can consume:**

Every acceptance criterion the human and agent draft will be consumed by `qa-authoring/SKILL.md` to produce a test entry with `covers`, `commands`, and `expected` fields (per `test-plan.schema.json`). Write criteria that map cleanly to those three fields:

- **Testable.** Each criterion describes a single behavior that can be verified by running a command and observing an outcome. "The API should be fast" is not testable. "GET /widgets returns HTTP 200 with a JSON array" is testable.
- **Scoped to a single behavior.** One criterion, one observable outcome. A criterion that says "GET /widgets returns a paginated list and rejects invalid page sizes" conflates two behaviors — split it into two criteria.
- **Linked to a spec fragment.** Each criterion references the spec element it validates: an operation ID, a channel name, a workflow step, or a narrative heading. The qa-authoring skill's `covers` field will carry this reference verbatim.

**Concrete example of a well-formed acceptance criterion:**

> AC-1 — `GET /widgets` (operationId: `listWidgets`) returns HTTP 200 with a JSON array of widget objects. Each object includes fields `id` (string), `name` (string), and `created_at` (ISO-8601 datetime).

This maps to qa-authoring's test entry as:
- `covers`: "AC-1: GET /widgets (operationId: listWidgets) returns HTTP 200 with a JSON array of widget objects."
- `commands`: the executable step to call the endpoint
- `expected`: "HTTP status is 200 and body parses as a JSON array where each element has string fields id, name, and ISO-8601 datetime field created_at."

**Output of Phase 2.** Spec files exist under `/product/` and the feature registry's `## Related specs` section links to every produced file. The acceptance criteria are enumerated in the spec files (for machine-readable specs, as response definitions; for narratives, as the `### Acceptance criteria` section).

**`## Related specs` path format.** Each entry in the `## Related specs` section must use a **repository-relative path** as the primary reference (e.g., `product/features/FEAT-2026-0008.md`, `product/specs/widget-update-api.yaml`). These paths are relative to the product specs repo root and are portable across local clones and GitHub views. Full GitHub URLs may appear as supplementary links for human readers, but the first reference in each list item must be a relative path — downstream agents (PM, QA, component) operate on local clones and cannot resolve GitHub URLs to filesystem paths without a `find` workaround. The worked example below demonstrates the format.

**After writing each file,** re-read the created file and confirm its content matches the intended draft. This is the spec-drafting skill's local application of the `verify-before-report.md` re-read discipline.

---

### Phase 3 — Pre-validation review

**Goal.** Review the drafted specs with the human for completeness, internal consistency, and readiness for Specfuse validation. The agent does not run validation itself — that is the spec-validation skill's concern.

**What "ready for validation" means:**

1. **All acceptance criteria are testable.** Each criterion maps to a test entry with `covers`, `commands`, and `expected` — verified by the agent walking each criterion against the test-plan schema's expectations.
2. **All spec files are syntactically valid.** YAML files parse without errors; JSON files are well-formed. OpenAPI, AsyncAPI, and Arazzo documents conform to their respective specification versions. The agent performs a syntactic check (parsing) but does not invoke Specfuse — that invocation belongs to the spec-validation skill.
3. **Cross-references are consistent.** Every spec file listed in the feature registry's `## Related specs` exists at the stated path. Every acceptance criterion references a spec element that exists in one of the related spec files.
4. **The feature registry's body sections are complete.** `## Description`, `## Scope`, `## Out of scope`, and `## Related specs` all contain substantive content — no placeholder text remains.

**The review checklist the agent presents to the human:**

```
Pre-validation review for FEAT-YYYY-NNNN:

[ ] Description: substantive, product-language description present
[ ] Scope: all bullets use prescriptive language (see §Scope and cardinality conventions)
[ ] Out of scope: boundaries are explicit
[ ] Related specs: every spec file is linked; every link resolves
[ ] Acceptance criteria: each is testable, single-behavior, linked to a spec fragment
[ ] Spec files: syntactically valid YAML/JSON
[ ] No frontmatter modifications: state, correlation_id, task_graph unchanged
```

If any item fails the review, the agent and human iterate on the specific issue before proceeding. Once all items pass, the agent informs the human that the feature is ready for the spec-validation skill.

## Managing the `/product/` subtree

The spec-drafting skill manages the `/product/` subtree in the product specs repo. Specific conventions:

- **Spec documents** are created under `/product/specs/<feature-slug>.yaml` (or `.json`). The feature slug is kebab-case, derived from the feature title.
- **Feature descriptions** (narrative specs with acceptance criteria) are created under `/product/features/<correlation-id>.md`.
- The skill **never** writes to `/business/` (`never-touch.md` §4).
- The skill **never** writes to `/product/test-plans/` — that subtree belongs to the QA agent.
- Before creating a file, the skill checks whether the path is already occupied. If it is, the skill asks the human whether to overwrite or use an alternative path.
- After creating or updating a file, the skill re-reads it to confirm the content matches the intended draft.

## Output discipline

The spec-drafting skill produces two categories of artifact:

1. **Spec files** under `/product/` in the product specs repo — the primary output.
2. **Feature registry body section updates** in the orchestration repo — populating `## Description`, `## Scope`, `## Out of scope`, and `## Related specs`.

The skill does **not** modify the feature registry's frontmatter. The frontmatter fields — `state`, `correlation_id`, `involved_repos`, `autonomy_default`, `task_graph` — are owned by other skills:

- `state` transitions are owned by the feature-intake skill (`→ drafting`) and the spec-validation skill (`drafting → validating`, `validating → planning`).
- `correlation_id` is minted by feature-intake and never changed.
- `task_graph` is populated by the PM agent during `planning`.
- `involved_repos` and `autonomy_default` are set at intake.

If the spec-drafting session surfaces a need to change `involved_repos` (e.g., the feature turns out to touch an additional repo), the agent informs the human and suggests re-running the relevant portion of feature intake — it does not modify the frontmatter directly.

## Delivery convention

Spec files produced by the spec-drafting skill must be committed to the product specs repo before the feature can proceed to validation. Uncommitted drafts are not a valid output state — the spec-validation skill reads spec files from the repo, and downstream agents (PM, QA) consume committed content.

**When to commit.** After the human approves the spec content at the end of Phase 3 (pre-validation review), the agent commits the spec files to the product specs repo. This is the natural boundary: the content is reviewed, the agent has verified each file via re-read, and the next step (spec-validation) requires the files to be in the repo.

**How to commit.** The delivery approach depends on the product specs repo's branch-protection posture:

- **If the repo has branch protection on `main`:** create a feature branch (suggested format: `specs/FEAT-YYYY-NNNN`), commit the spec files, push, and open a PR against `main`. The human merges the PR before proceeding to spec-validation. The agent stops at PR-open — it does not merge or close.
- **If the repo does not have branch protection:** commit directly to `main` and push. This is the simpler path for repos where the human is the sole reviewer and the spec-drafting session is the review.

In either case, the commit message should follow the format: `feat(specs): draft FEAT-YYYY-NNNN <feature-title>`.

**What to commit.** Only the spec files under `/product/` that this session created or modified. Do not commit files outside `/product/`, files in `/business/` (`never-touch.md` §4), or files in `/product/test-plans/` (QA agent's surface). The feature registry body-section updates (in the orchestration repo) are committed separately by the orchestration session or human operator — the spec-drafting agent does not commit to the orchestration repo (`verify-before-report.md` §"Event-emission operational discipline").

**Relationship to qa-authoring delivery convention.** This convention mirrors the qa-authoring skill's delivery convention (added in WU 3.9): both produce files in the product specs repo, both use branch + PR when branch protection is active, and both stop at PR-open. The commit boundary is the same: "content reviewed and verified → commit → downstream skill can proceed."

## Scope and cardinality conventions

This section addresses a Phase 3 finding that ambiguous scope language caused downstream confusion.

### The finding (F3.32)

During Phase 3 walkthroughs, the feature registry for `FEAT-2026-0007` used the phrase "three tests expected under the default cardinality convention" in its `## Scope` section. The word "expected" is ambiguous between two readings:

- **Confirmatory** — "we expect this to happen" (a prediction about the outcome of a process the author does not control).
- **Prescriptive** — "author exactly three tests" (a directive to the QA agent about what to produce).

The qa-authoring skill's collapse-only rule (the feature scope can only collapse the default per-behavior count, not expand it) made the ambiguity safe in Phase 3 — the QA agent could not misinterpret the clause as an expansion directive. But the ambiguity remained in the source text, and a future spec author or agent without the collapse-only rule context could misread the intent.

### The failure mode it prevents

If qa-authoring reads a `## Scope` clause as prescriptive when the author intended it as confirmatory (or vice versa), the test plan's cardinality may diverge from the spec's intent:

- Prescriptive misread on a confirmatory clause: the QA agent forces exactly N tests even when the spec's acceptance criteria naturally produce a different count.
- Confirmatory misread on a prescriptive clause: the QA agent ignores a deliberate cardinality override and produces the default per-behavior count.

### Conventions for unambiguous scope language

When drafting `## Scope` bullets and acceptance criteria, the agent guides the human toward:

**Prescriptive language (use this):**

Scope statements describe what the feature **does**, not what is "expected" to happen. Use active, declarative constructions:

- "The feature adds three endpoints: list, get, create."
- "GET /widgets returns HTTP 200 with a JSON array."
- "The page_size parameter defaults to 50 when absent."
- "QA: one authored test plan covering AC-1 and AC-2."

**Confirmatory language (avoid this):**

Scope statements do not predict outcomes or use hedging constructions:

- ~~"Three endpoints are expected under the default convention."~~
- ~~"We expect the API to return a JSON array."~~
- ~~"Three tests expected under the default cardinality convention."~~

**Cardinality clauses:**

When the `## Scope` section needs to state a QA cardinality override (collapsing the default one-test-per-behavior count), use explicit defaults with override language:

- "QA: one authored test plan covering both AC-1 and AC-2 (collapsed from the default two-test count because both behaviors exercise the same endpoint with different inputs)."
- "Default: one test per acceptance criterion. This feature collapses AC-1 and AC-2 into a single test — see rationale below."

Do **not** use:

- ~~"Two tests expected under the default convention."~~ (ambiguous: is this a prediction or a directive?)
- ~~"Expected cardinality: 2."~~ (ambiguous for the same reason)

### When this guidance applies

The agent surfaces this guidance during **Phase 1 — Feature scoping**, specifically when drafting the `## Scope` section's bullets. The agent reviews each bullet for ambiguous "expected" or hedging language and proposes concrete alternatives before the human approves the scope.

## Worked example

A realistic spec-drafting session for a small REST API feature, demonstrating the three-phase structure, F3.32-compliant scope language, and QA-consumable acceptance criteria.

---

**Context.** The human has just completed feature intake for `FEAT-2026-0042`. The registry file exists with placeholder body sections, `state: drafting`, and `involved_repos: ["acme/inventory-api"]`.

---

### Phase 1 — Feature scoping

**Human:** "I want to add a bookmarks API to the inventory API. Users can bookmark items and list their bookmarks with a default page size."

**Agent scoping questions:**

1. "Is bookmarking scoped to authenticated users only, or can anonymous sessions bookmark items? This determines whether the endpoint requires an auth header."
2. "What should happen when a user bookmarks the same item twice — idempotent success, or a 409 Conflict?"
3. "For the listing endpoint, what is the default page size, and should clients be able to override it?"

**Human answers:**

1. "Authenticated users only — require a `user_id` path segment, no auth header for now."
2. "Idempotent — return 201 on first bookmark, 200 on repeat."
3. "Default page size of 20. Clients can pass `page_size` up to 100; anything over 100 gets a 400."

**Agent drafts the body sections:**

```markdown
## Description

Adds a bookmarks API to the inventory API. Authenticated users can bookmark
inventory items and retrieve a paginated list of their bookmarks. The API
enforces a maximum page size to protect downstream query performance.

## Scope

- The feature adds three endpoints: create bookmark, list bookmarks, delete
  bookmark.
- `POST /users/{user_id}/bookmarks` creates a bookmark for the given item.
  Returns HTTP 201 on first creation and HTTP 200 on repeat (idempotent).
- `GET /users/{user_id}/bookmarks` returns a paginated JSON array of bookmarked
  items. The default page size is 20 when `page_size` is absent; `page_size`
  values over 100 are rejected with HTTP 400 and error code
  `page_size_over_limit`.
- `DELETE /users/{user_id}/bookmarks/{item_id}` removes a bookmark. Returns
  HTTP 204 on success and HTTP 404 if the bookmark does not exist.
- QA: one authored test plan with five tests (one per acceptance criterion).

## Out of scope

- Authentication middleware — the `user_id` path segment is the identity
  mechanism for this feature; token-based auth is a separate concern.
- Bookmark ordering or sorting options beyond the default insertion order.
- Bulk bookmark operations (create or delete multiple bookmarks in one call).
- Bookmark metadata (notes, tags, folders).

## Related specs

- To be populated during spec drafting (Phase 2).
```

**Human:** "Looks good. Let's proceed to drafting."

---

### Phase 2 — Spec drafting

The agent produces two files:

**File 1: `/product/features/FEAT-2026-0042.md`**

```markdown
# FEAT-2026-0042 — Inventory API bookmarks

## Overview

Adds user-scoped bookmark endpoints to the inventory API: create, list
(paginated), and delete. Enforces a maximum page size of 100 on the listing
endpoint.

### Acceptance criteria

- **AC-1** — `POST /users/{user_id}/bookmarks` (operationId:
  `createBookmark`) with body `{"item_id": "<valid_id>"}` returns HTTP 201
  with the created bookmark object containing `item_id` and `created_at`.

- **AC-2** — `POST /users/{user_id}/bookmarks` (operationId:
  `createBookmark`) with body `{"item_id": "<already_bookmarked_id>"}`
  returns HTTP 200 with the existing bookmark object (idempotent repeat).

- **AC-3** — `GET /users/{user_id}/bookmarks` (operationId:
  `listBookmarks`) returns HTTP 200 with a JSON array of up to 20 bookmark
  objects when no `page_size` parameter is supplied.

- **AC-4** — `GET /users/{user_id}/bookmarks?page_size=101` (operationId:
  `listBookmarks`) returns HTTP 400 with error code `page_size_over_limit`.

- **AC-5** — `DELETE /users/{user_id}/bookmarks/{item_id}` (operationId:
  `deleteBookmark`) returns HTTP 204 when the bookmark exists, and HTTP 404
  when it does not.
```

**File 2: `/product/specs/inventory-api-bookmarks.yaml`**

```yaml
openapi: "3.0.3"
info:
  title: Inventory API — Bookmarks
  version: "1.0.0"
paths:
  /users/{user_id}/bookmarks:
    post:
      operationId: createBookmark
      summary: Bookmark an inventory item
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [item_id]
              properties:
                item_id:
                  type: string
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
    get:
      operationId: listBookmarks
      summary: List bookmarked items (paginated)
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: string
        - name: page_size
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
      responses:
        "200":
          description: Paginated bookmark list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Bookmark"
        "400":
          description: Invalid page_size (over 100)
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Error"
  /users/{user_id}/bookmarks/{item_id}:
    delete:
      operationId: deleteBookmark
      summary: Remove a bookmark
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: string
        - name: item_id
          in: path
          required: true
          schema:
            type: string
      responses:
        "204":
          description: Bookmark removed
        "404":
          description: Bookmark not found
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
    Error:
      type: object
      required: [error]
      properties:
        error:
          type: object
          required: [code]
          properties:
            code:
              type: string
```

**The agent updates `## Related specs` in the feature registry:**

```markdown
## Related specs

- `product/features/FEAT-2026-0042.md` — feature narrative with acceptance
  criteria (AC-1 through AC-5).
- `product/specs/inventory-api-bookmarks.yaml` — OpenAPI spec for the
  bookmarks endpoints.
```

The agent re-reads both created files and confirms their content matches the draft.

---

### Phase 3 — Pre-validation review

The agent presents the review checklist:

```
Pre-validation review for FEAT-2026-0042:

[x] Description: substantive — states what the API does and why
[x] Scope: prescriptive language throughout; no "expected" ambiguity
     - "The feature adds three endpoints: create bookmark, list bookmarks,
       delete bookmark" (prescriptive, explicit count)
     - "QA: one authored test plan with five tests" (prescriptive, explicit
       count with rationale)
[x] Out of scope: four explicit exclusions
[x] Related specs: two files linked; both paths verified present
[x] Acceptance criteria: five criteria, each testable and single-behavior
     - AC-1 → covers=create-first, commands=[POST], expected=201+object
     - AC-2 → covers=create-repeat, commands=[POST twice], expected=200+object
     - AC-3 → covers=list-default-page, commands=[GET], expected=200+array≤20
     - AC-4 → covers=list-over-limit, commands=[GET ?page_size=101],
       expected=400+error code
     - AC-5 → covers=delete-exists-and-missing, commands=[DELETE],
       expected=204 or 404
[x] Spec files: inventory-api-bookmarks.yaml parses as valid OpenAPI 3.0.3
[x] No frontmatter modifications: state=drafting, correlation_id, task_graph
    unchanged from intake
```

**Agent:** "All checks pass. The feature is ready for the spec-validation skill — you can proceed with `drafting → validating` when ready."

---

### Verification against acceptance criteria

**(a) Every acceptance criterion is testable — maps to test_id with covers, commands, expected:**

| AC | covers | commands (illustrative) | expected |
|---|---|---|---|
| AC-1 | "AC-1: POST /users/{user_id}/bookmarks creates a bookmark and returns 201." | `curl -sS -X POST -H 'Content-Type: application/json' -d '{"item_id":"item-1"}' -o body.json -w '%{http_code}' http://localhost:<port>/users/user-1/bookmarks` | "HTTP status is 201; body.json contains item_id == 'item-1' and a valid created_at datetime." |
| AC-2 | "AC-2: POST /users/{user_id}/bookmarks with an already-bookmarked item returns 200 (idempotent)." | `curl -sS -X POST ... [same item_id a second time] -o body.json -w '%{http_code}' ...` | "HTTP status is 200; body.json contains the same bookmark object as AC-1." |
| AC-3 | "AC-3: GET /users/{user_id}/bookmarks returns up to 20 bookmarks when page_size is absent." | `curl -sS -o body.json -w '%{http_code}' http://localhost:<port>/users/user-1/bookmarks` | "HTTP status is 200; body.json parses as a JSON array with at most 20 elements." |
| AC-4 | "AC-4: GET /users/{user_id}/bookmarks?page_size=101 returns 400 with error code page_size_over_limit." | `curl -sS -o body.json -w '%{http_code}' 'http://localhost:<port>/users/user-1/bookmarks?page_size=101'` | "HTTP status is 400; body.json contains error.code == 'page_size_over_limit'." |
| AC-5 | "AC-5: DELETE /users/{user_id}/bookmarks/{item_id} returns 204 when the bookmark exists, 404 when it does not." | `curl -sS -X DELETE -w '%{http_code}' http://localhost:<port>/users/user-1/bookmarks/item-1` | "HTTP status is 204 (bookmark existed) or 404 (bookmark absent)." |

**(b) Scope language is unambiguous per F3.32 guidance:**

- "The feature adds three endpoints: create bookmark, list bookmarks, delete bookmark." — prescriptive, active voice, explicit count.
- "QA: one authored test plan with five tests (one per acceptance criterion)." — explicit count with rationale.
- No "expected" hedging anywhere in `## Scope`.

**(c) Feature registry body sections populated without touching frontmatter:**

- `## Description` — two sentences of product-language content.
- `## Scope` — five prescriptive bullets.
- `## Out of scope` — four explicit exclusions.
- `## Related specs` — two links to created spec files.
- Frontmatter (`state: drafting`, `correlation_id: FEAT-2026-0042`, `task_graph: []`) is unchanged from intake.

## File creation verification

Every file the spec-drafting skill creates or updates is verified by re-reading it after the write and confirming the on-disk content matches the intended draft. This is the skill's local application of `verify-before-report.md` §3.

The verification applies to:

- Spec files created under `/product/specs/` and `/product/features/`.
- Feature registry body-section updates at `/features/FEAT-YYYY-NNNN.md`.

If the re-read reveals a discrepancy (e.g., a write tool silently truncated content, or a concurrent edit modified the file between write and re-read), the skill corrects the file and re-verifies. Three consecutive re-read failures trigger `spinning_detected` escalation per `escalation-protocol.md`.

## What this skill does not do

- It does **not** run Specfuse validation. That is the spec-validation skill's concern (WU 4.4). Phase 3 of this skill reviews readiness for validation; it does not invoke the validator.
- It does **not** modify the feature registry frontmatter. State transitions (`drafting → validating`, etc.) are owned by the spec-validation skill. Correlation IDs and task graphs are owned by feature-intake and the PM agent respectively.
- It does **not** author test plans. Test plans are the QA agent's deliverable via `qa-authoring/SKILL.md`. This skill produces acceptance criteria that qa-authoring consumes — it does not produce the test plan itself.
- It does **not** write to `/product/test-plans/`. That subtree belongs to the QA agent.
- It does **not** write to `/business/`. That subtree is off-limits per `never-touch.md` §4.
- It does **not** write code, generated content, or hand-written files in component repos. The specs agent's only write surface in component or generator repos is spec-issue filing — and spec-issue filing is the spec-issue-triage skill's concern, not this skill's.
- It does **not** emit events. Event emission for feature state transitions is the spec-validation skill's responsibility. The spec-drafting skill produces content; the validation skill gates and transitions.
- It does **not** invoke any external tools, scripts, or validators. All external invocations — Specfuse validator, `validate-event.py`, `validate-frontmatter.py` — are the validation skill's responsibility.

## Deferred integration

### Phase 5 — Richer spec authoring

Phase 5 extends this skill's conversational foundation with two integrations:

1. **Arazzo-backed test plan skeletons.** When the Specfuse generator emits code scaffolds (Phase 5), it also emits test plan skeletons keyed off the OpenAPI/Arazzo surface. The spec-drafting skill can then surface these skeletons during Phase 2, showing the human which behaviors the generator has already identified and which need manual acceptance-criteria authoring. This reduces duplicated effort between spec drafting and qa-authoring without removing the human's judgment from acceptance-criteria design.

2. **Generator-emitted spec stubs.** When the generator supports spec-stub emission (Phase 5), the spec-drafting skill can start Phase 2 from a pre-populated OpenAPI or AsyncAPI document rather than from a blank file. The human reviews and extends the stub rather than authoring from scratch. The skill's Phase 2 structure (choose spec type → author the document → write acceptance criteria) is preserved; the starting point shifts from empty to pre-populated.

Phase 4 does **not** introduce these integrations. The v1.0 spec-drafting skill is a purely conversational tool that produces spec documents through human-agent dialogue. The generator integration is Phase 5's scope; Phase 4's remaining WUs (spec-validation, spec-issue-triage) operate on the v1.0 conversational output without requiring generator support.

## References

- `/docs/orchestrator-architecture.md` §5.1 (roles), §4.3 (test plan location), §6 (state machines).
- `/agents/specs/CLAUDE.md` — the specs agent role config that orchestrates this skill.
- `/agents/specs/skills/feature-intake/SKILL.md` — the preceding skill in the feature lifecycle; creates the registry entry this skill populates.
- `/agents/qa/skills/qa-authoring/SKILL.md` — the downstream skill that consumes the acceptance criteria this skill produces; its `covers`, `commands`, and `expected` fields are the target shape.
- `/shared/schemas/test-plan.schema.json` — the machine-readable contract for test plans; the acceptance criteria this skill produces must map onto the `tests[]` entries defined here.
- `/shared/templates/feature-registry.md` — the template for feature registry entries; this skill populates the body sections.
- `/shared/rules/verify-before-report.md` — re-read discipline applied after every file write.
- `/shared/rules/never-touch.md` — path prohibition; `/business/` and `/product/test-plans/` are off-limits for this skill.
- `/shared/rules/escalation-protocol.md` — `spinning_detected` escalation on file-creation verification failures.
- `/docs/walkthroughs/phase-3/retrospective.md` §F3.32 — the Phase 3 finding this skill's §"Scope and cardinality conventions" addresses.
