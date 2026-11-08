# omp adapter

`stack` runs in omp as prefixed skills, commands, agents and rules. Read this file once per session, right after a skill sends you here. It maps the Claude Code and Cursor names in the bundled skills to omp. Where this file and a bundled skill or `docs/harness/stack.md` disagree about omp specifics, this file wins.

## Tools and invoking skills

- `Task` is omp's `Task` tool (its wire name is `task`). `AskQuestion` means `ask`. The todo list is `todo`. `Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob` and `WebSearch` keep their names.
- A step that says to run another bundled skill (`how`, `interrogate`, `deslop`, `verify-this`, a `principle-*`, or a command like `plan`) means: read `skill://stack-<name>` or type `/skill:stack-<name>`. omp may also offer the plugin-prefixed form `/stack:<upstream-name>` for a skill; prefer the `skill://` form in a subagent brief. Commands are different: `/stack:plan`, `/stack:plan-prd`, `/stack:build-fix`, and the other `commands/*.md` entries stay `/stack:<name>`.
- `<stack>` means the plugin root, the folder that contains `skills/`, `commands/`, `agents/`, `rules/`, `scripts/`, `extensions/` and `docs/`. A command's body may use `$ARGUMENTS`; omp expands it the same way.

## Names

- Skills are `stack-<name>`: `stack-poteto-mode`, `stack-how`, `stack-interrogate`, `stack-deslop`, `stack-verify-this`, `stack-principle-prove-it-works`.
- Agents are `stack-<name>`: `stack-poteto-agent`, `stack-judgment`, `stack-comment-sicko`, `stack-rust-reviewer`, `stack-security-reviewer`, and the rest.
- Commands keep their upstream name under the plugin prefix: `/stack:plan`, `/stack:plan-prd`, `/stack:rust-build`, `/stack:hookify`.
- `subagent_type: "stack:<name>"` means `agent: "stack-<name>"`. `subagent_type: "general-purpose"` means `agent: "task"`. `readonly: true` means `agent: "scout"` with "do not edit any files" in the brief, then check `git status` after it returns.

## Models

omp does not use Claude aliases such as `opus` or `sonnet`. A Task spawn takes one exact selector, `provider/model-id[@upstream][:level]`.

1. Read the managed block in `~/.omp/agent/RULES.md` between `<!-- stack:models:start -->` and `<!-- stack:models:end -->`. It maps each astack role to one or more exact selectors. If the block is missing, run `/skill:stack-setup-stack`.
2. Pass the selector as `model` on the Task item. For a panel, spawn one subagent per selector in the list. `openrouter:<model-id>` is not a Task model: it is an external adversary, handled below.
3. Per-call model selection requires `task.perCallModel: on` in the operator's `~/.omp/agent/config.yml`. A project's `.omp/config.yml` can lower the mode but cannot turn it on or grant a model. The model must also be granted by a configured `modelRoles` value, by a bundled or user-level agent frontmatter `model`, or by the parent's live model, and must pass `task.perCallModelAllow` when that list is set.
4. For judgment roles, use `agent: "stack-judgment"` and **omit** `model`. `task.agentModelOverrides.stack-judgment` pins it to `@stack_judgment`; `retry.fallbackChains.stack_judgment` then switches to the configured fallback on a usage limit. A per-call `model` disables omp's retry fallback, so do not pass one for this agent.
5. `task.enableEffort` exposes the coarse `effort` hint. A selector that ends in `:high`, `:xhigh`, `:max` or another supported level sets the level directly. Keep the model family the role names; only change the level or `-fast` speed.
6. If omp rejects a selector before the spawn, the call fails preflight. Do not quietly substitute the session model. Name the rejection, then use a selector from `modelRoles` that the operator approved, or ask.
7. `resolvedModel`, `resolvedModelIdentity`, `resolvedThinkingLevel` and `resolvedModelIsFallback` in `details.results` are the proof of what ran. A role is routed only when those fields match the role's selector.

## Judgment fallback

The managed block can name `agent stack-judgment` on the judgment line. That agent has no per-call model. The operator's `task.agentModelOverrides.stack-judgment` resolves `@stack_judgment`, and `retry.fallbackChains.stack_judgment` plus `retry.fallbackOn` switch to the fallback selector when the primary hits a usage limit. This is the only path that gives automatic fallback: a Task item that passes `model` runs as a per-call worker, and omp disables retry fallback for those.

