---
name: stack-deslop
description: Remove AI-generated code slop and clean up code style
metadata:
  origin: astack
---

# Remove AI code slop

In omp, read [the omp adapter](../../docs/harness/omp.md) once per session before you follow this skill. It maps the upstream names in the bundled skills to omp.

Check the diff against main and remove AI-generated slop introduced in the branch.

## Focus Areas

- Extra comments that are unnecessary or inconsistent with local style
- Defensive checks or try/catch blocks that are abnormal for trusted code paths
- Casts to `any` used only to bypass type issues
- Deeply nested code that should be simplified with early returns
- Other patterns inconsistent with the file and surrounding codebase

## Guardrails

- Keep behavior unchanged unless fixing a clear bug.
- Prefer minimal, focused edits over broad rewrites.
- Keep the final summary concise (1-3 sentences).
