---
name: validate
description: "Run the complete validation suite for the project's OpenAPI specifications -- bundle, file structure, OpenAPI Generator, SpecFuse validator, Spectral lint, and Redocly -- plus AsyncAPI validation if async specs exist. Use to verify specs are correct and ready for code generation."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Run the complete validation suite for the project's OpenAPI specifications. Execute each step sequentially, stopping if a step produces errors (warnings are OK to continue).

*Enforces: (general — no single handbook)*

## Steps

1. **Bundle the specs** — Run `./scripts/specfuse/bundle-spec.sh api/specs/v1/openapi.yaml output/openapi-bundled.yaml` to produce the bundled file that downstream validators require.

2. **Validate file structure** — Run `./scripts/specfuse/validate-structure.sh` to ensure domain-based organization (main spec uses only $ref, no inline definitions).

3. **Validate with OpenAPI Generator** — Run `./scripts/specfuse/validate-openapi-generator.sh` to check schema structure, reference integrity, and generator compatibility.

4. **Run SpecFuse validator** — Run `./scripts/specfuse/validate-specs.sh` to validate aggregate boundaries, entity relationships, value objects, and x-entity metadata. Target: zero errors.

5. **Run Spectral lint** — Run `npx spectral lint --ruleset api/spectral.specfuse.yaml output/openapi-bundled.yaml` to validate Specfuse-specific rules (casing, naming, HTTP contract, auth metadata, x-entity shape, AI agent patterns). Target: zero errors (warnings are OK).

6. **Run Redocly validation** — Run `./scripts/specfuse/validate-redocly.sh v1` to validate OpenAPI 3.0 compliance.

## On failure

If any step fails with errors:
- Analyze the error output and identify the root cause
- Apply fixes to the spec files
- Re-run the bundle step, then re-run the failed validation step to confirm the fix
- Continue with remaining steps

## AsyncAPI Validation (if async specs exist)

If `api/specs/v1/asyncapi.yaml` exists, also run these steps after the OpenAPI validation:

7. **Bundle async specs** — Run `./scripts/specfuse/bundle-async-spec.sh api/specs/v1/asyncapi.yaml output/asyncapi-bundled.yaml`

8. **Validate async structure** — Run `./scripts/specfuse/validate-async-structure.sh`

9. **Run AsyncAPI Spectral lint** — Run `./scripts/specfuse/validate-async-spectral.sh`

## Report

After all steps complete, provide a summary:
- Which validations passed/failed (both OpenAPI and AsyncAPI)
- Any warnings worth noting
- Whether specs are ready for code generation
