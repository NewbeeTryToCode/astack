# ZCode adapter

`stack` runs in ZCode as the `stack-*` skills and `stack-*` agents. Read this file once per session, right after a skill sends you here. It maps the Claude Code and Cursor names in the bundled skills to ZCode. Where this file and a bundled skill disagree about ZCode specifics, this file wins.

## Tools and invoking skills

- A step that says to run another bundled skill (`how`, `interrogate`, `deslop`, `verify-this`, a `principle-*`, or a command like `plan`) means: invoke the `Skill` tool with the skill's ZCode name — `stack-` plus the name, e.g. `stack-how`, `stack-interrogate`, `stack-principle-prove-it-works`, `stack-plan`. If the `Skill` tool refuses the name, Read that skill's `SKILL.md` from `<stack>` and follow it.
- `Task` or "spawn a subagent" means the `Agent` tool. `AskQuestion` means `AskUserQuestion`. The todo list is `TodoWrite`. Everything else (Read, Write, Edit, Bash, Grep, Glob, WebFetch) keeps its name.
- `subagent_type: "stack:<name>"` means the ZCode agent `stack-<name>` (installed next to your other agents). If it is missing, fall back to `general-purpose` and paste the agent's body from `<stack>/agents/stack-<name>.md` into the brief.

## Names

- Slash names lose the colon: `/stack:poteto-mode` is `/stack-poteto-mode` here, and likewise for every command (`/stack-plan`, `/stack-plan-prd`, `/stack-build-fix`, …).
- The cursor-team-kit skills are bundled: `deslop`, `control-cli`, `control-ui`, `verify-this`, `run-smoke-tests`, `fix-ci`, `loop-on-ci`, `fix-merge-conflicts`, `check-compiler-errors` and `thermo-nuclear-code-quality-review` are `stack-deslop`, `stack-control-cli`, and so on.
- `<pstack>`, `<this skill's folder>` or `${CLAUDE_PLUGIN_ROOT}` in a skill means the folder that holds `skills/`, `docs/` and `rules/` (a user install: `~/.zcode`; the plugin install: the `stack` plugin folder).

## Models

Run every role on the session model. The model tables in `stack.md` and `setup-stack`, the Cursor slugs (`grok-4.7-xhigh-fast`, `claude-opus-5-5-xhigh`), and the `openrouter:` panel entries do not apply in ZCode: omit the model on every spawn. Keep panels diverse by different briefs, not different models. The rejected-slug rule never fires because no slug is passed.

## Subagents

- `readonly: true` → spawn an `Explore` subagent, put "do not edit any files" in the brief, and check `git status` after it returns.
- `environment: "cloud"` or `isolation: "worktree"` → create a git worktree with Bash first and point the subagent's `cwd` at it.
- `is_background: true` → `run_in_background: true`.
- Cursor-only features (Automations, Bugbot, cloud agents, `/loop`, custom modes, `option+enter`) are skipped with one line — `Skipped in ZCode: <step>. <reason>.` — and a placeholder, the same protocol the Cursor skills already use for missing features.

## Not wired in the ZCode port

- The guardrail hooks (Bash preflight, GateGuard, config protection, Hookify, end-of-turn checks) are Claude Code plugin hooks and are not installed here. Apply their intent by hand: never pass `--no-verify`, never weaken linter or formatter configs, strip `console.log` before finishing.
- `/stack-setup-stack`'s rules step writes `~/.claude/rules/stack/` in Claude Code. In ZCode, copy the chosen rule sets from `<stack>/rules/` into the project's instructions (or memory) instead, or read them when the step needs them.
- `~/.cursor/` paths and the `pstack-models` rule file do not exist here; model choice is the session model (see Models).