If the block has no fallback, spawn `agent: "stack-judgment"` with no model and the session model applies; otherwise follow the block's selector.

`/skill:stack-setup-stack` detects models with `omp models --json`, writes `modelRoles.stack_code`, `stack_judgment`, `stack_panel_primary`, `stack_panel_extra` and `stack_interrogate_extra`, enables per-call selection, writes the optional judgment fallback, and writes the same mapping to `RULES.md`.

## Subagents

- omp runs Task subagents in the background by default. Omit `run_in_background`; it is not an omp field.
- A child starts with no conversation. Put the goal, contract, target files, change and acceptance in `task`. Use `context` for shared background and `local://` files or absolute paths for large material. `solutionSpace` describes how open-ended the work is; it is not the brief.
- `isolation: "worktree"` or a cloud environment means `isolated: true` when `task.isolation.enabled` is on. Otherwise create a worktree with Bash first and point the worker at it. `isolation: "apply"` is the same idea; omp applies only when `task.isolation.apply=true`.
- The child must finish through `yield`. Read the full output from `agent://<id>` and the transcript from `history://<id>`. Review the diff yourself; do not pass through the child's summary.
- For structured returns, pass `outputSchema` and `schemaMode: "strict"`. A permissive schema can accept an invalid payload with a warning.

## Plan gate

The plan gate in `docs/harness/stack.md` still applies. Feature, Refactoring, Multi-phase plan, Orchestrate and `figure-it-out` write a plan with `/stack:plan` and wait for the operator. Under a full-autonomy grant, record the plan as the first decision-trail entries and proceed.

## External adversaries

The setup's default panels use OpenCode models, so no `OPENROUTER_API_KEY` is needed. An `openrouter:<model-id>` entry is still supported when the operator adds one: it is not passed to Task, and gets a different model family to look for failures while keeping pstack's rule that only a run proves a finding.

1. Write the restated intent to `intent.md` and the scoped diff to `change.diff` inside the adversary's worktree.
2. Spawn `agent: "task"` with `isolated: true` (or a worktree) on the judgment model. Its brief: run `python3 <stack>/scripts/openrouter-adversary.py --model <model-id> --intent intent.md --diff change.diff`, then run every finding's command in the worktree, and report only findings whose output shows the failure, each with the command, output and expected output. Name the external model as the finder.
3. Exit code 3 means `OPENROUTER_API_KEY` is not set. Put `Skipped: openrouter:<model-id>, no OPENROUTER_API_KEY.` in the reply and continue with the rest of the panel. Any other failure is reported the same way, with the script's error.

## Specialist adversaries

`interrogate` adds the specialist agents by what the scope touches, exactly as `docs/harness/stack.md` says. In omp their names carry the prefix: `stack-rust-reviewer`, `stack-python-reviewer`, `stack-mle-reviewer`, `stack-rag-pipeline-reviewer`, `stack-typescript-reviewer`, `stack-database-reviewer`, `stack-security-reviewer`, `stack-silent-failure-hunter`, `stack-type-design-analyzer`, `stack-performance-optimizer`. Spawn at most three per run.

## GitHub without `gh`

The playbooks use `gh`. When `gh` is missing or not authenticated, use the GitHub MCP tools for the same step and write no skip line. The mapping is the same as `docs/harness/stack.md`: `create_pull_request`, `pull_request_read`, `get_check_run`, `actions_list`, `get_job_logs`, `update_pull_request`, `merge_pull_request`, `add_issue_comment`, `add_reply_to_pull_request_comment`, `pull_request_review_write`, `resolve_review_thread`, `subscribe_pr_activity`. When the session has no GitHub MCP and no `gh`, skip the step with `Skipped in omp: <step>. <reason>.` and leave a placeholder.

## Hooks

`extensions/stack-guardrails.mjs` maps omp events to the vendored ECC hook scripts:

| omp event | ECC hook |
| --- | --- |
| `tool_call` for `bash` | `PreToolUse` Bash preflight |
| `tool_call` for `edit` or `write` | `PreToolUse` config protection and Hookify |
| `tool_result` | `PostToolUse` sync and async checks |
| `before_agent_start` with a prompt | `UserPromptSubmit` Hookify |
| `session_stop` | `Stop` Hookify, format/typecheck and console.log audit |

