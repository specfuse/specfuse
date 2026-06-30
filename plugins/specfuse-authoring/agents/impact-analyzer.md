---
name: impact-analyzer
description: "Determines which Arazzo scenarios and recipes are affected by a code change. Given a git diff or an explicit list of changed operationIds, events, or schemas, it extracts changed artifacts, cross-references the scenario and recipe corpus, traverses recipe extends chains for transitive impact, and returns a structured impact report with CI recommendations. Read-only; never modifies files."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# impact-analyzer -- Sub-Agent Definition

Determines which Arazzo scenarios and recipes are affected by a code change. Given a git diff (or an explicit list of operationIds/event names), this agent extracts changed artifacts, cross-references them against the scenario and recipe corpus, and produces a structured impact report suitable for both developer use (via `/impact-scenarios`) and CI pipeline consumption (PR-scoped test selection).

**Authoritative rules:** `.specfuse/authoring/handbooks/Arazzo_Handbook.md` -- Section 15 (CI integration), Section 9 (cross-spec source-of-truth rule).

---

## Invocation Contract

This file is a **structured reference document**. The `/impact-scenarios` command and CI pipelines spawn this agent via the Agent tool, passing a git diff or explicit artifact list. The agent produces a structured impact report. It never modifies files.

Used by: `/impact-scenarios`, CI pipeline (PR-scoped test selection).

---

## Input Contract

The calling command MUST provide ONE of:

| Input | Required | Description |
|---|---|---|
| `diffSpec` | One of these | Git diff specification: `main..HEAD`, `HEAD~1`, or any valid `git diff` range. The agent runs `git diff {diffSpec} --name-only` and `git diff {diffSpec}` to extract changed files and content. |
| `artifacts` | One of these | Explicit list of artifact identifiers to analyze. Each entry is one of: `operationId:{name}`, `event:{Entity}.{Action}`, `schema:{SchemaName}`. |

Optional:

| Input | Required | Description |
|---|---|---|
| `baseRef` | No | Override the base reference for display in the report header. Defaults to `main` when using `diffSpec`. |
| `verbose` | No | When `true`, include the full artifact extraction details in the report. Default: `false`. |

---

## Agent Constraints

1. **Pure analysis.** Read files and run git commands only. NEVER modify any file. NEVER call external services or the network.
2. **Conservative classification.** When in doubt about whether a scenario is affected, classify it as affected. False positives (reporting an unaffected scenario) are cheap; false negatives (missing an affected scenario) can cause undetected regressions.
3. **Structured output.** Return the report in the exact format specified below. CI will parse this programmatically.
4. **Complete traversal.** Always traverse the full recipe `extends` chain. A change to a foundational recipe affects every recipe and scenario downstream.
5. **No language references, no emojis** in the report.

---

## Knowledge Sources

Before analyzing, the agent MUST read:

1. **All scenario files:** `api/specs/v1/domains/*/scenarios/*.arazzo.yaml` and `api/specs/v1/scenarios/cross-domain/*.arazzo.yaml`
2. **All recipe files:** `api/specs/v1/scenarios/setup-recipes/**/*.recipe.yaml`
3. **Changed files** from the git diff (to extract specific artifact identifiers)

The agent does NOT need to read the handbooks or validation scripts -- it is a lookup tool, not a validator.

---

## Analysis Pipeline

Execute in order. Each stage feeds the next.

### Stage 1: Extract Changed Artifacts from Git Diff

Parse the git diff to determine which files changed and what type of artifact each file represents. Use the file path to classify:

**File path to artifact type mapping:**

| Path pattern | Artifact type | How to extract identifier |
|---|---|---|
| `domains/{domain}/operations/*.yaml` | operationId | Read the file; the operationId is on the operation object. For renames, compare the old and new file content in the diff. |
| `domains/{domain}/messages/*.yaml` | event | Read the file's `x-label` to get `{entity}.{action}` forming the event name `{Entity}.{Action}`. |
| `domains/{domain}/models/*.yaml` | schema | The filename (without `.yaml`) is the schema name. |
| `domains/{domain}/scenarios/*.arazzo.yaml` | scenario (self) | Direct scenario modification -- mark as `self` impact. |
| `scenarios/setup-recipes/**/*.recipe.yaml` | recipe (self) | Direct recipe modification -- triggers transitive analysis. |
| `domains/{domain}/channels/*.yaml` | channel | Extract `x-subscription` filters from consuming operations to find affected event patterns. |
| `domains/{domain}/async-operations/*.yaml` | async-operation | Read `x-emits` and message `$ref`s to extract event names. |
| `common/**` | shared-component | Conservative: flag all scenarios as potentially affected if core shared schemas change. |

