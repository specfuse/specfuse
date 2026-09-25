---
name: ideation-publish
description: "Publish a shaped backlog idea to GitHub as an issue, so it can be assigned to people and planned on a GitHub Project while its specs are authored. Explicit and opt-in per idea -- offered at the `ready` transition, never performed by it. Mirrors state silently afterwards; confirms anything that adds new public prose."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Specs agent — ideation-publish skill (v0.1)

> Gives a shaped idea a GitHub face: an issue people can be assigned to and a
> board position a team can plan against, while the dossier stays the decision
> record. Pairs with `ideation-capture --from-issue`, which is the same seam in
> the other direction.

## Purpose

An idea reaches `ready` and a team starts working it together. Markdown in a repo is a poor collaboration surface for that: you cannot assign it, and it is not on anyone's board.

This skill opens an issue carrying the idea's **summary and a link to its dossier** — never the dossier body — records the issue URL on the dossier, and optionally adds it to a GitHub Project.

## Why this is explicit and opt-in

Every skill in this cluster proposes and lets a human dispose: `triage-issues` *"never acts on the route it names"*, `ideation-groom` is *"report-first, read-mostly"*, `adopt-feature` *"accepts the human's explicit choice"*. Publishing would be the first thing here that performs an **outward-facing write without being asked**.

It is also irreversible in the way that matters. An issue can be deleted; it cannot be un-read. Ideation is the stage where the most commercially sensitive thinking lives — *"we should build X before competitor Y"* — and a repo that feels internal is still visible to everyone in the company.

So `ideation-shape` **offers** this at the `ready` transition and never fires it. The state machine drives the ask; a human drives the act.

## Scope

In scope:

- Opening one issue for one `ready`-or-later idea, from its dossier summary.
- Recording the issue URL in the dossier's `issue:` field.
- Adding the issue to `github.ideas.project` when one is configured.
- Mirroring the idea's state onto the issue afterwards — see below.

Out of scope:

- **Publishing the dossier's contents.** The dossier is the thinking workspace and the decision record. The issue gets a summary and a link.
- **Publishing anything below `ready`.** GitHub assignment reads as *"this person will do this"*, and an `idea`-state row promises nothing of the kind.
- **Bulk publishing.** One idea, one deliberate act. A loop over the backlog is how a disclosure decision stops being a decision.
- **Deciding state.** This skill mirrors state; it never changes it.

## Configuration

```sh
python3 scripts/specfuse/authoring-config.py github.ideas.repo --required
python3 scripts/specfuse/authoring-config.py github.ideas.label
python3 scripts/specfuse/authoring-config.py github.ideas.project
```

`github.ideas.repo` unset means publishing is **off**; the reader says so naming the key. Do not fall back to the current repo — the backlog is project-level and the current repo is a guess.

## Procedure

### Step 1 — Confirm the idea is publishable

State is `ready` or later, and the dossier has a summary worth reading. If `issue:` is already set, this is a **re-publish**: do not open a second issue. Update the existing one (§"Mirroring") and say which.

### Step 2 — Show what will be posted, then ask

Print the exact title and body. Then ask once:

> Publish IDEA-NNN to `<owner/repo>` as a public issue? (y/n)

On `n`, stop and change nothing. This is the one confirmation in the flow and it is worth its cost — everything after it is silent, which is only safe because this gate exists.

### Step 3 — Open the issue

Title from the idea. Body: the one-line summary, the dossier link, and the `IDEA-NNN`. Apply `github.ideas.label` and a state label. Add to `github.ideas.project` when configured.

### Step 4 — Record the pointer

Write the issue URL to the dossier's `issue:` field. **`IDEA-NNN` stays canonical** — the issue URL is a pointer. Ideas predate and can outlive any one repo, and an idea can be re-published if an issue is lost; the reverse is not true.

## After publish: split by concern, not by direction

Once a team is collaborating on the issue they will not go back to editing a markdown dossier. Pretending otherwise produces a dead file. So publishing is a **handover of the collaboration surface**:

- **The issue owns** discussion, assignment, planning state, board position — everything about *who and when*.
- **The dossier owns** the decision record: context, rationale, the readiness checklist, what was decided and why — everything about *what and why*.

The file remains authoritative for **state**. Two mirrors of one truth is fine; two partly-authoritative mirrors is the failure mode.

## Mirroring: status is silent, new prose is confirmed

The disclosure decision was made once, at Step 2. Afterwards, keeping a public thing accurate is not a decision anyone needs to weigh — and a stale public board is worse than no board, because people act on it.

| Transition on a published idea | Behaviour |
|---|---|
| any state change | update the status label / Project field **silently** |
| `→ minted` | close the issue, link the `INIT-` — silent; it is a fact |
| `→ dropped` | **show before posting** — the reason is new public prose |
| `→ delivered` | **show before posting**, same reason |

**The rule: status is mirrored; new prose is confirmed.** A label change reflects something already decided. A dropped-reason is a new sentence appearing on a company-visible issue with someone's name on it.

**Confirmations are a budget.** If every transition prompted, people would answer reflexively within a week — and then Step 2, the one that actually matters, would be answered reflexively too.

`ideation-groom` reconciles what the mirror missed: an offline transition, an API failure, someone editing the board by hand. That backstop is what makes a non-syncing design viable — periodic reconciliation instead of live sync, which is the pattern this cluster already uses.

## Anti-patterns

- **Publishing on the `ready` transition.** The transition offers; a human acts. Automating it trades a forgotten publish for an unwanted disclosure, and only one of those can be taken back.
- **Publishing the dossier body.** It is a thinking workspace with half-formed options in it. Summary and link.
- **Treating the board as authoritative.** State lives in the file. A Project column that overrides it makes the dossier a stale copy of itself.
- **Asking on every mirror update.** See the confirmation budget above.
- **Falling back to the current repo when `github.ideas.repo` is unset.** Unset means off. Guessing where to publish something outward-facing is the worst possible default.
