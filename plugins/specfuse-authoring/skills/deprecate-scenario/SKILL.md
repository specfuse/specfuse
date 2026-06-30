---
name: deprecate-scenario
description: "Mark an Arazzo scenario or recipe as deprecated -- sets x-version deprecation metadata (deprecatedAt, replacedBy, removalDate without bumping current), verifies the replacement exists, and warns about downstream consumers. Use when retiring a scenario or recipe in favor of a successor."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Mark an Arazzo scenario or recipe as deprecated. Updates `x-version` with deprecation metadata and warns about downstream impacts.

*Enforces: .specfuse/authoring/handbooks/Arazzo_Handbook.md*

## Input

Accept the target file. The user may provide:
- A full file path
- A domain and scenario/recipe name

If ambiguous, list matching files and ask the user to pick.

## Process

1. **Read the target file.** Confirm it exists. Check current `x-version.status` -- if already deprecated, report:

   > "This file is already deprecated (since {deprecatedAt}, replaced by {replacedBy}). No changes needed."

2. **Gather deprecation metadata.** Ask:

   - **Replacement:** "What scenario/recipe replaces this one? Provide the file stem (e.g., `refund-v2`). Leave blank if no replacement exists yet."
   - **Removal date:** "When should this deprecated file be removed? Provide an ISO date (e.g., `2026-12-01`), or leave blank for no target date."

3. **Verify the replacement exists** (if provided). Scan for a file matching the `replacedBy` value:
   - Scenarios: `api/specs/v1/domains/*/scenarios/{replacedBy}.arazzo.yaml` or `api/specs/v1/scenarios/cross-domain/{replacedBy}.arazzo.yaml`
   - Recipes: `api/specs/v1/scenarios/setup-recipes/**/{replacedBy}.recipe.yaml`

   If not found, warn:

   > "The replacement '{replacedBy}' does not exist yet. Create it with `/design-scenario` (or `/design-recipe`) before finalizing deprecation."

4. **Update `x-version`.** Apply these changes to the target file:

   ```yaml
   x-version:
     current: {unchanged -- do not increment}
     status: deprecated
     deprecatedAt: "{today's ISO date}"
     replacedBy: "{value}"        # if provided
     removalDate: "{value}"       # if provided
   ```

   **Version bump rule:** Deprecation sets `status: deprecated` but does NOT increment `x-version.current`. The content has not changed -- only the lifecycle status.

5. **Check for downstream consumers.** Scan for files that depend on the deprecated file:

   **If the deprecated file is a recipe:**
   - Find all recipes that `extends` this recipe (Grep for the recipe's file stem in `x-recipe.extends` across all recipe files)
   - Find all scenarios with `x-setup.recipe` matching this recipe's file stem

   **If the deprecated file is a scenario:**
   - Check if any other scenario references it (uncommon, but possible via cross-domain links)

6. **Warn about downstream impacts.** If consumers exist, present them:

   > "The following files depend on the deprecated recipe '{name}':
   > - `basic-fulfilled-orders.recipe.yaml` (extends this recipe)
   > - `order-lifecycle.arazzo.yaml` (uses as x-setup.recipe)
   > - `order-context-sync.arazzo.yaml` (uses as x-setup.recipe)
   >
   > These files will need to be updated to reference the replacement once it exists. This command does not modify them automatically -- the decision is yours."

7. **Validate.** Run validation to confirm the deprecated file is still valid YAML with correct extension shapes:
   ```bash
   ./scripts/validate-arazzo-spectral.sh
   ```

8. **Report.** Summarize what was changed:

   > "Deprecated: {file path}
   > - status: deprecated (was: {previous status})
   > - deprecatedAt: {date}
   > - replacedBy: {value or 'not set'}
   > - removalDate: {value or 'not set'}
   > - Downstream consumers: {count} files warned"

## Checklist

- [ ] Target file identified and read
- [ ] Current status checked (not already deprecated)
- [ ] `deprecatedAt` set to today's date
- [ ] `replacedBy` set (if replacement provided and verified)
- [ ] `removalDate` set (if provided)
- [ ] `x-version.current` NOT incremented (deprecation is lifecycle, not content)
- [ ] Downstream consumers identified and warned
- [ ] Validation passed after changes
