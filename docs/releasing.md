# Releasing

Three things ship on their own schedules: the **pip packages**, the **Claude
plugins**, and the **umbrella** that bundles the packages. They are independent,
and most of the time only one of them needs to move.

If you read nothing else: **a component release reaches users on its own.** The
umbrella does not need to re-release for a new `specfuse-loop` /
`specfuse-authoring` / `specfuse-orchestrator` to arrive.

## The map

| Distribution | Repo | Ships | Console commands |
|---|---|---|---|
| `specfuse` (umbrella) | `specfuse/specfuse` | the CLI + the whole suite as hard deps | `specfuse` (+ 11 deprecated aliases) |
| `specfuse-loop` | `specfuse/loop` | the gate-cycle driver, scaffold, monitoring | `specfuse run`, `lint`, `monitor`, `monitor-lint`, `stats` |
| `specfuse-authoring` | `specfuse/authoring` | the spec-authoring kit | `specfuse authoring` |
| `specfuse-orchestrator` | `specfuse/orchestrator` | multi-repo coordination | `specfuse pm`, `poller`, `runner`, `validate-event`, `validate-frontmatter` |

| Plugin | Source repo | Reaches users via |
|---|---|---|
| `specfuse` | `specfuse/loop` `plugins/specfuse/` | this marketplace |
| `specfuse-authoring` | `specfuse/authoring` `plugins/specfuse-authoring/` | this marketplace |
| `specfuse-orchestrator` | `specfuse/orchestrator` `plugins/specfuse-orchestrator/` | this marketplace |

## How a component release reaches users

Since 0.10.0 the components are **hard dependencies** of the umbrella, not
extras. `pipx upgrade specfuse` / `uv tool upgrade specfuse` re-resolves the
dependency set, so a newer component is pulled in even though the umbrella's own
version has not changed:

```
component publishes 0.5.9  ->  next `specfuse upgrade` pulls it. Done.
```

Verified against the live 0.10.0, umbrella untouched:

```
uv:    downgrade authoring to 0.5.6, `uv tool upgrade specfuse`
       -> Modified specfuse environment
          - specfuse-authoring==0.5.6
          + specfuse-authoring==0.5.9

pipx:  same, `pipx upgrade specfuse`
       -> "specfuse is already at latest version 0.10.0"   (umbrella unchanged)
          authoring: 0.5.6 -> 0.5.9                        (component moved anyway)
```

### One path does not work: plain `pip install -U specfuse`

`pipx`, `uv` and `specfuse upgrade` all carry components forward. A plain pip
upgrade does not, and it is the command people reach for:

```
pip 26.1.2, umbrella already at its newest version, authoring 0.5.6 installed,
0.6.0 on the index:

  pip install --upgrade specfuse                       -> authoring stays 0.5.6
  pip install --upgrade --upgrade-strategy eager ...   -> authoring 0.5.6 -> 0.6.0
```

