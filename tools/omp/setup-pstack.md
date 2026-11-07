---
name: stack-setup-pstack
description: Configure which omp models pstack uses per role and at what reasoning budget. Use for /skill:stack-setup-pstack, "configure pstack models", or changing pstack's model choices in omp.
disable-model-invocation: true
---

# Setup pstack in omp

Read [the omp adapter](../../docs/harness/omp.md) first.

This skill changes models only. Read `../stack-setup-stack/SKILL.md` and follow its **Models** step. Do not install rules, check the OpenRouter key, or change hooks here.

Result: `~/.omp/agent/config.yml` gains `task.perCallModel`, `task.perCallModelAllow`, `task.enableEffort`, `task.maxEffort` and the `modelRoles.stack_*` entries; `~/.omp/agent/RULES.md` gains the managed `<!-- stack:models:start -->` role block. Re-running updates both.

If the operator asks for a model the config does not grant, run `setup-models.py` again with that selector. Per-call model selection is fail-closed in omp: an unapproved selector stops the spawn before it starts.
