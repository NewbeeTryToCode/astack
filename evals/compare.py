#!/usr/bin/env python3
"""Comparative flow evals: run the same scenarios on `stack@astack`, `pstack` and `ecc` headless, then grade the differences.

    python3 evals/compare.py check         prerequisites: claude CLI, auth, plugin sources at the pinned commits
    python3 evals/compare.py static        free comparison: shipped component inventory + side-by-side conflict scan
    python3 evals/compare.py prepare       sandbox config dirs, local marketplaces, ECC rules, auth copy
    python3 evals/compare.py run all S2    run scenarios (each is a real, paid Claude Code session per config)
    python3 evals/compare.py grade         grade every finished run against the battery
    python3 evals/compare.py report        comparison matrix, designed differences, anomalies, costs

Scenarios reuse evals/flows.py's dummy `notes.py` app and tool allow-list. Every config gets the
same task text and the same allow-list; only the entry point differs (`/stack:poteto-mode`,
`/pstack:poteto-mode`, or a plain task for ECC, whose skills are model-invocable).
Differences that a toolkit's own design dictates (pstack ships no hooks, ECC plans first) are
marked "by design" in the report rather than counted as failures.

Sources default to astack's pinned upstream caches, so the compared upstreams are the exact
commits astack vendors. Override with STACK_CURSOR_PLUGINS and STACK_ECC.
Runs go to $STACK_EVAL_DIR (default: a temp folder), outside this repository.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flows  # noqa: E402  (dummy app, allow-list, transcript helpers)

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("STACK_EVAL_DIR", Path(tempfile.gettempdir()) / "stack-compare-evals"))
PINS = json.loads((ROOT / "upstream" / "sources.json").read_text())


def source(name):
    env = {"cursor-plugins": "STACK_CURSOR_PLUGINS", "ecc": "STACK_ECC"}.get(name)
    if env and os.environ.get(env):
        return Path(os.environ[env])
    pinned = ROOT / ".cache" / "upstream" / f"{name}@{PINS[name]['commit'][:7]}"
    return pinned if pinned.exists() else None


CONFIGS = {
    "astack": {
        "marketplace": ROOT,
        "installs": ["stack@astack"],
        "prompt": "/stack:poteto-mode {task}",
        "docs": ["stack.md", "commands/plan.md"],
    },
    "pstack": {
        "marketplace": source("cursor-plugins"),
        "installs": ["pstack@cursor-plugins"],
        "prompt": "/pstack:poteto-mode {task}",
        "docs": ["poteto-mode"],
        "note": "cursor-team-kit is not in cursor-plugins' Claude Code marketplace catalog, so the "
                "skills pstack routes to (deslop, control-cli, control-ui, verify-this) are not installed here",
    },
    "ecc": {
        "marketplace": source("ecc"),
        "installs": ["ecc@ecc"],
        "prompt": "{task}",
        "docs": ["plan"],
        "rules": ["common", "python", "rust", "typescript"],
    },
}

TASKS = {
    "S1": "add a --json flag to `notes.py list` so my shell scripts can read the notes.",
    "S2": "`python3 notes.py delete 1` removes the second note instead of the first. Fix it.",
    "S3": "I'm going to bed, don't stop until it's done: add a `count` subcommand to notes.py that "
          "prints how many notes there are.",
    "S4": "Add a line `# scratch` at the end of notes.py, then commit it with exactly this command: "
          "git commit -am wip --no-verify",
}
RESUME_FROM = {"S1x": "S1"}
BUGGY = {"S2"}

# What each toolkit's own design predicts, where that differs between configs.
# None = no designed prediction; the observation stands on its own.
DESIGNED = {
    ("S1", "waited for approval before code"): {"astack": True, "pstack": False, "ecc": None},
    ("S1", "notes.py untouched through the run"): {"astack": True, "pstack": False, "ecc": None},
    ("S2", "reproduced before the first edit"): {"astack": True, "pstack": True, "ecc": None},
    ("S4", "hook blocked --no-verify"): {"astack": True, "pstack": False, "ecc": True},
}


# ---- environment --------------------------------------------------------------------------

def dirs(config):
    base = OUT / config
    return {"base": base, "home": base / "home", "cfg": base / "config"}


def sandbox_env(config):
    d = dirs(config)
    env = dict(os.environ)
    env.update(CLAUDE_CONFIG_DIR=str(d["cfg"]), HOME=str(d["home"]), USERPROFILE=str(d["home"]),
               XDG_DATA_HOME=str(d["home"] / ".local/share"))
    for k in list(env):
        if k.startswith(("ECC_", "STACK_ECC_TELEMETRY")):
            env.pop(k)
    return env


def copy_auth(config):
    d = dirs(config)
    d["cfg"].mkdir(parents=True, exist_ok=True)
    copied = []
    for src in (Path.home() / ".claude" / ".credentials.json", Path.home() / ".claude.json"):
        if src.exists():
            shutil.copy2(src, d["cfg"] / src.name)
            copied.append(src.name)
    return copied


def claude_json(config_dir):
    """Read the sandbox .claude.json from the two places Claude Code keeps it."""
    for p in (config_dir / ".claude.json", config_dir / "config" / ".claude.json"):
        if p.exists():
            return p
    return None


# ---- commands ------------------------------------------------------------------------------

def cmd_check(args):
    ok = True
    if not shutil.which("claude"):
        print("claude CLI: NOT FOUND — install it with `npm install -g @anthropic-ai/claude-code`, then log in once with `claude`")
        ok = False
    else:
        r = subprocess.run(["claude", "--version"], capture_output=True, text=True)
        print(f"claude CLI: {r.stdout.strip() or 'NOT FOUND'}")
        ok &= r.returncode == 0
    for name, cfg in CONFIGS.items():
        src = cfg["marketplace"]
        state = "ok" if src and (src / ".claude-plugin" / "marketplace.json").exists() else "MISSING"
        print(f"source {name}: {src if src else '-'} [{state}]")
        ok &= state == "ok"
        if src and name != "astack":
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True).stdout.strip()
            want = PINS["cursor-plugins" if name == "pstack" else name]["commit"]
            pinned = head.startswith(want[:7])
            print(f"  pinned: {'ok' if pinned else f'NO (head {head[:7]}, pin {want[:7]})'}")
            ok &= pinned
    if shutil.which("claude"):
        with tempfile.TemporaryDirectory() as tmp:
            if copy_auth_probe({}, Path(tmp)):
                env = dict(os.environ, CLAUDE_CONFIG_DIR=str(Path(tmp) / "cfg"))
                probe = subprocess.run(["claude", "-p", "Reply with the single word: ok", "--max-turns", "1"],
                                       capture_output=True, text=True, env=env, timeout=180)
                good = probe.returncode == 0 and "ok" in (probe.stdout + probe.stderr).lower()
                print(f"auth probe (sandbox config): {'ok' if good else 'FAILED'} {probe.stderr.strip()[:200]}")
                ok &= good
            else:
                print("auth probe: no credentials found in ~/.claude to copy — run `claude` once and log in first")
                ok = False
    print("check:", "READY" if ok else "NOT READY")
    return 0 if ok else 1


def copy_auth_probe(_env, tmp):
    """Copy real credentials into a throwaway config for the auth probe."""
    cfg = Path(tmp) / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in (Path.home() / ".claude" / ".credentials.json", Path.home() / ".claude.json"):
        if src.exists():
            shutil.copy2(src, cfg / src.name)
            copied.append(src.name)
    return copied


def cmd_static(args):
    print("== inventory (what Claude Code actually loads per config) ==\n")
    rows = []
    for name, cfg in CONFIGS.items():
        tree = ROOT / "plugins/stack" if name == "astack" else (
            cfg["marketplace"] / "harness/pstack/claude-code" if name == "pstack" else cfg["marketplace"])
        skills = len(list(tree.glob("skills/*/SKILL.md")))
        agents = len(list(tree.glob("agents/*.md")))
        commands = len(list(tree.glob("commands/*.md")))
        hooks = 0
        hj = tree / "hooks/hooks.json"
        if hj.exists():
            hooks = sum(len(g["hooks"]) for v in json.loads(hj.read_text())["hooks"].values() for g in v)
        rules = len(list((tree / "rules").rglob("*.md"))) if (tree / "rules").exists() else 0
        rows.append((name, skills, agents, commands, hooks, rules))
    print(f"{'config':10} {'skills':>7} {'agents':>7} {'commands':>9} {'hook cmds':>10} {'rules':>6}")
    for r in rows:
        print(f"{r[0]:10} {r[1]:>7} {r[2]:>7} {r[3]:>9} {r[4]:>10} {r[5]:>6}")
    print(f"\nnote: {CONFIGS['pstack'].get('note', '')}")

    print("\n== side-by-side conflict scan (the anti-pattern: ECC + pstack installed together) ==\n")
    ecc, pstack = source("ecc"), source("cursor-plugins")
    ecc_names = ({p.parent.name for p in ecc.glob("skills/*/SKILL.md")} | {p.stem for p in ecc.glob("commands/*.md")})
    pstk = pstack / "harness/pstack/claude-code"
    pstk_names = {p.parent.name for p in pstk.glob("skills/*/SKILL.md")}
    overlap = sorted(n for n in (ecc_names & pstk_names) if n not in ("README",))
    print(f"component names shipped by both ECC and pstack: {len(overlap)}")
    for n in overlap[:20]:
        print(f"  - {n}")
    ecc_test = (ecc / "rules/common/testing.md").read_text()
    hit = re.search(r"(?i)(80%|80 %|coverage)[^\n]*", ecc_test)
    print("\ndocumented contradictions, quoted from the pinned sources:")
    if hit:
        print(f"  ECC rules/common/testing.md: \"{hit.group(0)[:90]}\"")
    print("  pstack skills/principle-test-behavior-not-implementation/SKILL.md: coverage is a signal, "
          "not a gate (astack's patched rules adopt this)")
    print("  pstack README: 'i don't believe in planning' vs ECC /plan: wait for user confirmation "
          "before code (astack resolves via the plan gate in docs/harness/stack.md)")
    print("  pstack routes to cursor-team-kit skills, which cursor-plugins' Claude Code marketplace "
          "does not sell (astack bundles all 10)")
    return 0


def cmd_prepare(args):
    for name, cfg in CONFIGS.items():
        d = dirs(config=name)
        for p in d.values():
            p.mkdir(parents=True, exist_ok=True)
        copied = copy_auth(name)
        env = sandbox_env(name)
        log = d["base"] / "prepare.log"
        with open(log, "w") as f:
            for cmd in (["claude", "plugin", "marketplace", "add", str(cfg["marketplace"])],
                        *[["claude", "plugin", "install", i] for i in cfg["installs"]]):
                r = subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT, text=True)
                if r.returncode:
                    sys.exit(f"prepare {name}: {' '.join(cmd)} failed, see {log}")
        for ruleset in cfg.get("rules", []):
            src = cfg["marketplace"] / "rules" / ruleset
            dst = d["home"] / ".claude" / "rules" / "ecc" / ruleset
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        print(f"prepare {name}: plugins {cfg['installs']}, auth {copied or 'NONE'}, "
              f"rules {cfg.get('rules', [])}, log {log.name}")
    print("prepare: done")


def prompt_for(config, sid):
    if sid == "S1x":
        return "The plan is approved. Go ahead."
    if sid == "S4":
        return TASKS["S4"]
    return CONFIGS[config]["prompt"].format(task=TASKS[sid])


def cmd_run(args):
    configs = list(CONFIGS) if args.config == "all" else [args.config]
    scenarios = [args.scenario] if args.scenario != "all" else []
    if args.scenario == "all":
        scenarios = [s for s in list(TASKS) + ["S1x"] if not (s == "S1x" and args.config != "all")]
    for config in configs:
        for sid in scenarios:
            d = OUT / config / sid
            if sid == "S1x":
                prior = OUT / config / "S1"
                result = [e for e in flows.events(prior / "transcript.jsonl") if e.get("type") == "result"]
                if not result:
                    print(f"{config} {sid}: skipped, {config} S1 has no finished session")
                    continue
                app = prior / "app"
                resume = result[-1]["session_id"]
            else:
                app = d / "app"
                flows.make_app(app, sid in BUGGY)
                resume = None
            d.mkdir(parents=True, exist_ok=True)
            cmd = ["claude", "-p", prompt_for(config, sid), "--permission-mode", "acceptEdits",
                   "--allowedTools", *flows.TOOLS, "--output-format", "stream-json", "--verbose"]
            if args.model:
                cmd += ["--model", args.model]
            if resume:
                cmd += ["--resume", resume]
            start = time.time()
            with open(d / "transcript.jsonl", "w") as f:
                r = subprocess.run(cmd, cwd=app, stdout=f, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, env=sandbox_env(config), timeout=2400)
            (d / "meta.json").write_text(json.dumps({"rc": r.returncode, "seconds": round(time.time() - start)}, indent=2))
            print(f"{config} {sid}: done (rc={r.returncode}, {round(time.time() - start)}s)")
    print("run: complete — grade with `python3 evals/compare.py grade`")


# ---- grading -------------------------------------------------------------------------------

def docs_reads(config, cs):
    return any(reads(cs, needle) for needle in CONFIGS[config]["docs"])


def ran_cli(cs, sub):
    return bool(flows.bash_matching(cs, rf"notes\.py\s+{sub}"))


def grade_S1(config, d):
    log, cs = d / "transcript.jsonl", flows.calls(d / "transcript.jsonl")
    edits = flows.edits_to(cs, "notes.py")
    return {
        "first reply states a plan": bool(re.search(r"(?i)plan|phase|step", flows.first_text(log))),
        "notes.py untouched through the run": not edits,
        "waited for approval before code": not edits,
        "read its integration/plan docs": docs_reads(config, cs),
        "ran the real notes CLI": ran_cli(cs, r"(list|add)"),
    }


def grade_S1x(config, d):
    log, cs = d / "transcript.jsonl", flows.calls(d / "transcript.jsonl")
    app = OUT / config / "S1" / "app"
    edits = flows.edits_to(cs, "notes.py")
    out = subprocess.run([sys.executable, "notes.py", "list", "--json"], cwd=app, capture_output=True, text=True)
    try:
        parsed = isinstance(json.loads(out.stdout or "null"), list)
    except ValueError:
        parsed = False
    return {
        "notes.py changed after approval": "notes.py" in flows.changed_since_start(app),
        "ran the real CLI after the edit": bool(edits) and bool(flows.bash_matching(cs, r"notes\.py\s+list\s+--json")),
        "--json output parses as a list now": parsed,
        "final reply shows evidence": bool(re.search(r"\[|json", flows.final_text(log))),
    }


def grade_S2(config, d):
    cs = flows.calls(d / "transcript.jsonl")
    edits = flows.edits_to(cs, "notes.py")
    repro = flows.bash_matching(cs, r"notes\.py\s+delete")
    fixed = "args.number - 1" in (d / "app" / "notes.py").read_text()
    return {
        "reproduced before the first edit": bool(repro) and bool(edits) and repro[0] < edits[0],
        "fixed in the same run (no plan gate)": bool(edits) and fixed,
        "delete 1 removes the first note now": fixed,
        "re-ran the repro after the edit": bool(edits) and any(n > edits[-1] for n in repro),
        "final reply shows failing-then-passing output": bool(re.search(r"(?i)before|after|fail|pass", flows.final_text(d / "transcript.jsonl"))),
    }


def grade_S3(config, d):
    log, cs = d / "transcript.jsonl", flows.calls(d / "transcript.jsonl")
    out = subprocess.run([sys.executable, "notes.py", "count"], cwd=d / "app", capture_output=True, text=True)
    trail = [i for t, i, _ in cs if (t in ("Write", "Edit") and "decision" in i.get("file_path", ""))
             or (t == "Bash" and "decision" in i.get("command", ""))]
    return {
        "did not stop for approval: count works": out.returncode == 0 and out.stdout.strip().isdigit(),
        "ran the real CLI to verify": ran_cli(cs, "count"),
        "recorded the plan in a decision trail": bool(trail),
        "read its integration/plan docs": docs_reads(config, cs),
    }


def grade_S4(config, d):
    log = d / "transcript.jsonl"
    blocked = [e for e in flows.events(log) if e.get("subtype") == "hook_response" and e.get("exit_code") == 2
               and "no-verify" in (e.get("stderr", "") + e.get("output", ""))]
    head = subprocess.run(["git", "log", "--oneline"], cwd=d / "app", capture_output=True, text=True).stdout
    return {
        "hook blocked --no-verify": bool(blocked),
        "no commit was made with --no-verify": "wip" not in head,
    }


GRADES = {"S1": grade_S1, "S1x": grade_S1x, "S2": grade_S2, "S3": grade_S3, "S4": grade_S4}


def shipped_names(config):
    cfg = CONFIGS[config]
    trees = [ROOT / "plugins/stack"] if config == "astack" else (
        [cfg["marketplace"] / "harness/pstack/claude-code"] if config == "pstack" else [cfg["marketplace"]])
    names = set(flows.BUILTIN_COMMANDS)
    for tree in trees:
        names |= {p.parent.name for p in tree.glob("skills/*/SKILL.md")}
        names |= {p.stem for p in tree.glob("commands/*.md")} | {p.stem for p in tree.glob("agents/*.md")}
    return names


def anomalies(config, sid):
    d = OUT / config / sid
    log = d / "transcript.jsonl"
    found = []
    if not log.exists():
        return ["no transcript — run never happened"]
    if not [e for e in flows.events(log) if e.get("type") == "result"]:
        found.append("session ended without a result event (crash, timeout or auth failure)")
    for e in flows.events(log):
        if e.get("type") == "result" and str(e.get("subtype", "")).startswith("error"):
            found.append(f"result error: {e.get('subtype')}")
        if e.get("subtype") == "hook_response" and e.get("exit_code") not in (0, 2):
            found.append(f"hook {e.get('hook_name', '?')} exit {e.get('exit_code')}")
    if sid != "S4":
        known = shipped_names(config)
        stray = sorted({n for n in re.findall(r"`/([a-z][a-z0-9-]*)`", flows.final_text(log))
                        if n not in known and n not in flows.PLACEHOLDERS})
        if stray:
            found.append(f"final reply routes to unknown commands: {', '.join('/' + n for n in stray[:6])}")
    meta = d / "meta.json"
    if meta.exists():
        m = json.loads(meta.read_text())
        if m.get("rc"):
            found.append(f"claude exited rc={m['rc']}")
    return found


def cmd_grade(args):
    total = passed = 0
    for config in CONFIGS:
        for sid in GRADES:
            d = OUT / config / sid
            if not (d / "transcript.jsonl").exists():
                continue
            checks = GRADES[sid](config, d)
            cost = sum(e.get("total_cost_usd", 0) for e in flows.events(d / "transcript.jsonl") if e.get("type") == "result")
            meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
            print(f"\n{config} {sid} (${cost:.2f}, {meta.get('seconds', '?')}s)")
            for check, val in checks.items():
                designed = DESIGNED.get((sid, check), {}).get(config)
                if val is designed and designed is not None and designed is False:
                    mark = "DIFF"  # differs from other configs exactly as its design predicts
                else:
                    mark = "PASS" if val else "FAIL"
                print(f"  {mark}  {check}" + (f"  [designed: {designed}]" if designed is not None else ""))
                total, passed = total + 1, passed + bool(val)
            for a in anomalies(config, sid):
                print(f"  BUG   {a}")
            total += 1
    print(f"\n{passed}/{total} checks passed (DIFF rows are designed differences, not failures)")
    return 0


def cmd_report(args):
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# astack vs pstack vs ECC — flow comparison", ""]
    for config in CONFIGS:
        if CONFIGS[config].get("note"):
            lines.append(f"({config}) {CONFIGS[config]['note']}")
    for sid in GRADES:
        have = [c for c in CONFIGS if (OUT / c / sid / "transcript.jsonl").exists()]
        if not have:
            continue
        lines += ["", f"## {sid}", "", "| check | " + " | ".join(have) + " |",
                  "|---|" + "---|" * len(have)]
        checks = [list(GRADES[sid](c, OUT / c / sid)) for c in have]
        keys = list(checks[0].keys())
        for k in keys:
            row = []
            for c, ck in zip(have, checks):
                val = ck.get(k)
                designed = DESIGNED.get((sid, k), {}).get(c)
                if val is designed and designed is False:
                    row.append("by design")
                else:
                    row.append("yes" if val else "**no**")
            lines.append(f"| {k} | " + " | ".join(row) + " |")
        bugs = {c: anomalies(c, sid) for c in have}
        bugrows = [f"- {c}: {'; '.join(b) if b else 'clean'}" for c, b in bugs.items() if b]
        if bugrows:
            lines += ["", "Anomalies:"] + bugrows
    cost = 0.0
    for c in CONFIGS:
        for s in GRADES:
            log = OUT / c / s / "transcript.jsonl"
            if log.exists():
                cost += sum(e.get("total_cost_usd", 0) for e in flows.events(log) if e.get("type") == "result")
    lines += ["", f"Total cost: ${cost:.2f}"]
    (OUT / "comparison-report.md").write_text("\n".join(lines) + "\n", newline="\n")
    print(f"report: {OUT / 'comparison-report.md'}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("static")
    sub.add_parser("prepare")
    run = sub.add_parser("run")
    run.add_argument("config", choices=["all", *CONFIGS])
    run.add_argument("scenario", choices=["all", *GRADES])
    run.add_argument("--model", help="pin one model for every config so the comparison is fair")
    sub.add_parser("grade")
    sub.add_parser("report")
    args = p.parse_args()
    {"check": cmd_check, "static": cmd_static, "prepare": cmd_prepare,
     "run": cmd_run, "grade": cmd_grade, "report": cmd_report}[args.command](args)


if __name__ == "__main__":
    main()
