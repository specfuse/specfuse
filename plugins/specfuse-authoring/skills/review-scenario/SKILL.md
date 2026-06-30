---
name: review-scenario
description: "Request an independent pre-merge review of an Arazzo scenario or recipe -- spawns the scenario-reviewer subagent, which evaluates the file cold (without the original PM intent) across seven quality and granularity categories and returns an APPROVE / REQUEST CHANGES / NEEDS DISCUSSION verdict. Use before merging a scenario for an unbiased second opinion."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Request an independent pre-merge review of an Arazzo scenario or recipe file. Spawns the `scenario-reviewer` sub-agent, which evaluates the file cold -- without seeing the original PM intent or design conversation.

*Enforces: .specfuse/authoring/handbooks/Arazzo_Handbook.md*

## Input

Accept the target file. The user may provide:
- A full file path (e.g., `api/specs/v1/domains/order/scenarios/order-lifecycle.arazzo.yaml`)
- A domain and scenario name (e.g., "order order-lifecycle")

If ambiguous, list matching files and ask the user to pick.

## Process

1. **Read the target file.** Confirm it exists and is a valid `.arazzo.yaml` or `.recipe.yaml` file.

2. **Gather domain context.** Read the same-domain corpus for granularity comparison:
   - Glob `api/specs/v1/domains/{domain}/scenarios/*.arazzo.yaml` for all existing scenarios in the target's domain. Extract workflowIds and step operationId sequences from each.
   - Glob `api/specs/v1/scenarios/setup-recipes/**/*.recipe.yaml` for all existing recipes. Extract file stems and output keys.

3. **Spawn the `scenario-reviewer` subagent** (provided by the specfuse-authoring plugin). Use the Agent tool with a prompt that:
   - Relies on the subagent's built-in review process
   - Provides the target file path
   - Provides the existing scenario list with workflowIds and step operationId sequences
   - Provides the existing recipe list with file stems and output keys
   - Instructs the agent to follow the 7-category review process (A through G) and return the structured report format

   **Independence constraint:** Do NOT pass any of the following to the reviewer agent:
   - The original PM conversation or use-case description
   - The `/design-scenario` session history
   - The architect agent's generation output or reasoning
   - Any commentary about why the scenario was designed this way

   The reviewer must form its own judgment from the YAML alone.

4. **Present the review report.** Show the structured output to the user:
   - **Verdict:** APPROVE, REQUEST CHANGES, or NEEDS DISCUSSION
   - **Checklist** with per-category status
   - **Granularity assessment** (if overlap detected)
   - **Findings** ordered by severity
   - **Recommendation** summary

5. **Handle the verdict:**
   - **APPROVE:** Report that the scenario is ready to merge. Note any warnings for optional follow-up.
   - **REQUEST CHANGES:** List each error finding with its suggested action. The author should address these before merging.
   - **NEEDS DISCUSSION:** Highlight the granularity assessment. The human reviewer must decide whether the overlap is acceptable or the scenarios should be consolidated.

## Checklist

- [ ] Target file identified and read
- [ ] Domain context gathered (existing scenarios and recipes)
- [ ] Scenario-reviewer agent spawned with file and context only (no PM intent)
- [ ] Structured review report presented to the user
- [ ] Verdict and recommended actions clearly communicated
