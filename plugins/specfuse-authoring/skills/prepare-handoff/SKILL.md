---
name: prepare-handoff
description: "Produce a feature handoff manifest under api/docs/handoffs/ per the orchestrator's consumer contract -- runs the full validation suite, regenerates scenario docs and bundles, builds operation/async/entity/scenario inventories and the prompt index, then delegates manifest composition to the handoff-composer subagent. Use when packaging a completed spec feature for downstream implementation; can autonomously mint the correlation ID."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Produce a feature handoff manifest at `api/docs/handoffs/<correlation-id>.md` per the consumer contract in the project's orchestrator (typically `../orchestrator/project/specs-handoff-contract.md`). Composes existing primitives (validation, scenario doc regen, bundling, scenario impact, prompt-corpus parser) and delegates manifest composition to the `handoff-composer` sub-agent.

*Enforces: (general — no single handbook)*

**Before doing anything**, read and internalize:

1. `../orchestrator/project/specs-handoff-contract.md` — authoritative section list, formats, freshness rules.
2. `../orchestrator/project/coordination-conventions.md` — §2 operation classification, §7 async classification, §10 direction-of-reference rule.
3. `../orchestrator/shared/rules/correlation-ids.md` — minting rules, per-year-resetting numbering.
4. `../orchestrator/shared/templates/feature-registry.md` — registry-entry template.
5. `../orchestrator/shared/schemas/feature-frontmatter.schema.json` — registry-entry frontmatter schema.
6. The input/output contract of the `handoff-composer` subagent (provided by the specfuse-authoring plugin) — you will delegate manifest composition to it.
7. `api/docs/implementation-prompts/README.md` — front-matter convention for prompt files.

## Input

Accept ONE positional argument and optional flags:

| Argument / flag | Required | Behavior |
|---|---|---|
| `<correlation-id>` | no | When supplied, validate format `FEAT-\d{4}-\d{4}` and use as-is. When omitted, **mint autonomously** — see §1 below. |
| `--scope <paths>` | no | Comma-separated list of paths under `api/specs/v1/` to override scope derivation. |
| `--since <ref>` | no | Override the diff base for scope derivation; default `origin/main`. |
| `--dry-run` | no | Produce manifest content and registry-entry content but do not write or commit. Useful for review before live use. |

## Process

Run sequentially. Stop at any **gate** that asks for user confirmation; surface validation/HC failures faithfully (no suppression).

---

### Step 1: Resolve correlation ID

**If supplied:**
- Validate format `FEAT-\d{4}-\d{4}`.
- Compare year against `date +%Y`. Mismatch → warn but continue (historical features may legitimately need backfill); user can confirm or abort.
- Check whether `../orchestrator/features/<correlation-id>.md` exists. If yes, treat this as a re-run (Step 11 path). If no, treat as supplied-mint and create the registry entry as part of Step 12.

**If omitted (autonomous mint):**

1. Verify `../orchestrator/features/` exists. If not, STOP:
   > Orchestrator repo not found at `../orchestrator/features/`. Cannot mint correlation ID. Confirm the sibling-path layout matches `<project>App/{orchestrator,<project>-specs}/`.
2. Read `../orchestrator/shared/schemas/feature-frontmatter.schema.json`. If unreachable, STOP with the same shape of message.
3. Glob `../orchestrator/features/FEAT-{currentYear}-*.md`. Extract the largest `NNNN`. Pick the next ordinal (or `0001` if none). Per-year-resetting per `correlation-ids.md`.
4. Set `correlationId = FEAT-<year>-<NNNN>`.
5. Defer the registry-entry write until Step 12 — production failure should not leave a phantom entry behind.

---

### Step 2: Scope derivation gate

If `--scope` is supplied, use it verbatim.

Otherwise:
- Run `git diff <since>...HEAD --name-only` (default `<since>` = `origin/main`).
- Filter to paths matching `api/specs/v1/**`.
- Plus any uncommitted-but-staged files under `api/specs/v1/**` (from `git diff --cached --name-only`).

