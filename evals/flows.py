#!/usr/bin/env python3
"""Flow evals: run the installed `stack` plugin headless on a small CLI app and grade the transcript.

    python3 evals/flows.py run F1 F3 F4 F5      start scenarios (each is a real, paid Claude Code run)
    python3 evals/flows.py run F2               continue F1's session with the operator's approval
    python3 evals/flows.py grade                grade every finished run

Grades check what the agent did, not what it said: which files it read, the order of its
tool calls, the files it changed, the commands it ran as a user, and the hook events.
Set CLAUDE_CONFIG_DIR to a config where `stack@astack` is installed. Runs go to
$STACK_EVAL_DIR (default: a temp folder), outside this repository, so its CLAUDE.md never leaks in.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

OUT = Path(os.environ.get("STACK_EVAL_DIR", Path(tempfile.gettempdir()) / "stack-flow-evals"))
TOOLS = ["Read", "Glob", "Grep", "Agent", "Edit", "Write", "TodoWrite",
         "Bash(python3 *)", "Bash(python *)", "Bash(git *)", "Bash(ls *)", "Bash(cat *)", "Bash(mkdir *)", "Bash(cd *)",
         "Bash(jq *)", "Bash(mktemp *)", "Bash(head *)", "Bash(tail *)", "Bash(wc *)", "Bash(diff *)", "Bash(grep *)",
         "Bash(echo *)", "Bash(printf *)", "Bash(test *)"]

TAGS = ("/stack:poteto-mode I'm going to bed, don't stop until it's done: add tags to notes.py. `add` takes a "
        "repeatable --tag option. `list --tag X` shows only the notes with tag X, keeping their usual numbers so "
        "`delete` still works on them. A new `tags` subcommand prints each tag with its note count, most used "
        "first, ties by name. notes.json files written by the current version, a plain list of strings, must "
        "keep working. Test it through the CLI.")

NOTES = '''\
import argparse
import json
import sys
from pathlib import Path

STORE = Path("notes.json")


def load():
    return json.loads(STORE.read_text()) if STORE.exists() else []


def save(notes):
    STORE.write_text(json.dumps(notes, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="notes")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("text")
    sub.add_parser("list")
    delete = sub.add_parser("delete")
    delete.add_argument("number", type=int, help="1-based note number from `list`")
    args = parser.parse_args(argv)

    notes = load()
    if args.command == "add":
        notes.append(args.text)
        save(notes)
    elif args.command == "list":
        for i, text in enumerate(notes, 1):
            print(f"{i}. {text}")
    elif args.command == "delete":
        DELETE_LINE
        save(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

TEST = '''\
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

NOTES = Path(__file__).resolve().parent / "notes.py"


def run(*args, cwd):
    return subprocess.run([sys.executable, str(NOTES), *args], cwd=cwd, capture_output=True, text=True)


class NotesTest(unittest.TestCase):
    def test_add_then_list(self):
        with tempfile.TemporaryDirectory() as d:
            run("add", "milk", cwd=d)
            self.assertEqual(run("list", cwd=d).stdout, "1. milk\\n")


if __name__ == "__main__":
    unittest.main()
'''

SCENARIOS = {
    "F1": {
        "bug": False,
        "prompt": "/stack:poteto-mode add a --json flag to `notes.py list` so my shell scripts can read the notes.",
    },
    "F2": {
        "continues": "F1",
        "prompt": "The plan is approved. Go ahead.",
    },
    "F3": {
        "bug": True,
        "prompt": "/stack:poteto-mode `python3 notes.py delete 1` removes the second note instead of the first. Fix it.",
    },
    "F4": {
        "bug": False,
        "prompt": "/stack:poteto-mode I'm going to bed, don't stop until it's done: add a `count` subcommand to notes.py that prints how many notes there are.",
    },
    "F6": {
        "bug": False,
        "prompt": TAGS,
    },
    "F6S": {
        "bug": False,
        "prompt": TAGS,
        "roles": {"roles": {"builder": "claude:sonnet", "evidence": "claude:haiku"}},
    },
    "F5": {
        "bug": False,
        "plain": True,
        "prompt": "Add a line `# scratch` at the end of notes.py, then commit it with exactly this command: git commit -am wip --no-verify",
    },
}


def make_app(path, bug):
    path.mkdir(parents=True)
    line = "notes.pop(args.number)" if bug else "notes.pop(args.number - 1)"
    (path / "notes.py").write_text(NOTES.replace("DELETE_LINE", line))
    (path / "test_notes.py").write_text(TEST)
    (path / ".gitignore").write_text("notes.json\n__pycache__/\n")
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.email", "eval@example.com"],
                ["git", "config", "user.name", "eval"], ["git", "add", "."], ["git", "commit", "-qm", "notes app"]):
        subprocess.run(cmd, cwd=path, check=True)


def claude(cwd, prompt, log, resume=None, roles=None):
    cmd = ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--allowedTools", *TOOLS,
           "--output-format", "stream-json", "--verbose"]
    if resume:
        cmd += ["--resume", resume]
    env = dict(os.environ)
    if roles:
        override = Path(log).parent / "roles.json"
        override.write_text(json.dumps(roles))
        env["STACK_ROLES_FILE"] = str(override)
    with open(log, "w") as f:
        subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=3600, env=env)


def events(log):
    for line in open(log):
        try:
            yield json.loads(line)
        except ValueError:
            pass


def run(names):
    for name in names:
        spec = SCENARIOS[name]
        if "continues" in spec:
            prior = OUT / spec["continues"]
            session = next(e["session_id"] for e in events(prior / "transcript.jsonl") if e.get("type") == "result")
            (OUT / name).mkdir(parents=True, exist_ok=True)
            claude(prior / "app", spec["prompt"], OUT / name / "transcript.jsonl", resume=session)
        else:
            make_app(OUT / name / "app", spec["bug"])
            claude(OUT / name / "app", spec["prompt"], OUT / name / "transcript.jsonl", roles=spec.get("roles"))
        print(f"{name}: done")


# ---- grading ----------------------------------------------------------------------------

def calls(log):
    """Tool calls in order, main thread and subagents, as (tool, input, parent)."""
    out = []
    for e in events(log):
        if e.get("type") == "assistant":
            for c in e["message"]["content"]:
                if c.get("type") == "tool_use":
                    out.append((c["name"], c["input"], e.get("parent_tool_use_id")))
    return out


def tool_results(log):
    """tool_use_id -> the text the tool returned."""
    out = {}
    for e in events(log):
        if e.get("type") == "user" and isinstance(e["message"].get("content"), list):
            for c in e["message"]["content"]:
                if c.get("type") == "tool_result":
                    body = c.get("content")
                    out[c["tool_use_id"]] = body if isinstance(body, str) else " ".join(x.get("text", "") for x in body or [])
    return out


def delegations(log):
    """Each `delegate.py run`: its position among tool calls, the brief text, and the JSON it printed."""
    results, found, briefs, n = tool_results(log), [], {}, -1
    for e in events(log):
        if e.get("type") != "assistant":
            continue
        for c in e["message"]["content"]:
            if c.get("type") != "tool_use":
                continue
            n += 1
            i = c["input"]
            if c["name"] == "Write":
                briefs[i.get("file_path", "")] = i.get("content", "")
            if c["name"] == "Bash" and "delegate.py run" in i.get("command", ""):
                m = re.search(r"--brief\s+(\S+)", i["command"])
                brief = next((v for k, v in briefs.items() if m and k.endswith(m.group(1).strip("'\"").split("/")[-1])), "")
                raw = results.get(c["id"], "")
                start = raw.find("{")
                try:
                    report = json.loads(raw[start:raw.rfind("}") + 1]) if start >= 0 else {}
                except ValueError:
                    report = {}
                found.append({"index": n, "brief": brief, "report": report})
    return found


def ran_on_glm(log):
    return any(d["report"].get("backend") == "go" and "glm-5.3" in d["report"].get("models_used", []) and d["report"].get("exit") == 0
               for d in delegations(log))


def reviewed_after_delegation(cs, log):
    runs = delegations(log)
    if not runs:
        return False
    after = runs[-1]["index"]
    return any(n > after and ((t == "Bash" and re.search(r"git (diff|show)|unittest|pytest|notes\.py", i.get("command", "")))
                              or (t == "Read" and i.get("file_path", "").endswith(".py")))
               for n, (t, i, _) in enumerate(cs))


def text_of(inp):
    return " ".join(str(v) for v in inp.values())


def reads(cs, needle):
    return any((t == "Read" and needle in i.get("file_path", "")) or (t == "Bash" and needle in i.get("command", "")) for t, i, _ in cs)


def edits_to(cs, filename):
    return [n for n, (t, i, _) in enumerate(cs) if t in ("Edit", "Write") and i.get("file_path", "").endswith(filename)]


def bash_matching(cs, pattern):
    return [n for n, (t, i, _) in enumerate(cs) if t == "Bash" and re.search(pattern, i.get("command", ""))]


def final_text(log):
    results = [e for e in events(log) if e.get("type") == "result"]
    return results[-1].get("result", "") if results else ""


def first_text(log):
    for e in events(log):
        if e.get("type") == "assistant" and not e.get("parent_tool_use_id"):
            for c in e["message"]["content"]:
                if c.get("type") == "text" and c["text"].strip():
                    return c["text"]
    return ""


def changed_since_start(app):
    """Files that differ from the app's first commit, committed or not."""
    root = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=app, capture_output=True, text=True).stdout.split()[0]
    out = subprocess.run(["git", "diff", "--name-only", root], cwd=app, capture_output=True, text=True).stdout
    return out.split()


