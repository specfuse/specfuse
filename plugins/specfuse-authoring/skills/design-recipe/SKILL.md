---
name: design-recipe
description: "Design a new Arazzo setup recipe that provisions test fixtures via real OpenAPI operations so scenarios start from a known state. Use when a scenario needs precondition entities no existing recipe provides; walks composition (extends chains, depth limits, output contracts, $system actor) and validates with zero forbidden extensions."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Design a new Arazzo setup recipe for scenario preconditions. Recipes are infrastructure -- they provision test fixtures using real OpenAPI operations so that scenarios start from a known state.

*Enforces: .specfuse/authoring/handbooks/Arazzo_Handbook.md*

**Audience:** architects and lead developers, not PMs.

**Before writing any files**, read and internalize the authoritative rules:
1. Read `.specfuse/authoring/handbooks/Arazzo_Handbook.md` -- Section 7 (setup recipes: composition, extends chain, scope, discriminator, implicit $system actor)
2. Read `.specfuse/authoring/samples/recipe-samples.yaml` -- canonical recipe template (covers the full foundational chain and a domain-specific example)
3. Note the report format of the `scenario-validator` subagent (provided by the specfuse-authoring plugin) -- you will spawn it to validate

Then scan the existing recipe files to understand what is already available:
- `api/specs/v1/scenarios/setup-recipes/foundational/*.recipe.yaml`
- `api/specs/v1/scenarios/setup-recipes/domain-specific/**/*.recipe.yaml`

## What this command produces

A single Arazzo 1.0.1 recipe file (`.recipe.yaml`) placed in:
- `api/specs/v1/scenarios/setup-recipes/foundational/` for domain-agnostic foundational recipes
- `api/specs/v1/scenarios/setup-recipes/domain-specific/{domain}/` for domain-specific recipes

Recipes are Arazzo workflows with the `x-recipe` extension. They are NOT scenarios -- the following extensions are **forbidden** on recipes:
- `x-actors` -- recipes run as the implicit `$system` actor mapped to `Admin`
- `x-as` -- every recipe step runs as `$system` (no actor binding on steps)
- `x-setup` -- recipes compose via `extends`, not `$setup`
- `x-mcp` -- recipes are infrastructure, not user-facing tools
- `x-ui` -- no user-facing interactions in fixture setup

## Input clarification

Ask the user these questions before designing:

1. **Purpose.** What precondition state does the recipe establish?

   > "What entities need to exist before the scenario starts? For example: 'a tenant with 3 customers and a fulfilled order.'"

2. **Fixture type.** What is the recipe for?

   | Purpose | Behavior |
   |---------|----------|
   | `test-fixture` | Fast, minimal, disposable. Created and torn down per scenario. Most common. |
   | `demo-fixture` | Rich, realistic, persistent. For demos, UAT, stakeholder walkthroughs. NOT cleaned up after execution. |
   | `dev-fixture` | Like demo-fixture but refreshable. For local dev seeding. |

3. **Domain.** Which domain does this recipe primarily serve? This determines `x-domain` and file placement.

4. **Composition.** Present the existing recipe tree (see step 1 below) and ask: does this recipe extend an existing one?

5. **Output contract.** What entity IDs and values should the recipe expose for scenarios to reference via `$setup.outputs.X`?

   > "What outputs do scenarios need from this recipe? Think about the actors and resources the scenario will reference -- each needs a distinct output name."

   This is where mistakes happen. If a scenario needs `requesterId` and `approverId` (two different customers), the recipe must create both and expose both with distinct output names. Ask about this explicitly.

---

## Design process

### Step 1: Map to existing chain

Build and present the current recipe composition tree by scanning existing recipe files. Show the `extends` relationships:

```
minimal-tenant (foundational, tenant)
  outputs: tenantId, adminUserId
  └── minimal-customer (foundational, customer)
        outputs: + customerId, managerUserId
        └── basic-orders (foundational, order)
              outputs: + orderId1, orderId2, requesterId, approverId,
                         catalogItemId, customerCatalogId
              └── basic-fulfilled-orders (order)
                    outputs: + fulfillmentId, templateId, lineId1,
                               lineId2, lineId
```

Identify the deepest existing recipe that provides a subset of the needed state. Propose extending it:

> "The recipe 'basic-orders' already provides a tenant, customer, manager, and two orders. Your recipe needs fulfilled orders on top of that. I recommend extending 'basic-orders' (depth 3). Does that work, or should we extend 'basic-fulfilled-orders' (depth 4) instead?"

If extending would push the chain past depth 6 (the maximum), warn:

> "Extending '{recipe}' would create a chain of depth {N}, exceeding the maximum of 6. Consider restructuring: can any intermediate recipe be flattened or bypassed?"

If the recipe needs entities from multiple unrelated chains, it must extend the chain that covers the most and create the rest from scratch.

---

### Step 2: Identify additional operations

List the OpenAPI operations needed to create the state beyond what the parent recipe provides.

1. Glob `api/specs/v1/domains/{domain}/operations/*.yaml` and present the available write operations (POST endpoints).
2. If the recipe serves a different domain than its parent, also scan that domain's operations.
3. Confirm each operationId exists. If an operation is missing, stop:

   > "The recipe needs to create a '{entity}' but no 'create{Entity}' operation exists in OpenAPI. Design the endpoint first."

Present the operation list and confirm:

> "To build on top of '{parentRecipe}', these additional operations are needed:
> 1. `createOrderTemplate` -- create the order template
> 2. `generateFulfillment` -- generate the fulfillment from the template
> 3. `addOrderLine` -- add lines for each item
>
> Confirm or adjust."

---

### Step 3: Design steps

For each operation identified in step 2, design a recipe step:

- `stepId` (kebab-case, descriptive)
- `operationId` (confirmed from step 2)
- `parameters` and `requestBody` using:
  - `$steps.parent-setup.outputs.X` for values from the parent recipe
  - `$steps.{stepId}.outputs.X` for values from earlier steps in this recipe
  - `$inputs.X` for parameterized values with defaults
  - Date tokens (`@today+3d`) for date fields
- `successCriteria` matching OpenAPI conventions (POST -> 201)
- `outputs` capturing the entity IDs the recipe needs to expose

**No `x-as` on any step.** Recipe steps run as the implicit `$system` actor.

Present each step for confirmation. Keep them minimal -- recipes create only what scenarios need, nothing more.

**Workflow inputs**: identify values that should be parameterizable (dates, names, counts). Define them as workflow `inputs` with sensible defaults. Callers (child recipes or scenarios) can override these.

---

### Step 4: Define output contract

The output contract is the recipe's public API. Scenarios reference these via `$setup.outputs.X`.

1. List all outputs the recipe will expose (its own + inherited from the parent chain).
2. **Check for namespace collisions.** If any output name in this recipe matches a parent output name, it is a validator error. Rename one of them.
3. Use descriptive names: `requesterId` not `id1`, `fulfillmentId` not `planId`.
4. Present the complete merged output namespace:

   > "Scenarios using this recipe will have access to:
   > - From `minimal-tenant`: tenantId, adminUserId
   > - From `minimal-customer`: customerId, managerUserId
   > - From `basic-orders`: orderId1, orderId2, requesterId, approverId, catalogItemId, customerCatalogId
   > - From this recipe (new): fulfillmentId, templateId, lineId1, lineId2
   >
   > Any name collisions? Any missing outputs?"

**Output stability rule**: adding outputs later is safe. Removing or renaming outputs is a **breaking change** that requires updating all dependent scenarios and child recipes.

---

### Step 5: Generate and validate

1. Generate the complete recipe YAML file including:
   - `arazzo: "1.0.1"` header
   - `info` with a descriptive title and `version: "1.0.0"`
   - `sourceDescriptions` with the correct relative path to `openapi.yaml`
   - `x-version: { current: 1, status: draft }`
   - `x-domain` matching the confirmed domain
   - `x-recipe` with `purpose`, `extends` (if applicable), `idempotent`, `estimatedDurationMs`, `scope`
   - `workflows` with a single `setup` workflow containing steps and outputs

2. Determine the `sourceDescriptions[].url` relative path based on file location:
   - Foundational: `../../../openapi.yaml` (from `scenarios/setup-recipes/foundational/`)
   - Domain-specific: `../../../../openapi.yaml` (from `scenarios/setup-recipes/domain-specific/{domain}/`)

3. Write the file to disk.

4. Spawn the `scenario-validator` subagent (provided by the specfuse-authoring plugin) to validate, following its pipeline:
   - `./scripts/specfuse/validate-arazzo-spectral.sh` (Spectral lint)
   - `./scripts/specfuse/validate-arazzo.sh` (structural + cross-spec checks)