Controls: `ECC_HOOKS_ENABLED=false` turns the guardrails off; `ECC_HOOK_PROFILE=minimal|standard|strict` selects the profile; `ECC_DISABLED_HOOKS=<ids>` disables individual hooks; `STACK_ECC_TELEMETRY=1` turns ECC's tracking checks back on. The Claude plugin options `hooks_enabled` and `hook_profile` do not apply in omp; use the environment variables.

The extension runs the vendored ECC scripts with `node` or `bun` from `PATH`. Set `STACK_NODE` to an absolute runtime path when neither is on `PATH`; without a runtime the guardrails fail open and report the spawn error.

## Rules

`/skill:stack-setup-stack` installs the chosen ECC rule sets as flat files:

- user scope: `~/.omp/agent/rules/stack-<set>-<rule>.md`
- project scope: `<repo>/.omp/rules/stack-<set>-<rule>.md`

omp's native and plugin rule loaders scan `rules/*.md` non-recursively, so the sets are flattened. Do not install into `~/.claude/rules/`; omp does not read that directory. `~/.omp/agent/RULES.md` is the sticky rule that carries the model routing block and is also delivered to task subagents.

## MCP servers

The plugin ships `.mcp.json`, which omp discovers for an installed plugin: one `context7` server over Streamable HTTP at `https://mcp.context7.com/mcp`. `/mcp list` names it, `/mcp disable context7` hides it for the profile, and `stack-docs-lookup` needs it. Servers for GitHub, Slack and issue trackers come from the operator's own configuration, not from this plugin.

omp prefixes plugin MCP tools with the plugin name, so the tools are `mcp__stack_context7_resolve_library_id` and `mcp__stack_context7_query_docs`, not the `mcp__context7__resolve-library-id` and `mcp__context7__query-docs` that the bundled `docs-lookup` text names. omp maps the `tools:` list of `stack-docs-lookup` to them. When a skill names `mcp__context7__...`, call the prefixed tool.

## Memory

When the session has rewire's MCP tools (`recall`, `remember`, `get`), `/skill:stack-recall` treats `recall` as the shared record, and `skill://stack-reflect` proposes lasting lessons with `remember` in addition to skill edits. Without rewire, both skills work from the session transcripts as written.

## Paths and transcripts

- `~/.claude/rules` → `~/.omp/agent/rules`
- `~/.claude/projects/<slug>/<session>.jsonl` → `~/.omp/agent/sessions/<slug>/<timestamp>_<id>.jsonl`
- `~/.claude/settings.json` → `~/.omp/agent/config.yml`
- `CLAUDE_PLUGIN_ROOT` → `<stack>`
- The newest `.jsonl` directly in `~/.omp/agent/sessions/<slug>/` is the current session. Its `<session>/subagents/` folder, when present, holds subagent transcripts.

## Cursor-only features

Cursor Automations, Bugbot, Cursor cloud agents, `/loop` and Cursor's built-in PR tool have no omp equivalent. Skip the step with one line, `Skipped in omp: <step>. <reason>.`, then continue. A Bugbot comment on a GitHub PR is an ordinary review thread; triage it with `gh` or the GitHub MCP tools.

## Name map additions

| Name | In omp |
| --- | --- |
| `claude-code.md` | `docs/harness/omp.md` |
| `~/.claude/rules/pstack-models.md` | `~/.omp/agent/RULES.md`, plus `modelRoles` and `task.perCallModel` in `~/.omp/agent/config.yml` |
| `hooks/hooks.json` | `extensions/stack-guardrails.mjs` |
| `CLAUDE_PLUGIN_ROOT` | `<stack>` |
| `AskQuestion` | `ask` |
| `TodoWrite` | `todo` |
| `subagent_type: "stack:<name>"` | `agent: "stack-<name>"` |
| judgment role | `agent: "stack-judgment"` with no `model`; the role and fallback chain apply |
| `subagent_type: "general-purpose"` | `agent: "task"` |
| `readonly: true` | `agent: "scout"`, brief says "do not edit any files" |
| `run_in_background: true` | omit; omp runs subagents in the background by default |
| `isolation: "worktree"` | `isolated: true` when enabled, otherwise a worktree created with Bash |
