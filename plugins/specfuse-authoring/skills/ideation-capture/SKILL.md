---
name: ideation-capture
description: "Capture a candidate initiative into the ideation backlog -- one index row plus a stub dossier under docs/product/backlog/, both at state `idea`. The frictionless pre-intake entry point that records an idea so it is never lost. Use before any INIT- is minted; deliberately low-ceremony with no interrogation, no readiness assessment, and no orchestrator-repo write."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Specs agent — ideation-capture skill (v0.1)

> **Model B (docs/naming-convention.md).** Captures a candidate **initiative** into
> the ideation backlog — the pre-intake fuzzy front end. This skill is upstream of
> `initiative-intake`: it records an idea so it is never lost; intake later mints
> the `INIT-` id when the idea is `ready`. Frictionless by design.

When this file and the specs agent role config disagree, **the role config
wins and this file is wrong.** Raise an escalation rather than reconciling silently.

## Purpose

Capture a candidate initiative in two writes: one row at state `idea` in the
backlog index (`docs/product/INITIATIVE_BACKLOG.md`) and a **stub dossier** at
`docs/product/backlog/IDEA-NNN-<slug>.md`. The index row is the scannable pointer;
the dossier is the shaping workspace `ideation-shape` fills later. The whole point
is low ceremony — capture must be faster than the urge to skip it. This skill does
not interrogate the idea.

## Scope

In scope:

- Creating the index file from
  `initiative-backlog.template.md`
  and the `docs/product/backlog/` folder if they do not yet exist.
- Allocating the next sequential `IDEA-NNN` and a kebab `<slug>` from the title.
- Appending one `idea`-state index row (title, state, repos-if-known, dossier link).
- Creating the stub dossier from
  `initiative-idea-dossier.template.md`,
  filling only what the human volunteered; the rest stays template placeholders.

Out of scope:

- **Shaping, interrogating, or assessing readiness** — the `ideation-shape` skill.
- **Minting an `INIT-` id or creating a registry** — the `initiative-intake` skill;
  capture never touches the orchestrator repo.
- **Triage / reprioritization** — the `backlog-groom` skill.

## Inputs

1. A title (required) and any free-form blurb the human offers.
2. `docs/product/INITIATIVE_BACKLOG.md` — to read the max `IDEA-NNN` and append.
3. `docs/product/backlog/` — the dossier folder (created if absent).

## Outputs

- One new index row + one stub dossier, both state `idea`. No orchestrator write,
  no event.

## Procedure

### 1. Ensure the index + folder exist

If `INITIATIVE_BACKLOG.md` is absent, create it from the index template (header,
table, Notes; no example rows). If `docs/product/backlog/` is absent, create it.
State intent: "Capturing a new idea into the backlog."

### 2. Allocate ID + slug

Scan existing `IDEA-NNN` rows, take `max + 1` (or `001`), zero-pad to three digits.
Derive a kebab `<slug>` from the title. IDs are transient and sequential; never
reuse a retired ID.

### 3. Write the index row

Add the row: `State: idea`, `INIT: —`, repos if the human named them else blank,
`Dossier` linking `backlog/IDEA-NNN-<slug>.md`. Keep the `## IDEA-NNN` index
section to a one-line summary + dossier link (the rich content goes in the
dossier, not here).

### 4. Write the stub dossier

Create `docs/product/backlog/IDEA-NNN-<slug>.md` from the dossier template. Set
frontmatter `idea_id`, `slug`, `state: idea`. Fill any section the human
volunteered; leave the rest as placeholders. Do **not** ask follow-up questions —
an empty-but-captured idea is the success state.

### 5. Result

Emit the RESULT block per the shared result contract. `status: complete` = index
row + stub dossier written. Point the human at `/ideation-shape IDEA-NNN` for when
they want to flesh it out.

## Version

**v0.1.** Deliberately minimal — one row, no interrogation. The friction budget for
capture is near zero; resist adding prompts here.
