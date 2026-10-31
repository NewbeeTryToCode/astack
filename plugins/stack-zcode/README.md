# stack for ZCode

astack's `stack` plugin ported to ZCode: pstack (judgment, verification, the `poteto-mode`
playbooks), cursor-team-kit (`deslop`, `control-cli`, `control-ui`, `verify-this`) and ECC
(planning, specialists, security) as 105 `stack-*` skills and 23 `stack-*` agents.

- every skill keeps its upstream name under the `stack-` prefix, so nothing shadows other skills
- the Claude Code adapter is replaced by [docs/harness/zcode.md](docs/harness/zcode.md) — read it once per session
- commands are skills: `/stack:plan` is `stack-plan` here
- the guardrail hooks are Claude Code plugin hooks and are not wired in this port (see the adapter)

Install (user scope): `python3 tools/port-zcode.py --install` from the astack repository,
or add this repository as a ZCode marketplace and install `stack@astack`.
