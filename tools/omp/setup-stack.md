---
name: stack-setup-stack
description: Set up the stack plugin in omp. Picks the model for each role, writes the per-role routing rule, installs the ECC rule sets you choose, checks the OpenRouter key for external adversaries, and reports which guardrails are on. Use for /skill:stack-setup-stack or "configure stack in omp".
disable-model-invocation: true
---

# Setup stack in omp

Read [the omp adapter](../../docs/harness/omp.md) first. It names the defaults and the per-call model gate this skill writes.

## 1. Models

Run `omp models --json` and keep the `kind: "chat"` entries. Each entry has a `selector` (`provider/model-id`), a `name`, and a `thinking` list. If the command fails, ask the operator to paste their selectors.

**(a) Budget.** Use the `ask` tool with these four options and these exact labels. Name the current budget when `~/.omp/agent/RULES.md` already has a `# stack model routing` block.

- `unlimited — max reasoning`
- `large — xhigh reasoning`
- `medium — high reasoning`
- `small — medium reasoning`

Map the answer to the target level: `max`, `xhigh`, `high`, `medium`.

**(b) Pick the models.** Use the `ask` tool. Offer the detected chat models as options, and mark the strongest reasoning model (the one with the most thinking levels, then the largest context) as recommended for judgment. Offer a fast, cheaper coding model as recommended for code. Ask separately for:

- the code model, used by feature, refactoring, bug-fix, perf-issue, hillclimb, how explorer, why investigators, reflect tooling and swarm workers;
- the judgment model, used by judgment and prose, the hardest tasks, how explainer, why synthesizer and reflect judgment;
- optionally a panel primary, used by arena runners, architect runners and interrogate reviewers. Default it to a non-Claude OpenCode model when the judgment model is Claude, so panels do not spend the Claude quota;
- optionally a panel extra. Use an OpenCode model. Do not add an `openrouter:` entry unless the operator asks for one;
- optionally a full interrogate reviewer list as a comma-separated set of exact selectors. One subagent runs per entry. Prefer three or more model families. This list overrides the single interrogate extra.

If only one chat model is available, use it for everything and say routing is mechanical until another model is configured.

**(b2) Ask for a judgment fallback.** When the judgment model is Claude, ask for a fallback, and recommend `opencode-go/gpt-5.6-luna`. The fallback is used only on a usage limit by default. Explain the limit: a Task item that passes a per-call `model` runs as a per-call worker, and omp disables retry fallback for those. To use the fallback, the judgment roles must spawn `agent: "stack-judgment"` with no `model`; the operator's `task.agentModelOverrides.stack-judgment` resolves `@stack_judgment`, and the role's fallback chain applies. The omp adapter already says this.

**(c) Apply the budget.** Append the level to each selector only when that model's `thinking` list contains it. If it does not, use the highest supported level at or below the target and tell the operator. For example, a model whose highest level is `high` becomes `provider/model:high` under `unlimited`.

**(d) Write the routing.** Run (use `python` instead of `python3` on Windows):

```bash
python3 <this skill's folder>/scripts/setup-models.py \
  --code <selector> --judgment <selector> \
  [--panel-primary <selector>] [--panel-extra <selector>] \
  [--interrogate-extra <selector>] \
  [--interrogate-reviewers <selector>,<selector>,...] \
  [--judgment-fallback <selector>] \
  --max-effort <level>
```

The script writes `task.perCallModel: on`, the exact `task.perCallModelAllow` list, `task.enableEffort: true`, `task.maxEffort`, the `modelRoles.stack_*` entries, and, when a fallback is given, `retry.fallbackOn`, `retry.fallbackChains.stack_judgment` and `task.agentModelOverrides.stack-judgment` in `~/.omp/agent/config.yml`. It writes the astack role block to `~/.omp/agent/RULES.md`. Pass `--agent-dir` to write a different profile. If it reports a selector problem, fix the selector and rerun; do not bypass the check with `--no-validate` unless the operator confirms the model is valid but discovery is stale.

The settings that grant per-call models must live in the operator layer. A project's `.omp/config.yml` can turn `task.perCallModel` off but cannot turn it on or grant a model.

## 2. Rules

Ask which ECC rule sets to install and where. Offer `common` (recommended for any project), `rust`, `python` and `typescript`, and the scopes `user` (`~/.omp/agent/rules/`, every project) and `project` (`<repo>/.omp/rules/` in the current repository). Rules load into every session, so suggest only the languages the operator works in. Then run:

```bash
python3 <this skill's folder>/scripts/install-rules.py --sets <sets> --scope <scope>
```

Add `--project <path>` for the project scope. Show the operator the files it printed. The script flattens each set to `stack-<set>-<rule>.md` because omp scans `rules/*.md` non-recursively.

## 3. External adversary

The default panels use omp models, so no OpenRouter key is needed. Only if the operator adds an `openrouter:<model-id>` entry, check whether `OPENROUTER_API_KEY` is set, without printing its value (`test -n "$OPENROUTER_API_KEY" && echo set`). If it is not, tell the operator that `interrogate` will skip the `openrouter:` panel entry. The executor still runs on an omp model; the external model only proposes findings.

## 4. Hooks and memory

The guardrails run through `extensions/stack-guardrails.mjs`. Tell the operator the controls:

- `ECC_HOOKS_ENABLED=false` turns all guardrails off.
- `ECC_HOOK_PROFILE=minimal|standard|strict` selects the profile.
- `ECC_DISABLED_HOOKS=<comma-separated ids>` disables individual hooks.
- `STACK_ECC_TELEMETRY=1` turns ECC's tracking checks back on. They are off by default.

The Claude plugin options `hooks_enabled` and `hook_profile` do not apply in omp.

Check whether the session has rewire's MCP tools (`recall`, `remember`). Say whether `/skill:stack-recall` and `skill://stack-reflect` will use them.

## 5. Report

One short list: the rule path and the roles that differ from the session default, whether a judgment fallback is configured and on which trigger, the rule sets installed and where, whether external adversaries are on, the hook profile, and whether rewire is connected.
