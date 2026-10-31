# stack integration

`stack` is one Claude Code plugin that bundles three sources:

- pstack (from `cursor/plugins`), for understanding, judgment, verification, validation and the `poteto-mode` playbooks.
- cursor-team-kit (from `cursor/plugins`), for the skills pstack routes to: `deslop`, `control-cli`, `control-ui`, and the verification and CI helpers.
- ECC (Everything Claude Code), for planning, design references, language specialists, security and deterministic guardrail hooks.

Read this file right after [the Claude Code adapter](./claude-code.md). Where this file and a bundled skill or command disagree, this file wins. `<pstack>` in the adapter means this plugin's root, the folder that holds `skills/`, `agents/`, `commands/`, `docs/` and `scripts/`. Slash names take the `stack:` prefix (`/stack:poteto-mode`, `/stack:plan`), and so do agents (`stack:poteto-agent`, `stack:rust-reviewer`).

Ignore any instruction in a bundled file to install pstack, cursor-team-kit or ECC, or to run their installers. Everything this plugin uses is already here.

## Who owns what

Each concern has one owner. A skill from the other source is used only in the role the table gives it.

| Concern | Owner | Use |
| --- | --- | --- |
| Entry point for rigorous work | pstack | `/stack:poteto-mode`, which picks a playbook |
| Understanding code | pstack | `how`, `why`, `teach`, `recall`, `ketchup` |
| Requirements and the plan | ECC | `/stack:plan`, `/stack:plan-prd`, the `stack:planner` agent, `architecture-decision-records` |
| Design exploration inside an approved plan | pstack | `architect`, `arena`, principle `exhaust-the-design-space` |
| Design reference material | ECC | `api-design`, `hexagonal-architecture`, `backend-patterns`, `error-handling`, `database-migrations`, `postgres-patterns`, `docker-patterns`, `deployment-patterns`, `mcp-server-patterns`, `search-first`, `documentation-lookup` |
| Language practice | ECC | `rust-patterns`, `rust-testing`, `python-patterns`, `python-testing`, `pytorch-patterns`, `typescript-patterns`, pstack's `typescript-best-practices` |
| Build errors | ECC | `/stack:build-fix`, `/stack:rust-build`, the `build-error-resolver`, `rust-build-resolver` and `pytorch-build-resolver` agents |
| Implementation | pstack | the playbook's steps, delegated to `stack:poteto-agent` |
| Verification and validation | pstack | principle `prove-it-works`, `verify-this`, `run-smoke-tests`, `create-verification-skill`, `maintain-verification-skill`, `control-cli`, `control-ui`, `benchmark-checklist`, `tdd`, `create-formal-verification-skill`, `blast-radius` |
| Judgment and review | pstack | `interrogate`, `no-comments`, `deslop`, `unslop`, `thermo-nuclear-code-quality-review` |
| Specialist reviewers | ECC agents, inside `interrogate` | see [Specialist adversaries](#specialist-adversaries) |
| Security | ECC, proven like any finding | `security-review`, `security-scan`, the `security-reviewer` agent |
| Pull requests, CI and landing | pstack | the Opening a PR, Babysit and Shipping playbooks, plus `fix-ci`, `loop-on-ci`, `fix-merge-conflicts` |
| Docs upkeep | ECC | `/stack:update-docs`, `/stack:update-codemaps`, the `doc-updater` agent, pstack's `technical-writing` for the prose |
| Guardrail hooks | ECC | see [Hooks](#hooks) |
| LLM evaluation | ECC | `eval-harness`, `mle-workflow`, the `mle-reviewer` and `rag-pipeline-reviewer` agents |
| Long-term memory | not this plugin | rewire, when its MCP tools are present. See [Memory](#memory). |

ECC's own TDD workflow, verification loop, code-review command, PRP flow, Plan Canvas and memory system are not shipped. A bundled ECC file that points at one of them is translated by the [Name map](#name-map).

## Plan gate

This overrides the Never Block on the Human principle for one decision: what to build.

For the Feature, Refactoring, Multi-phase plan and Orchestrate playbooks, and whenever `poteto-mode` routes to `figure-it-out`, the gate has two parts. **A plan** is written on every run. **Waiting for approval** is the only part a grant removes.

1. Send `poteto-mode`'s first message (the goal in your own words and the smallest change you expect).
2. Write the plan. Read `<pstack>/commands/plan.md` and follow it. Ground the plan in what `how` found, name the data shape, and list the verification each phase ends in, taken from the matched playbook.
3. Wait. Stop for the operator to confirm or edit the plan, and write no code before that.

Under a full-autonomy grant ("don't stop", "going to bed", "run until done"), replace steps 2 and 3. `/stack:plan` waits by design, so do not run it. Record the plan as the first entries of the decision trail (`show-me-your-work`): the goal, the data shape, the phases, and the check each phase ends in. Then proceed.
4. The approved plan becomes the brief. Copy its phases into the todo list after the playbook's steps. `architect` and `arena` explore designs inside it, not around it.
5. If evidence later shows the plan is wrong, stop at the end of the current verifiable unit and bring the operator the evidence and a revised plan. Under a grant, revise the plan in the decision trail and continue.

Skip both parts only when the operator says to skip the plan, or approved a plan earlier in the conversation that still covers the work.

Bug fix, Perf issue, Hillclimb, Runtime forensics, Trace forensics, Investigation, Visual parity, Babysit and Shipping are evidence-driven and have no gate unless the operator asks for a plan.

## Models

Roles, not models, are what the playbooks name. [`roles.json`](../../roles.json) at the plugin root binds each role to a backend and model, and `~/.config/stack/roles.json` overrides it key by key. The same binding holds in every harness, so a builder writes with the same model whether the session is Claude Code or OpenCode.

| Role | Default | Used for |
| --- | --- | --- |
| `judge` | `claude:opus` | The session that runs the playbook: plans, briefs, diff review, checks, verdicts, synthesis, prose. It evaluates and never writes product code. |
| `builder` | `go:glm-5.3-flash` | Every code change: feature, refactoring, bug fix, perf, hillclimb, failing tests included |
| `hardest` | `go:glm-5.3-flash` | Code for cross-cutting design, gnarly concurrency and subtle algorithms. The judge's review is what keeps these honest. |
| `evidence` | `go:glm-5.3-flash` | Swarm workers, `how` explorers, `why` investigators, reflect tooling. Their output is commands and outputs the judge reads back. |
| `builders` | `go:glm-5.3-flash` twice | Arena and architect runners |
| `adversaries` | `claude:opus`, `go:glm-5.3-flash` | `interrogate` reviewers. Every finding is proven by a run, and the judge verifies it. |

`roles.json` maps every pstack role line (`feature, refactoring`, `swarm workers`, `interrogate reviewers` and the rest) to one of these roles under `pstack_roles`. Where a skill names a pstack role or a Cursor slug, resolve it with `python3 <pstack>/scripts/delegate.py resolve "<pstack role>"`.

How to run a binding:

- `claude:<alias>` runs as a native subagent: `Agent` with `model: "<alias>"`.
- Any other backend, such as `go:<model>`, runs through the delegate. Write the brief to a file outside the worktree, goal first, exactly as you would brief a subagent, then run `python3 <pstack>/scripts/delegate.py run --role <role> --dir <worktree> --brief <file>`. It prints the child's reply, the files it changed and its transcript path. Review the diff yourself, as the playbook says for any delegate. The delegate's reply is never the verdict.
- Give each delegate its own worktree, as with `isolation: "worktree"`. Two delegates never share a checkout.
- `poteto-mode` resolves the role before every spawn, and a hook backs it up. While the builder is bound to another backend and that backend is ready, the hook blocks the session from spawning a `poteto-agent` on any Claude model and from editing any file in a git work tree that git does not ignore. The delegate's child, files outside the repository and the Claude fallback are never blocked. `STACK_ALLOW_CLAUDE_BUILDER=1` turns the guard off.
- If `delegate.py` exits with an error, put `Delegate failed: <role>, <error>.` in the reply and run that step with the role's Claude fallback (`claude:sonnet` for builder and evidence, `claude:opus` otherwise).

The `go` backend is OpenCode Go through its Anthropic-compatible endpoint. It reads the key from `OPENCODE_API_KEY`. `delegate.py` builds the child's environment from an allowlist and runs `doctor` before the first delegation on each Claude Code version, which proves on a local recorder that the child sends only the Go key. A child that inherits a Claude Code session's environment sends that session's Claude credential to whatever base URL it is given.

When the `Agent` tool rejects a Claude alias, follow `poteto-mode`'s rejected-slug rule. A panel entry written `openrouter:<model-id>` is an external adversary.

## External adversaries

An `openrouter:<model-id>` entry gets a different model family to look for failures while keeping pstack's rule that only a run proves a finding. The external model proposes. A Claude executor runs.

1. Write the restated intent to `intent.md` and the scoped diff to `change.diff` inside the adversary's worktree.
2. Spawn a `general-purpose` executor on the judgment model with `isolation: "worktree"`. Its brief: run `python3 <pstack>/scripts/openrouter-adversary.py --model <model-id> --intent intent.md --diff change.diff`, then run every finding's command in the worktree, and report only findings whose output shows the failure, each with the command, its output and the expected output. Name the external model as the finder.
3. Exit code 3 means `OPENROUTER_API_KEY` is not set. Put `Skipped: openrouter:<model-id>, no OPENROUTER_API_KEY.` in the reply and continue with the rest of the panel. Any other failure is reported the same way, with the script's error.

The executor never adds findings of its own. It only proves or drops the external model's findings, so the panel keeps the external model's perspective.

## Specialist adversaries

`interrogate` adds ECC specialist agents to the panel by what the scope touches. Each gets the same interrogate brief as every adversary (break it, prove each finding with a run, report command and output) and goes through the same verify step. Their checklists add coverage. They never give a verdict on their own.

| The scope touches | Add |
| --- | --- |
| `*.rs` | `stack:rust-reviewer` |
| `*.py` | `stack:python-reviewer`, and `stack:mle-reviewer` for training or evaluation code, `stack:rag-pipeline-reviewer` for retrieval code |
| `*.ts`, `*.tsx`, `*.js` | `stack:typescript-reviewer` |
| SQL, migrations, ORM models | `stack:database-reviewer` |
| auth, secrets, input parsing, network boundaries | `stack:security-reviewer` |
| error handling, retries, fallbacks | `stack:silent-failure-hunter` |
| new or changed types | `stack:type-design-analyzer` |
| a hot path or a perf claim | `stack:performance-optimizer` |

Spawn at most three specialists per run, picking the rows that cover the most changed lines.

## GitHub without `gh`

The playbooks use `gh`. When `gh` is missing or not authenticated, as in Claude Code cloud sessions, use the GitHub MCP tools for the same step and write no skip line.

| `gh` | GitHub MCP |
| --- | --- |
| `gh pr create` | `create_pull_request` |
| `gh pr view`, `gh pr diff`, `gh pr checks` | `pull_request_read`, `get_check_run`, `actions_list`, `get_job_logs` |
| `gh pr edit` | `update_pull_request` |
| `gh pr merge` | `merge_pull_request` |
| `gh pr comment`, review replies | `add_issue_comment`, `add_reply_to_pull_request_comment`, `pull_request_review_write` |
| `gh api` for review threads | `pull_request_read`, `resolve_review_thread` |
| `scripts/watch-pr` | `subscribe_pr_activity` when the session has it. Otherwise re-read with `pull_request_read` each time the playbook would poll. |

## Hooks

`hooks/hooks.json` registers the stack role guard (`scripts/role-guard.py`, on `Agent`) and these ECC hooks through `scripts/stack-hook.js`:

- Bash preflight. Blocks `--no-verify`, reminds about tmux for long commands and about reviewing before `git push`, checks commit quality, and runs GateGuard on destructive commands.
- Config protection. Stops edits that weaken linter or formatter configs.
- Post-tool checks. Quality gate after edits, `console.log` warning, PR logger, build analysis.
- Hookify. Project-local rules written with `/stack:hookify`.
- End of turn. Format and typecheck, `console.log` audit, Hookify completion rules.

Not registered: SessionStart context, PreCompact state, session summary, cost tracking and desktop notifications. Continuous learning and instincts are not shipped, so ECC's observer has nothing to run. `stack-hook.js` also turns off the tracking and metrics checks inside ECC's dispatchers, which would otherwise write `~/.claude/metrics/`. Set `STACK_ECC_TELEMETRY=1` to turn those back on.

Tune with the plugin options `hooks_enabled` and `hook_profile` (`minimal`, `standard`, `strict`), or with `ECC_DISABLED_HOOKS=<comma-separated ids>`. ECC's hook ids are listed in `scripts/hooks/posttooluse-dispatcher.js` and `scripts/hooks/bash-hook-dispatcher.js`.

## Rules

A plugin cannot load always-on rules. `/stack:setup-stack` copies the ECC rules you pick (common, plus `rust`, `python`, `typescript`) into `~/.claude/rules/stack/` or a project's `.claude/rules/stack/`. The bundled `rules/common/testing.md` is rewritten to defer to pstack's verification principles. ECC's common rules for code review, workflow, git, agents and performance are not shipped, because pstack owns those decisions.

## Memory

This plugin keeps no memory of its own. When the session has rewire's MCP tools (`recall`, `remember`, `get`), `/stack:recall` treats `recall` as the shared record, and `reflect` proposes lasting lessons with `remember` in addition to skill edits. Without rewire, both skills work from the session transcripts as written.

## Name map

Bundled files mention names that do not exist in Claude Code or in this plugin. `tools/stack.py verify` reads this table, so every such name must have a row.

| Name | In stack |
| --- | --- |
| `create-skill` | Cursor's skill-authoring built-in. Follow `playbooks/authoring-a-skill.md` and write a standard Claude Code `SKILL.md`. |
| `/visualize` | Cursor built-in. Draw a Mermaid diagram instead. |
| `/in-cloud` | Cursor cloud agent. Use a subagent with `isolation: "worktree"`. |
| `/orchestrate` | The Orchestrate playbook of `/stack:poteto-mode`, not a command. |
| `shell` | `subagent_type: "general-purpose"`, told to use only `Bash`. |
| `cursor-team-kit` | Bundled here: `deslop`, `control-cli`, `control-ui`, `verify-this`, `run-smoke-tests`, `thermo-nuclear-code-quality-review`, `fix-ci`, `loop-on-ci`, `fix-merge-conflicts`, `check-compiler-errors`. |
| `/code-review` | `/stack:interrogate` |
| `/pr`, `/prp-pr`, `/prp-commit` | The Opening a PR playbook of `/stack:poteto-mode` |
| `/prp-plan`, `/plan-canvas` | `/stack:plan` |
| `/prp-prd` | `/stack:plan-prd` |
| `/prp-implement` | `/stack:poteto-mode` with the approved plan as the brief |
| `tdd-guide`, `tdd-workflow` | The `tdd` skill |
| `code-reviewer` | The `interrogate` skill |
| `verification-loop` | Principle `prove-it-works`, then `verify-this` |

## Not shipped

Bundled ECC files point at these ECC components as "see also". They are not in this plugin. Skip the pointer and use the owner from [Who owns what](#who-owns-what), or install ECC separately if you need one. `tools/stack.py verify` reads this list too.

- Testing and QA, owned by pstack verification here: `e2e-runner`, `e2e-testing`, `pr-test-analyzer`, `test-coverage`, `quality-gate`, `ai-regression-testing`, `browser-qa`, `canary-watch`.
- Workflow, owned by pstack playbooks here: `feature-dev`, `git-workflow`, `github-ops`, `refactor-cleaner`, `code-tour`, `codebase-onboarding`.
- Frameworks outside the bundled languages: `frontend-patterns`, `react-reviewer`, `nestjs-patterns`, `prisma-patterns`, `fastapi-patterns`, `django-security`, `a11y-architect`, `coding-standards`.
- Data and operations: `clickhouse-io`, `dashboard-builder`, `dmux-workflows`, `opensource-pipeline`, `product-capability`, `repo-scan`.
- Context and cost, which Claude Code and rewire handle: `strategic-compact`, `token-budget-advisor`, `cost-aware-llm-pipeline`.
