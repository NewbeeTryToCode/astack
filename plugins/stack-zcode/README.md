# stack for ZCode

astack's `stack` plugin ported to ZCode: pstack (judgment, verification, the `poteto-mode`
playbooks), cursor-team-kit (`deslop`, `control-cli`, `control-ui`, `verify-this`) and ECC
(planning, specialists, security) as 105 `stack-*` skills and 23 `stack-*` agents.

- every skill keeps its upstream name under the `stack-` prefix, so nothing shadows other skills
- the Claude Code adapter is replaced by [docs/harness/zcode.md](docs/harness/zcode.md) — read it once per session
- commands are skills: `/stack:plan` is `stack-plan` here
- the guardrail hooks ship in ZCode `process` form (plugin `hooks/hooks.json`; `--install` registers them in the ZCode config)

Install (user scope): `python3 tools/port-zcode.py --install` from the astack repository —
copies the skills to `~/.zcode/skills`, the agents to `~/.zcode/agents`, and `docs/` + `rules/`
to `~/.zcode/` so every relative link from an installed skill resolves — or add this repository
as a ZCode marketplace and install `stack@astack`.
