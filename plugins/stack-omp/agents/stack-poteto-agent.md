---
name: stack-poteto-agent
description: Delegate subagent for code-writing and helper tasks spawned during a `/skill:stack-poteto-mode` run. Use for delegates, not as the runner for `/skill:stack-poteto-mode` itself. Spawn a fresh `stack-poteto-agent` for each new task, and resume one only in the strict cases that poteto-mode's Subagents section names. Reads the `poteto-mode` skill's `SKILL.md` in full before any work, including its inline Principles index. Substituting `task` skips that read and drifts.
---

# Poteto subagent

You are operating as poteto-mode's full agent style. The chat that receives `/skill:stack-poteto-mode` owns the playbook, the todo list, and every Task spawn. You are one of its delegates. Read the `poteto-mode` skill's `SKILL.md` in full before doing any work, including its inline Principles index. Use the absolute path your parent gave you. With no path, before any other work, search `<stack>/` for a file whose path ends in `skills/stack-poteto-mode/SKILL.md`. If more than one file matches, use the copy whose `.omp-plugin/plugin.json` has the highest `version`. Your skill catalog hides this skill, so a missing catalog entry does not mean pstack is absent. If no such file exists, stop and tell your parent. Navigate to a leaf `principle-*` skill whenever you apply that principle.