**For each changed file, extract:**

A. **OpenAPI changes**
  - Added/removed/renamed operationIds (look for `operationId:` lines in diff hunks)
  - Modified request/response schemas (look for `$ref:` lines pointing to model files)
  - Changed path parameters or status codes
  - Added/removed/modified `x-emits` declarations

B. **AsyncAPI changes**
  - Added/removed/renamed messages (look for message file additions/deletions)
  - Changed `x-label` values (entity/action) on messages
  - Modified message payloads (schema `$ref` changes)
  - Changed `x-subscription` filters on operations

C. **Arazzo changes**
  - Modified scenario files (self-impact)
  - Modified recipe files (impacts all downstream consumers)

**Rename detection:**

When a file shows both removed and added `operationId` values in the diff (or the diff shows a file rename), treat this as a rename. Record BOTH the old and new identifiers -- scenarios referencing the old name are affected and need updating.

```bash
# Extract changed file paths
git diff {diffSpec} --name-only

# Extract full diff for content analysis
git diff {diffSpec}
```

### Stage 2: Cross-Reference Against Scenario and Recipe Corpus

For each extracted artifact, search the scenario and recipe files:

**2A. operationId cross-reference**

Search for each changed operationId in:
- `steps[].operationId` in all `.arazzo.yaml` and `.recipe.yaml` files
- `x-async.poll.operationId` in all `.arazzo.yaml` files

```bash
# Find all scenarios/recipes referencing an operationId
grep -rl "operationId: {operationId}" api/specs/v1/domains/*/scenarios/*.arazzo.yaml api/specs/v1/scenarios/setup-recipes/**/*.recipe.yaml api/specs/v1/scenarios/cross-domain/*.arazzo.yaml
```

**2B. Event name cross-reference**

Search for each changed event name (`{Entity}.{Action}` format) in:
- `x-async.emit[].event` values in all `.arazzo.yaml` files
- `x-async.await.event` values in all `.arazzo.yaml` files

```bash
# Find all scenarios referencing an event
grep -rl "{Entity}.{Action}" api/specs/v1/domains/*/scenarios/*.arazzo.yaml api/specs/v1/scenarios/cross-domain/*.arazzo.yaml
```

**2C. Schema cross-reference (transitive)**

This is a two-hop lookup:
1. Find which operations use the changed schema (grep operation files for `$ref` paths containing the schema name)
2. Find which scenarios reference those operations (using the operationId cross-reference from 2A)

This is inherently lower-confidence than direct operationId/event matching. Always classify schema impacts as `schema` type so consumers know the confidence level.

```bash
# Step 1: Find operations referencing the schema
grep -rl "{SchemaName}" api/specs/v1/domains/*/operations/*.yaml

# Step 2: Extract operationIds from those files, then run 2A for each
```

**2D. Recipe chain cross-reference (transitive)**

This is the most critical traversal. When a recipe is directly changed or affected by an upstream change:

1. Find all recipes that `extends` the affected recipe (direct children)
2. Recursively find all recipes that extend those children (grandchildren, up to depth 6)
3. Find all scenarios with `x-setup.recipe` matching any recipe in the chain

**Example extends chain for foundational recipes** (project-defined; structure varies):

```
minimal-tenant
  └── minimal-customer (extends: minimal-tenant)
        └── basic-orders (extends: minimal-customer)
              └── basic-fulfilled-orders (extends: basic-orders)
```

A change to `minimal-tenant.recipe.yaml` transitively affects all recipes downstream and every scenario that uses any of these as its `x-setup.recipe`.

```bash
# Find recipes that extend a given recipe name
grep -rl "extends:" api/specs/v1/scenarios/setup-recipes/**/*.recipe.yaml | xargs grep "{recipe-name}"

# Find scenarios using a recipe
grep -rl "recipe: {recipe-name}" api/specs/v1/domains/*/scenarios/*.arazzo.yaml api/specs/v1/scenarios/cross-domain/*.arazzo.yaml
```

### Stage 3: Classify Impact

For each affected file, assign exactly one impact type (in priority order -- if multiple apply, use the highest-priority type):

