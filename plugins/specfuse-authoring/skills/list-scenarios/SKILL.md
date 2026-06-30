---
name: list-scenarios
description: "Browse existing Arazzo scenarios and recipes filtered by domain, actor role, tag, or status. A discovery tool -- use when you want to understand what behavioral coverage already exists before authoring, updating, or reviewing scenarios. Pure file-system scan with YAML metadata extraction, no subagent."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Browse existing Arazzo scenarios and recipes by domain, actor role, tag, or status. A discovery tool for understanding what behavioral coverage exists.

*Enforces: .specfuse/authoring/handbooks/Arazzo_Handbook.md*

This command does not use a sub-agent -- it is a direct file-system scan with YAML metadata extraction.

## Input

Accept optional filters from the user's request. All filters are combinable:

| Filter | Matches on | Example |
|--------|-----------|---------|
| domain | `x-domain` value | "order", "customer", "cross-domain" |
| actor | `x-actors.*.role` value | "Customer", "Manager" |
| tag | `tags` array entries | "critical-path", "order-lifecycle" |
| status | `x-version.status` value | "draft", "stable", "deprecated" |
| recipe | Show recipes instead of scenarios | (flag, no value) |

If no filters are provided, list all scenarios.

## Process

1. **Discover files.** Scan for Arazzo files:
   - Scenarios: Glob `api/specs/v1/domains/*/scenarios/*.arazzo.yaml` and `api/specs/v1/scenarios/cross-domain/*.arazzo.yaml`
   - Recipes (when `recipe` filter is set): Glob `api/specs/v1/scenarios/setup-recipes/**/*.recipe.yaml`

2. **Extract metadata.** For each file, read the top-level fields (do not parse deeply into steps):
   - `x-domain`
   - `x-version.status`
   - `x-actors` keys and roles (scenarios only)
   - `tags` array
   - `info.title`
   - Workflow count and IDs
   - `x-recipe.purpose` and `x-recipe.extends` (recipes only)

3. **Apply filters.** Exclude files that do not match all provided filters.

4. **Present results.** Format as a table:

   **For scenarios:**

   | Domain | Scenario | Title | Actors | Tags | Status |
   |--------|----------|-------|--------|------|--------|
   | order | order-lifecycle | Order lifecycle | manager (Manager), customer (Customer) | critical-path, order | draft |

   **For recipes:**

   | Domain | Recipe | Title | Extends | Purpose | Outputs | Status |
   |--------|--------|-------|---------|---------|---------|--------|
   | order | basic-fulfilled-orders | Basic fulfilled orders fixture | basic-orders | test-fixture | fulfillmentId, templateId, lineId1, lineId2, lineId | draft |

5. **Report totals.**

   > "N scenarios across M domains. K tagged critical-path. J in draft, L stable, P deprecated."

   Or for recipes:

   > "N recipes (F foundational, D domain-specific). Max chain depth: X."

## Checklist

- [ ] All matching files discovered
- [ ] Metadata extracted without deep file parsing
- [ ] Filters applied correctly
- [ ] Results presented in scannable table format
- [ ] Totals reported
