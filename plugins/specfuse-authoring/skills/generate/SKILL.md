---
name: generate
description: "Generate frontend (Flutter) and backend (C#) code, workers, and Markdown documentation artifacts from the API specifications. Use when you want to produce generated code and docs from validated specs; runs the project generate scripts and reports each step's outcome."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Generate frontend and backend code artifacts from the API specifications.

*Enforces: (general — no single handbook)*

## Prerequisites — verify before running

1. `specfuse-generator.jar` exists in the `scripts/` directory
2. The project config file (typically `<project>-project.json`) exists in the project root
3. Specifications are valid — if not recently validated, run `/validate` first

## Steps

1. **Generate backend (C#)** — Run `./scripts/generate-backend.sh`
2. **Generate frontend (Flutter)** — Run `./scripts/generate-flutter.sh`
3. **Generate workers (C#)** — If `./scripts/generate-workers.sh` exists and `asyncSpecifications` is defined in the project config, run `./scripts/generate-workers.sh`
4. **Generate documentation (Markdown)** — Run `./scripts/generate-scenario-docs.sh`. This invokes both markdown artifact groups defined in the project config:
   - `Documentation - Scenarios` → `scenarioDocument`, `scenarioIndex` (output: `./api/docs`)
   - `Documentation - Technical References` → `recipeDocumentation`, `entityDiagram`, `eventCatalog`, `channelTopology`, `docsIndex` (output: `./docs/generated`)

Report the outcome of each step. If generation fails, analyze the error output and suggest fixes.
