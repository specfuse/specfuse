# Work plan — one install owns the whole suite

**Status:** both phases ship together in **0.10.0**; alias window open until 1.0.0.
**Goal:** `uv tool install specfuse` (or `pipx install specfuse`) installs and
upgrades every Specfuse script component, with no extras, no installer flags, and
no per-component version for a user to reason about. Claude plugins stay separate
and per-repo — that is the toolset choice a repository actually makes.

The work is written up as two phases because that is the order it was built and
verified, and because phase 1 stands alone. Neither was published separately
though, so they ship as one release: no pointless version gap on PyPI, and one
release note instead of two.

## Why the extras model fails

The suite ships four PyPI distributions:

| Distribution | Console scripts |
|---|---|
| `specfuse` (umbrella) | `specfuse` |
| `specfuse-loop` | `specfuse-loop`, `specfuse-lint`, `specfuse-monitor`, `specfuse-monitor-lint`, `specfuse-stats` |
| `specfuse-authoring` | `specfuse-authoring` |
| `specfuse-orchestrator` | `specfuse-orchestrator`, `specfuse-poller`, `specfuse-runner`, `specfuse-validate-event`, `specfuse-validate-frontmatter` |

Before this change the umbrella pulled the driver as a hard dependency and the
other two as **optional extras** (`specfuse[orchestrator]`, `[authoring]`,
`[all]`). That collides with the pipx/uv tool model in three independent ways:

1. **Tool installers link only the main package's own entry points.** An extra's
   commands are installed but not on PATH unless the user passes
   `--include-deps` (pipx) / `--with-executables-from` (uv). The default,
   obvious install is silently incomplete.
2. **Extras are resolved once, at install time, and never re-resolved.** `pipx
   upgrade specfuse` will not pull a newer `specfuse-authoring` while the
   umbrella's own version is unchanged — which is why `pyproject.toml` carried a
   standing instruction to bump the extra's floor with every component release.
3. **An extra's console scripts share names with the standalone package's.** Two
   supported install paths compete for one name in `~/.local/bin`; pipx refuses
   to overwrite a shim another venv owns, warns once on stderr, and the command
   keeps resolving to the *other* install. Upgrading the package you believe you
   are running changes nothing about what runs.

This is not theoretical. A developer machine running the documented
`specfuse[all]` path was found in this state:

```
~/.local/bin/specfuse-orchestrator       -> venvs/specfuse/bin/specfuse-orchestrator   (target gone)
~/.local/bin/specfuse-poller             -> (target gone)
~/.local/bin/specfuse-runner             -> (target gone)
~/.local/bin/specfuse-validate-event     -> (target gone)
~/.local/bin/specfuse-validate-frontmatter -> (target gone)
~/.local/bin/specfuse-authoring          -> venvs/specfuse-authoring/...   (foreign venv)
venvs/specfuse/                           holds specfuse + specfuse-loop only
specfuse-monitor / -monitor-lint / -stats in the venv's bin, never linked to PATH
```

Five dangling shims, one foreign shim, three commands unreachable. A
`pipx install --force` at some point re-resolved the umbrella without the extras
and left the shims behind; nothing detected it.

Hard `dependencies` have none of the three problems: they are always installed,
they are re-resolved on every `pipx upgrade` / `uv tool upgrade`, and combined
with re-exported entry points they need no installer flag.

## Settled design decisions

1. **Components are hard dependencies, not extras.** Everything the umbrella is
   meant to deliver is a `dependencies` entry. `[orchestrator]`, `[authoring]`
   and `[all]` are removed; only `dev` remains an extra, because it describes
   developing *this* package rather than using the suite.
2. **Floors are minimums, not upgrade levers.** With hard deps, `pipx upgrade
   specfuse` re-resolves and pulls the newest compatible component regardless of
   the floor, so the "bump this floor with every component release" ritual is
   retired. Floors express the oldest version the umbrella's own code can call.
3. **Every component console script is re-exported by the umbrella.** The trick
   already used for `specfuse-loop`/`specfuse-lint` is applied to all eleven, so
   `pipx install specfuse` puts the whole suite on PATH with no flags. In phase 2
   these become the deprecated aliases, so the work is not thrown away.
4. **One advertised version.** The umbrella's version is the only number in the
   docs; `specfuse --version` prints the resolved component table for support.
   Components keep their own PyPI versions — users stop having to read them.