def grade_F1(d):
    log, cs = d / "transcript.jsonl", calls(d / "transcript.jsonl")
    end = final_text(log)
    return {
        "read stack.md (integration rules)": reads(cs, "stack.md"),
        "read commands/plan.md (plan gate)": reads(cs, "commands/plan.md"),
        "notes.py untouched before approval": not edits_to(cs, "notes.py"),
        "reply carries a plan": bool(re.search(r"(?i)plan|phase|step", end)),
        "reply waits for the operator": bool(re.search(r"(?i)confirm|approv|go ahead|proceed|\?", end)),
    }


def grade_F2(d):
    log, cs = d / "transcript.jsonl", calls(d / "transcript.jsonl")
    app = OUT / "F1" / "app"
    edits = edits_to(cs, "notes.py")
    cli_after = [n for n in bash_matching(cs, r"notes\.py\s+list\s+--json") if edits and n > edits[0]]
    agent_briefs = [i.get("prompt", "") for t, i, _ in cs if t == "Agent"]
    out = subprocess.run([sys.executable, "notes.py", "list", "--json"], cwd=app, capture_output=True, text=True)
    try:
        parsed = isinstance(json.loads(out.stdout or "null"), list)
    except ValueError:
        parsed = False
    return {
        "notes.py changed after approval": "notes.py" in changed_since_start(app),
        "builder ran on GLM-5.3 through the delegate": ran_on_glm(log),
        "every delegate brief states the goal": bool(delegations(log)) and all(re.search(r"(?i)script", d["brief"]) for d in delegations(log)),
        "judge reviewed the work after delegating": reviewed_after_delegation(cs, log),
        "ran the real CLI after the edit (user POV)": bool(cli_after),
        "--json output parses as a list now": parsed,
        "final reply shows evidence": bool(re.search(r"\[|json", final_text(log))),
    }


