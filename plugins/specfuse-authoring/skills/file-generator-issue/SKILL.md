---
name: file-generator-issue
description: "File a GitHub issue against the Specfuse generator repo for a code-generation bug, then start a background monitor that polls for resolution and auto-verifies the fix when the generator agent resolves it. Use when generated code is wrong and you need to report the symptom (never propose template fixes) and resume work once fixed; supports a --verify-only mode."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->


# File Generator Issue + Auto-Monitor (Specs project)

*Enforces: (general — no single handbook)*

File a GitHub issue against the Specfuse Generator repository for this
project, then start a background monitor that polls every 5 minutes for
resolution.

**Generator repo**: resolved at runtime from the `GENERATOR_REPO`
environment variable (format: `<owner>/<repo>`). Set this in your
project's `.envrc`, shell profile, or wherever your project keeps
per-project env vars. Example: `export GENERATOR_REPO=acme/specfuse-generator`.
If unset, the command stops and asks you to configure it.

**Arguments:** `$ARGUMENTS`

Parse arguments:
- Default (no flags): File a new issue. `$0` is the short title.
- `--verify-only <N>`: Skip filing, just verify issue N and resume.

## GitHub API access

**Always use `curl` with the GitHub REST API instead of `gh` CLI.**
The macOS sandbox blocks Go's TLS certificate verification path,
causing `gh` to fail in Claude Code.

Resolve the token and target repo once at the start:
```bash
GH_TOKEN="${GH_TOKEN:-$(gh auth token 2>/dev/null || echo '')}"
GENERATOR_REPO="${GENERATOR_REPO:-}"
if [ -z "$GENERATOR_REPO" ]; then
  echo "GENERATOR_REPO is not set. Export it as <owner>/<repo> (e.g. acme/specfuse-generator) and re-run." >&2
  exit 1
fi
```

Standard headers for all requests:
```
-H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json"
```

## Rules of the road (read first)

- You are a **consumer** of generated code. Report **symptoms**, never
  propose fixes to templates or the generation pipeline.
- Status values you can set: `open` (new or reopened) and `closed`
  (reporter confirming the fix works — reporter-only). You may NOT set
  `in-progress`, `resolved`, or `wont-fix` — those are maintainer-only.

## Step 1 — Check for duplicates

Search existing open issues to avoid filing a duplicate:

```bash
curl -s -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GENERATOR_REPO}/issues?labels=bug&state=open" \
  | jq '[.[] | {number, title}]'
```

If a similar open issue already exists, add a comment on that issue
with your additional observations and skip to Step 3 using the
existing issue number.

## Step 2 — File the GitHub issue

Create a GitHub issue using the bug report template:

```bash
curl -s -X POST -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  "https://api.github.com/repos/${GENERATOR_REPO}/issues" \
  -d "$(jq -n \
    --arg title "[BUG] <short description>" \
    --arg body "$(cat <<'BODY'
## Description

<What is wrong — describe the symptom, not a fix suggestion>

## Language / Artifact

- **Language:** <csharp | python | flutter | markdown>
- **Artifact:** <e.g., Entity, ScenarioDocument, ApiModel>
- **Generated file:** <path to the generated file, e.g., api/docs/flows/order/order-lifecycle.md>

## OpenAPI snippet

```yaml
<relevant spec section — use Arazzo source snippet if the issue is about scenario doc generation>
```

## Actual output

```
<generated output verbatim — 10+ lines of surrounding context or full file if short>
```

## Expected output

```
<what correct output should look like>
```

## Workaround applied

<what you changed, or "None">

## Additional context

<error messages, framework/language docs, etc.>

## Severity

- [ ] **Critical** — generated code does not compile / crashes at runtime
- [ ] **Major** — incorrect behavior, wrong output, missing required element
- [ ] **Minor** — cosmetic, suboptimal but functional
BODY
)" \
    '{title: $title, labels: ["bug","status:open","severity:<critical|major|minor>","language:<language>","reporter:specs-agent"], body: $body}')"
```

