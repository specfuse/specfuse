---
name: preview-async
description: "Launch the AsyncAPI documentation preview server (port 8082) in the background for live viewing of the async specs while editing. Use when you want to visually review AsyncAPI docs in the browser; coexists with the OpenAPI preview on 8081."
---

<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

Launch the AsyncAPI documentation preview server for live viewing of the async specifications.

*Enforces: (general — no single handbook)*

## Steps

1. **Start the preview server** — Run `./scripts/specfuse/serve-async-docs.sh` in the background using `run_in_background: true`. The server starts on port 8082 by default.

2. **Confirm it's running** — After a few seconds, check the output to verify the server started successfully.

3. **Inform the user** — Tell the user the async docs are available at http://localhost:8082.

## Prerequisites

The AsyncAPI CLI must be installed: `npm install -g @asyncapi/cli`

## Notes

- The server runs in the background so you can continue making changes to the specs.
- To stop the server, the user can press Ctrl+C in the terminal or kill the background process.
- The OpenAPI docs preview remains on port 8081 (via `/preview`), so both can run simultaneously.
