---
name: stack-check-compiler-errors
description: Run compile and type-check commands and report failures
metadata:
  origin: astack
---

# Check compiler errors

In omp, read [the omp adapter](../../docs/harness/omp.md) once per session before you follow this skill. It maps the upstream names in the bundled skills to omp.

## Trigger

Compile or type-check failures are blocking local validation or CI.

## Workflow

1. Run the repo's compile and type-check commands.
2. Summarize errors by file and type.
3. Fix the highest-confidence issues first.
4. Re-run checks until clean or blocked.

## Output

- Current compile and type-check status
- Error summary grouped by file and category
- Fixes applied and remaining blockers
