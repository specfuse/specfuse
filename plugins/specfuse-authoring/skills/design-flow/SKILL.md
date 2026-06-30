---
name: design-flow
description: "Compatibility shim -- /design-flow has been replaced by /design-scenario as part of the Arazzo integration. Use when someone asks to design a flow; redirect to scenario authoring (all procedural flow docs are now Arazzo-driven), or edit a domain overview directly for conceptual overviews."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

*Enforces: .specfuse/authoring/handbooks/AsyncAPI_Handbook.md* (flow docs section)

This command has been replaced by `/design-scenario` as part of the Arazzo integration.

When the user invokes `/design-flow`, run `/design-scenario` instead. All flow documentation is now driven by Arazzo scenarios — see the Arazzo Handbook §14 for the authoring path.

For conceptual domain overviews (not procedural flows), create or edit `api/docs/flows/{domain}/overview.md` directly.
