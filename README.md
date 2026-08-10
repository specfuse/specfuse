# Specfuse

Two things live here: the **`specfuse` pip package** — one install that owns the
whole script suite — and the [Claude Code plugin
marketplace](https://code.claude.com/docs/en/plugin-marketplaces) for the
**Specfuse gate-cycle methodology**.

The split is deliberate. The *scripts* are one install because choosing between
them is not a decision anyone wants to make; the *plugins* stay separate because
which Claude assets a repository enables is exactly the decision it should make.

## Install

```
uv tool install specfuse      # or: pipx install specfuse
cd <your repo> && specfuse init
```

That's the whole suite — driver, spec-authoring kit, orchestrator — behind one
command. No extras, no `--include-deps`, no bracket quoting. Upgrade with:

```
specfuse upgrade              # runs your installer for you
```

That upgrades the components too, even when the umbrella's own version has not
changed — which is the normal case, since components release on their own
schedule. Use it rather than `pip install -U specfuse`: plain pip leaves a
component at its installed version whenever the umbrella's floor is already
satisfied, exits 0, and tells you nothing. `specfuse doctor` reports any
component that has fallen behind.

Then, in Claude Code, install the plugins the repo needs:

```
/plugin marketplace add specfuse/specfuse
/plugin install specfuse@specfuse
```

`specfuse init` already wires the marketplace and the `specfuse` plugin into the
repo's `.claude/settings.json`, so that second command is usually all that's left.
Add `--plugins authoring,orchestrator` to enable those too.

Hitting a platform bug, or migrating off the retired `specfuse[all]` extras? See
[`docs/troubleshooting.md`](docs/troubleshooting.md), and run `specfuse doctor`.

## The `specfuse` command

One command, one name on PATH.

```
specfuse init [DIR]           # scaffold .specfuse/ + wire .claude/ — or upgrade what's there
specfuse upgrade [DIR]        # the same thing, named for the other direction
specfuse doctor [--fix]       # check every suite command resolves here + flag outdated components
                              #   --fix clears dead shims; --no-network skips the PyPI check
specfuse --version            # the umbrella version + every component's resolved version
```

`init` and `upgrade` are one idempotent operation under two names — neither is
ever the wrong one to run — and `DIR` defaults to the current directory. Both take
`--dry-run` (writes nothing), `--plugins`, and `--no-self-upgrade`.

The component tools are subcommands:

| Subcommand | What it does | Component |
|---|---|---|
| `specfuse run` | run the gate-cycle driver | `specfuse-loop` |
| `specfuse lint` | lint a feature plan | `specfuse-loop` |
| `specfuse monitor`, `monitor-lint` | the monitoring CLI and its linter | `specfuse-loop` |
| `specfuse stats` | event statistics for a repo's loop | `specfuse-loop` |
| `specfuse authoring` | design / validate / bundle specs | `specfuse-authoring` |
| `specfuse pm` | multi-repo initiative coordination | `specfuse-orchestrator` |
| `specfuse poller`, `runner` | the orchestrator's poller and agent runner | `specfuse-orchestrator` |
| `specfuse validate-event`, `validate-frontmatter` | orchestrator validators | `specfuse-orchestrator` |

> **The old flat commands still work.** `specfuse-loop`, `specfuse-lint`,
> `specfuse-authoring` and the rest are deprecated aliases, removed in 1.0.0.
> `specfuse doctor` lists the ones still on PATH. One name on PATH is the point:
> the flat names are also the standalone packages' console scripts, so two
> installs could fight over them and the loser's upgrades silently changed nothing
> about what ran. See
> [`docs/plan-bundle-suite-distribution.md`](docs/plan-bundle-suite-distribution.md).

`specfuse init` also provisions the core methodology substrate — the rules,
schemas and glossary in [`methodology/`](methodology/) — into
`.specfuse/methodology/`, so agent skills resolve the shared contract from the
repo they are working in rather than from a sibling checkout. These files are
core's: `init`/`upgrade` overwrite them, and repo-local rules belong in
`.specfuse/rules-local/`.

`specfuse init` lays down `.specfuse/` (templates, rules, docs, `verification.yml`)
and merge-safely wires `.claude/` (including this plugin's config) — pip-native
scaffolding via `specfuse.loop.scaffold`, no `init.sh` checkout required. Every
`specfuse run` also self-provisions (version-syncs `.specfuse/` from the installed
package), so an upgrade reaches existing projects on their next run.

The suite is one distribution with three components as **hard dependencies**
(`specfuse-loop`, `specfuse-authoring`, `specfuse-orchestrator`) — that is what
makes one install and one upgrade cover everything. They contribute to the shared
`specfuse.*` import namespace, so `specfuse.loop`, `specfuse.authoring` and
`specfuse.orchestrator` coexist in one environment.

See [specfuse/loop](https://github.com/specfuse/loop) for the methodology, the
driver, and getting-started docs.

## Plugins

Installed per repo, via the marketplace — pick the toolset that repo needs.

| Plugin | What it ships | Source repo |
|--------|----------------|-------------|
| `specfuse` | Gate-cycle skills (pick / draft / arm / diagnose / wrap, authoring, verification) | [`specfuse/loop`](https://github.com/specfuse/loop) `plugins/specfuse/` |
| `specfuse-authoring` | Spec-craft: design OpenAPI/AsyncAPI/Arazzo, validate, bundle + the `specs` agent (idea → validated initiative) | [`specfuse/authoring`](https://github.com/specfuse/authoring) `plugins/specfuse-authoring/` |
| `specfuse-orchestrator` | Multi-repo initiative coordination (onboard, pm) | [`specfuse/orchestrator`](https://github.com/specfuse/orchestrator) `plugins/specfuse-orchestrator/` |

Update with `/plugin update specfuse@specfuse`; reload after changes with
`/reload-plugins`. The skills drive the pip-installed commands above.

## Layout

```
.claude-plugin/marketplace.json   # catalog: per plugin { name, source, source_repo, managed }
plugins/<name>/                    # GENERATED copies — do not hand-edit (see below)
  .claude-plugin/plugin.json
  skills/<skill>/SKILL.md
  agents/<agent>.md
```

## Releasing (contributors)

**[`docs/releasing.md`](docs/releasing.md)** is the reference: who publishes what,
and when a component release does — or does not — need an umbrella release.

The short version: the components are hard dependencies of `specfuse`, so a
component release reaches users on their next `specfuse upgrade` **without** an
umbrella release. Version floors here are minimums, not levers — don't bump one
just because a component shipped. An umbrella release is needed only when its own
code changes, or when a component adds a command or renames a module.

## How the plugins are sourced (contributors)

**Edit a plugin in its origin repo, never here.** Each plugin's canonical source
lives in its own repo at `plugins/<name>/` (for the loop, `.specfuse/skills/` is
vendored *from* `plugins/specfuse/skills/` for its dogfood — the plugin dir is
still the source). The copies under `plugins/` in **this** repo are **generated
output**, produced by [`specfuse/publish.py`](specfuse/publish.py).

- **Publish on release.** When a source repo publishes its package to PyPI, its
  release workflow dispatches to this repo; the publish step regenerates that
  plugin from the source at tag `v<version>`, stamps `plugin.json.version` to the
  released version (`plugin@X == package@X == tag vX`), and opens a PR **only if
  the plugin changed**.
- **Drift-guard.** The `plugin-drift-guard` CI (required check) re-derives every
  `managed` plugin from its source at the pinned tag and fails on any diff — so a
  hand-edit, a bad merge, or an agent's "quick fix" cannot land in `plugins/`. The
  only way in is a faithful publish.
- **Manual publish** (testing / backfill): the `plugin-publish` workflow's
  `workflow_dispatch` (`plugin`, `version`) runs the same path by hand.

See [`docs/plan-unify-plugin-sourcing.md`](docs/plan-unify-plugin-sourcing.md) for
the full design. Skills reach a target repo through the installed plugin (under
the `/specfuse:` etc. namespaces), not by copying files into the repo.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
