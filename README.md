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

The skills drive the **specfuse-loop** driver (`pip install specfuse-loop`); see
[specfuse/loop](https://github.com/specfuse/loop) for the methodology, the driver,
and getting-started docs.

## The `specfuse` umbrella CLI

This repo also ships the **`specfuse`** pip package — the umbrella CLI that bridges
the pip-installed driver and this plugin:

```
pip install specfuse          # pulls specfuse-loop too
specfuse upgrade              # pip-upgrade driver + CLI, then points at /plugin update
specfuse init <repo>          # ensure the driver is installed; print bootstrap steps
```

`specfuse` contributes to the shared `specfuse.*` import namespace (so
`specfuse.loop` from the driver and a future `specfuse.orchestrator` coexist). Note:
fully pip-native scaffolding (`specfuse init` laying down `.specfuse/` templates and
rules) is deferred — until it ships, scaffolding a new repo still uses the loop's
`init.sh`; `specfuse upgrade` already owns the pip ↔ plugin bridge.

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
repo is canonical; a sync step keeps this plugin's copy current (see the loop's
FEAT-2026-0019). Until the native-plugin migration completes, the loop's `init.sh`
also installs these skills into a target repo's `.specfuse/skills/` — the plugin is
the forward path, `init.sh` the legacy one.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
