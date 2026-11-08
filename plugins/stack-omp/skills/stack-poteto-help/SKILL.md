---
name: stack-poteto-help
description: Guides users through pstack setup, /poteto-mode, and picking the skill, playbook, or principle for a task. Type /poteto-help with a question.
metadata:
  origin: astack
---

# Poteto help

In omp, read [the omp adapter](../../docs/harness/omp.md) once per session before you follow this skill. It maps the upstream names in the bundled skills to omp.

Answer the user's question about pstack, hand them a prompt they can send, and link the file the answer came from. For a help question, don't start the work. The user asked how, and a pstack run spends real tokens, so let them send the prompt.

A message that asks for work, such as "use pstack to fix this bug", is not a help question. Read [`poteto-mode`](../stack-poteto-mode/SKILL.md), do the work under it, and mention once that a Custom Mode keeps it on.

This file maps questions to the skills and guide pages that hold the answers. Those files own the details. Read the file you route to before you quote it, and trust it when it disagrees with this map. The links here point into the installed plugin, which the user may not be able to open, so give the user the file's public copy: `https://github.com/cursor/plugins/blob/main/pstack/` followed by its path.

## Find out what they need

Infer the need from the message and the conversation. A named situation, such as "which skill reviews a PR?", goes straight to its section. If the need is still unclear, ask one multiple-choice question with these options, then answer only the section they pick:

- Get set up
- Start a task with `/skill:stack-poteto-mode`
- Pick a skill for a situation
- Fix a run that went wrong
- Make pstack my own

Check the state that changes the answer, and mention it only when it does:

- No `~/.omp/agent/RULES.md` means `/skill:stack-setup-pstack` hasn't run for this user, so every role uses its default model.
- No `verify-*` skill or other app harness in the project means agents have no scripted way to drive the app. Mention `/skill:stack-create-verification-skill` when the question is about proving a change works.
- No formal verification skill in the project means no property is checked past what tests reach. Mention `/skill:stack-create-formal-verification-skill` when the question is about a race, an invariant, or another case tests rarely hit. When one exists and the code it covers changed after the commit it records as last in sync, mention `/skill:stack-maintain-formal-verification-skill` if the question touches that code.

When the model rule is missing and it matters, ask whether the user wants to pick a model for each role and a reasoning budget now. It matters when the user is new, the question is about setup or cost, or the answer depends on which models run. Ask at most once per chat. If the need is also unclear, ask both questions together. Offer two choices:

- Now: give them `/skill:stack-setup-pstack` to type, and answer their question too.
- Later: answer their question, and add one line saying every role keeps its default model until they run `/skill:stack-setup-pstack`.

## Get set up

1. Install with `/add-plugin pstack` in chat, or from Customize in the sidebar.
2. Run [`/skill:stack-setup-pstack`](../stack-setup-pstack/SKILL.md). It asks for a reasoning budget, maps a model to each role, and writes a rule. The rule applies to new chats. Then it offers once each to generate a verification skill and a formal verification skill for the project, unless the project already has one.
3. Start a real task with `/skill:stack-poteto-mode`, a goal, and a check that can pass or fail.

Installing changes nothing until the user invokes a skill. Only `/skill:stack-setup-pstack` loads from the user's words. The [README](../../README.md) and [guide page 1](../../docs/guide/01-setup.md) have the details. Offer to word their first prompt with them, per [`references/prompting.md`](references/prompting.md).

If cost is the worry, say where the tokens go and how to spend fewer. pstack spends extra tokens on subagents and review panels. Rerun `/skill:stack-setup-pstack` and pick a smaller budget or cheaper models. A role with no selector runs on the session model, which saves tokens when the chat runs on Auto or a cheaper model. A shorter panel list runs fewer subagents, one for each entry. Save `/skill:stack-poteto-mode` for work that needs rigor.

This port installs in omp from the astack marketplace with `/marketplace add NewbeeTryToCode/astack` and `/marketplace install stack@astack`. Commands take a `stack:` prefix, such as `/stack:plan`, and skills are `/skill:stack-<name>`. The [omp adapter](../../docs/harness/omp.md) maps the Cursor names, and a step that needs a Cursor-only feature, such as Bugbot or Automations, is skipped with a one-line note.

