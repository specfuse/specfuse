# Troubleshooting installs

The [README](../README.md) carries the happy path only. Everything here is a
platform or installer problem, plus the one-time migration for installs that
predate 0.10.0.

Start with:

```
specfuse doctor          # report problems
specfuse doctor --fix    # and delete the shims that point at nothing
```

It reports every suite command whose PATH shim is missing, stale, orphaned, or
owned by a different install, with the fix for each, and exits non-zero if
anything is wrong. `--fix` removes dangling shims — it never touches a shim owned
by another install, because that one works and removing it is your call, not the
tool's. After a removal, run `pipx install --force specfuse` (or `uv tool install
--force specfuse`) to put the affected commands back on PATH.

`specfuse --version` prints the resolved version of every component.

## The deprecated `specfuse-*` commands

`specfuse-loop`, `specfuse-lint`, `specfuse-authoring` and the rest are aliases of
`specfuse run`, `specfuse lint`, `specfuse authoring` … and are removed in 1.0.0.
`specfuse doctor` lists the ones still on PATH with their replacements.

Running one prints a one-line notice **in an interactive terminal only** — scaffold
hooks and `verification.yml` call these constantly, and a line per call is noise in
a CI log nobody can act on from there.

Even interactively it is best-effort: each component also ships its own console
script under the same flat name, and inside a single venv whichever distribution
was installed last owns the file (measured: pip/pipx left `specfuse-loop` and
`specfuse-lint` pointing straight at the driver, uv routed all of them through the
alias). The command works identically either way — only the notice is skipped.
That is why `doctor` is the authority on migration status.

To silence it in an interactive shell too:

```
export SPECFUSE_NO_DEPRECATION_WARNING=1
```

## Migrating from `specfuse[all]` (installs before 0.10.0)

Until 0.10.0 the authoring kit and orchestrator were optional **extras**, which
required `pipx install --include-deps 'specfuse[all]'` (or uv's
`--with-executables-from`) and competed with the standalone packages for names in
`~/.local/bin`. They are now hard dependencies of `specfuse`, so the extras and
those flags are gone.

One reinstall converges an old install:

```
pipx uninstall specfuse-authoring        # if you also installed it standalone
pipx uninstall specfuse-orchestrator     # ditto
pipx install --force specfuse            # or: uv tool install --force specfuse
specfuse doctor --fix                    # clear shims the old layout left behind
specfuse doctor                          # should now report a clean install
```

`--force` (not `upgrade`) is the operative part: it rebuilds the venv and relinks
every shim, which is what clears shims left dangling by the extras path.

Symptoms of an un-migrated machine:

- `specfuse-orchestrator: command not found`, or a shim in `~/.local/bin` whose
  symlink target no longer exists.
- `specfuse-authoring` runs an old version no matter how often you upgrade — its
  shim belongs to a standalone venv, and pipx will not overwrite a shim another
  venv owns. It says so once, on stderr:
  `File exists at ~/.local/bin/specfuse-authoring and points to … Not modifying.`
- `specfuse-monitor` / `specfuse-stats` missing: they were never linked without
  `--include-deps`. The umbrella declares them itself now.

## `pip install` fails with "externally-managed-environment"

A bare `pip install` into a system Python is blocked on PEP 668 distributions
(Debian/Ubuntu, Homebrew). Use `uv tool install specfuse` or `pipx install
specfuse` — both give an isolated env with the commands on PATH — or a
virtualenv you manage yourself.

## Windows + Python 3.14: `pipx install` crashes with `UnicodeDecodeError`

If the output shows `Successfully installed … specfuse-…` and then a
`UnicodeDecodeError: … can't decode byte 0x89 …` traceback ending in pipx's
`_copy_launcher_targets_venv → os.fsdecode(...)`, the packages installed fine.
This is an **upstream pipx bug on Python 3.14/Windows**, not a specfuse defect:
pipx copies the console-script `.exe` launchers into `%USERPROFILE%\.local\bin`
and its post-install cleanup mis-reads them. Same class as
[pypa/pipx#1723](https://github.com/pypa/pipx/issues/1723).

`--force` re-copies and re-scans the same launchers, so it hits the identical
crash; deleting the shims doesn't help either (they are recreated and re-trigger
it).

**Use uv instead** — pipx-equivalent model (isolated env, shims on PATH,
one-line install/upgrade), different launcher machinery, so it doesn't hit this:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   # one-time
uv tool install specfuse
specfuse --version
uv tool upgrade specfuse
```

If you must stay on pipx: delete any leftover broken launchers
(`del "$env:USERPROFILE\.local\bin\specfuse*.exe"`) and run pipx itself under
**Python 3.13** so its own process isn't 3.14. A plain `py -m venv` + `pip
install specfuse` also works (you manage PATH yourself).

## Windows: `uv tool install` fails with "Access is denied" on a trampoline .exe

```
Failed to update Windows PE resources: …uv-trampoline-….exe … Access is denied
```

Antivirus/Defender blocking uv's trampoline `.exe` in `%TEMP%`. uv 0.9.9 stores
trampoline metadata in `.rcdata` instead, avoiding it — run `uv self update` and
retry. If it persists, add an AV exclusion for `%LOCALAPPDATA%\uv`, or point
`$env:TMP`/`$env:TEMP` at an unmonitored dir before installing. See
[astral-sh/uv#10030](https://github.com/astral-sh/uv/issues/10030).

## `specfuse upgrade` says it skipped the package upgrade

```
specfuse: this is a pipx-managed install but `pipx` is not on PATH.
```

`specfuse upgrade` overlays the repo's `.specfuse/` scaffold and then upgrades the
suite by running whichever installer owns the environment — `pipx upgrade
specfuse`, `uv tool upgrade specfuse`, or `python -m pip install -U specfuse`. It
falls back to printing the command when it cannot find that installer on PATH
(installed from a different shell, or via a system package). The scaffold overlay
still happened; run the printed command yourself.

Pass `--no-self-upgrade` to skip the package step entirely and only touch the
repo's scaffold.

## `specfuse init`/`upgrade` scaffolded the wrong component

Before 0.12.2 both commands ran the driver's scaffold unconditionally, so
pointing them at a spec-authoring repo or an orchestrator-substrate repo dropped a
whole gate-cycle driver `.specfuse/` into it — templates, rules and a
`verification.yml` for a loop that repo does not run.

They now detect what the repo already has and overlay only that. Run
`specfuse upgrade --dry-run` to see the verdict; the first line names it:

```
specfuse: detected authoring (the spec kit) in /path/to/repo.
```

If the verdict is wrong — a repo with no scaffold yet, or one whose layout
predates the markers — name the components explicitly:

```
specfuse upgrade --components authoring,orchestrator
```

To clean up a repo that already received the unwanted driver scaffold: the loop's
`.specfuse/.scaffold-manifest` lists every file that scaffold wrote, so it is the
record of what to delete. Remove those paths plus `.specfuse/VERSION` and the
manifest itself, then re-run `specfuse upgrade` and confirm the detection line.

## A command runs an old version after upgrading

Run `specfuse doctor`. The usual cause is a shim owned by another venv — see the
migration section above. `specfuse --version` confirms which component versions
this install actually resolves.
