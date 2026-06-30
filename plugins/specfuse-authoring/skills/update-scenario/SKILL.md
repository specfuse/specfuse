---
name: update-scenario
description: "Apply targeted, surgical edits to an existing Arazzo scenario -- operationId or event renames, step add/remove, actor changes, extension updates, version bumps, deprecation -- then re-validate. Use when modifying an existing scenario rather than creating one; can auto-detect renames from recent git history and guides version-bump decisions."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Update an existing Arazzo scenario -- handles operationId renames, step additions/removals, actor changes, extension updates, version bumps, and deprecation.

*Enforces: .specfuse/authoring/handbooks/Arazzo_Handbook.md*

**Before modifying any files**, read and internalize the authoritative rules:
1. Read `.specfuse/authoring/handbooks/Arazzo_Handbook.md` -- especially Section 10 (versioning and deprecation), Section 13 (Do/Don't)
2. Read `.specfuse/authoring/samples/scenario-samples.yaml` -- canonical scenario template
3. Note the report format of the `scenario-validator` subagent (provided by the specfuse-authoring plugin) -- you will spawn it to validate

Then read the target scenario file the user wants to update.

## What this command does

Applies targeted changes to an existing Arazzo scenario file and re-validates. Unlike `/design-scenario` (which starts from PM intent and walks through an 11-step flow), this command starts from an existing file and makes surgical edits -- think "modify" rather than "create."

## Input clarification

Ask the user:

1. **Which scenario?** Accept a file path or domain + name. If ambiguous, list matching files:

   > "Which scenario do you want to update? Provide the file path or the domain and use-case name."

   If the user says something like "update the order scenario", scan for matches:
   ```
   api/specs/v1/domains/order/scenarios/order-lifecycle.arazzo.yaml
   api/specs/v1/domains/order/scenarios/order-context-sync.arazzo.yaml
   ```
   and ask them to pick.

2. **What kind of change?** Present the supported change types:

   > "What would you like to change?"
   > - **A.** Rename an operationId (or auto-detect renames from recent git changes)
   > - **B.** Rename an event (`{Entity}.{Action}`)
   > - **C.** Add step(s) to a workflow
   > - **D.** Remove step(s) from a workflow
   > - **E.** Change actors (add, remove, rename, change role)
   > - **F.** Update extensions (x-doc, x-mcp, x-ui, tags, x-setup, etc.)
   > - **G.** Version bump or deprecation

   The user may also describe the change in plain language. Map it to the appropriate handler.

3. **Specifics.** Each handler (below) has its own follow-up questions.

Multiple changes may be applied in sequence within a single session. After each change, re-validate before proceeding to the next.

---

## Change type handlers

### A. operationId rename

An operationId in the OpenAPI spec was renamed. All scenario references must follow.

**Clarify:**
- The old operationId and the new operationId. If the user is unsure, offer to auto-detect (see "Auto-detection of renames" below).

**Apply:**
1. Find every occurrence of the old operationId in the scenario file:
   - `steps[].operationId`
   - `x-async.poll.operationId`
2. Replace each with the new operationId.
3. Verify the new operationId exists in OpenAPI by reading `api/specs/v1/domains/{domain}/operations/` for a file containing it.
4. Check if the new operation has different response codes or a different request body shape. If so, warn the user:

   > "The new operation '{newId}' has a different response shape. Review the successCriteria and outputs for these steps: [{stepIds}]."

5. Determine if a version bump is warranted (see "Version bump guidance").

---

### B. Event name change

An event's `x-label` in AsyncAPI was changed, so `{Entity}.{Action}` references in the scenario must follow.

**Clarify:**
- The old event name (`Entity.Action`) and the new event name.

**Apply:**
1. Find every occurrence of the old event name:
   - `x-async.emit[].event`
   - `x-async.await.event`
2. Replace each with the new event name.
3. Verify the new event name exists in AsyncAPI by reading `api/specs/v1/domains/{domain}/messages/` for a message with matching `x-label`.
4. Check if `x-async.emit[].expect` or `x-async.await.match` payload field names need updating (if the event's payload schema changed alongside the rename).
5. Determine if a version bump is warranted.

---

### C. Add step(s)

Insert one or more new steps into an existing workflow.

**Clarify:**
- Which workflow within the file (if multiple exist).
- What the new step does (brief description).
- Where in the step sequence it should go (before/after which existing step).

**Apply:**
1. Read the domain's available operationIds (Glob `api/specs/v1/domains/{domain}/operations/*.yaml`). Present candidates relevant to the described action.
2. Confirm the operationId, actor (`x-as`), parameters, expected status code, and outputs.
3. If the operation is a write (POST/PUT/PATCH/DELETE), check its `x-emits` in the OpenAPI operation file. Add `x-async.emit` for each declared event.
4. If the step needs to wait for an async outcome, add `x-async.await` or `x-async.poll` as appropriate.
5. Insert the step at the specified position. Update any downstream `$steps.{id}.outputs.X` references if the new step provides outputs that subsequent steps should use.
6. If the user wants UI hints, collect `x-ui` actions following the same pattern as `/design-scenario` step 7.
7. This change warrants a version bump (new steps change the observable behavior).

---

### D. Remove step(s)

Remove one or more steps from an existing workflow.

**Clarify:**
- Which workflow and which step(s) to remove.

**Apply:**
1. **Check for dangling references.** Scan all remaining steps and workflow outputs for `$steps.{removedStepId}.outputs.X` expressions. List every dangling reference found.
2. If dangling references exist, present them:

   > "Removing step '{stepId}' will break these references:
   > - Step '{downstreamStep}' uses `$steps.{stepId}.outputs.{output}` in its parameters
   > - Workflow output '{outputName}' references `$steps.{stepId}.outputs.{output}`
   >
   > How should these be resolved? Options: (a) rewire to another step's output, (b) remove the downstream reference too, (c) cancel the removal."

3. Do NOT proceed until all dangling references are resolved.
4. Remove the step(s).
5. This change warrants a version bump.

---

### E. Actor changes

Add, remove, rename, or change the role of actors.

**Clarify:**
- What to change: add a new actor, remove an existing one, rename an actor key, or change a role.

**Apply -- add actor:**
1. Confirm the actor key (camelCase), role (from the project's closed role enum defined in the OpenAPI common enums file, typically `common/enums.yaml`), description, and optional `ref` binding to a recipe output.
2. Add to `x-actors`.
3. If the setup recipe does not provide an output for the new actor's `ref`, flag:

   > "The recipe '{recipeName}' does not provide output '{outputKey}'. The recipe may need to be updated, or the ref can be omitted."

**Apply -- remove actor:**
1. Check for `x-as` references to the actor being removed. List every step that uses this actor.
2. If steps reference the actor, those steps must be reassigned:

   > "These steps use `$actorKey`: [{stepIds}]. Reassign them to another actor before removing."

3. Do NOT remove an actor with active step references.

**Apply -- rename actor key:**
1. Rename the key in `x-actors`.
2. Update every `x-as: $oldKey` to `x-as: $newKey` across all steps.
3. Update any `x-actors.{oldKey}.ref` cross-references.

**Apply -- change role:**
1. Verify the new role is in the project's closed role enum.
2. Update `x-actors.{key}.role`.
3. Consider whether the role change affects authorization -- a step that worked for a manager-class role might not work for a customer-class role. Warn:

   > "Changing '{actorKey}' from '{oldRole}' to '{newRole}' may affect authorization. Verify that all operations this actor performs are accessible to the new role."

4. Actor changes warrant a version bump.

---

### F. Extension updates

Update any workflow-level or step-level extension value.

**Clarify:**
- Which extension to update (e.g., `x-doc.summary`, `x-mcp.exposed`, `tags`, `x-setup.recipe`, step-level `x-ui`).
- The new value.

**Apply:**
1. Read the current value and present it for reference.
2. Apply the update.
3. For `x-setup.recipe` changes: verify the new recipe exists and provides the outputs the scenario needs. Check that all `$setup.outputs.X` references in `x-actors.*.ref` and step parameters still resolve.
4. For `x-mcp.exposed: true`: ensure `toolName` and `description` are provided. Verify `toolName` is globally unique by scanning other scenario files.
5. For `tags` changes: note that adding `critical-path` means this scenario will block PR merges once test generation is in place.
6. Extension-only updates (typos, description rewording) do NOT warrant a version bump. Semantic changes (different recipe, changed `x-mcp` exposure) DO.

---

### G. Version bump and deprecation

Explicitly bump the version or deprecate the scenario.

**Version bump:**
1. Increment `x-version.current` by 1.
2. Optionally update `info.version` semver (minor bump for additive changes, major for breaking changes).

**Deprecation:**
1. Set `x-version.status` to `deprecated`.
2. Require `deprecatedAt` (ISO date -- use today's date as default).
3. Require `replacedBy` (file stem of the successor scenario).
4. Optionally set `removalDate`.
5. Verify the `replacedBy` scenario exists. If not, warn:

   > "The replacement scenario '{replacedBy}' does not exist yet. Create it with `/design-scenario` before finalizing deprecation."

---

## Auto-detection of operationId renames

When the user says "update for recent renames" or is unsure which operationIds changed, offer to scan git for renames:

1. Run `git diff HEAD~5..HEAD --name-status -- 'api/specs/v1/domains/{domain}/operations/'` to find renamed or modified operation files.
2. For each modified file, compare the old and new `operationId` values using `git diff HEAD~5..HEAD -- '{file}'`.
3. For renamed files (`R` status in git), extract the operationId from both the old and new file.
4. Present the detected rename mappings:

   > "I detected these operationId changes in the last 5 commits:
   > - `getRefunds` -> `listRefunds` (in `list-refunds.yaml`)
   > - `createRefund` -> `requestRefund` (in `request-refund.yaml`)
   >
   > Apply these renames to the scenario?"

5. On confirmation, apply each rename using handler A.

Also scan for event name changes:
1. Run `git diff HEAD~5..HEAD -- 'api/specs/v1/domains/{domain}/messages/'` and compare `x-label` values.
2. Present detected changes and apply using handler B on confirmation.

If no renames are detected:

> "No operationId or event name changes detected in the last 5 commits for the '{domain}' domain."

---

## Version bump guidance

After applying changes, determine whether a version bump is warranted. Present the recommendation to the user -- they can override, but the default should be correct.

**Bump `x-version.current`** (breaking or behavioral change):
- Steps added or removed
- Actor added, removed, or role changed
- `x-setup.recipe` changed to a recipe with a different output contract
- `successCriteria` assertions tightened
- `x-async` timeout or assertion changes that could fail previously-passing tests
- operationId or event name renames (the scenario's observable behavior changed)

**No bump** (non-breaking / cosmetic):
- `x-doc` text changes (summary, tutorialNote, businessOutcome)
- `x-ui` action text rewording
- Tag additions
- `x-mcp` description changes
- Typo fixes in descriptions or summaries

Present the recommendation:

> "This change warrants a version bump because [reason]. Current version: {N}. Bump to {N+1}?"

Or:

> "This change is cosmetic (description update). No version bump needed."

---

## Post-update validation

After every change (or batch of changes), validate the updated file.

1. Write the modified file to disk.
2. Spawn the `scenario-validator` subagent (provided by the specfuse-authoring plugin) to run validation, following its pipeline:
   - `./scripts/validate-arazzo-spectral.sh` (Spectral lint)
   - `./scripts/validate-arazzo.sh` (structural + cross-spec checks)
3. Process the validation report:
   - **Auto-fix mechanical issues silently**: casing fixes, missing defaults, ISO duration format.
   - **Surface judgment calls**: unresolved references, granularity alerts, cross-spec contradictions.
4. If new errors were introduced by the change, offer:

   > "The update introduced {N} validation errors:
   > {error list}
   >
   > Options: (a) fix them now, (b) revert the change, (c) proceed anyway (not recommended)."

5. Re-validate after fixes until the report shows zero errors.

---

## Post-update checklist

Verify all of these before reporting completion:

- [ ] Target scenario file saved
- [ ] All references updated (no dangling `$steps.{id}.outputs.X` or `$setup.outputs.X`)
- [ ] All operationIds resolve against OpenAPI
- [ ] All event names resolve against AsyncAPI
- [ ] Status code assertions still match OpenAPI conventions
- [ ] Actor roles are in the closed set
- [ ] `x-version.current` bumped if the change is behavioral (not cosmetic)
- [ ] Granularity still valid (changes did not push step overlap above 80% with another scenario)
- [ ] Validation passes with zero errors
- [ ] No hardcoded dates -- date tokens used throughout
- [ ] No language-specific references
