---
name: bundle
description: "Bundle the OpenAPI and (if present) AsyncAPI specifications into single self-contained files for code generation. Use when you need a bundled spec artifact before generating code, or when a downstream validator or generator requires the combined output."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Bundle the API specifications into single files for code generation.

*Enforces: (general — no single handbook)*

## OpenAPI Bundle

Run:
```bash
./scripts/specfuse/bundle-spec.sh api/specs/v1/openapi.yaml output/openapi-bundled.yaml
```

## AsyncAPI Bundle (if async specs exist)

If `api/specs/v1/asyncapi.yaml` exists, also run:
```bash
./scripts/specfuse/bundle-async-spec.sh api/specs/v1/asyncapi.yaml output/asyncapi-bundled.yaml
```

Report whether each bundle was created successfully. If either fails, analyze the error and suggest fixes.
