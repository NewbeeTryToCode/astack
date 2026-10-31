---
name: setup-stack
description: Set up the stack plugin for this machine or project. Picks pstack's model per role with stack's defaults, installs the ECC rule sets you choose, checks the OpenRouter key for external adversaries, and reports which guardrail hooks are on. Use for /setup-stack or "configure stack".
disable-model-invocation: true
---

# Setup stack

Read [the stack integration](../../docs/harness/stack.md) first. It names the defaults this skill writes.

## 1. Models

Read `../setup-pstack/SKILL.md` and follow it, with two changes. Its defaults are the **In stack** column of the Models table in `stack.md`, not the Cursor slugs. Keep the `openrouter:<model-id>` entry in the `interrogate reviewers` line unless the operator removes it, because it is a valid alias that the `Agent` tool never sees.

## 2. Rules

Ask which ECC rule sets to install and where. Offer `common` (recommended for any project), `rust`, `python` and `typescript`, and the scopes `user` (`~/.claude/rules/stack/`, every project) and `project` (`.claude/rules/stack/` in the current repository). Rules load into every session, so suggest only the languages the operator works in. Then run:

```bash
python3 <this skill's folder>/scripts/install-rules.py --sets <sets> --scope <scope>
```

Add `--project <path>` for the project scope. Show the operator the files it printed.

## 3. External adversary

Check whether `OPENROUTER_API_KEY` is set, without printing its value (`test -n "$OPENROUTER_API_KEY" && echo set`). If it is not, tell the operator that `interrogate` will skip the `openrouter:` panel entry, and that they can export the key in their shell profile to turn it on. In a cloud environment whose proxy injects the OpenRouter key, any placeholder value works.

## 4. Hooks and memory

Tell the operator which hooks run, from the Hooks section of `stack.md`, and how to change them (`/plugin` options `hooks_enabled` and `hook_profile`, or `ECC_DISABLED_HOOKS`). Check whether the session has rewire's MCP tools (`recall`, `remember`). Say whether `/stack:recall` and `reflect` will use them.

## 5. Report

One short list: the model rule path and the roles that differ from the defaults, the rule sets installed and where, whether external adversaries are on, the hook profile, and whether rewire is connected.