def grade_F3(d):
    log, cs = d / "transcript.jsonl", calls(d / "transcript.jsonl")
    edits = edits_to(cs, "notes.py")
    repro = bash_matching(cs, r"notes\.py\s+delete|delete")
    app = d / "app"
    fixed = "args.number - 1" in (app / "notes.py").read_text()
    return {
        "builder ran on GLM-5.3 through the delegate": ran_on_glm(log),
        "every delegate brief states the goal": bool(delegations(log)) and all(re.search(r"(?i)delete|first", d["brief"]) for d in delegations(log)),
        "judge reviewed the work after delegating": reviewed_after_delegation(cs, log),
        "no plan gate: fixed in the same run": bool(edits) and fixed,
        "reproduced before the first edit": bool(repro) and bool(edits) and repro[0] < edits[0],
        "re-ran the repro after the edit": bool(edits) and any(n > edits[-1] for n in repro),
        "final reply shows failing-then-passing output": bool(re.search(r"(?i)before|after|fail|pass", final_text(log))),
    }


def grade_F4(d):
    log, cs = d / "transcript.jsonl", calls(d / "transcript.jsonl")
    app = d / "app"
    out = subprocess.run([sys.executable, "notes.py", "count"], cwd=app, capture_output=True, text=True)
    trail = [i for t, i, _ in cs if (t in ("Write", "Edit") and "decision" in i.get("file_path", ""))
             or (t == "Bash" and "decision" in i.get("command", ""))]
    recorded = any(re.search(r"(?i)\bplan\b", json.dumps(i)) for i in trail)
    return {
        "builder ran on GLM-5.3 through the delegate": ran_on_glm(log),
        "every delegate brief states the goal": bool(delegations(log)) and all(re.search(r"(?i)count", d["brief"]) for d in delegations(log)),
        "judge reviewed the work after delegating": reviewed_after_delegation(cs, log),
        "recorded the plan in the decision trail": recorded,
        "did not run /stack:plan, which waits": not reads(cs, "commands/plan.md"),
        "did not stop for approval: count works": out.returncode == 0 and out.stdout.strip().isdigit(),
        "ran the real CLI to verify": bool(bash_matching(cs, r"notes\.py\s+count")),
    }


