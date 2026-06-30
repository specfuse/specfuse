---
name: validate-async
description: "Run the complete validation suite for the project's AsyncAPI specifications -- bundle, structural validation, and Spectral lint -- stopping on errors. Use to verify async specs are correct and ready for code generation."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Run the complete validation suite for the project's AsyncAPI specifications. Execute each step sequentially, stopping if a step produces errors (warnings are OK to continue).

*Enforces: .specfuse/authoring/handbooks/AsyncAPI_Handbook.md*

## Steps

1. **Bundle the async specs** — Run `./scripts/bundle-async-spec.sh api/specs/v1/asyncapi.yaml output/asyncapi-bundled.yaml` to produce the bundled file that downstream validators require.

2. **Validate async file structure** — Run `./scripts/validate-async-structure.sh` to ensure domain-based organization (main spec uses only $ref, correct file naming conventions, cross-references to OpenAPI models resolve).

3. **Run AsyncAPI Spectral lint** — Run `./scripts/validate-async-spectral.sh` to validate Specfuse AsyncAPI-specific rules (channel conventions, message categories, worker metadata, saga rules, delivery guarantees). Target: zero errors (warnings are OK).

## On failure

If any step fails with errors:
- Analyze the error output and identify the root cause
- Apply fixes to the spec files
- Re-run the bundle step, then re-run the failed validation step to confirm the fix
- Continue with remaining steps

## Report

After all steps complete, provide a summary:
- Which validations passed/failed
- Any warnings worth noting
- Whether async specs are ready for code generation