It exits 0 and says nothing. `--upgrade-strategy only-if-needed` (pip's default)
upgrades a dependency only when it no longer *satisfies* the requirement — and
since the floors are minimums, a satisfied floor is the normal state of every
component between umbrella releases.

`specfuse upgrade` handles this: in a plain venv it shells out to pip with
`--upgrade-strategy eager` (`_pip_install`), and in a pipx/uv environment it runs
that installer. **Tell users `specfuse upgrade`, not `pip install -U`.** The eager
flag in `cli.py` is load-bearing for venv installs; an earlier comment there
claimed it was not, measured on pip 25. It is.

This is why version floors in the umbrella's `pyproject.toml` are **minimums, not
levers**. Before 0.10.0 the components were extras, extras resolve exactly once at
install time, and the only way to move a user forward was for the umbrella to
raise the floor and re-release — hence the standing "bump this floor with every
component release" note that used to live in `pyproject.toml`. That is retired.
**Do not bump a floor just because a component shipped.**

## Do I need an umbrella release?

| What changed | Umbrella release? |
|---|---|
| Component bug fix, new feature, new flag on an existing command | **No** |
| Component plugin skills / agents | **No** (plugin track, below) |
| Component adds a **new command** | **Yes** — needs a `DELEGATED_COMMANDS` entry |
| Component **renames a module or `main()`** | **Yes** — plus a floor bump to that release |
| Umbrella's own code (`cli.py`, `doctor`, `init`/`upgrade`, `publish.py`) | **Yes** |
| Umbrella starts calling a newer component API | **Yes** — plus a floor bump |

The two "new command" / "rename" cases are the only ones needing coordination
between repos. Everything else is independent.

## Releasing a component

In the component's own repo:

1. Land the change on `main`.
2. Bump the version (the repo's `pyproject.toml`, and its `__version__` if it has
   one — the release workflow checks tag/version agreement).
3. Tag `vX.Y.Z` and push the tag.
4. The repo's release workflow builds, tests and publishes to PyPI via OIDC.
5. It then fires a `plugin-release` `repository_dispatch` at
   `specfuse/specfuse` — see the plugin track below.

Nothing to do here afterwards. Users get it on their next `specfuse upgrade`.

## Releasing the umbrella

In this repo:

1. Land the change on `main`.
2. Bump **both** `pyproject.toml` `version` and `specfuse/cli.py` `__version__`.
   `release.yml` fails the release if the tag and these two disagree.
3. Tag `vX.Y.Z` and push the tag.
4. `release.yml` builds the wheel + sdist, installs the wheel **with deps** into a
   clean venv, runs the test suite against it, verifies the installed command
   surface (all 12 console scripts present, every `DELEGATED_COMMANDS` target
   importable), then publishes to PyPI via OIDC trusted publishing.

Publish order only matters when a floor moved: publish the component first, so the
floor is resolvable when the umbrella's release runs. Otherwise release whenever.

> **uv's index cache can serve a stale version right after a release.** If a fresh
> `uv tool install specfuse` gives you the previous version, that is the cache, not
> the release — `uv tool install --refresh specfuse`. Worth knowing before you go
> looking for a publishing bug.

## The methodology substrate

The umbrella ships `methodology/` and provisions it into a repo. `methodology/`
stays canonical at the repo root — the orchestrator's ownership manifest names
that exact path — and the in-tree build backend (`_build/backend.py`) mirrors it
to `specfuse/_methodology/` at build time so a wheel can carry it. That mirror is
gitignored: generated, never committed, so there is no second copy to edit by
mistake.

`specfuse init` / `upgrade` lay it down in `.specfuse/methodology/`, which is
**this** upgrader's slot. `.specfuse/rules/` and `.specfuse/schemas/` belong to
`loop-init`; the manifest's invariant is one writer per install path, and the
separate slot is what keeps the two from fighting.

Why it ships from core rather than from a component: follow-up #3 of
`decision-authoring-execution-boundary.md` requires both planes to depend on core
and neither to import the other. Shipping the substrate from the loop would
relocate that dependency rather than remove it. Before this, `methodology/`
shipped nowhere at all — consumers copied it out of git, which is how core's own
event schema came to sit two releases behind the orchestrator's (#135).

Provisioning **overwrites**. These files are core's; a local edit is drift by
definition. Repo-local rules belong in the loop scaffold's `rules-local/`.

## The plugin track

Fully automatic, and independent of the pip packages:

```
component publishes to PyPI
   -> fires `plugin-release` repository_dispatch at specfuse/specfuse {plugin, version}
   -> plugin-publish.yml regenerates that plugin from the source repo at tag v<version>,
      stamps plugin.json.version, opens a PR IF the committed copy changed
   -> plugin-drift-guard (required check) re-derives it and verifies no drift
   -> a human merges
```

Rules that follow from this:

- **Never hand-edit `plugins/**` in this repo.** It is generated output. The
  drift-guard re-derives every `managed` plugin from its source at the pinned tag
  and fails on any diff, so a hand-edit, a bad merge, or an agent's "quick fix"
  cannot land. The only way in is a faithful publish.
- **Edit a plugin in its origin repo**, at `plugins/<name>/`.
- `plugin-publish.yml` also has a `workflow_dispatch` (`plugin`, `version`) for
  manual backfills — it runs the same code path.
- Plugin version == package version == tag, by construction.

See [`plan-unify-plugin-sourcing.md`](plan-unify-plugin-sourcing.md) for the full
design.

## The nightly guard

Because a component release now reaches users without passing through anything of
ours, `component-compat.yml` runs nightly (06:17 UTC, plus `workflow_dispatch`) and
asks two questions:

1. **Are users broken right now?** Installs the *published* `specfuse` with
   `--no-cache-dir`, checks all 12 console scripts landed, and resolves every
   `DELEGATED_COMMANDS` target.
2. **Is `main` broken against what components ship today?** Installs the working
   tree with the latest components and runs the suite.

On failure it opens — or comments on — a single issue. The failure it exists to
catch is a component renaming a module or `main()`, which turns a `specfuse
<subcommand>` into a run-time `ImportError`: `ci.yml` would find it, but only when
someone next opens a PR here.

It catches components that **break** users, not components that merely **moved**.
Nothing pushes a "there is a newer component" signal — every path above is pull.
The closest thing is `specfuse doctor`, which compares each installed component
against PyPI and prints one advisory line when any is behind (`--no-network`
skips it; any lookup failure is silent). That still requires the user to run
`doctor`.

Scheduled workflows run only from the default branch, so changes to that file take
effect once merged.

## The road to 1.0.0

The flat `specfuse-*` commands are deprecated aliases. Removing them is a
coordinated train, in this order:

1. **Each component migrates its own strings** — hooks, `verification.yml`,
   scaffold templates, skills — from `specfuse-loop` to `specfuse run`, etc. Safe
   to do independently; the aliases still work throughout.
2. **Each component drops its own flat `[project.scripts]`.** This is the step
   that actually removes the names — the umbrella cannot do it alone, because each
   component declares the same console-script names itself.
3. **Then** the umbrella drops `alias_main`, the alias entry points, and the
   shim-collision half of `doctor`, and cuts 1.0.0.

Do not do step 2 before every component has done step 1.

Background and the measurements behind these decisions:
[`plan-bundle-suite-distribution.md`](plan-bundle-suite-distribution.md).
