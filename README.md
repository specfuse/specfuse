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

Or install with **[uv](https://docs.astral.sh/uv/)** (`uv tool`) — a single standalone
binary with the same isolated-env-on-PATH model as pipx, and the **recommended path
on Windows** (it sidesteps the pipx/Python-3.14 bug noted below):

```
uv tool install specfuse                             # core: specfuse / specfuse-loop / specfuse-lint
uv tool install --with-executables-from specfuse-orchestrator,specfuse-authoring 'specfuse[all]'   # whole suite
uv tool upgrade specfuse                             # upgrade (re-resolves, like pipx upgrade)
```

> **`--with-executables-from` is uv's `--include-deps`.** `uv tool install specfuse`
> exposes only the umbrella's own scripts; the orchestrator/authoring commands live
> in the extra packages, so name them in `--with-executables-from` to put them on
> PATH. uv also manages its own Python, so a system Python 3.14 doesn't affect it.
>
> **Use uv ≥ 0.9.9 on Windows.** If `uv tool install` fails with `Failed to update
> Windows PE resources: …uv-trampoline-….exe … Access is denied`, that's antivirus/
> Defender blocking uv's trampoline `.exe` in `%TEMP%`. uv 0.9.9 stores trampoline
> metadata in `.rcdata` instead, avoiding it — run `uv self update` and retry. If it
> persists, add an AV exclusion for `%LOCALAPPDATA%\uv` (or point `$env:TMP`/`$env:TEMP`
> at an unmonitored dir before installing). See astral-sh/uv#10030.

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
> **Windows + Python 3.14: `pipx install` crashes with `UnicodeDecodeError`.**
> If the output shows `Successfully installed … specfuse-…` and then a
> `UnicodeDecodeError: … can't decode byte 0x89 …` traceback ending in pipx's
> `_copy_launcher_targets_venv → os.fsdecode(...)`, the packages installed fine —
> this is an **upstream pipx bug on Python 3.14/Windows**, not a specfuse defect.
> pipx copies the console-script `.exe` launchers into `%USERPROFILE%\.local\bin`
> and its post-install cleanup then mis-reads them. `--force` re-copies and
> re-scans the same launchers, so it hits the identical crash; deleting the shims
> doesn't help either (they're recreated and re-trigger it). Same 3.14/Windows
> class as [pypa/pipx#1723](https://github.com/pypa/pipx/issues/1723).
>
> **Use uv instead** (recommended) — uv's `tool` model is pipx-equivalent (isolated
> env, shims on PATH, one-line install/upgrade) but uses its own launcher machinery,
> so it doesn't hit this bug:
>
> ```powershell
> powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   # one-time: install uv
> uv tool install specfuse                                     # core CLIs
> uv tool install --with-executables-from specfuse-orchestrator,specfuse-authoring 'specfuse[all]'   # whole suite
> specfuse --version
> uv tool upgrade specfuse                                     # upgrade later
> ```
>
> If you must stay on pipx: delete any leftover broken launchers
> (`del "$env:USERPROFILE\.local\bin\specfuse*.exe"`) and run pipx itself under
> **Python 3.13** so its own process isn't 3.14. A plain `py -m venv` + `pip install
> "specfuse[all]"` also works (you manage PATH yourself).

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
