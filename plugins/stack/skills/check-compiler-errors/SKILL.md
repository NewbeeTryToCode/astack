---
name: check-compiler-errors
description: Run compile and type-check commands and report failures
---

# Check compiler errors

In Claude Code, read [the Claude Code adapter](../../docs/harness/claude-code.md) once per session before you follow this skill. It maps the Cursor names in pstack skills to Claude Code.

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