Other tools can read the skills, because they use the Agent Skills format. But most workflow skills, including `/skill:stack-poteto-mode`, `/skill:stack-how`, `/skill:stack-why`, and `/skill:stack-teach`, spawn `stack-*` subagents with the role selector from `~/.omp/agent/RULES.md`; omp's plan mode and loop mode cover those parts.

## Start a task with `/skill:stack-poteto-mode`

`/skill:stack-poteto-mode` matches the task to a playbook, copies the playbook's steps into the todo list, and runs the other skills as the steps need them. A step it skips stays in the list as `skip: <reason>`. A good prompt states the goal and how to tell it's done. It doesn't list skills, because a hand-written sequence tends to drop or reorder steps the playbook would keep. Read [`references/prompting.md`](references/prompting.md) before you help word one. [Guide page 2](../../docs/guide/02-poteto-mode.md) has examples.

Whether `/skill:stack-poteto-mode` stays on depends on how the user starts it:

- Enter on `/skill:stack-poteto-mode` attaches the skill to one message. It fades as the chat moves on.
- Use omp's plan mode or loop mode when the mode should stay in context across turns.
- Otherwise start each new task with `/skill:stack-poteto-mode`.

Link the [upstream skills docs](https://cursor.com/docs/skills) when this comes up. Mid-chat, "new task" makes the mode match a fresh playbook. `/skill:stack-poteto-mode` already uses `stack-poteto-agent` for the subagents its playbook steps spawn. To get the same style from a subagent of your own, spawn it with `agent: "stack-poteto-agent"`.

## Pick a skill

The default answer is `/skill:stack-poteto-mode`, which runs most of the others when its steps need them. Name a skill directly when the user wants more or less of something than the playbook gives. Read the skill before you recommend it, and give one example prompt.

| The user wants to | Skill |
|---|---|
| Do any non-trivial task with rigor | [`/skill:stack-poteto-mode`](../stack-poteto-mode/SKILL.md) |
| Check that the agent understood their goal and the problem before it starts | [`/skill:stack-in-your-own-words`](../stack-in-your-own-words/SKILL.md) |
| Get a prompt rewritten deeper, not bigger, before sending it: what a top professional would add, their raw material and methods, and an outside check. It returns the prompt and doesn't do the task | [`/skill:stack-sharpen`](../stack-sharpen/SKILL.md) |
| Know how code works now, or where new code should live | [`/skill:stack-how`](../stack-how/SKILL.md) |
| Know why code is shaped this way, or where a number came from | [`/skill:stack-why`](../stack-why/SKILL.md) |
| Understand a change or subsystem, explained plainly | [`/skill:stack-teach`](../stack-teach/SKILL.md) |
| Catch up on their own recent work on a topic | [`/skill:stack-recall`](../stack-recall/SKILL.md) |
| Catch up on what changed in this chat since their last message, in plain words and small visuals, with every item waiting on them listed and decidable from the reply alone | [`/skill:stack-ketchup`](../stack-ketchup/SKILL.md) |
| Catch up like `/skill:stack-ketchup`, in a short subtitled video of slides, with the waiting calls as text under it | [`/skill:stack-ketchup-video`](../stack-ketchup-video/SKILL.md) |
| Know what a small diff could break outside itself | [`/skill:stack-blast-radius`](../stack-blast-radius/SKILL.md) |
| Settle types and module shape before code that crosses a function boundary | [`/skill:stack-architect`](../stack-architect/SKILL.md) |
| Get several attempts at one brief, merged into the best one | [`/skill:stack-arena`](../stack-arena/SKILL.md) |
| Run parallel checks over slices, or race workers, as cloud agents | [`/skill:stack-swarm`](../stack-swarm/SKILL.md) |
| Have different models review a diff and try to break it | [`/skill:stack-interrogate`](../stack-interrogate/SKILL.md) |
| Fix a bug test-first when a cheap local test exists | [`/skill:stack-tdd`](../stack-tdd/SKILL.md) |
| Apply TypeScript rules to `.ts` or `.tsx` work | [`/skill:stack-typescript-best-practices`](../stack-typescript-best-practices/SKILL.md) |
| Strip comments before review, using a reviewer that didn't write them | [`/skill:stack-no-comments`](../stack-no-comments/SKILL.md) |
| Clean AI tells out of prose | [`/skill:stack-unslop`](../stack-unslop/SKILL.md) |
| Write docs, an RFC, a README, a PR description, or a commit message to a standard | [`/skill:stack-technical-writing`](../stack-technical-writing/SKILL.md) |
| Hear the last reply again in plain words | [`/skill:stack-bro`](../stack-bro/SKILL.md) |
| Give agents a scripted way to drive the app and prove behavior | [`/skill:stack-create-verification-skill`](../stack-create-verification-skill/SKILL.md) |
| Bring a verification skill and its feature map back in line with the app | [`/skill:stack-maintain-verification-skill`](../stack-maintain-verification-skill/SKILL.md) |
| Formally verify a race, invariant, or other property that tests rarely reach | [`/skill:stack-create-formal-verification-skill`](../stack-create-formal-verification-skill/SKILL.md) |
| Bring a formal verification back in line after the code it covers changed, and learn whether a failure is drift or a bug | [`/skill:stack-maintain-formal-verification-skill`](../stack-maintain-formal-verification-skill/SKILL.md) |
| Show a PM or designer what the user sees as a chart checked by a TLA+ model, with the shortest path to each state that breaks a rule | [`/skill:stack-statechart`](../stack-statechart/SKILL.md) |
| Vet a performance number before reporting or acting on it | [`/skill:stack-benchmark-checklist`](../stack-benchmark-checklist/SKILL.md) |
| Run a large or cross-cutting change, or one to review after stepping away | [`/skill:stack-figure-it-out`](../stack-figure-it-out/SKILL.md) |
| Keep a decision log during a run, and review it afterward | [`/skill:stack-show-me-your-work`](../stack-show-me-your-work/SKILL.md) |
| Pick a model for each role and a reasoning budget | [`/skill:stack-setup-pstack`](../stack-setup-pstack/SKILL.md) |
| Turn their own working habits into a personal mode skill | [`/skill:stack-automate-me`](../stack-automate-me/SKILL.md) |
| Turn what a finished task taught into skill edits | [`/skill:stack-reflect`](../stack-reflect/SKILL.md) |
| Stop agents from repeating the same mistakes in this repo | [`/skill:stack-correct`](../stack-correct/SKILL.md) |
| Build a page whose buttons wake a Grok Bot over a webhook | [`/skill:stack-make-bot-ui`](../stack-make-bot-ui/SKILL.md) |
| Find their way around pstack | `/skill:stack-poteto-help` |

If a skill directory next to this one is missing from the table, read its frontmatter and route by its description. The `principle-*` directories are covered under principles below.

Close calls:

- `/skill:stack-how` explains what the code does. `/skill:stack-why` explains the reasons. `/skill:stack-teach` runs one or both and explains the result plainly.
- `/skill:stack-arena` gives every worker the same brief and merges the best parts. `/skill:stack-swarm` splits work into slices or a race and returns one report.
- `/skill:stack-architect` implements right after it settles the design. Add "with checkpoint" to review the design before it writes code.
- `/skill:stack-interrogate` reviews the diff. `/skill:stack-blast-radius` looks for breakage outside the diff and proves the one fact that makes the change safe.
- `/skill:stack-recall` rebuilds context across recent chats. `/skill:stack-ketchup` covers only this chat since the user's last message. Resuming one specific chat or branch is the Session pickup playbook.
- `/skill:stack-figure-it-out` designs one rigorous run. The Orchestrate playbook runs a program that spans days and many PRs. The Autonomous run playbook drives one task to a finish condition.

Not in pstack:

- `/skill:stack-deslop`, `control-cli`, and `control-ui` ship in the `cursor-team-kit` plugin.
- `/loop` and `/create-skill` are harness built-ins.
- pstack has no `/orchestrate` skill. Orchestrate is a `/skill:stack-poteto-mode` playbook. If the slash menu shows `/orchestrate`, another plugin provides it.

## Playbooks and principles

Playbooks are step lists inside `/skill:stack-poteto-mode`, not skills, so they have no slash command. Inside `/skill:stack-poteto-mode`, describing the task picks one, and these phrases name one directly:

- "babysit this pr" or "check on pr 123" runs Babysit. It drives the PR to merge-ready and stops there. It doesn't merge unless the user asks to merge, land, or ship.
- "land the stack" runs Shipping.
- "take over this branch" runs Session pickup.
- "pause safely" runs Pause safely.
- "full autopilot on this queue" runs Autopilot-full. "autopilot, don't merge" runs Autopilot-stack.
- "run the eval playbook" runs Eval.

Without `/skill:stack-poteto-mode`, a phrase such as "babysit this pr" can start the harness's own skill for the same job instead. The Playbooks section of [`poteto-mode`](../stack-poteto-mode/SKILL.md) lists every playbook and when it applies. [Guide page 6](../../docs/guide/06-verify-and-ship.md) covers opening, babysitting, and landing a PR.

pstack has no planning skill. omp's plan mode works alongside it. For work that spans phases or stacked PRs, asking `/skill:stack-poteto-mode` for a plan runs the [Multi-phase plan playbook](../stack-poteto-mode/playbooks/multi-phase-plan.md), which writes the plan and doesn't implement it. For a design question, the Prototype playbook or `/skill:stack-architect` settles it in code first.

Principles are one-rule skills that `/skill:stack-poteto-mode` reads and cites in its replies. The user rarely invokes one. They steer with the names instead, as in "apply prove it works. show me the real output." Typing `/principle-<name>` still loads one on demand. [Guide page 8](../../docs/guide/08-principles.md) lists them.

## Fix a run that went wrong

| Symptom | Fix |
|---|---|
| The mode stopped applying after a few turns | It was started with Enter. Start it as a Custom Mode, or start each task with `/skill:stack-poteto-mode`. |
| A question got treated as the next step of the last task | Say "new task", or say the turn doesn't need the mode. |
| A new model choice had no effect | The rule from `/skill:stack-setup-pstack` applies to new chats. Start one. |
| Runs cost more than expected | See the cost paragraph under Get set up. |
| A skill didn't load on its own | Only `/skill:stack-setup-pstack` loads from the user's words. The others load when the user types them or when `/skill:stack-poteto-mode` runs them, and it doesn't run every skill. |
| Parallel agents overwrote each other | Give each agent its own worktree, or run them as cloud agents, which each get their own machine. |
| An overnight run moved but finished nothing | `/loop` needs a check that can pass or fail, not a duration. See [guide page 7](../../docs/guide/07-overnight.md). |
| The reply claims success from a green build | Ask for the real command, flow, stored value, or profile. That's the prove-it-works principle. |

For a run that drifts, [`references/prompting.md`](references/prompting.md) has one-line steers. [Guide page 10](../../docs/guide/10-recipes-and-pitfalls.md) has more pitfalls and the recipes worth copying.

## Make pstack my own

- [`/skill:stack-automate-me`](../stack-automate-me/SKILL.md) drafts a personal mode skill from the user's own history, to use alongside `/skill:stack-poteto-mode`.
- [`/skill:stack-reflect`](../stack-reflect/SKILL.md) after a session turns its lessons into skill edits the user approves.
- `/poteto-mode write a skill for <workflow>` runs the authoring playbook. The eval playbook tests a skill change blind.
- Fix a misbehaving skill in its own PR, not inside the feature work where it went wrong.

[Guide page 9](../../docs/guide/09-make-it-yours.md) covers each of these.

## Reply

Lead with the answer. Give at most one example prompt in a code block, adapted from [`references/recipes.md`](references/recipes.md) when one fits, then the link to that file. Keep it short unless the user asked for the whole map.
