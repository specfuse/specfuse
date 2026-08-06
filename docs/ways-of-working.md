<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Ways of working

How a team actually operates under the gate cycle: which moments demand
attention, who owns each one, and what goes wrong when a routine is skipped.

This file owns two things and nothing else — the **cadence model** and the
**failure modes**. Every command it names is documented elsewhere; it links
rather than restates.

- Commands, by lifecycle phase: [loop `docs/skills.md`](https://github.com/specfuse/loop/blob/main/docs/skills.md)
- A narrated end-to-end run: [loop `docs/getting-started.md`](https://github.com/specfuse/loop/blob/main/docs/getting-started.md)
- The contracts underneath: [`methodology/methodology.md`](../methodology/methodology.md)
- Orientation, if you are new: [`methodology/overview.md`](../methodology/overview.md)

---

## 1. The four cadences

Specfuse does not run on standups and sprints. Attention concentrates at four
moments, and between them the loop runs without you. Most of learning the method
is learning to recognize which moment you are in.

| Cadence | Roughly | Owner | The question being answered |
| --- | --- | --- | --- |
| **Continuous** | minutes | the driver | Does this unit pass its verification? |
| **At each gate** | hours – days | reviewer / tech lead | Is the next batch of work framed correctly? |
| **Per feature** | weekly-ish | planner + product | What should we build next, and what does done mean? |
| **Periodic** | monthly-ish | repo owner | What have we learned, and is the backlog still honest? |

Note the asymmetry: the first row consumes nearly all wall-clock time and nearly
none of your attention. The second row is where the method earns its keep.

## 2. Continuous — the unattended stretch

The driver walks the gate's ready work units, dispatches each as a fresh session,
re-runs verification itself as the exit oracle, and commits one squashed commit
per unit. Failures retry with the failure evidence attached, then escalate.

You do not supervise this. You start it (`specfuse-loop`, after
`specfuse-loop --dry-run`) and come back at the gate.

**One driver per working tree.** The driver holds an exclusive lock; to run two
features at once use separate `git worktree` checkouts. `--dry-run` is exempt.

When it stops unexpectedly, start with `/specfuse:gate-status` — it is read-only,
reads the WU statuses, `events.jsonl` and per-attempt notes, and synthesizes a
diagnosis. The full symptom→action table is in the loop's
[getting-started](https://github.com/specfuse/loop/blob/main/docs/getting-started.md#operating-a-running-loop).

## 3. At each gate — the review

The one meeting-shaped thing in the method, except it is a document rather than a
meeting, and it is about the future rather than the past.

Either the gate auto-closes (clean and on-plan) or the driver halts with
`awaiting_review`. Either way `plan-next` has drafted the next gate, so the human
step still fires.

How to run it:

1. **Read `GATE-NN-REVIEW.md` first.** It is written weighted toward where the
   planner was *least* certain: decisions and rationale, an explicit "if you
   check only three things" list, a roadmap-anchor check, and open questions each
   mapped to the draft work unit it affects.
2. **Check the roadmap anchor before the work units.** A well-formed gate pointed
   at the wrong goal is the expensive failure; a badly-scoped unit is the cheap
   one.
3. **Look for revisions to gates you have not reached.** `plan-next` may split,
   merge or re-scope them and must say so loudly. It never touches a gate already
   passed.
4. **Then `/specfuse:arm-gate`** — accept / revise / reject each drafted unit.

Arming is deliberately not automated, except under `auto` mode and only when
every safety condition holds at once ([`methodology.md` §9](../methodology/methodology.md)).
Even then it never auto-merges.

## 4. Per feature — planning and wrapping

This is where the human investment pays off, and where to expect to spend real
time. Every loop skill is **propose-and-confirm**: it reads state, shows what it
intends to do, and writes only on explicit go-ahead.

- **Once per repo, at adoption** — make the verification set match real CI, and
  wire monitoring if there are deployed components.
- **Start of a feature** — pick, then draft. Keep ceremony proportional: four or
  fewer planned substantive work units means one gate with one terminal close.
  Lint the folder before dispatching; it is far cheaper than a failed dispatch.
- **When a feature stalls on something external** — park it properly. `blocked`
  names and links its blocker; `deferred` is a voluntary park with no named
  blocker. Both stay resumable, unlike `abandoned`.
- **End of a feature** — wrap it: push, PR, watch CI, point at the next pick.

On the authoring plane the equivalent per-initiative rhythm is capture → shape →
mint → draft → validate → hand off, all run conversationally from the
product-specs repo. See the
[authoring/execution boundary decision](https://github.com/specfuse/orchestrator/blob/main/docs/decision-authoring-execution-boundary.md).

## 5. Periodic — the routines teams skip

Low-frequency, high-leverage. Skipping these is how the method degrades quietly.

**The learnings loop has two halves, and teams usually run only the first.**
`LEARNINGS.md` is loaded *whole* into every planning session, so it must stay
bounded — an unbounded learnings file silently degrades every future plan.
`/specfuse:learnings-suggest` mines recurring failures into candidate entries;
`/specfuse:learnings-curate` merges duplicates, retires superseded entries, and
promotes methodology-wide rules into `.specfuse/rules/`. Run both.

Alongside them: archive finished features out of the active roadmap, groom the
idea backlog on the authoring side, and keep the scaffold current.

## 6. Failure modes

| Failure mode | What it looks like | The routine that prevents it |
| --- | --- | --- |
| **Hollow pass** | A unit reports done, verification is green, nothing meaningful was built | Acceptance criteria that are machine-checkable *and* substantive. Read `authoring-work-units` while drafting; lint before dispatch. |
| **Learnings bloat** | Planning sessions get slower and less focused as the file grows | Run the curation half, not just the additive half. Only rules that would change how a *future* work unit is written belong there. |
| **Rubber-stamped gates** | Arming without reading the review summary because the last five gates were fine | Start at the roadmap-anchor check and the "check only three things" list. Arming in under a minute means the checkpoint has stopped existing. |
| **Verification drift** | Units pass locally, PRs fail at the merge gate | Treat `verification.yml` and branch protection as one artifact; re-derive after any CI change. |
| **Bug-as-feature** | A one-line fix acquires a plan, three gates and a retrospective | `/specfuse:fix-bug` — one bug, one branch, one PR, test-first. It refuses and proposes promotion if the work is genuinely large. |
| **Two drivers, one checkout** | Confusing state, lock errors | A separate `git worktree` per concurrent feature. The lock exists to stop corruption, not to be worked around. |
| **Stalled "active" features** | Several features nominally active, none progressing | Park with a named blocker, or abandon. `blocked` and `deferred` exist so parked work stays honest and resumable. |

## 7. Work that does not go through the cycle

Not everything is a feature, and forcing it through the gate cycle is a common
early mistake. Bugs get their own path — one bug, one branch, one PR, test-first.
Monitoring findings get diagnosed before anyone decides whether to fix them. The
judgement call is size and risk, not category.
