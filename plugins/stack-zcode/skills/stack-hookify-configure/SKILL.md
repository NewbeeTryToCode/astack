---
name: stack-hookify-configure
description: Enable or disable hookify rules interactively
when_to_use: Enable or disable hookify rules interactively
metadata:
  origin: ECC
---
# hookify-configure


Interactively enable or disable existing hookify rules.

## Steps

1. Find all `.claude/hookify.*.local.md` files
2. Read the current state of each rule
3. Present the list with current enabled / disabled status
4. Ask which rules to toggle
5. Update the `enabled:` field in the selected rule files
6. Confirm the changes
