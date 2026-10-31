#!/usr/bin/env python3
"""PreToolUse hook on Agent: send a Claude code delegate to the backend its role is bound to.

A `poteto-agent` spawned on a model other than opus is a builder or evidence delegate. When roles.json
binds the builder to another backend and that backend is ready (its key is set and delegate.py doctor
passed for this Claude Code version), the spawn is blocked with the delegate.py command to run instead.
Opus spawns pass, because they carry the hardest and judgment roles. When the backend is not ready, every
spawn passes, so the Claude fallback keeps working. STACK_ALLOW_CLAUDE_BUILDER=1 turns the guard off.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path


def load_delegate():
    spec = importlib.util.spec_from_file_location("delegate", Path(__file__).resolve().parent / "delegate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decide(call, delegate):
    """None to allow, or the message that blocks the spawn."""
    if os.environ.get("STACK_ALLOW_CLAUDE_BUILDER") == "1":
        return None
    tool_input = call.get("tool_input") or {}
    if not str(tool_input.get("subagent_type", "")).endswith("poteto-agent"):
        return None
    model = str(tool_input.get("model") or "").lower()
    if not model or model.startswith("opus"):
        return None
    roles = delegate.load_roles()
    builder = delegate.resolve(roles, "builder")[0]
    if builder["via"] != "delegate":
        return None
    spec = roles["backends"][builder["backend"]]
    if not os.environ.get(spec.get("key_env", "")) or not delegate.doctor_passed(builder["backend"]):
        return None
    script = Path(delegate.__file__).resolve()
    return (
        f"stack: the builder role is bound to {builder['backend']}:{builder['model']}, so a {model} poteto-agent "
        f"is not the builder. Write the brief to a file outside the worktree and run "
        f"`python3 {script} run --role \"<role line, e.g. feature, refactoring or bug-fix>\" --dir <worktree> --brief <file>`, "
        f"then review the diff yourself. Spawn on opus only for the hardest tasks."
    )


def main():
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    message = decide(call, load_delegate())
    if message:
        print(message, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
