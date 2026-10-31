#!/usr/bin/env python3
"""PreToolUse hook: while the builder is bound to another backend, only that backend writes product code.

When roles.json binds the builder to a backend other than claude, and that backend is ready (its key
is set and delegate.py doctor passed for this Claude Code version), this hook blocks two things in a
Claude session:

- spawning a `poteto-agent`, the code-writing delegate, on any Claude model;
- Edit, Write, MultiEdit or NotebookEdit on a file inside a git work tree that git does not ignore.

The delegate's own child is marked with STACK_DELEGATE_ROLE and is never blocked. Files outside a
repository, such as briefs and the decision trail, are never blocked. When the backend is not ready,
nothing is blocked, so the Claude fallback keeps working. A backend that delegate.py recorded as down
(quota, credit, auth, outage) counts as not ready until its cooldown ends. STACK_ALLOW_CLAUDE_BUILDER=1 turns the guard off.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def load_delegate():
    spec = importlib.util.spec_from_file_location("delegate", Path(__file__).resolve().parent / "delegate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ready_builder(delegate):
    """The builder binding when it is another backend and ready, else None."""
    roles = delegate.load_roles()
    builder = delegate.resolve(roles, "builder")[0]
    if builder["via"] != "delegate":
        return None
    spec = roles["backends"][builder["backend"]]
    if not os.environ.get(spec.get("key_env", "")) or not delegate.doctor_passed(builder["backend"]):
        return None
    if delegate.backend_down(builder["backend"]):
        return None
    return builder


def product_file(path):
    """True when the path sits in a git work tree and git does not ignore it."""
    target = Path(path).expanduser()
    folder = target.parent
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent
    inside = subprocess.run(["git", "-C", str(folder), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    if inside.stdout.strip() != "true":
        return False
    ignored = subprocess.run(["git", "-C", str(folder), "check-ignore", "-q", str(target)], capture_output=True)
    return ignored.returncode != 0


def decide(call, delegate):
    """None to allow, or the message that blocks the call."""
    if os.environ.get("STACK_ALLOW_CLAUDE_BUILDER") == "1" or os.environ.get("STACK_DELEGATE_ROLE"):
        return None
    tool, tool_input = call.get("tool_name", ""), call.get("tool_input") or {}
    spawn = tool in ("Agent", "Task") and str(tool_input.get("subagent_type", "")).endswith("poteto-agent")
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    edit = tool in EDIT_TOOLS and path and product_file(path)
    if not (spawn or edit):
        return None
    builder = ready_builder(delegate)
    if not builder:
        return None
    script = Path(delegate.__file__).resolve()
    run = (f"`python3 {script} run --role \"<role line, e.g. feature, refactoring or bug-fix>\" "
           f"--dir <worktree> --brief <file>`")
    what = f"a poteto-agent on {tool_input.get('model') or 'the parent model'}" if spawn else f"editing {path} here"
    return (f"stack: the builder role is bound to {builder['backend']}:{builder['model']}, and this session only "
            f"evaluates, so {what} is not allowed. Write the brief to a file outside the repository, run {run}, "
            f"then review the diff and run the checks yourself.")


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
