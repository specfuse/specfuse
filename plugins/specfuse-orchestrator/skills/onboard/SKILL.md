---
name: onboard
description: "Bring a project under orchestrator coordination -- inventory existing repos (brownfield), scaffold a fresh project (greenfield), or draft a phased integration plan. Use when a human wants to start coordinating a new set of repos, or refresh an existing project's inventory/plan."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Converted from the orchestrator repo's `/onboard` command
(`.claude/commands/onboard.md`); preserves that command's routing behavior for
distribution as a plugin skill.

The user wants to bring a project under orchestrator coordination -- either
onboarding existing repos (brownfield) or scaffolding a fresh project
(greenfield).

## Process

1. Switch into the **onboarding agent** role: read this plugin's bundled
   `agents/onboarding.md` (name, responsibilities, interaction model, output
   surfaces, verification, escalation, anti-patterns) before acting. It is the
   flattened, distributable form of the orchestrator repo's
   `agents/onboarding/CLAUDE.md`.

2. Determine which path the situation calls for. Ask **one** disambiguating
   question if needed; don't interrogate.

   - **Greenfield** (new project, no repos exist yet): produce
     `project/bootstrap-checklist.md` covering environment prereqs, repo
     creation order, per-repo conventions, and first-feature scoping. Also
     create a stub `project/manifest.md`.
   - **Brownfield, no inventory yet** (`project/repos/` is empty or absent):
     walk each involved repo, ask targeted questions (purpose,
     language/framework, build/test commands, spec coverage, in-flight work,
     orchestrator-readiness gaps), and produce `project/repos/<repo-slug>.md`
     per repo plus the `project/manifest.md` repo list. No "TBD" placeholders
     in the readiness checklist.
   - **Brownfield, inventory exists, no integration plan**: draft
     `project/integration-plan.md` with a phased rollout (pilot -> expand ->
     import in-flight -> steady state), a risk register naming specific risks
     with mitigations, and observable success criteria.
   - **Brownfield, inventory and plan exist**: re-running probably means
     refreshing one of them. Ask the user which.

3. Follow the onboarding agent's verification discipline: re-read every
   produced artifact after writing it (never assume written from tool-call
   success alone), and keep the manifest, per-repo files, and integration plan
   referencing the same set of repos with consistent identifiers.

4. If `project/` is currently empty (just the README), this is the first
   onboarding session for the project -- say so and proceed accordingly. If
   artifacts already exist, read them first before deciding what to update vs.
   create fresh.

## Escalate

Per the onboarding agent's escalation rules: insufficient information about a
repo (or an undiscoverable repo) to produce a useful inventory entry; a project
structure fundamentally incompatible with the orchestrator's expectations that
blocks drafting an integration plan without an architectural decision; three
iterations of the inventory or planning conversation without progress, or a
wall-clock/token budget exceeded. This role has no autonomy gate -- onboarding
work is always human-driven.

## Known coupling

The orchestrator repo's `/onboard` command also routes to three detailed
per-artifact procedures --
`agents/onboarding/skills/bootstrap-greenfield/SKILL.md`,
`agents/onboarding/skills/repo-inventory/SKILL.md`, and
`agents/onboarding/skills/integration-plan/SKILL.md` -- that are not yet
bundled into this plugin (only the top-level `agents/onboarding.md` role
definition was bundled, in a prior work unit). Until those three procedures are
ported as bundled plugin skills, this skill's step 2 substitutes the summarized
artifact shape above, driven by the onboarding agent's role definition and
judgment. Porting the three detailed procedures is follow-up work, tracked
separately -- it is not required for this skill to route and produce correct
artifacts today.
