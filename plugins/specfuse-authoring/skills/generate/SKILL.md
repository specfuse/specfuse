---
name: generate
description: "Generate code and Markdown documentation from the API specifications for the artifact groups the project file declares (any language — C#, Python, Dart, TypeScript, Markdown). Use when you want to produce generated code and docs from validated specs; bundles the specs, runs the pinned generator once per selected group, and reports each group's outcome."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Generate code and documentation artifacts from the API specifications, one artifact group at a time.

*Enforces: (general — no single handbook)*

## Prerequisites — verify before running

1. `specfuse` is on PATH (`pipx install specfuse`, or `uv tool install specfuse`). The generator itself is not a file in the project — the CLI resolves and checksum-verifies the version pinned in `generator.lock` (or the project's `.specfuse/generator.lock`, which takes precedence) on demand. On a standalone kit install the deprecated flat `specfuse-authoring` command still works; drop the `specfuse ` prefix from the commands below.
2. The project config file (typically `<project>-project.json`) exists in the project root
3. Specifications are valid — if not recently validated, run `/validate` first

## Steps

Artifact groups are declared in the project config's `groups` array; generate the ones the project defines, never a fixed set.

1. **List the groups.** Read `groups[]` from `<project>-project.json` and show each group's `name`, `language`, `destination`, and whether it sets `cleanGenerated`. If the user named groups, select those; otherwise ask which to generate. Treat "all" as an explicit opt-in, never the default.
2. **Check the destinations before writing.** A `destination` outside the project (for example `../Backend/`) writes into another repo, and `cleanGenerated: true` deletes that group's generated tree before rewriting it. For each such destination, confirm the target repo has no uncommitted changes and is on a branch the user expects to receive the regen. Stop and ask if not.
3. **Bundle the specs** (the project file reads the bundled output):
   - `./scripts/specfuse/bundle-spec.sh api/specs/v1/openapi.yaml output/openapi-bundled.yaml`
   - If `asyncSpecifications` is set: `./scripts/specfuse/bundle-async-spec.sh api/specs/v1/asyncapi.yaml output/asyncapi-bundled.yaml`
4. **Generate each selected code group**, one invocation per group (the generator's `--group` takes a single name), from the project root:
   ```bash
   specfuse authoring generate generate --progress --group "<group name>" <project>-project.json
   ```
   The word `generate` appears twice on purpose: `specfuse authoring generate` launches the pinned generator and passes everything after it through verbatim, so the generator's own `generate` command must follow. Without it the generator prints `Unknown option: --group` and its usage text, and generates nothing.
5. **Run language post-steps** for groups that need them. Dart: the generator writes `part '*.g.dart'` / `part '*.freezed.dart'` directives but does not run `source_gen`, so run `dart pub get && dart run build_runner build --delete-conflicting-outputs` in the generated package before analysing it.
6. **Generate documentation (Markdown)** — if a Markdown group is selected, run `./scripts/specfuse/generate-scenario-docs.sh` instead of step 4 for it. It bundles the specs, generates every group of the project file with `"language": "markdown"` (whatever their names), then adds cross-links and the scenario index. With `--clean` it first removes each Markdown group's `destination`, except one outside the project, the project root, or a folder holding `api/docs/flows/` or `api/specs/`; scenario pages under `api/docs/flows/` are deleted file by file instead. It stops with an error when the project file has no Markdown group.

Report the outcome of each group: generator exit code `0` is success, `3` is a generation failure with a structured error, `1`/`2` are validation or system errors. If generation fails, analyze the error output and suggest fixes. For each group written into another repo, name the repo and remind the user that the regen is reviewed and merged there before `.specfuse/state` baselines are advanced.
