#!/usr/bin/env python3
"""Write stack's per-role model routing into an omp agent directory.

    python3 setup-models.py --code provider/model:high --judgment provider/model:xhigh
    python3 setup-models.py --code ... --judgment ... --panel-extra ... --max-effort max

The script writes three things:

- `task.perCallModel`, `task.perCallModelAllow`, `task.enableEffort` and `task.maxEffort`
  in `config.yml` (or the agent directory named by `--agent-dir` / `PI_CODING_AGENT_DIR`);
- `modelRoles.stack_code`, `modelRoles.stack_judgment` and an optional
  `modelRoles.stack_panel_extra` in the same file;
- a managed role block in `RULES.md`, the sticky rule every omp session and subagent reads.

Existing config and user text are preserved. Re-running is idempotent.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

LEVELS = ("low", "medium", "high", "xhigh", "max", "minimal")
START = "<!-- stack:models:start -->"
END = "<!-- stack:models:end -->"


def agent_dir(value):
    if value:
        return Path(value).expanduser().resolve()
    env = os.environ.get("PI_CODING_AGENT_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".omp" / "agent").resolve()


def split_level(selector):
    base, sep, level = selector.rpartition(":")
    if sep and level in LEVELS:
        return base, level
    return selector, ""


def models_json():
    try:
        result = subprocess.run(["omp", "models", "--json"], capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    return {item.get("selector"): item for item in payload.get("models", []) if item.get("kind") == "chat"}


def validate(selectors, no_validate):
    if no_validate:
        return []
    models = models_json()
    if not models:
        return ["could not read `omp models --json`; pass --no-validate if the selector is correct"]
    problems = []
    for selector in selectors:
        base, level = split_level(selector)
        model = models.get(base)
        if model is None:
            problems.append(f"{selector}: {base} is not an available chat model")
            continue
        if level and level not in (model.get("thinking") or []):
            problems.append(f"{selector}: {base} does not support thinking level {level}")
    return problems


def set_task(agent, key, value, dry_run):
    if dry_run:
        print(f"would set task.{key} = {value}")
        return
    if shutil.which("omp"):
        rendered = json.dumps(value) if isinstance(value, list) else str(value)
        result = subprocess.run(
            ["omp", "config", "set", f"task.{key}", rendered],
            capture_output=True,
            text=True,
            env={**os.environ, "PI_CODING_AGENT_DIR": str(agent)},
        )
        if result.returncode == 0:
            return
        print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
    # fallback: edit the block directly
    path = agent / "config.yml"
    lines = path.read_text().splitlines() if path.exists() else []
    start = next((i for i, line in enumerate(lines) if re.match(r"^task:\s*$", line)), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("task:")
        start = len(lines) - 1
    end = start + 1
    while end < len(lines) and (lines[end].startswith(" ") or not lines[end].strip()):
        end += 1
    block = lines[start + 1:end]
    pattern = re.compile(rf"^\s{{1,}}{re.escape(key)}:\s*")
    index = next((i for i, line in enumerate(block) if pattern.match(line)), None)
    rendered = render_scalar(value)
    if index is None:
        block.append(f"  {key}: {rendered}")
    else:
        block[index] = f"  {key}: {rendered}"
    lines[start + 1:end] = block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", newline="\n")


def render_scalar(value):
    if isinstance(value, list):
        return "\n" + "\n".join(f"    - {item}" for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def set_model_roles(agent, roles, dry_run):
    path = agent / "config.yml"
    lines = path.read_text().splitlines() if path.exists() else []
    start = next((i for i, line in enumerate(lines) if re.match(r"^modelRoles:\s*$", line)), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("modelRoles:")
        start = len(lines) - 1
    end = start + 1
    while end < len(lines) and (lines[end].startswith(" ") or not lines[end].strip()):
        end += 1
    block = lines[start + 1:end]
    for role, value in roles.items():
        pattern = re.compile(rf"^\s+{re.escape(role)}:\s*")
        index = next((i for i, line in enumerate(block) if pattern.match(line)), None)
        line = f"  {role}: {value}"
        if index is None:
            block.append(line)
        else:
            block[index] = line
    lines[start + 1:end] = block
    if dry_run:
        print("would write config.yml:\n" + "\n".join(lines))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", newline="\n")


def rules_block(code, judgment, panel_extra):
    panel_entries = []
    for selector in (judgment, code, panel_extra):
        if selector and selector not in panel_entries:
            panel_entries.append(selector)
    panel = ", ".join(panel_entries)
    interrogate = f"{panel}, openrouter:x-ai/grok-4.7"
    lines = [
        START,
        "# stack model routing. Generated by stack-setup-stack; edit config.yml, not this block.",
        "# Each value is one exact omp selector. A comma-separated list is a panel: one spawn per entry.",
        f"feature, refactoring, bug-fix, perf-issue, hillclimb, how explorer, why investigators, reflect tooling, swarm workers: {code}",
        f"judgment and prose, hardest tasks, how explainer, why synthesizer, reflect judgment, divergent, synthesizer: {judgment}",
        f"arena runners, arena cross-judge pool, architect runners: {panel}",
        f"interrogate reviewers: {interrogate}",
        END,
    ]
    return "\n".join(lines)


def write_rules(agent, block, dry_run):
    path = agent / "RULES.md"
    text = path.read_text() if path.exists() else ""
    if START in text and END in text:
        text = re.sub(re.escape(START) + r".*?" + re.escape(END), block, text, flags=re.S)
    else:
        text = text.rstrip()
        text = f"{text}\n\n{block}\n" if text else f"{block}\n"
    if dry_run:
        print(f"would write {path}:\n{block}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent-dir", help="omp agent directory (default: PI_CODING_AGENT_DIR or ~/.omp/agent)")
    parser.add_argument("--code", required=True, help="selector for feature, refactoring, bug-fix and the other code roles")
    parser.add_argument("--judgment", required=True, help="selector for judgment, prose and the hardest tasks")
    parser.add_argument("--panel-extra", help="optional third selector for arena, architect and interrogate panels")
    parser.add_argument("--allow", action="append", default=[], metavar="SELECTOR",
                        help="extra selector to approve for per-call model use; repeatable")
    parser.add_argument("--max-effort", default="xhigh", choices=LEVELS, help="ceiling for per-call effort (default: xhigh)")
    parser.add_argument("--no-validate", action="store_true", help="skip the `omp models --json` check")
    parser.add_argument("--dry-run", action="store_true", help="print the changes without writing")
    args = parser.parse_args()

    selectors = [args.code, args.judgment] + ([args.panel_extra] if args.panel_extra else []) + args.allow
    problems = validate(selectors, args.no_validate)
    if problems:
        print(*problems, sep="\n", file=sys.stderr)
        sys.exit("setup-models: the model list does not match `omp models --json`")

    agent = agent_dir(args.agent_dir)
    allow = sorted({split_level(selector)[0] for selector in selectors})
    roles = {"stack_code": args.code, "stack_judgment": args.judgment}
    if args.panel_extra:
        roles["stack_panel_extra"] = args.panel_extra

    set_task(agent, "perCallModel", "on", args.dry_run)
    set_task(agent, "perCallModelAllow", allow, args.dry_run)
    set_task(agent, "enableEffort", True, args.dry_run)
    set_task(agent, "maxEffort", args.max_effort, args.dry_run)
    set_model_roles(agent, roles, args.dry_run)
    write_rules(agent, rules_block(args.code, args.judgment, args.panel_extra), args.dry_run)

    action = "would write" if args.dry_run else "wrote"
    print(f"{action} model routing in {agent}")
    print(f"  stack_code: {args.code}")
    print(f"  stack_judgment: {args.judgment}")
    if args.panel_extra:
        print(f"  stack_panel_extra: {args.panel_extra}")
    print(f"  perCallModelAllow: {', '.join(allow)}")
    print(f"  maxEffort: {args.max_effort}")


if __name__ == "__main__":
    main()
