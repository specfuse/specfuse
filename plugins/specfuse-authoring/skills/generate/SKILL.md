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

1. `specfuse-authoring` is on PATH (`pipx install specfuse-authoring`). The generator itself is not a file in the project — the CLI resolves and checksum-verifies the version pinned in `generator.lock` on demand.
2. The project config file (typically `<project>-project.json`) exists in the project root
3. Specifications are valid — if not recently validated, run `/validate` first

## Steps

Artifact groups are declared in the project config; generate the ones the project defines. `specfuse-authoring generate` passes its arguments through to the generator.

1. **Generate backend (C#)** — Run `specfuse-authoring generate --group "<backend group>" <project>-project.json`
2. **Generate frontend (Flutter)** — Run `specfuse-authoring generate --group "<frontend group>" <project>-project.json`
3. **Generate workers (C#)** — If `asyncSpecifications` is defined in the project config, run `specfuse-authoring generate --group "<workers group>" <project>-project.json`
4. **Generate documentation (Markdown)** — Run `./scripts/generate-scenario-docs.sh`. It bundles the specs, then calls the CLI for both markdown artifact groups defined in the project config:
   - `Documentation - Scenarios` → `scenarioDocument`, `scenarioIndex` (output: `./api/docs`)
   - `Documentation - Technical References` → `recipeDocumentation`, `entityDiagram`, `eventCatalog`, `channelTopology`, `docsIndex` (output: `./docs/generated`)

Report the outcome of each step. If generation fails, analyze the error output and suggest fixes.
