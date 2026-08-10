---
name: ideation-shape
description: "Interactively shape a captured backlog idea into an intake-ready initiative candidate: fill its dossier, drive a four-point readiness checklist, and move it idea → shaping → ready, recording any decision to bundle several ideas into one initiative. Use between ideation-capture and initiative-intake; evidence-led (infer from files first, ask last), ends at `ready`, and does not mint the INIT-."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Specs agent — ideation-shape skill (v0.1)

> **Model B (docs/naming-convention.md).** Shapes a captured backlog idea into an
> intake-ready candidate **initiative**. Sits between `ideation-capture` (records
> the idea) and `initiative-intake` (mints the `INIT-`). Interactive and
> evidence-led; moves an item `idea → shaping → ready`.

When this file and the specs agent role config disagree, **the role config
wins and this file is wrong.** Raise an escalation rather than reconciling silently.

## Purpose

Take one backlog idea and, through a focused interactive session, fill its
**dossier** (`docs/product/backlog/IDEA-NNN-<slug>.md`) — Considerations,
References, Constraints, Affected domains/repos, Sizing/risk, Mint plan — and drive
its readiness checklist. When all four readiness boxes are checked and no blocking
question remains, flip the dossier (and its index row) to `ready` — the signal that
it is eligible for `initiative-intake`. This skill does **not** mint the INIT; it
makes the idea ready to be minted. It is also where the decision to **bundle**
several ideas into one initiative is made and recorded.

## Scope

In scope:

- Reading the idea's dossier + the product context that informs it (`docs/product/`,
  `docs/business/` domain narratives, existing specs under `/product/`, the
  orchestrator `roadmap.md` + registries for overlap/ordering).
- Asking the human a small, batched set of shaping questions — only those no
  readable file answers.
- Writing the dossier sections, the `Mint plan`, the `Decision log`, and the
  readiness checklist.
- **Bundling**: when several ideas are one initiative, designating a lead dossier,
  setting `bundles:` on it and `bundled_into:` on the followers, and keeping every
  bundled row's state in step.
- Flipping dossier `state:` (frontmatter) and the matching index row together:
  `shaping`, then `ready`.

Out of scope:

- **Minting the INIT / starting `drafting`** — that is `initiative-intake`, run by
  the human once the idea (or bundle) is `ready`. This skill ends at `ready`.
- **Drafting actual specs** (OpenAPI/AsyncAPI/Arazzo under `/product/`) — that is
  spec-drafting at `drafting`, after intake. Scope here stays coarse.
- **Decomposition into features** — the PM's job after `planning`.

## Inputs

1. The target `IDEA-NNN` (or several, when shaping a candidate bundle) — from the trigger.
2. `docs/product/backlog/IDEA-NNN-<slug>.md` — the dossier(s) to work.
3. `docs/product/INITIATIVE_BACKLOG.md` — the index row(s) to keep in step.
4. Product grounding: `docs/product/`, `docs/business/`, existing `/product/` specs,
   and the orchestrator `roadmap.md` + `features/INIT-*.md` (overlap / supersede /
   unblock relationships with already-minted work).

## Procedure

### 1. Read and ground

State intent: "I will shape `IDEA-NNN` toward intake-ready." Read the dossier and the
product context. **Infer first, ask last** — a question a readable file answers is a
skill bug. Pre-fill the `References & sources to use` section with the concrete
files you found (business narratives, overlapping specs) so they aren't re-hunted at
`drafting`.

### 2. Probe overlap + bundling

Check the roadmap + registries: does this idea overlap, supersede, or depend on an
already-minted initiative? If it duplicates one, recommend `parked` or `dropped`
rather than shaping a redundant item.

> **When the orchestrator is not reachable, degrade — do not stop.** The roadmap
> and `features/INIT-*.md` reads are read-only enrichment, and this skill's own
> subject (`docs/product/backlog/`) lives in this repo. If they cannot be
> resolved, shape the idea from the backlog alone and say so in the report:
> *"Overlap against minted work was not checked — orchestrator registries
> unreachable."* An unchecked overlap is a caveat on the recommendation; a hard
> stop here would make the skill unusable in any project without a sibling
> orchestrator checkout, which is the coupling authoring #26 is removing.

Then check the **backlog itself**: do other
open ideas belong with this one as a single initiative? If so, surface the bundle
candidate — bundling is proposed here, confirmed by the human, never auto-applied.

### 3. Ask — one batched round

Present a single batched set of shaping questions, only for gaps the files left.
Aim at the four readiness criteria specifically:
- Problem — a real pain/opportunity, not a pre-baked solution?
- Value — the one-sentence user-observable outcome.
- Scope + boundary — coarse in/out; bounded enough to mint.
- Target repos — which components it spans.
Plus any **[blocking]** unknown that would stop intake, and (if raised in step 2)
the bundling decision. Non-blocking unknowns are recorded as `[carry]` and ride into
`drafting`.

### 4. Write the dossier + readiness

Fill the dossier sections from the answers (trace every clause to a file or an
answer; invent nothing). Complete the `Mint plan` so intake's handoff is mechanical
(title, `involved_repos`, `autonomy_default`, scope sentence, bundled-ideas list).
Append a dated `Decision log` line for any consequential call. Check each readiness
box now satisfied. Flip dossier `state:` to `shaping` on first substantive edit and
mirror it to the index row.

### 5. Apply bundling (if decided)

On a confirmed bundle: pick the lead dossier, set its `bundles: [IDEA-…]`, set each
follower's `bundled_into: <lead>`, and record the rationale in the lead's
`Related ideas & bundling` section + `Decision log`. Followers shape toward the same
`ready` as the lead; at mint they all flip to `minted` on the lead's INIT.

### 6. Flip to ready (or stop at shaping)

If all four readiness boxes are checked and no `[blocking]` unknown remains, set the
dossier + row to `ready` and tell the human it is eligible for `/initiative-intake`
(for a bundle, intake runs once on the lead and consumes every bundled dossier). If
a box can't be checked, leave it `shaping` and name exactly what's missing.

### 7. Result

Emit the RESULT block. `status: complete` = dossier written and state advanced
(`shaping` or `ready`) honestly per the checklist, with the index row in step. Never
check a box the evidence doesn't support to force a `ready`.

## Version

**v0.1.** One batched question round; four readiness criteria; lead/follower
bundling. Expected to grow as real ideas are shaped — which criterion most often
blocks `ready`, how often ideas genuinely bundle, and how much overlap-probing earns
its cost.