Print the derived list to the user. Ask:

> Scope ({N} paths under api/specs/v1/):
>
>   {path1}
>   {path2}
>   ...
>
> Confirm? (y/n)

On `n`, stop and ask for a `--scope` override or different `--since`. On `y`, continue.

---

### Step 3: Run validation suite

Run sequentially. **Stop at the first FAIL** and surface to the user — the contract treats failed validation as invalid-manifest grounds (composer HC-3).

| Step | Command | Captures |
|---|---|---|
| 3a | `./scripts/validate-spectral.sh` | OpenAPI Spectral lint |
| 3b | `./scripts/validate-specs.sh` | SpecFuse structural validator |
| 3c | `./scripts/validate-redocly.sh` | Redocly validation |
| 3d | `./scripts/validate-async-spectral.sh` | AsyncAPI Spectral |
| 3e | `./scripts/validate-async-structure.sh` | AsyncAPI structural |
| 3f | `./scripts/validate-arazzo-spectral.sh` | Arazzo Spectral |
| 3g | `./scripts/validate-arazzo.sh` | Arazzo structural + cross-spec |

Aggregate result → `validationResults.layer1 = PASS|FAIL`. On FAIL, print failing rule + file location and STOP.

---

### Step 4: Tier-A scenario doc regen

For each `.arazzo.yaml` in `scopePaths`:

- Compare its mtime (or last-commit time via `git log -1 --format=%ct`) against the corresponding `api/docs/flows/<domain>/scenarios/<file>.md`.
- If the rendered doc is missing or older, run `/generate` (Markdown group only) to refresh.

Set `validationResults.tierARegen = PASS` after all scenario docs are current. On regen failure, STOP with the underlying error.

---

### Step 5: Bundle regeneration (always — produce, don't check)

Run unconditionally:

- `./scripts/bundle-spec.sh api/specs/v1/openapi.yaml output/openapi-bundled.yaml`
- `./scripts/bundle-async-spec.sh api/specs/v1/asyncapi.yaml output/asyncapi-bundled.yaml`

Set `validationResults.bundleRegen = PASS` and capture `sourceCommitForBundle` from `git rev-parse --short HEAD` AFTER staging the regenerated bundles (Step 12 captures the final commit reference).

The contract treats §8's "Bundled spec freshness" as a producer responsibility, not a check — see contract §8 "Producer behavior: produce, don't check."

---

### Step 6: Open-issue gate

Run `gh issue list --label spec_level_blocker --state open --json number,title,assignees,body --limit 50`.

Filter to issues whose `body` contains at least one path in `scopePaths`. (Substring match on each scope path is sufficient at v0.1; refine if false-positive rate is high.)

Build `openIssues` list. If non-empty:

> {N} open spec_level_blocker issues touch this feature's scope:
>
>   {repo}#{number}: {title} (assignee: {assignee})
>   ...
>
> Per the contract, the PM agent will not transition this feature to `planning`
> while §7 is non-empty. Publish manifest with §7 populated anyway? (y/n)

On `y`, continue. On `n`, stop — user resolves issues first.

---

### Step 7: Build inventories

For each path in `scopePaths`, read the spec file and pre-classify:

**Operations** (`api/specs/v1/domains/*/operations/*.yaml`):
- Operation files are HTTP-method-keyed at the root (`get:` / `post:` / `put:` / `patch:` / `delete:`). Identify the HTTP method, then descend into that object to read `operationId` and `x-operation`.
- Extract `operationId`, `x-operation.category` (NOT `x-operation.type` — the field name is `category`).
- Apply `coordination-conventions.md` §2: absent `x-operation` or `category == aggregate` → `auto-generated`; everything else → `hand-crafted`.
- If `category == resource` is encountered, classify as `hand-crafted` per the mechanical rule but flag for the user — `resource` is being phased out (per the §2 guidance) and the spec should be reviewed.

