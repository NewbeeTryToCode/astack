#!/usr/bin/env python3
"""Write stack's per-role model routing into an omp agent directory.

    python3 setup-models.py --code provider/model:high --judgment provider/model:xhigh
    python3 setup-models.py --code ... --judgment ... --panel-primary ... \
        --panel-extra ... --interrogate-extra ... \
        --judgment-fallback provider/model:xhigh --max-effort xhigh

The script writes:

- `task.perCallModel`, `task.perCallModelAllow`, `task.enableEffort` and `task.maxEffort`
  in `config.yml` (or the agent directory named by `--agent-dir` / `PI_CODING_AGENT_DIR`);
- `modelRoles.stack_code`, `stack_judgment`, `stack_panel_primary`,
  `stack_panel_extra` and `stack_interrogate_extra` in the same file;
- optional `task.agentModelOverrides.stack-judgment` and
  `retry.fallbackChains.stack_judgment`, so the judgment agent falls back when
  the primary model hits a usage limit;
- a managed role block in `RULES.md`, the sticky rule every omp session and subagent reads.

Existing config and user text are preserved. Re-running is idempotent.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

LEVELS = ("low", "medium", "high", "xhigh", "max", "minimal")
EFFORT_ORDER = ("minimal", "low", "medium", "high", "xhigh", "max")
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


def top_block(lines, name):
    pattern = re.compile(rf"^{re.escape(name)}:\s*$")
    index = next((i for i, line in enumerate(lines) if pattern.match(line)), None)
    if index is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{name}:")
        index = len(lines) - 1
    end = index + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line[0].isspace():
            break
        end += 1
    return index, end


def find_child(lines, start, end, key, indent):
    prefix = " " * indent + key + ":"
    for index in range(start, end):
        line = lines[index]
        if line.startswith(prefix) and (len(line) == len(prefix) or line[len(prefix)] in " \t"):
            return index
    return None


def child_end(lines, index, end, indent):
    cursor = index + 1
    while cursor < end:
        line = lines[cursor]
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        cursor += 1
    return cursor


def render_leaf(key, value, indent):
    pad = " " * indent
    if isinstance(value, list):
        return [f"{pad}{key}:"] + [f"{pad}  - {item}" for item in value]
    if isinstance(value, bool):
        return [f"{pad}{key}: {'true' if value else 'false'}"]
    if isinstance(value, str) and value.startswith("@"):
        return [f'{pad}{key}: "{value}"']
    return [f"{pad}{key}: {value}"]


def set_path(lines, start, end, path, value, indent):
    key = path[0]
    index = find_child(lines, start, end, key, indent)
    if len(path) == 1:
        rendered = render_leaf(key, value, indent)
        if index is None:
            lines[end:end] = rendered
        else:
            stop = child_end(lines, index, end, indent)
            lines[index:stop] = rendered
        return
    if index is None:
        lines[end:end] = [" " * indent + key + ":"]
        index = end
        end = index + 1
    elif lines[index].strip() != key + ":":
        lines[index] = " " * indent + key + ":"
    stop = child_end(lines, index, end, indent)
    set_path(lines, index + 1, stop, path[1:], value, indent + 2)


def existing_role_values(agent):
    config = agent / "config.yml"
    if not config.exists():
        return set()
    lines = config.read_text().splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^modelRoles:\s*$", line)), None)
    if start is None:
        return set()
    end = start + 1
    while end < len(lines) and (lines[end].startswith(" ") or not lines[end].strip()):
        end += 1
    values = set()
    for line in lines[start + 1:end]:
        match = re.match(r"^\s+[A-Za-z0-9_-]+:\s*(.+?)\s*$", line)
        if match:
            value = match.group(1).strip().strip('"').strip("'")
            if value:
                values.add(value)
    return values


def set_nested(agent, root, path, value, dry_run):
    config = agent / "config.yml"
    lines = config.read_text().splitlines() if config.exists() else []
    index, end = top_block(lines, root)
    set_path(lines, index + 1, end, path, value, 2)
    if dry_run:
        print(f"would set {root}." + ".".join(path) + f" = {value}")
        return
    agent.mkdir(parents=True, exist_ok=True)
    config.write_text("\n".join(lines) + "\n", newline="\n")


def rules_block(code, judgment, panel_primary, panel_extra, interrogate_extra, fallback, reviewers=None):
    def dedupe(values):
        seen = []
        for value in values:
            if value and value not in seen:
                seen.append(value)
        return seen

    panel = dedupe([panel_primary or judgment, code, panel_extra])
    interrogate = dedupe(reviewers if reviewers else panel + [interrogate_extra])
    judgment_line = judgment
    if fallback:
        judgment_line = f"{judgment} (use agent stack-judgment; fallback {fallback} on usage limits)"
    lines = [
        START,
        "# stack model routing. Generated by stack-setup-stack; edit config.yml, not this block.",
        "# Each value is one exact omp selector. A comma-separated list is a panel: one spawn per entry.",
        f"feature, refactoring, bug-fix, perf-issue, hillclimb, how explorer, why investigators, reflect tooling, swarm workers: {code}",
        f"judgment and prose, hardest tasks, how explainer, why synthesizer, reflect judgment, divergent, synthesizer: {judgment_line}",
        f"arena runners, arena cross-judge pool, architect runners: {', '.join(panel)}",
        f"interrogate reviewers: {', '.join(interrogate)}",
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
    agent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent-dir", help="omp agent directory (default: PI_CODING_AGENT_DIR or ~/.omp/agent)")
    parser.add_argument("--code", required=True, help="selector for feature, refactoring, bug-fix and the other code roles")
    parser.add_argument("--judgment", required=True, help="selector for judgment, prose and the hardest tasks")
    parser.add_argument("--panel-primary", help="selector for the arena, architect and interrogate panels (default: judgment)")
    parser.add_argument("--panel-extra", help="optional extra selector for arena, architect and interrogate panels")
    parser.add_argument("--interrogate-extra", help="optional extra selector for the interrogate panel only")
    parser.add_argument("--interrogate-reviewers", help="comma-separated full interrogate panel; overrides --interrogate-extra")
    parser.add_argument("--judgment-fallback", help="selector tried when the judgment model hits a usage limit")
    parser.add_argument("--judgment-agent", default="stack-judgment",
                        help="agent name pinned to the judgment role (default: stack-judgment)")
    parser.add_argument("--fallback-on", default="usage-limit",
                        choices=["usage-limit", "any", "except-usage-limit"],
                        help="when omp walks the judgment fallback chain (default: usage-limit)")
    parser.add_argument("--allow", action="append", default=[], metavar="SELECTOR",
                        help="extra selector to approve for per-call model use; repeatable")
    parser.add_argument("--max-effort", default="xhigh", choices=LEVELS, help="ceiling for per-call effort (default: xhigh)")
    parser.add_argument("--no-validate", action="store_true", help="skip the `omp models --json` check")
    parser.add_argument("--dry-run", action="store_true", help="print the changes without writing")
    args = parser.parse_args()

    reviewers = [item.strip() for item in (args.interrogate_reviewers or "").split(",") if item.strip()]
    selectors = [args.code, args.judgment, args.panel_primary, args.panel_extra,
                 args.interrogate_extra, args.judgment_fallback] + reviewers + args.allow
    problems = validate([s for s in selectors if s], args.no_validate)
    if problems:
        print(*problems, sep="\n", file=sys.stderr)
        sys.exit("setup-models: the model list does not match `omp models --json`")

    requested = [split_level(selector)[1] for selector in selectors if selector and split_level(selector)[1]]
    if requested:
        highest = max(requested, key=EFFORT_ORDER.index)
        if EFFORT_ORDER.index(highest) > EFFORT_ORDER.index(args.max_effort):
            print(f"warning: {highest} selectors are clamped to --max-effort {args.max_effort}; "
                  f"pass --max-effort {highest} to keep them", file=sys.stderr)

    agent = agent_dir(args.agent_dir)
    allow = sorted({split_level(selector)[0] for selector in selectors if selector})
    roles = {"stack_code": args.code, "stack_judgment": args.judgment}
    if args.panel_primary:
        roles["stack_panel_primary"] = args.panel_primary
    if args.panel_extra:
        roles["stack_panel_extra"] = args.panel_extra
    if args.interrogate_extra:
        roles["stack_interrogate_extra"] = args.interrogate_extra
    known = set(roles.values()) | existing_role_values(agent)
    for index, selector in enumerate(reviewers, 1):
        if selector not in known:
            roles[f"stack_reviewer_{index}"] = selector
            known.add(selector)

    set_nested(agent, "task", ["perCallModel"], "on", args.dry_run)
    set_nested(agent, "task", ["perCallModelAllow"], allow, args.dry_run)
    set_nested(agent, "task", ["enableEffort"], True, args.dry_run)
    set_nested(agent, "task", ["maxEffort"], args.max_effort, args.dry_run)
    for role, value in roles.items():
        set_nested(agent, "modelRoles", [role], value, args.dry_run)
    if args.judgment_fallback:
        set_nested(agent, "retry", ["fallbackOn"], args.fallback_on, args.dry_run)
        set_nested(agent, "retry", ["fallbackChains", "stack_judgment"],
                   [args.judgment_fallback], args.dry_run)
        set_nested(agent, "task", ["agentModelOverrides", args.judgment_agent],
                   "@stack_judgment", args.dry_run)
    write_rules(agent, rules_block(args.code, args.judgment, args.panel_primary,
                                   args.panel_extra, args.interrogate_extra,
                                   args.judgment_fallback, reviewers or None), args.dry_run)

    action = "would write" if args.dry_run else "wrote"
    print(f"{action} model routing in {agent}")
    print(f"  stack_code: {args.code}")
    print(f"  stack_judgment: {args.judgment}")
    if args.panel_primary:
        print(f"  stack_panel_primary: {args.panel_primary}")
    if args.panel_extra:
        print(f"  stack_panel_extra: {args.panel_extra}")
    if args.interrogate_extra:
        print(f"  stack_interrogate_extra: {args.interrogate_extra}")
    if reviewers:
        print(f"  interrogate reviewers: {', '.join(reviewers)}")
    if args.judgment_fallback:
        print(f"  judgment fallback: {args.judgment_fallback} on {args.fallback_on}")
        print(f"  agent override: {args.judgment_agent} -> @stack_judgment")
    print(f"  perCallModelAllow: {', '.join(allow)}")
    print(f"  maxEffort: {args.max_effort}")


if __name__ == "__main__":
    main()
