# Specfuse — Claude Code plugin marketplace

This repository is the [Claude Code plugin
marketplace](https://code.claude.com/docs/en/plugin-marketplaces) for the
**Specfuse gate-cycle methodology**. It is the shared distribution home so the
loop today — and the orchestrator and future products later — install their Claude
assets from one place.

## Install

```
/plugin marketplace add specfuse/specfuse
/plugin install specfuse@specfuse
```

That installs the **`specfuse`** plugin: the methodology's interactive skills,
namespaced under `/specfuse:` (e.g. `/specfuse:pick-feature`,
`/specfuse:draft-feature`, `/specfuse:arm-gate`). Update with `/plugin update
specfuse@specfuse`; reload after changes with `/reload-plugins`.

The skills drive the **specfuse-loop** driver — install it with the umbrella
package below (`pip install specfuse` pulls it), or on its own with `pip install
specfuse-loop`. See [specfuse/loop](https://github.com/specfuse/loop) for the
methodology, the driver, and getting-started docs.

## The `specfuse` umbrella CLI

This repo also ships the **`specfuse`** pip package — the umbrella CLI that bridges
the pip-installed driver and this plugin:

```
pipx install specfuse         # recommended (CLI app); pulls specfuse-loop too
#   gives you: specfuse / specfuse-loop / specfuse-lint
#   (or, inside a venv you control: python3 -m pip install specfuse)
specfuse init <repo>          # scaffold .specfuse/ + wire .claude/ (--dry-run previews)
specfuse upgrade <repo>       # overlay a newer scaffold, then pip-upgrade driver + CLI, point at /plugin update
```

> A bare `pip install` into a system Python is blocked on PEP-668
> externally-managed environments (Debian/Ubuntu, Homebrew). Use `pipx` (then
> `pipx upgrade specfuse`) or a virtualenv, so `specfuse-loop` / `specfuse-lint`
> land on PATH for the gate commands to find.

`specfuse init` lays down `.specfuse/` (templates, rules, docs, `verification.yml`)
and merge-safely wires `.claude/` (including this plugin's config) — pip-native
scaffolding via `specfuse.loop.scaffold`, no `init.sh` checkout required. Every
`specfuse-loop` run also self-provisions (version-syncs `.specfuse/` from the
installed package), so `pip install -U specfuse` reaches existing projects on
their next run. `specfuse` contributes to the shared `specfuse.*` import namespace
(so `specfuse.loop` from the driver and a future `specfuse.orchestrator` coexist).

## Plugins

| Plugin | What it ships | Source |
|--------|----------------|--------|
| `specfuse` | Gate-cycle skills (pick / draft / arm / diagnose / wrap, authoring, verification) | [`plugins/specfuse/`](plugins/specfuse/) |

Future products (orchestrator, shared core) will add entries here and reuse the
same marketplace.

## Layout

```
.claude-plugin/marketplace.json   # this marketplace's catalog
plugins/specfuse/
  .claude-plugin/plugin.json       # the specfuse plugin manifest
  skills/<skill>/SKILL.md          # the gate-cycle skills
```

## Relationship to specfuse/loop

The skills here are the same craft authored in
[`specfuse/loop`](https://github.com/specfuse/loop)'s `.specfuse/skills/`. The loop
repo is canonical; a sync step keeps this plugin's copy current. Skills reach a
target repo through this plugin (under the `/specfuse:` namespace) — `specfuse
init` wires the plugin into the repo's `.claude/settings.json`; it does not copy
skill files into the repo. (`init.sh` is a deprecated v1.0 shim that delegates to
`specfuse init`/`upgrade`.)

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