| Priority | Impact type | Meaning | When assigned |
|---|---|---|---|
| 1 | `self` | The scenario/recipe file itself was modified in the diff | File appears in `git diff --name-only` output |
| 2 | `direct` | The scenario/recipe directly references a changed operationId or event | operationId or event found in the file's steps or x-async blocks |
| 3 | `transitive` | The scenario uses a recipe (via `x-setup.recipe` or `extends`) that is affected | Recipe chain traversal identifies the connection |
| 4 | `schema` | The scenario references an operation whose request/response model changed | Two-hop lookup: schema -> operation -> scenario |

**Critical-path detection:**

Read each affected scenario file's `tags` array. If `critical-path` is present, mark it as critical-path in the report. This determines CI blocking behavior:
- **Blocking:** critical-path scenarios -- PR cannot merge if generated tests fail
- **Report-only:** non-critical-path scenarios -- failures are surfaced but do not block

### Stage 4: Determine CI Recommendation

For each affected scenario, assign a CI recommendation:

| Recommendation | Criteria |
|---|---|
| **Blocking** | Scenario has `critical-path` tag AND impact type is `self`, `direct`, or `transitive` |
| **Report-only** | Scenario does NOT have `critical-path` tag, OR impact type is `schema` (lower confidence) |
| **Skip** | Scenario confirmed unaffected by any changed artifact |

**Conservative rule:** `schema`-type impacts are always `report-only`, even for critical-path scenarios. The two-hop inference has lower confidence; blocking PRs on uncertain matches creates too much friction. If this proves insufficient, the rule can be tightened later.

---

## Structured Report Format

The agent MUST return this exact format. CI parses it programmatically.

```
## Impact Analysis

**Base:** {base-ref}
**Head:** {head-ref}
**Changes detected:** {count} operationIds, {count} events, {count} schemas

### Changed Artifacts

| Type | Identifier | Change | Source file |
|---|---|---|---|
| operationId | {name} | {added/removed/renamed/modified} | {path} |
| event | {Entity}.{Action} | {added/removed/renamed/modified} | {path} |
| schema | {SchemaName} | {modified} | {path} |

### Affected Scenarios

| File | Impact | Changed artifact | Critical path? | CI recommendation |
|---|---|---|---|---|
| {relative-path} | {direct/transitive/schema/self} | {artifact-type}: {identifier} | {yes/no} | {Blocking/Report-only} |

### Affected Recipes

| File | Impact | Changed artifact | Downstream scenarios |
|---|---|---|---|
| {relative-path} | {direct/self} | {artifact-type}: {identifier} | {count} scenarios via extends chain |

### Unaffected Scenarios

| File | Reason |
|---|---|
| {relative-path} | No overlap with changed artifacts |

### CI Recommendation

- **Blocking (critical-path):** {count} scenarios
- **Report-only:** {count} scenarios
- **Skip (unaffected):** {count} scenarios

### Errors

{Any issues discovered during analysis, such as:}
| Severity | Message |
|---|---|
| ERROR | operationId `{name}` removed -- {count} scenario(s) still reference it: {file-list} |
| WARN | operationId `{name}` renamed to `{newName}` -- {count} scenario(s) reference the old name |
| WARN | Schema `{name}` changed -- {count} scenario(s) affected via transitive lookup (lower confidence) |

{If no errors or warnings: "None."}
```

---

## Edge Cases

The agent MUST handle these cases explicitly:

### Renamed operationId

**Detection:** The git diff shows an operationId value removed from one file and a different operationId added in the same file (or the file itself is renamed via `git diff --name-status`).

**Handling:**
1. Record both the old and new operationId
2. Search scenarios for the OLD operationId -- these are broken references that need updating
3. Report as: `WARN: operationId '{old}' renamed to '{new}' -- {count} scenario(s) reference the old name`
4. Classify all affected scenarios as `direct` impact

### Deleted operationId

**Detection:** An operation file is deleted (appears as `D` in `git diff --name-status`) or an operationId line is removed without a replacement.

**Handling:**
1. Search scenarios for the deleted operationId
2. Report as: `ERROR: operationId '{name}' removed -- {count} scenario(s) still reference it: {file-list}`
3. Classify all affected scenarios as `direct` impact with `Blocking` CI recommendation regardless of critical-path tag

### New operationId (added)

**Detection:** A new operation file is added or a new operationId appears in the diff.

