---
name: validate-scenarios
description: "Run the complete validation suite for all Arazzo scenarios and recipes -- Spectral lint plus structural and cross-spec checks (operationId and event resolution, recipe chains, granularity). The Arazzo equivalent of /validate and /validate-async; use to verify scenarios before merge or generation."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Run the complete validation suite for all Arazzo scenarios and recipes. The Arazzo equivalent of `/validate` (OpenAPI) and `/validate-async` (AsyncAPI).

*Enforces: .specfuse/authoring/handbooks/Arazzo_Handbook.md*

## Steps

Execute sequentially. Stop if a step produces errors (warnings are OK to continue).

1. **Discover files.** Glob all `.arazzo.yaml` and `.recipe.yaml` files under `api/specs/v1/`. Report the count:

   > "Found N scenario files and M recipe files."

2. **Run Spectral lint.** Execute:
   ```bash
   ./scripts/validate-arazzo-spectral.sh
   ```
   This runs the 24-rule Specfuse Arazzo Spectral ruleset (`api/spectral.specfuse-arazzo.yaml`) against all discovered files. Target: zero errors (warnings are OK).

3. **Run structural validation.** Execute:
   ```bash
   ./scripts/validate-arazzo.sh
   ```
   This runs the 14-check structural + cross-spec validator covering operationId resolution, event name resolution, recipe chain validation, file organization, and granularity checks. Target: zero errors.

4. **Report summary.** Present results in a clear format:

   If all pass:
   > "All N scenarios and M recipes are valid. 0 errors, K warnings."

   If failures exist, list each with file path, rule ID, and message:

   | File | Rule | Severity | Message |
   |---|---|---|---|
   | {path} | {rule-id} | error | {message} |

   Group by file for readability.

## On failure

If any step fails with errors:
- Analyze the error output and identify the root cause
- If the errors are auto-fixable (per the classification used by the `scenario-validator` subagent, provided by the specfuse-authoring plugin): apply fixes and re-run
- If the errors require judgment: present them to the user with suggested actions
- Re-run the failed validation step after fixes to confirm

## Checklist

- [ ] All `.arazzo.yaml` and `.recipe.yaml` files discovered
- [ ] Spectral lint passed (0 errors)
- [ ] Structural validation passed (0 errors)
- [ ] Summary reported with file counts and error/warning totals
