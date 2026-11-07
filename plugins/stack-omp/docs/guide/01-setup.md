# Set up pstack

In this page you install the plugin, pick which models pstack uses, and run your first task. Setup is one command plus a short conversation.

## Install the plugin

Add the astack marketplace and install the stack plugin:

```text
/marketplace add NewbeeTryToCode/astack
/marketplace install stack@astack
```

omp confirms the plugin is installed. Skills are `stack-<name>`, agents are `stack-<name>`, and commands keep the `stack:` prefix, such as `/stack:plan`. The [omp adapter](../harness/omp.md) covers the rest.

## Pick your models

Run:

```text
/skill:stack-setup-pstack
```

[`/skill:stack-setup-pstack`](../../skills/stack-setup-pstack/SKILL.md) detects the models you have access to, asks for a reasoning budget, shows you each role (code delegates, judgment, the review panels), and asks what you want. Answer the questions. It writes `~/.omp/agent/RULES.md`, a small rule every pstack skill reads.

The setup skill picks from `omp models --json`. It uses `xhigh` by default, lifts a model to its highest supported level under `unlimited`, and never exceeds `max`. A model that does not support the chosen level uses the highest level it does support.

You only override what you care about. A role with no line in the rule keeps the skill's default. To restore a default, delete that role's line. A rerun of `/skill:stack-setup-pstack` keeps any role whose model differs from the default. When a default changes, a rule written before the change still pins the old default, so delete those role lines, or delete the file, then run `/skill:stack-setup-pstack` again.

A role with no selector runs on the session model. Panels are lists; one subagent runs per entry, and the list length sets the panel size. Setup also configures `swarm workers`, the default for every swarm worker unless a race names a model for each arm.

## Accept the verification offers, or don't

At the end of setup, `/skill:stack-setup-pstack` looks for a way to prove app behavior in your project, either a `verify-*` skill or an existing harness. If it finds neither, it offers once to generate one with [`/skill:stack-create-verification-skill`](../../skills/stack-create-verification-skill/SKILL.md).

Say yes and it writes `.omp/skills/verify-<app>/`, a project-local skill that teaches agents to drive your app the way a user does. It proves the skill works once before handing it over. Say no and setup moves on. You can run `/skill:stack-create-verification-skill` yourself any time. [Verify and ship](./06-verify-and-ship.md#create-a-project-verification-skill) covers it in depth.

If you're new to pstack, say yes. An agent that can check its own work keeps going until the check passes. An agent that can't hands every result back to you to check by hand. Of everything in this guide, the verification skill pays off the most.

Then setup offers once to generate a formal verification skill with [`/skill:stack-create-formal-verification-skill`](../../skills/stack-create-formal-verification-skill/SKILL.md), unless the project already has one. Tests check the cases someone thought to write. A formal verification skill checks one key property of your code, such as "a job never runs twice at once", in every case within a stated scope. Say yes when your code has concurrency, retries, a state machine, or a parser, where a bug is costly and tests rarely reach the case that breaks. Otherwise say no, and run it later if that changes. [Verify and ship](./06-verify-and-ship.md#prove-a-property-with-a-formal-verification-skill) covers it.

After setup, start a new chat. The model rule applies to new sessions.

## Keep the cost in check

pstack spends extra tokens on subagents and review panels. That's the price of the rigor. To spend fewer:

- Rerun `/skill:stack-setup-pstack` and pick a smaller reasoning budget or cheaper models. A strong model in the main chat with cheaper, faster models in the code roles is a good split.
- Leave a role without a selector so it runs on the session model.
- Shorten a panel list. Each entry runs one subagent.
- Save `/skill:stack-poteto-mode` for work that needs rigor. A small, obvious edit doesn't.

## Run your first task

Pick something real but small, and describe it the way you'd describe it to a colleague:

```text
/poteto-mode add a --json flag to this command. text output stays byte-identical. verify both.
```

Watch the todo list. Its first items are the matched playbook's steps copied in, the Feature playbook for this prompt. If `/skill:stack-poteto-mode` skips a step, the step stays in the list with `skip: <reason>`, so you can see what it chose not to do.

From here you can type normal follow-ups. To keep `/skill:stack-poteto-mode` on for the whole chat, use omp's plan mode or loop mode. A plain invocation attaches the skill to one message, and it fades as the chat moves on.

Next: [Route work through `/skill:stack-poteto-mode`](02-poteto-mode.md).
