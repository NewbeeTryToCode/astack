# stack for omp

astack's `stack` plugin ported to omp: pstack (judgment, verification, the `poteto-mode`
playbooks), cursor-team-kit (`deslop`, `control-cli`, `control-ui`, `verify-this`) and ECC
(planning, specialists, security, guardrails) as prefixed skills, commands, agents and rules.

- every skill and agent keeps its upstream name under the `stack-` prefix
- commands stay `commands/*.md`; omp exposes them as `/stack:<name>`
- the Claude Code adapter is replaced by [docs/harness/omp.md](docs/harness/omp.md) — read it once per session
- rules are flattened into `rules/stack-<set>-<rule>.md` so omp's non-recursive rule loaders see them
- the ECC guardrails run through `extensions/stack-guardrails.mjs`, which maps omp events to the vendored hook scripts

Install from the repository marketplace:

```bash
/marketplace add NewbeeTryToCode/astack
/marketplace install stack@astack
```

Then run `/skill:stack-setup-stack` once. It detects your omp models, writes the per-role
routing rule to `~/.omp/agent/RULES.md`, enables per-call model selection in
`~/.omp/agent/config.yml`, and installs the rule sets you choose.

Version: 0.1.0