5. **One shim, subcommands (phase 2).** `specfuse` becomes the single name in
   `~/.local/bin`, with `specfuse run|lint|monitor|stats|authoring|pm|…`
   dispatching into the component modules. One name makes collisions
   structurally impossible and `specfuse --help` the whole discovery surface.
6. **Plugins stay separate and per-repo.** Unchanged: `specfuse init` wires
   `extraKnownMarketplaces` + `enabledPlugins` in `.claude/settings.json`, and
   which plugins a repo enables remains its own decision.
7. **Docs carry the happy path only.** Platform-installer bugs (pipx on Python
   3.14/Windows, uv trampoline AV, PEP 668) move to `docs/troubleshooting.md`.
   The README install block is two lines.

## Phase 1 — flagless bundled install (this change)

Ships in `0.10.0`. The minor bump is load-bearing: the install semantics change,
and existing `specfuse[all]` installs need one reinstall to converge.

- **T1 — pyproject: extras → dependencies.** `specfuse-orchestrator>=0.4.1` and
  `specfuse-authoring>=0.5.6` become hard deps; `[orchestrator]`/`[authoring]`/
  `[all]` are deleted. No dependency conflict: loop and authoring have no
  third-party runtime deps, orchestrator adds `jsonschema` + `pyyaml`.
- **T2 — pyproject: re-export all component console scripts.** All eleven names
  declared as the umbrella's own entry points, targeting the component modules
  the hard deps guarantee are importable.
- **T3 — `specfuse --version` prints the component table.** Umbrella version
  plus each component's resolved version (or `not installed`), so a support
  question is one command, not four.
- **T4 — upgrade path upgrades the whole suite.** `pip install -U` on the umbrella
  alone; its hard deps come with it. `--upgrade-strategy eager` is passed to state
  the intent explicitly. It is **not** load-bearing: pip's default
  `only-if-needed` is documented as holding a still-satisfying dependency back,
  but measured on pip 25 a plain `--upgrade` carries satisfied dependencies to the
  newest version anyway (verified on this wheel and on a neutral
  package/dependency pair). The flag pins the behaviour the suite wants instead of
  inheriting whatever the default means in a given pip release.
- **T5 — `doctor` fixes describe the new world.** `--include-deps` /
  `--with-executables-from` disappear from the fix strings. An unlinked suite
  command is now a genuine broken install (every suite script is an umbrella
  entry point), so it is promoted from "quiet, expected" to a warned finding.
- **T6 — docs.** README trimmed to the happy path; `docs/troubleshooting.md`
  holds the platform notes and the migration step for existing `[all]` users.

Out of scope for phase 1, deliberately: `doctor --fix`, merging `init`/`upgrade`,
self-upgrade via the detected installer. Each changes a command's behaviour, and
phase 1 was a pure distribution change. They ship with phase 2 (below).

### Bugs phase 1 surfaced

Verifying phase 1 against real installs found three defects in code that had
shipped green, all fixed in 0.10.0:

1. **`specfuse doctor` had never detected anything.** In a pipx or uv-tool venv,
   `bin/python` is a symlink to the base interpreter, so
   `Path(sys.executable).resolve()` walked out of the venv (to
   `/opt/homebrew/Cellar/python@3.14/...`, or uv's managed cpython). Every path
   comparison was against the wrong directory: `_managed_by_tool()` matched
   neither installer and reported "not a pipx/uv-managed install" on both. Now
   `sys.prefix` + `sysconfig.get_path("scripts")`, neither of which follows that
   symlink.
2. **`--version` was word-wrapped.** argparse's built-in `action="version"` routes
   the string through HelpFormatter, which re-wrapped the component table into a
   ragged paragraph (`specfuse-\nauthoring 0.5.9`). Replaced with a custom action.
3. **`doctor` policed `jsonschema`.** Bundling the suite pulled a transitive
   dependency that ships its own console script. `_console_scripts()` now filters
   to `SUITE_DISTS`.

## Phase 2 — one shim, subcommands (alias window) — also 0.10.0

`specfuse` is now the suite's single command; every component command is a
subcommand of it, and the flat names are deprecated aliases.

- **T7 — the subcommand surface.** `DELEGATED_COMMANDS` maps `run`, `lint`,
  `monitor`, `monitor-lint`, `stats`, `authoring`, `pm`, `poller`, `runner`,
  `validate-event`, `validate-frontmatter` to the component mains. Dispatch
  happens in `main()` **before** argparse: the component owns everything after the
  subcommand name, and letting argparse parse it would mean reinterpreting flags
  this CLI knows nothing about (`specfuse lint --help` must print the linter's
  help). Nine of the eleven component mains take no arguments and read `sys.argv`
  themselves, so `_delegate` swaps `sys.argv` and restores it in a `finally`.
- **T8 — one alias entry point.** All eleven flat commands resolve to
  `specfuse.cli:alias_main`, which recovers the invoked name from `sys.argv[0]`,
  prints the replacement, and delegates. One function, so the console-script table
  cannot drift from `DELEGATED_COMMANDS`.
- **T9 — deprecation is reported by `doctor`, not only by the alias.** See the
  limitation below.
- **T10 — `doctor --fix`.** Deletes dangling shims (`stale`, `orphan`) and
  re-diagnoses so the exit code reflects what is left. A `foreign` shim is never
  touched: it works, it just belongs to another install, and deleting another
  install's property is the user's call. A new `orphan` kind catches shims for
  commands this venv no longer provides — invisible to the original scan, and
  exactly the wreckage the extras path left behind.
- **T11 — `init` and `upgrade` are one idempotent operation.** Either name works
  on either state; `init` on an existing scaffold upgrades it, `upgrade` on a bare
  repo scaffolds it. `DIR` defaults to the cwd. `--no-self-upgrade` scaffolds
  without touching the installed packages.
- **T12 — real self-upgrade.** `_self_upgrade` runs `pipx upgrade specfuse` /
  `uv tool upgrade specfuse` / `python -m pip install -U specfuse` according to
  `_installer()`, instead of detecting the environment only to print the command.
  Falls back to advice when the installer is not on PATH.
- **T13 — `--plugins authoring,orchestrator`.** Asserts the extra `enabledPlugins`
  keys in `.claude/settings.json`, so wiring a repo for a chosen toolset is a flag.

### The alias notice is interactive-only, and best-effort even then

It prints only when stderr is a terminal. The flat commands are invoked constantly
by scaffold hooks and `verification.yml`; a line per call would be noise in a CI
log nobody can act on from there, and it would land in every un-migrated repo the
day 0.10.0 ships. `SPECFUSE_NO_DEPRECATION_WARNING=1` silences it interactively too.

Each component also declares its own console script under the same flat name, and
inside one venv the last distribution installed wins the file. Measured on the
same wheel: pip/pipx left `specfuse-loop` and `specfuse-lint` pointing straight at
the driver (no notice), while uv routed all eleven through `alias_main`. The
command behaves identically either way — only the notice is skipped.

Rather than pretend otherwise, migration status is reported by `specfuse doctor`,
which lists every flat command still on PATH regardless of who provides it, and
never fails on account of it. This also means **1.0.0 cannot drop the flat
commands by editing this package alone** — the components must drop their own
console scripts in the same release train.

### `--pip-args` must not be passed to pipx

An earlier cut of T12 passed `--pip-args=--upgrade-strategy=eager` to
`pipx upgrade`. pipx 1.8+ can use **uv** as its install backend, and `uv pip`
rejects that pip-only flag, so the upgrade failed outright:

```
'uv pip install --python … --upgrade --upgrade-strategy=eager …' failed
specfuse: pipx upgrade failed (exit 1).
```

Both installers re-resolve correctly unaided, so the flag is gone from the pipx
path. It is kept on the plain-`pip` path only to pin intent (see T4).

### Consequence: nothing of ours gates a component release

Hard deps re-resolve on upgrade, which is the point — but it also removed the
accidental gate a stale floor used to provide. A component that renames a module
or `main()` breaks a `specfuse <subcommand>` for every user on their next upgrade,
and `ci.yml` only runs on pull requests and pushes to main here.

`component-compat.yml` closes that: nightly, it installs the *published* umbrella
with `--no-cache-dir` and resolves every dispatch target, then runs the suite from
the working tree against the same components, and opens an issue on failure. The
release flow this implies is written up in [`releasing.md`](releasing.md).

## Remaining work for 1.0.0

1. Migrate every scaffold template, hook, `verification.yml` and skill in the
   component repos to the subcommand form. The installed tree still references
   `specfuse-loop` 31 times, `specfuse-lint` 16, `specfuse-monitor` 11.
2. Have each component repo drop its own flat console scripts (see the limitation
   above) — that, not this package, is what actually removes the old names.
3. Then drop `ALIAS_TO_SUBCOMMAND`, `alias_main`, the alias entry points, and the
   collision-detection half of `doctor`: with one shim on PATH there is nothing
   left to collide.
