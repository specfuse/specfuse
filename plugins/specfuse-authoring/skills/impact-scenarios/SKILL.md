---
name: impact-scenarios
description: "Determine which Arazzo scenarios and recipes are affected by a code change by cross-referencing changed operationIds, events, and schemas against the corpus. Use after renaming or removing spec artifacts, or before a PR, to find the blast radius; wraps the impact-analyzer subagent, traverses recipe extends chains, and highlights critical-path scenarios."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Determine which Arazzo scenarios and recipes are affected by a code change. Wraps the `impact-analyzer` sub-agent to cross-reference changed operationIds, events, and schemas against the scenario corpus.

*Enforces: .specfuse/authoring/handbooks/Arazzo_Handbook.md*

## Input

Accept one of:
- **A git diff range:** e.g., `main..HEAD`, `HEAD~3`, `origin/main..HEAD`. The agent extracts changed artifacts from the diff.
- **An explicit list:** e.g., "operationId finalizeOrder was renamed to completeOrder" or "event Order.Finalized was removed". Passed directly to the agent.

If no input is provided, default to `main..HEAD`.

## Process

1. **Spawn the `impact-analyzer` subagent** (provided by the specfuse-authoring plugin). Use the Agent tool with a prompt that:
   - Relies on the subagent's built-in analysis pipeline
   - Provides the diff range or explicit artifact list
   - Instructs the agent to:
     1. Extract changed artifacts from the git diff (operationIds, events, schemas)
     2. Cross-reference against all scenario and recipe files
     3. Traverse recipe `extends` chains for transitive impacts
     4. Classify each affected file by impact type (self, direct, transitive, schema)
     5. Determine CI recommendation (blocking, report-only, skip)
     6. Return the structured impact report

2. **Present the impact report.** Show the structured output to the user:
   - Changed artifacts table
   - Affected scenarios with impact type and CI recommendation
   - Affected recipes with downstream scenario counts
   - Error/warning table (broken references, renames needing updates)

3. **Highlight critical-path scenarios.** If any affected scenario has the `critical-path` tag, present a prominent warning:

   > **Critical-path scenarios affected:**
   > - `order-lifecycle.arazzo.yaml` (direct impact -- operationId: finalizeOrder)
   >
   > These scenarios will block the PR in CI once test generation is in place. Verify they still pass by running `/validate-scenarios`.

4. **Suggest next steps.**
   - If operationIds were renamed: "Run `/update-scenario` to apply the rename to affected scenarios."
   - If scenarios are affected: "Run `/validate-scenarios` to verify affected scenarios still pass."
   - If operationIds were deleted: "Affected scenarios have broken references that must be fixed before merging."

## Checklist

- [ ] Impact-analyzer agent spawned with diff range or explicit artifact list
- [ ] Structured impact report presented
- [ ] Critical-path scenarios highlighted prominently
- [ ] Actionable next steps suggested