5. Process the validation report:
   - Auto-fix mechanical issues (missing defaults, casing).
   - Surface any cross-spec errors (unresolved operationIds, chain depth, output collisions).
   - Re-validate until zero errors.

6. Report the file path and the complete output contract.

---

## Composition rules

These are validator-enforced. The command must check them before generating:

| Rule | Constraint |
|------|-----------|
| Single inheritance | `extends` is an ordered array expressing a chain, not multiple parents |
| Max depth 6 | Count the full chain from root to this recipe. Depth > 6 = error. |
| No cycles | A recipe cannot extend itself or form a circular chain (A -> B -> A) |
| No output collisions | If a parent and child both declare an output with the same name, the validator errors. The flat namespace keeps `$setup.outputs.X` unambiguous. |
| No scenario extensions | Recipes must NOT have `x-actors`, `x-mcp`, `x-setup`, or `x-ui` |
| Implicit `$system` actor | All steps run as `$system` mapped to `Admin`. No `x-as` on steps. |
| `$setup` forbidden | Recipes cannot reference `$setup`. Use `$steps.parent-setup.outputs.X` for parent outputs. |

---

## File placement rules

| Type | Location | Example |
|------|----------|---------|
| Foundational (domain-agnostic) | `api/specs/v1/scenarios/setup-recipes/foundational/` | `minimal-tenant.recipe.yaml` |
| Domain-specific | `api/specs/v1/scenarios/setup-recipes/domain-specific/{domain}/` | `basic-fulfilled-orders.recipe.yaml` |

File naming: `{descriptive-name}.recipe.yaml` (kebab-case). The `.recipe.yaml` suffix is mandatory -- it is the file-level discriminator that tooling uses to classify files.

**Foundational vs domain-specific**: a recipe is foundational if it creates entities used by many domains (tenants, customers, base users). It is domain-specific if it creates entities tied to a single domain (orders, refunds, compliance items).

---

## Post-creation checklist

Verify all of these before reporting completion:

- [ ] Recipe file written to the correct directory (foundational or domain-specific)
- [ ] All `operationId` values confirmed against OpenAPI
- [ ] `x-recipe` fields set: `purpose`, `extends` (if applicable), `idempotent`, `estimatedDurationMs`, `scope`
- [ ] `x-version` present with `current: 1` and `status: draft`
- [ ] `x-domain` present and matches the recipe's primary domain
- [ ] `extends` chain valid: depth <= 6, acyclic, parent recipe exists
- [ ] No output namespace collisions with parent outputs
- [ ] Output contract clearly documented (both new outputs and inherited ones noted)
- [ ] `sourceDescriptions[].url` is a correct relative path to `openapi.yaml`
- [ ] No forbidden extensions present (`x-actors`, `x-mcp`, `x-setup`, `x-ui`, `x-as`)
- [ ] No hardcoded dates -- date tokens used in inputs and step payloads
- [ ] No language-specific references
- [ ] Validation passes with zero errors

## Tips for good recipes

- **Minimal by design.** Create only what the scenario needs. A recipe with 20 steps creating entities "just in case" is over-engineered. If a scenario needs more, create a child recipe that extends this one.
- **Extend, do not duplicate.** If `basic-orders` already creates a tenant, customer, and orders, do not repeat those steps. Extend it and add only the new entities.
- **Output names matter.** Scenarios bind actors and parameters to recipe outputs. `requesterId` is clear; `id1` is not. Use descriptive names that tell the scenario author what the value represents.
- **`idempotent: true` is the default.** Test fixtures should be safe to re-run. If the recipe creates entities with unique constraints (e.g., unique tenant codes), use parameterized inputs with defaults that the Specfuse runtime can make unique per run.
- **Estimate duration realistically.** `estimatedDurationMs` is informational (for test scheduling). A recipe that calls 5 API endpoints with typical latency should estimate 1000-2000ms, not 100ms.
- **Recipes do not mint tokens.** Token provisioning is the Specfuse runtime's responsibility. Recipes create entities (users, customers); the runtime maps scenario actors to those entities and mints auth tokens. Never call auth endpoints in a recipe.
- **Date tokens keep recipes time-independent.** Use `@today+3d` instead of `"2026-05-01"`. Date tokens resolve only in workflow `inputs` defaults and step `requestBody.payload`/`parameters` values.
