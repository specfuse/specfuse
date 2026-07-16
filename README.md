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
pipx install specfuse                                # driver only; gives specfuse / specfuse-loop / specfuse-lint
pipx install --include-deps 'specfuse[orchestrator]' # + the multi-repo orchestrator
pipx install --include-deps 'specfuse[authoring]'    # + the spec-authoring kit
pipx install --include-deps 'specfuse[all]'          # the whole suite in one command
specfuse init <repo>          # scaffold .specfuse/ + wire .claude/ (--dry-run previews)
specfuse upgrade <repo>       # overlay a newer scaffold, then pip-upgrade driver + CLI, point at /plugin update
```

> **`--include-deps` is required for the extras' CLIs.** pipx only exposes the main
> package's own console scripts; the orchestrator/authoring commands
> (`specfuse-orchestrator`, `specfuse-poller`, `specfuse-authoring`, …) live in the
> extra packages, so `--include-deps` is what surfaces them on PATH. Without it the
> extra is *installed* but its commands aren't linked.
>
> **Quote the brackets** — zsh globs them (`'specfuse[all]'`). And extras are only
> re-resolved on a *fresh* install — to add one to an existing install use
> `pipx install --force --include-deps 'specfuse[all]'`; `pipx upgrade` alone won't
> pull a newly-added extra.

> A bare `pip install` into a system Python is blocked on PEP-668
> externally-managed environments (Debian/Ubuntu, Homebrew). Use `pipx` (then
> `pipx upgrade specfuse`) or a virtualenv, so `specfuse-loop` / `specfuse-lint`
> land on PATH for the gate commands to find.
>
> **Windows: `pipx install` crashes with `UnicodeDecodeError` after a successful
> install.** If the output shows `Successfully installed … specfuse-…` followed by
> `⚠️ File exists at …\.local\bin\specfuse*.exe and does not match …` and then a
> `UnicodeDecodeError: … can't decode byte 0x89 …` traceback, the packages
> installed fine — the crash is pipx's post-install cleanup choking on **stale
> `specfuse*.exe` launchers** left in `%USERPROFILE%\.local\bin` by an earlier
> non-pipx install (e.g. a prior `pip install --user`). Clear them and reinstall:
>
> ```powershell
> del "$env:USERPROFILE\.local\bin\specfuse.exe","$env:USERPROFILE\.local\bin\specfuse-loop.exe","$env:USERPROFILE\.local\bin\specfuse-lint.exe"
> pipx install --force specfuse[all]
> pipx ensurepath
> specfuse --version
> ```

`specfuse init` lays down `.specfuse/` (templates, rules, docs, `verification.yml`)
and merge-safely wires `.claude/` (including this plugin's config) — pip-native
scaffolding via `specfuse.loop.scaffold`, no `init.sh` checkout required. Every
`specfuse-loop` run also self-provisions (version-syncs `.specfuse/` from the
installed package), so `pip install -U specfuse` reaches existing projects on
their next run. `specfuse` contributes to the shared `specfuse.*` import namespace
(so `specfuse.loop` from the driver and a future `specfuse.orchestrator` coexist).

## Plugins

| Plugin | What it ships | Source repo |
|--------|----------------|-------------|
| `specfuse` | Gate-cycle skills (pick / draft / arm / diagnose / wrap, authoring, verification) | [`specfuse/loop`](https://github.com/specfuse/loop) `plugins/specfuse/` |
| `specfuse-authoring` | Spec-craft: design OpenAPI/AsyncAPI/Arazzo, validate, bundle + the `specs` agent (idea → validated initiative) | [`specfuse/authoring`](https://github.com/specfuse/authoring) `plugins/specfuse-authoring/` |
| `specfuse-orchestrator` | Multi-repo initiative coordination (onboard, pm) | [`specfuse/orchestrator`](https://github.com/specfuse/orchestrator) `plugins/specfuse-orchestrator/` |

## Layout

```
.claude-plugin/marketplace.json   # catalog: per plugin { name, source, source_repo, managed }
plugins/<name>/                    # GENERATED copies — do not hand-edit (see below)
  .claude-plugin/plugin.json
  skills/<skill>/SKILL.md
  agents/<agent>.md
```

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
