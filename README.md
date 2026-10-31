# astack

A Claude Code plugin marketplace with one plugin, `stack`. It merges two toolkits into one with no contradicting instructions:

- **pstack** by Lauren Tan ([cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack)): judgment, verification, validation and the `poteto-mode` playbooks, plus the cursor-team-kit skills it routes to (`deslop`, `control-cli`, `control-ui`, `verify-this`, CI helpers).
- **ECC** by Affaan Mustafa ([everything-claude-code](https://github.com/affaan-m/everything-claude-code)): planning, design references, Rust, Python and TypeScript specialists, security, and guardrail hooks.

Each concern has one owner. The full table is in [`plugins/stack/docs/harness/stack.md`](plugins/stack/docs/harness/stack.md), and the reasoning is in [`docs/design.md`](docs/design.md).

## Install

```bash
/plugin marketplace add NewbeeTryToCode/astack
```

```bash
/plugin install stack@astack
```

Then run `/stack:setup-stack` once. It sets the model per role, installs the ECC rule sets you pick into `~/.claude/rules/stack/`, and checks the OpenRouter key for external adversaries.

## Use

| You want to | Type |
| --- | --- |
| Do any non-trivial task rigorously | `/stack:poteto-mode <task>` |
| Plan before code (Feature and Refactoring work does this for you) | `/stack:plan <feature>` or `/stack:plan-prd` |
| Have adversaries break a diff, keeping only proven findings | `/stack:interrogate` |
| Prove a claim with fresh evidence | `/stack:verify-this` |
| Strip AI slop and stray comments before review | `/stack:deslop`, `/stack:no-comments` |
| Generate a project skill that drives your app like a user | `/stack:create-verification-skill` |
| Understand a subsystem or its history | `/stack:how`, `/stack:why` |
| Fix a Rust or Python build | `/stack:rust-build`, `/stack:build-fix` |
| Add a guardrail as a hook | `/stack:hookify` |

New to pstack? Ask `/stack:poteto-help`.

## What is inside

| | Count | From |
| --- | --- | --- |
| Skills | 92 | pstack 58, cursor-team-kit 10, ECC 23, stack 1 |
| Commands | 13 | ECC |
| Agents | 23 | pstack 2, cursor-team-kit 2, ECC 19 |
| Hooks | 4 events | ECC guardrails, run through `scripts/stack-hook.js` |

Not included: ECC's memory, continuous learning, session and cost hooks (memory belongs to [rewire](https://github.com/NewbeeTryToCode/rewire)), ECC's TDD workflow, verification loop, code-review command and PRP flow (pstack owns those), and ECC skills for frameworks outside Rust, Python and TypeScript.

## Develop

```bash
python3 tools/stack.py build
```

```bash
python3 tools/stack.py verify
```

```bash
python3 -m unittest discover -s tests -v
```

```bash
python3 tools/stack.py check
```

On Windows, use `python` in place of `python3` (the alias may be a Store stub).

Edit vendored files in `plugins/stack`, then run `python3 tools/stack.py diff` to turn the edits into patches. Files this repo owns live in `src/`. To move to a new upstream commit, follow [Updating upstream](docs/design.md#updating-upstream).

## License

MIT. The vendored sources keep their own MIT licenses in [`plugins/stack/LICENSES/`](plugins/stack/LICENSES/).
