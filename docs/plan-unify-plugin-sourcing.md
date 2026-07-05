# Work plan — unify plugin sourcing (issue specfuse/specfuse#23)

**Status:** Ready to execute, gate-ordered.
**Goal:** one uniform, drift-proof model for how the three plugins reach the
`specfuse/specfuse` marketplace. Editing a plugin is always done in its origin
repo; the marketplace copies are generated, versioned, and mechanically guarded
against divergence.

## Settled design decisions

1. **Committed generated copies + publish script.** The marketplace keeps real
   `plugins/<name>/` copies (so `/plugin marketplace add` works), produced by a
   publish script, never hand-edited.
2. **PyPI-release-triggered, marketplace-executed, idempotent.** A source repo's
   PyPI release fires the marketplace publish; the marketplace-owned script
   regenerates that plugin and opens a PR **only if the plugin content changed**.
   Trigger is source-side; publish logic lives once, in the marketplace.
3. **Plugin version = PyPI package version.** The publish stamps
   `plugin.json.version` to the released package version (`plugin@X == package@X
   == tag vX`). Fixes today's stale `0.1.0`s.
4. **Uniform `plugins/<name>/` layout in every source repo.** Each source repo
   holds its plugin as a complete dir (`plugin.json` + `skills/` + `agents/` +
   README). The **loop vendors** `plugins/specfuse/skills/` → `.specfuse/skills/`
   for its dogfood, via the sync mechanism it already uses for rules — operation
   unchanged, single canonical source.
5. **Each repo authors its `plugin.json`;** publish only stamps the version.
6. **Anti-drift = CI regenerate-and-diff (load-bearing) + `plugins/` lock.** The
   marketplace CI regenerates each plugin from source **at its published version
   tag** and fails on any diff, so nothing enters `plugins/` except a faithful
   publish — not a hand-edit, a bad merge, or an agent. Branch protection on
   `plugins/` is cheap defense-in-depth.

Execution-level choices (folded in, not blocking): the source→repo mapping
extends `marketplace.json` (add `source_repo` per entry) rather than a new file;
README is taken from the source plugin dir, not templated.

The gates are dependency-ordered. Prove the mechanism on the plugin that already
fits (orchestrator), then onboard the two that need restructuring (loop, then
authoring).

---

## Gate 1 — Publish mechanism, proven on the orchestrator plugin

The orchestrator already ships `plugins/specfuse-orchestrator/` in-repo — the
cleanest first onboarding.

1. Extend `marketplace.json`: add `source_repo` (e.g. `specfuse/orchestrator`) to
   each plugin entry alongside its existing `source` path.
2. Write the **publish script** (in the marketplace repo): given a plugin name, a
   source checkout, and a version, it copies `<source>/plugins/<name>/` →
   `plugins/<name>/`, stamps `plugin.json.version` = version, and is idempotent
   (no change → no write). No transformation beyond the version stamp.
3. Run it for `specfuse-orchestrator` from the orchestrator repo at its current
   PyPI version → **backfills the stale marketplace mirror** (the missing `pm`
   skill etc.) and sets the version off `0.1.0`.
4. **Verify:** the regenerated copy is a complete, valid plugin; `plugin.json`
   version matches the orchestrator package; re-running the script is a no-op
   (idempotent); `/plugin marketplace add` still resolves it.

## Gate 2 — Drift-guard CI + lock (marketplace repo)

1. Add a CI job: on any push/PR touching `plugins/`, for each plugin, fetch its
   `source_repo` at the tag matching its `plugin.json.version`, regenerate, and
   `diff` against the committed copy. **Fail on mismatch.**
2. Add branch protection / CODEOWNERS so `plugins/` is writable only via the
   publish flow.
3. **Verify:** a deliberate hand-edit to a committed plugin file fails CI; a
   faithful publish passes; the guard pins to `source@version`, not drifting HEAD.

## Gate 3 — Wire the release trigger (orchestrator first)

1. In the orchestrator repo's PyPI-release workflow, after the package publishes,
   fire a `repository_dispatch` (or equivalent) at the marketplace with
   `{plugin: specfuse-orchestrator, version: vX}`.
2. Marketplace CI runs the publish script on that event and opens a PR if the
   plugin changed.
3. **Verify:** a dry-run/test release triggers a marketplace publish PR; a
   package-only release (no plugin change) opens no PR (idempotent).

## Gate 4 — Loop restructure + onboard

1. Create `plugins/specfuse/` in the **loop repo** as the canonical plugin:
   `plugin.json` + README + `skills/` (+ agents if any), authored here.
2. Repoint the loop's sync so `.specfuse/skills/` is **vendored from**
   `plugins/specfuse/skills/` (reuse the `sync-scaffold` machinery that already
   vendors rules). The loop's runtime behavior is unchanged — skills still resolve
   at `.specfuse/skills/`.
3. Add `source_repo: specfuse/loop` to `marketplace.json`; publish; wire the
   loop's PyPI-release trigger (Gate 3 pattern).
4. **Verify:** the loop's full gate set stays green (dogfood skills still found +
   used identically); `.specfuse/skills/` matches `plugins/specfuse/skills/`
   byte-for-byte; the marketplace `specfuse` plugin regenerates cleanly.

## Gate 5 — Authoring migration + onboard

1. **Move** the authoring plugin content out of the marketplace and into the
   **authoring repo** at `plugins/specfuse-authoring/` (the 20 spec-craft skills +
   5 agents + the specs agent + 7 skills landed in Gate 4a + `plugin.json` +
   README). This is the heaviest gate — the authoring repo currently has no
   plugin content.
2. Add `source_repo: specfuse/authoring` to `marketplace.json`; publish; wire the
   authoring PyPI-release trigger.
3. **Verify:** the regenerated marketplace copy equals the migrated source; all
   authoring skills (incl. specs) resolve; nothing was lost in the move.

## Gate 6 — Cutover + cleanup

1. All three plugins are now publish-managed and drift-guarded; every
   `plugins/**` file in the marketplace is script-output.
2. Remove any obsolete manual-copy artifacts / notes; document the model in the
   marketplace README (edit-in-origin-repo; releases publish; never hand-edit).
3. **Verify:** the drift-guard passes for all three at their published versions;
   `marketplace.json` lists all three with `source_repo`; a full re-publish of
   each is a no-op.

---

## One-look summary

| Gate | Repo | Outcome |
| --- | --- | --- |
| 1 | marketplace | publish script + `marketplace.json.source_repo`; orchestrator mirror backfilled + versioned |
| 2 | marketplace | regenerate-and-diff CI guard + `plugins/` lock |
| 3 | orchestrator | PyPI release fires the marketplace publish |
| 4 | loop | canonical `plugins/specfuse/`; `.specfuse/skills/` vendored from it; onboarded |
| 5 | authoring | plugin content migrated into the repo; onboarded (heaviest) |
| 6 | all | cutover; everything generated + guarded; docs |

## Notes / risks

- **Loop restructure (Gate 4)** and **authoring migration (Gate 5)** are the real
  work; Gates 1–3 stand up the mechanism on the plugin that already fits.
- The publish script is the single home of publish logic (Decision 2); resist
  per-repo publish scripts — that recreates the drift #23 removes.
- Ties to related follow-ups: specfuse/specfuse#24 (Model-B reframe in the specs
  skills — an authoring-repo edit once Gate 5 makes that repo the source) and the
  orchestrator `methodology` distributor (Track C2) is independent of this plan.