**Async** (`api/specs/v1/domains/*/async-operations/*.yaml`, `messages/*.yaml`):
- Extract verb prefix from filename (`on-`, `run-`, `emit-`).
- Detect `x-worker` presence and `x-ai.enabled`.
- Apply `coordination-conventions.md` §7: `on-`/`run-` with `x-worker` → `worker`/`scheduled-job`; `emit-` → `emission-only`.

**Entities** (any model file with `x-entity` whose `aiAccess` differs from prior version, OR newly-added entity files):
- Capture `name`, `aggregate` (from `x-entity.belongsTo` chain), `newTier`, `priorTier` (read from prior commit if changed).

**Scenarios** (`api/specs/v1/domains/*/scenarios/*.arazzo.yaml`):
- Capture `specPath`, `renderedDocPath` (computed from domain), `tags`.
- Status: `new` if file is newly added in scope, `changed` if modified, `referenced-only` if it's referenced from another in-scope file but itself unchanged.

**Cross-domain deps** (one-hop walk, narrow scope per Friction #3 finding):
- Restrict the walk to **direct `$ref`s from operation files (`operations/*.yaml`) and async-operation files (`async-operations/*.yaml`) in `scopePaths`**. Do NOT follow refs into messages, channels, or async-common/common shared traits — those pull in trait-inherited cross-domain references that are infrastructure, not feature consumption.
- One hop only: read each in-scope operation/async-operation file, collect every `$ref` whose resolved path is under `api/specs/v1/domains/<other-domain>/`. Group by domain. Do not recurse into the referenced files.
- Exclude refs whose resolved path is under `api/specs/v1/common/` or `api/specs/v1/async-common/` — those are shared infrastructure.
- For each external-domain target, evaluate the HC-7 predicate (per artifact type per the contract §6 table) and set `live: true|false`. If a single artifact reports both flags inconsistently → STOP and file `spec_level_blocker` per `coordination-conventions.md` §4.

The narrow walk is intentional: contract §6 means "operations / events / entities the feature *consumes*", not "anything transitively reachable through trait inheritance." Surfacing many domains because of correlation-header trait refs creates noise that obscures the real deps.

---

### Step 8: Build prompt index

Run `./scripts/build-prompt-index.sh`. Capture stdout (JSON map) and stderr (warnings).

Filter the index to the subset of keys present in `scopePaths`. This becomes `promptIndex` for the composer.

If stderr produced any warnings, surface them to the user as informational — do not block.

---

### Step 9: Read Tier-B hints

Read the project config file (typically `../<project>-project.json`) live, per contract §9 advisory rule. Extract group names whose `destination` paths overlap consumer-repo paths the feature touches. Heuristic mapping — when uncertain, include the group; the PM agent re-derives anyway.

If the file is unreachable, `tierBHint = []` and emit a warning.

---

### Step 10: Existing-manifest / draft-notes detection

- If `api/docs/handoffs/<correlation-id>.md` exists: this is a re-run. Read the file, extract §11 verbatim into `existingManifest`. The composer will preserve §11 (HC-8).
- Else if `api/docs/handoffs/<correlation-id>.notes-draft.md` exists: this is first creation with notes. Read the body, set `draftNotesPath`. The composer slurps it once.
- Else: neither exists. §11 will be `_None._`.

Never both. If both files exist, STOP — the calling user is in an inconsistent state. Ask them to either delete the draft (if §11 should preserve from existing manifest) or delete the existing manifest (if they want to recreate from scratch).

---

### Step 11: Compose manifest

Spawn the `handoff-composer` subagent (provided by the specfuse-authoring plugin) with the full structured brief assembled from Steps 1–10. The subagent applies its input/output contract and HC-1 through HC-8, and returns the manifest as Markdown.

If the agent reports any HC violation, surface verbatim and STOP.

If `--dry-run`, print the manifest to stdout and stop here.

---

### Step 12: Write artifacts

In this order (manifest first, registry entry second — production-then-registry):

1. Write `api/docs/handoffs/<correlation-id>.md` with the composed Markdown.
2. If a draft was slurped in Step 10, delete `api/docs/handoffs/<correlation-id>.notes-draft.md` (the manifest is now the source of truth for §11).
3. If the registry entry doesn't yet exist, write `../orchestrator/features/<correlation-id>.md` per `shared/templates/feature-registry.md` with minimum frontmatter:
   ```yaml
   ---
   correlation_id: <correlation-id>
   title: <featureTitle>
   state: validating
   ---

   See [handoff manifest](../../<project>-specs/api/docs/handoffs/<correlation-id>.md) for feature scope.
   ```
4. Validate the registry entry's frontmatter against `../orchestrator/shared/schemas/feature-frontmatter.schema.json` before writing — schema-validation failure here is a hard error.

---

### Step 13: Print summary + commit instructions

Print a section-count summary and a copy-paste two-repo commit/push line:

```
Manifest written: api/docs/handoffs/<correlation-id>.md
Registry entry:   ../orchestrator/features/<correlation-id>.md
Bundles:          output/openapi-bundled.yaml, output/asyncapi-bundled.yaml

Summary:
  §2 Scenarios:      {N} ({n_new} new, {n_changed} changed, {n_ref} referenced-only)
  §3 Operations:     {N} ({n_auto} auto-generated, {n_hand} hand-crafted)
  §4 Async surface:  {N} ({n_w} workers, {n_sj} scheduled-jobs, {n_em} emission-only)
  §5 Entities:       {N} (or "no changes")
  §6 Cross-domain:   {domains}
  §7 Open issues:    {N} (or "none")
  §8 Validation:     PASS / PASS / regenerated at <sha>
  §9 Tier-B hint:    {groups} (advisory)
  §10 References:    {N} prompts
  §11 Design notes:  {N} lines (or "none")

To commit and push (two repos, in order):

  # 1. <project>-specs
  git add api/docs/handoffs/<correlation-id>.md \
          output/openapi-bundled.yaml \
          output/asyncapi-bundled.yaml
  # also add any of your already-staged spec changes if needed
  git commit -m "feat(<domain>): handoff manifest for <correlation-id>"
  git push

  # 2. orchestrator
  cd ../orchestrator
  git add features/<correlation-id>.md
  git commit -m "feat: register <correlation-id>"
  git push

If the orchestrator push is rejected (race with another producer), re-run:
  /prepare-handoff   (no arg — will mint a fresh ordinal)
```

The command does NOT run `git add`, `git commit`, or `git push` itself. Cross-repo writes are exactly the kind of shared-state action where a confirmation gate earns its keep — the copy-paste line preserves user control.

---

## Failure modes

Faithful reporting per `scenario-validator.md` discipline. Never suppress, downgrade, or reinterpret:

- Validation FAIL → STOP at Step 3.
- HC violation in composer → STOP at Step 11.
- Cross-domain spec inconsistency (HC-7) → STOP at Step 7 + file `spec_level_blocker`.
- Registry-schema validation failure → STOP at Step 12.
- Orchestrator repo unreachable → STOP at Step 1.
- Both existing manifest and draft present → STOP at Step 10.

## Checklist

- [ ] Correlation ID resolved (supplied or autonomously minted)
- [ ] Scope confirmed by user (gate)
- [ ] All 7 validation scripts PASS (gate)
- [ ] Scenario docs regenerated as needed
- [ ] Bundles regenerated unconditionally
- [ ] Open-issue gate cleared
- [ ] Inventories built with HC-7 predicate evaluated
- [ ] Prompt index built and filtered
- [ ] Tier-B hint read live
- [ ] §11 source resolved (existing / draft / none)
- [ ] Composer agent invoked, manifest returned
- [ ] Manifest written, draft deleted (if any), registry entry written
- [ ] Summary + two-repo commit instructions printed
