---
name: setup-stack
description: Set up the stack plugin for this machine or project. Picks pstack's model per role with stack's defaults, installs the ECC rule sets you choose, checks the OpenRouter key for external adversaries, and reports which guardrail hooks are on. Use for /setup-stack or "configure stack".
disable-model-invocation: true
---

# Setup stack

Read [the stack integration](../../docs/harness/stack.md) first. It names the defaults this skill writes.

## 1. Roles and models

Show the operator each role and its binding: run `python3 <this skill's folder>/../../scripts/delegate.py resolve <role>` for `judge`, `hardest`, `builder`, `evidence`, `builders` and `adversaries`. Ask whether to keep them. To change one, write only the changed keys to `~/.config/stack/roles.json`, in the same shape as the plugin's `roles.json`, for example `{"roles": {"builder": "claude:sonnet"}}`.

If `~/.claude/rules/pstack-models.md` exists, tell the operator it overrides `roles.json` for the roles it names, and offer to delete it.

## 2. Rules

Ask which ECC rule sets to install and where. Offer `common` (recommended for any project), `rust`, `python` and `typescript`, and the scopes `user` (`~/.claude/rules/stack/`, every project) and `project` (`.claude/rules/stack/` in the current repository). Rules load into every session, so suggest only the languages the operator works in. Then run:

```bash
python3 <this skill's folder>/scripts/install-rules.py --sets <sets> --scope <scope>
```

Add `--project <path>` for the project scope. Show the operator the files it printed.

## 3. Other backends

For each backend that a role uses other than `claude`, check its key without printing it. For `go`, that is `test -n "$OPENCODE_API_KEY" && echo set`. If it is set, run `python3 <this skill's folder>/../../scripts/delegate.py doctor --backend go` and show the result. `ok: true` means the child sends only the Go key. On `ok: false`, show the problems and suggest binding those roles to `claude:` until it passes. If the key is not set, tell the operator those roles fall back to Claude, and that they add `OPENCODE_API_KEY` to their shell profile, or to the cloud environment's settings for cloud sessions.

Check whether `OPENROUTER_API_KEY` is set the same way. Without it, `interrogate` skips `openrouter:` panel entries.

## 4. Hooks and memory

Tell the operator which hooks run, from the Hooks section of `stack.md`, and how to change them (`/plugin` options `hooks_enabled` and `hook_profile`, or `ECC_DISABLED_HOOKS`). Check whether the session has rewire's MCP tools (`recall`, `remember`). Say whether `/stack:recall` and `reflect` will use them.

## 5. Report

One short list: the roles that differ from the defaults and where they are set, the doctor result for each backend, the rule sets installed and where, whether external adversaries are on, the hook profile, and whether rewire is connected.