Body rules:
- Fill out every section. Use `None` if a section does not apply.
- Reference the relevant Arazzo source spec snippet (instead of OpenAPI
  snippet) when the issue is about scenario doc generation.
- Do **NOT** suggest how to fix the generator or its templates.
- One issue per problem — if multiple issues are found, file them
  separately and run this skill once per issue.

Capture the issue number from the JSON response (`.number`) for Step 3.

## Step 3 — Start background monitor

After filing (or finding a duplicate), start polling for resolution:

```bash
bash .claude/scripts/monitor-generator-issue.sh <issue-number> ${GENERATOR_REPO} 300
```

Use the Bash tool with `run_in_background: true`. The monitor checks
every 5 minutes (300 seconds). When the generator agent adds the
`status:resolved` label, the monitor prints a notification and exits.

Tell the user: "Background monitor started for issue #<N>. I'll be
notified automatically when the generator agent resolves it."

## Step 4 — On resolution notification

When the background monitor completes (you'll receive a task
notification), **automatically**:

1. Read the issue comments to find the `## Resolution` details:
   ```bash
   curl -s -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
     "https://api.github.com/repos/${GENERATOR_REPO}/issues/<N>/comments" | jq '.[].body'
   ```
2. Check if the generated files in this project have been updated.
3. **If the generated files were updated** and match the expected
   output:
   - Regenerate docs if applicable: `./scripts/generate-scenario-docs.sh`
   - Compare output against expected — check the specific symptom
     described in the issue.
   - If fix is correct: add a verification comment and close:
     ```bash
     # Add verification comment
     curl -s -X POST -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
       -H "Content-Type: application/json" \
       "https://api.github.com/repos/${GENERATOR_REPO}/issues/<N>/comments" \
       -d "$(jq -n --arg body "## Verification (specs-agent)

     <describe what you tested and the result>" '{body: $body}')"

     # Close the issue
     curl -s -X PATCH -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
       -H "Content-Type: application/json" \
       "https://api.github.com/repos/${GENERATOR_REPO}/issues/<N>" \
       -d '{"state":"closed"}'
     ```
   - If fix is wrong: remove `status:resolved`, add `status:open`,
     and comment with updated actual/expected.
4. **If the generated files were NOT updated**: comment asking for
   regeneration and reset to open:
   ```bash
   # Update labels
   CURRENT_LABELS=$(curl -s -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
     "https://api.github.com/repos/${GENERATOR_REPO}/issues/<N>/labels" | jq -r '.[].name')
   NEW_LABELS=$(echo "$CURRENT_LABELS" | sed 's/status:resolved/status:open/' | jq -R . | jq -s .)
   curl -s -X PUT -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
     -H "Content-Type: application/json" \
     "https://api.github.com/repos/${GENERATOR_REPO}/issues/<N>/labels" \
     -d "{\"labels\":$NEW_LABELS}"

   # Add comment
   curl -s -X POST -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
     -H "Content-Type: application/json" \
     "https://api.github.com/repos/${GENERATOR_REPO}/issues/<N>/comments" \
     -d '{"body":"Generated files not yet updated in this project. Please regenerate."}'
   ```

## Step 5 — Resume interrupted work

After verifying (or rejecting) the fix, resume whatever task was
interrupted by the generator issue. Check the task list for
in-progress items.

## Verify-only mode

When called with `--verify-only <N>`:

1. Check the issue's labels and state:
   ```bash
   curl -s -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
     "https://api.github.com/repos/${GENERATOR_REPO}/issues/<N>" \
     | jq '{labels: [.labels[].name], state: .state}'
   ```
2. If the issue does not have `status:resolved` label: report the
   current status and stop — there is nothing to verify.
3. Otherwise, follow Step 4 verification process and resume.