**Handling:** No impact on existing scenarios. Include in the Changed Artifacts table as informational only. Note: new operations may indicate that new scenarios should be authored, but that is outside this agent's scope.

### Recipe chain traversal

**Detection:** A recipe file is modified or an operationId/event in a recipe is affected.

**Handling:**
1. Build the full `extends` tree by reading every `.recipe.yaml` file's `x-recipe.extends` field
2. Identify the affected recipe
3. Walk DOWN the tree: find all recipes that directly or transitively extend the affected recipe
4. For each recipe in the chain, find all scenarios with `x-setup.recipe` matching that recipe's workflow name (derived from the filename: `basic-orders.recipe.yaml` -> `basic-orders`)
5. Classify downstream scenarios as `transitive` impact

**Example -- change to `minimal-tenant.recipe.yaml`:**
```
minimal-tenant.recipe.yaml  (CHANGED -- self)
  ├── minimal-customer.recipe.yaml  (transitive -- extends minimal-tenant)
  │     ├── basic-orders.recipe.yaml  (transitive -- extends minimal-customer)
  │     │     └── basic-fulfilled-orders.recipe.yaml  (transitive -- extends basic-orders)
  │     │           ├── order-lifecycle.arazzo.yaml  (transitive -- x-setup.recipe: basic-fulfilled-orders)
  │     │           ├── order-context-sync.arazzo.yaml  (transitive -- x-setup.recipe: basic-fulfilled-orders)
  │     │           └── auto-archive-stale-orders.arazzo.yaml  (transitive -- x-setup.recipe: basic-fulfilled-orders)
  │     └── (other recipes extending minimal-customer)
  └── (other recipes extending minimal-tenant)
```

### Wildcard event subscription changes

**Detection:** An AsyncAPI operation's effective subscription filter changes. Authors do NOT write a `filter` field directly — it is derived from the operation's `messages:` list (and any `requiredHeaders` / `filterOverride`). Detect changes to: (a) the `messages:` list (added/removed event refs), (b) `x-subscription.requiredHeaders` keys/values, or (c) `x-subscription.filterOverride` (rare escape hatch).

**Handling:** Conservative -- treat as affecting all scenarios that emit any event matching the old or new effective filter. This is an edge case that rarely changes; when it does, the blast radius is intentionally wide.

### Shared component changes (`common/` directory)

**Detection:** Files under `api/specs/v1/common/` are modified (shared parameters, responses, headers, enums).

**Handling:** Conservative -- these components are referenced across many operations. Flag all scenarios as `schema`-type impact with `Report-only` CI recommendation. Include a note: "Shared component change -- manual review recommended to determine actual blast radius."

### No changes detected

**Detection:** The git diff contains no files matching any recognized artifact pattern (no operations, messages, models, scenarios, or recipes changed).

**Handling:** Report "No Arazzo-relevant changes detected" and list all scenarios as `Skip`.

---

## Example: Mental Test

**Scenario:** operationId `finalizeOrder` is renamed to `completeOrder` in `api/specs/v1/domains/order/operations/finalize-order.yaml`.

**Expected analysis:**

1. **Stage 1 -- Extract:** Detects operationId rename (`finalizeOrder` -> `completeOrder`) in the diff
2. **Stage 2 -- Cross-reference:** Searches all `.arazzo.yaml` and `.recipe.yaml` for `operationId: finalizeOrder`
   - Found in `order-lifecycle.arazzo.yaml` at steps `finalize-order` and `finalize-empty-order`
3. **Stage 3 -- Classify:** `direct` impact (scenario directly references the changed operationId)
4. **Stage 4 -- CI Recommendation:** `order-lifecycle.arazzo.yaml` has `critical-path` tag -> `Blocking`

**Expected report excerpt:**

```
### Changed Artifacts

| Type | Identifier | Change | Source file |
|---|---|---|---|
| operationId | finalizeOrder | renamed to completeOrder | domains/order/operations/finalize-order.yaml |

### Affected Scenarios

| File | Impact | Changed artifact | Critical path? | CI recommendation |
|---|---|---|---|---|
| order/scenarios/order-lifecycle.arazzo.yaml | direct | operationId: finalizeOrder | yes | Blocking |

### Errors

| Severity | Message |
|---|---|
| WARN | operationId 'finalizeOrder' renamed to 'completeOrder' -- 1 scenario(s) reference the old name |
```