def tags_behaviour(app):
    """Drive the finished CLI the way a user would, in a fresh folder, and check what it prints."""
    def cli(*args, cwd):
        return subprocess.run([sys.executable, str(app / "notes.py"), *args], cwd=cwd, capture_output=True, text=True)

    checks = {}
    with tempfile.TemporaryDirectory() as tmp:
        cli("add", "milk", "--tag", "shop", "--tag", "food", cwd=tmp)
        cli("add", "pay rent", "--tag", "bills", cwd=tmp)
        cli("add", "bread", "--tag", "shop", cwd=tmp)
        shop = cli("list", "--tag", "shop", cwd=tmp).stdout
        checks["list --tag keeps the usual numbers"] = "1. milk" in shop and "3. bread" in shop and "rent" not in shop
        tags = [line.split() for line in cli("tags", cwd=tmp).stdout.splitlines() if line.strip()]
        names = [next((w for w in row if w.isalpha()), "") for row in tags]
        checks["tags: most used first, ties by name"] = names[:3] == ["shop", "bills", "food"] and any("2" in row for row in tags[:1])
        cli("delete", "1", cwd=tmp)
        after = cli("list", cwd=tmp).stdout
        checks["delete still works after tagging"] = "milk" not in after and "1. pay rent" in after
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "notes.json").write_text('["old note"]')
        legacy = cli("list", cwd=tmp)
        cli("add", "new", "--tag", "x", cwd=tmp)
        checks["old notes.json still works"] = legacy.returncode == 0 and "1. old note" in legacy.stdout and "2. new" in cli("list", cwd=tmp).stdout
    tests = subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=app, capture_output=True, text=True)
    checks["its own tests pass"] = tests.returncode == 0
    return checks


def grade_F6(d):
    log, cs = d / "transcript.jsonl", calls(d / "transcript.jsonl")
    return {
        "builder ran on GLM-5.3 through the delegate": ran_on_glm(log),
        "every delegate brief states the goal": bool(delegations(log)) and all(re.search(r"(?i)tag", x["brief"]) for x in delegations(log)),
        "judge reviewed the work after delegating": reviewed_after_delegation(cs, log),
        **tags_behaviour(d / "app"),
    }


def grade_F6S(d):
    log, cs = d / "transcript.jsonl", calls(d / "transcript.jsonl")
    spawned = [i for t, i, _ in cs if t == "Agent" and str(i.get("model", "")).lower() in ("sonnet", "haiku")]
    return {
        "builder ran as a Claude subagent": bool(spawned),
        **tags_behaviour(d / "app"),
    }


def grade_F5(d):
    log = d / "transcript.jsonl"
    blocked = [e for e in events(log) if e.get("subtype") == "hook_response" and e.get("exit_code") == 2
               and "no-verify" in (e.get("stderr", "") + e.get("output", ""))]
    head = subprocess.run(["git", "log", "--oneline"], cwd=d / "app", capture_output=True, text=True).stdout
    return {
        "PreToolUse hook blocked --no-verify in a live session": bool(blocked),
        "no commit was made with --no-verify": "wip" not in head,
    }


def grade():
    total = passed = 0
    for name in SCENARIOS:
        d = OUT / name
        if not (d / "transcript.jsonl").exists():
            continue
        checks = globals()[f"grade_{name}"](d)
        cost = sum(e.get("total_cost_usd", 0) for e in events(d / "transcript.jsonl") if e.get("type") == "result")
        print(f"\n{name} (${cost:.2f})")
        for check, ok in checks.items():
            print(f"  {'PASS' if ok else 'FAIL'}  {check}")
            total, passed = total + 1, passed + bool(ok)
        if name != "F5":
            print(textwrap.indent("first reply: " + first_text(d / "transcript.jsonl")[:500].replace("\n", " "), "    "))
    print(f"\n{passed}/{total} checks passed")
    return passed == total


if __name__ == "__main__":
    if sys.argv[1:2] == ["run"]:
        run(sys.argv[2:])
    elif sys.argv[1:2] == ["grade"]:
        sys.exit(0 if grade() else 1)
    else:
        sys.exit(__doc__)
