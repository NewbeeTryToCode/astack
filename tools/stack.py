#!/usr/bin/env python3
"""Build, check and verify the `stack` plugin from pinned upstream sources.

    python3 tools/stack.py build    vendor the manifest, apply rewrites and patches, add the overlay
    python3 tools/stack.py check    rebuild into a temp dir and fail if plugins/stack differs
    python3 tools/stack.py diff     turn edits made in plugins/stack into patches and overlay changes
    python3 tools/stack.py verify   fail if any skill, agent, command, link, playbook or hook script is missing

`--local NAME=PATH` uses a checkout already at the pinned commit instead of fetching.
"""

import argparse
import difflib
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "upstream"
PATCHES = UPSTREAM / "patches"
CACHE = ROOT / ".cache" / "upstream"

ADAPTER_LINE = (
    "In Claude Code, read [the Claude Code adapter](../../docs/harness/claude-code.md) once per "
    "session before you follow this skill. It maps the Cursor names in pstack skills to Claude Code."
)


def load(name):
    return json.loads((UPSTREAM / name).read_text())


def sh(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def fetch(name, spec, local):
    if name in local:
        path = Path(local[name]).resolve()
        head = sh("git", "rev-parse", "HEAD", cwd=path).strip()
        if head != spec["commit"]:
            sys.exit(f"--local {name} is at {head}, the lock pins {spec['commit']}")
        return path
    path = CACHE / f"{name}@{spec['commit']}"
    if (path / ".git").is_dir():
        return path
    path.mkdir(parents=True, exist_ok=True)
    sh("git", "init", "-q", cwd=path)
    sh("git", "fetch", "-q", "--depth", "1", spec["repo"], spec["commit"], cwd=path)
    sh("git", "checkout", "-q", "FETCH_HEAD", cwd=path)
    return path


def glob_files(base, include, exclude):
    files = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())
    files = [f for f in files if not f.startswith(".git/") and "/node_modules/" not in f and not f.endswith(".DS_Store")]

    def hit(f, patterns):
        return any(fnmatch.fnmatchcase(f, p) or (p.endswith("/**") and f.startswith(p[:-2])) for p in patterns)

    picked = [f for f in files if hit(f, include)]
    missing = [p for p in include if not any(hit(f, [p]) for f in picked)]
    if missing:
        sys.exit(f"manifest names files the source does not have: {missing}")
    return [f for f in picked if not hit(f, exclude)]


REQUIRE = re.compile(r"""require\(\s*['"](\.{1,2}/[^'"]+)['"]\s*\)""")


def js_closure(base, seeds):
    seen, stack = set(), list(seeds)
    while stack:
        rel = stack.pop()
        for candidate in (rel, rel + ".js", rel + "/index.js", rel + ".json"):
            if (base / candidate).is_file():
                rel = candidate
                break
        else:
            sys.exit(f"hook runtime requires {rel}, which the source does not have")
        if rel in seen:
            continue
        seen.add(rel)
        if rel.endswith(".js"):
            for m in REQUIRE.finditer((base / rel).read_text()):
                stack.append(os.path.normpath(os.path.join(os.path.dirname(rel), m.group(1))))
    return sorted(seen)


def inject_adapter(text):
    if ADAPTER_LINE in text or not text.startswith("---\n"):
        return text
    end = text.index("\n---\n", 4) + 5
    head, body = text[:end], text[end:].lstrip("\n")
    title, _, rest = body.partition("\n")
    if title.startswith("# "):
        return f"{head}\n{title}\n\n{ADAPTER_LINE}\n{rest}"
    return f"{head}\n{ADAPTER_LINE}\n\n{body}"


SLASH = re.compile(r"`/([a-z][a-z0-9-]*)((?: [^`]*)?)`")


def rewrite_commands(text, plugin, shipped, remap):
    def sub(m):
        name, args = m.group(1), m.group(2)
        if name in shipped:
            return f"`/{plugin}:{name}{args}`"
        if name in remap:
            return f"`/{plugin}:{remap[name]}{args}`"
        return m.group(0)

    return SLASH.sub(sub, text)


def build(out, local, with_patches=True, with_overlay=True):
    sources, manifest = load("sources.json"), load("manifest.json")
    plugin = manifest["plugin"]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    roots = {name: fetch(name, spec, local) for name, spec in sources.items()}
    vendored = {}

    for entry in manifest["entries"]:
        base = roots[entry["source"]] / entry["base"]
        if "js_closure" in entry:
            files = js_closure(base, entry["js_closure"])
        else:
            files = glob_files(base, entry["include"], entry.get("exclude", []))
        for rel in files:
            dest = out / rel
            if rel in vendored:
                sys.exit(f"two manifest entries write {rel}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base / rel, dest)
            vendored[rel] = {"source": entry["source"], "path": f"{entry['base']}/{rel}".lstrip("/"), "entry": entry}

    shipped_commands = {Path(r).stem for r in vendored if r.startswith("commands/")}
    for rel, info in vendored.items():
        entry, path = info.pop("entry"), out / rel
        if not rel.endswith(".md"):
            continue
        text = path.read_text()
        if entry.get("inject_adapter") and rel.endswith("SKILL.md"):
            text = inject_adapter(text)
        if entry.get("rewrite_commands"):
            text = rewrite_commands(text, plugin, shipped_commands, manifest.get("command_remap", {}))
        path.write_text(text)

    for name, lic in manifest["licenses"].items():
        dest = out / "LICENSES" / f"{name}.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(roots[lic["source"]] / lic["path"], dest)

    if with_patches:
        for patch in sorted(PATCHES.glob("*.patch")):
            subprocess.run(["patch", "-p1", "-s", "-f", "--no-backup-if-mismatch", "-d", str(out), "-i", str(patch)], check=True)

    overlay = ROOT / manifest["overlay"]
    if with_overlay:
        for src in sorted(p for p in overlay.rglob("*") if p.is_file()):
            rel = src.relative_to(overlay).as_posix()
            if rel in vendored:
                sys.exit(f"overlay file {rel} shadows a vendored file. Patch it instead.")
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    lock = {
        "sources": {n: s["commit"] for n, s in sources.items()},
        "files": {rel: dict(info, sha256=hashlib.sha256((out / rel).read_bytes()).hexdigest()) for rel, info in sorted(vendored.items())},
    }
    (out / "VENDORED.json").write_text(json.dumps(lock, indent=2) + "\n")
    return out


def tree(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def cmd_build(args):
    out = build(ROOT / load("manifest.json")["out"], args.local)
    print(f"built {out.relative_to(ROOT)}")


def cmd_check(args):
    committed = ROOT / load("manifest.json")["out"]
    with tempfile.TemporaryDirectory() as tmp:
        fresh = tree(build(Path(tmp) / "out", args.local))
    current = tree(committed)
    drift = sorted(f for f in fresh.keys() | current.keys() if fresh.get(f) != current.get(f))
    if drift:
        print("plugins/stack does not match upstream + patches + overlay:", *drift[:40], sep="\n  ")
        print("run `python3 tools/stack.py diff` to keep the edits, or `build` to drop them")
        sys.exit(1)
    print("check: plugins/stack matches upstream + patches + overlay")


def cmd_diff(args):
    manifest = load("manifest.json")
    committed = ROOT / manifest["out"]
    lock = json.loads((committed / "VENDORED.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        pristine = build(Path(tmp) / "out", args.local, with_patches=False, with_overlay=False)
        for old in PATCHES.glob("*.patch"):
            old.unlink()
        written = 0
        for rel in lock["files"]:
            if (pristine / rel).read_bytes() == (committed / rel).read_bytes():
                continue
            if rel.endswith((".jpg", ".png", ".gif")):
                sys.exit(f"{rel} is binary and differs from upstream. Binary files cannot be patched.")
            before, after = (pristine / rel).read_text(), (committed / rel).read_text()
            lines = difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{rel}", f"b/{rel}")
            (PATCHES / (rel.replace("/", "__") + ".patch")).write_text("".join(lines))
            written += 1
    overlay = ROOT / manifest["overlay"]
    for rel, data in tree(committed).items():
        if rel in lock["files"] or rel == "VENDORED.json" or rel.startswith("LICENSES/"):
            continue
        dest = overlay / rel
        if not dest.exists() or dest.read_bytes() != data:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            print(f"overlay updated: {rel}")
    print(f"diff: {written} patch file(s) in upstream/patches")


# ---- verify -------------------------------------------------------------------------------

BUILTIN_COMMANDS = {
    "loop", "compact", "plugin", "plugins", "model", "effort", "clear", "init", "agents", "mcp",
    "config", "hooks", "help", "memory", "permissions", "resume", "review", "status", "add-dir",
    "context", "cost", "doctor", "export", "ide", "login", "logout", "rewind", "skills", "tasks",
    "todos", "fast", "plan", "goal", "add-plugin", "create-skill", "autopilot",
}
NOT_COMMANDS = {"tmp", "dev", "usr", "bin", "etc", "opt", "var", "home", "users", "proc", "repo", "api", "v1", "workspace"}
BUILTIN_AGENTS = {"general-purpose", "generalPurpose", "Explore", "explore", "Plan"}
PLACEHOLDERS = {"name", "url", "skill", "skill-name"}
FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
LINK = re.compile(r"\]\(([^)\s]+)\)")
PLAYBOOK = re.compile(r"playbooks/([a-z0-9-]+)\.md")
PRINCIPLE = re.compile(r"\bprinciple-([a-z0-9]+(?:-[a-z0-9]+)*)\b")
PLUGIN_REF = re.compile(r"\b{plugin}:([a-z0-9]+(?:-[a-z0-9]+)*)\b")
BOLD_SKILL = re.compile(r"(?:\*\*|`)([a-z0-9]+(?:-[a-z0-9]+)*)(?:\*\*|`) (?:skill|agent)\b")
AGENT_TYPE = re.compile(r"subagent_type: \"([a-zA-Z0-9:_-]+)\"")
SLASH_REF = re.compile(r"`/([a-z][a-z0-9-]*)(?:[ `])")


def frontmatter(text):
    if not text.startswith("---\n"):
        return {}
    block = text[4:text.find("\n---", 4)]
    return dict(re.findall(r"^([a-zA-Z_-]+):\s*(.*)$", block, re.M))


def name_map(out):
    """Names that docs/harness/stack.md maps or lists as not shipped, read from those two sections."""
    doc = out / "docs/harness/stack.md"
    if not doc.exists():
        return set()
    text = doc.read_text()
    mapped = text.split("## Name map", 1)[-1].split("\n## ", 1)[0]
    first_cells = re.findall(r"^\|([^|]*)\|", mapped, re.M)
    names = {name for cell in first_cells for name in re.findall(r"`/?([A-Za-z0-9:_-]+)`", cell)}
    if "## Not shipped" in text:
        names |= set(re.findall(r"`([a-z0-9-]+)`", text.split("## Not shipped", 1)[1].split("\n## ", 1)[0]))
    return names


def upstream_names(local):
    """Every skill, agent and command name the pinned sources define."""
    roots = {name: fetch(name, spec, local) for name, spec in load("sources.json").items()}
    names = set()
    for base in (roots["cursor-plugins"] / "pstack", roots["cursor-plugins"] / "cursor-team-kit", roots["ecc"]):
        names |= {p.parent.name for p in base.glob("skills/*/SKILL.md")}
        names |= {p.stem for p in base.glob("agents/*.md")} | {p.stem for p in base.glob("commands/*.md")}
    return names


MENTION = re.compile(r"(?:\*\*|`)/?([a-z0-9]+(?:-[a-z0-9]+)+)(?:\*\*|`)")


def verify(out, plugin, upstream=frozenset()):
    problems = []
    md = {p.relative_to(out).as_posix(): p.read_text() for p in out.rglob("*.md")}
    skills = {p.parent.name for p in out.glob("skills/*/SKILL.md")}
    commands = {p.stem for p in out.glob("commands/*.md")}
    agents = {p.stem for p in out.glob("agents/*.md")}
    mapped = name_map(out)

    for name in sorted(skills):
        fm = frontmatter(md[f"skills/{name}/SKILL.md"])
        if fm.get("name") != name:
            problems.append(f"skills/{name}/SKILL.md: frontmatter name is {fm.get('name')!r}")
        if not fm.get("description"):
            problems.append(f"skills/{name}/SKILL.md: no description")
    for name in sorted(agents):
        fm = frontmatter(md[f"agents/{name}.md"])
        if not fm.get("description"):
            problems.append(f"agents/{name}.md: no description")
    unshipped = set(upstream) - skills - commands - agents - mapped
    for rel, text in md.items():
        for name in sorted(set(MENTION.findall(FENCE.sub("", text))) & unshipped):
            problems.append(f"{rel}: mentions {name}, which this plugin does not ship and the Name map does not cover")
    for clash in sorted(skills & commands):
        problems.append(f"/{plugin}:{clash} is both a skill and a command")

    for rel, text in md.items():
        prose = FENCE.sub("", text)
        here = (out / rel).parent
        for target in LINK.findall(prose):
            if re.match(r"^[a-z]+:", target) or target.startswith("#") or "<" in target or target in PLACEHOLDERS:
                continue
            path = target.split("#")[0]
            if path and not (here / path).exists():
                problems.append(f"{rel}: broken link {target}")
        for name in PLAYBOOK.findall(text):
            if not (out / "skills/poteto-mode/playbooks" / f"{name}.md").exists():
                problems.append(f"{rel}: playbook {name} does not exist")
        for name in PRINCIPLE.findall(text):
            if f"principle-{name}" not in skills:
                problems.append(f"{rel}: principle-{name} does not exist")
        for name in BOLD_SKILL.findall(prose):
            if name not in skills | commands | agents | mapped | PLACEHOLDERS and not name.startswith("principle-"):
                problems.append(f"{rel}: **{name}** skill does not exist")
        for name in re.findall(PLUGIN_REF.pattern.format(plugin=plugin), text):
            if name not in skills | commands | agents:
                problems.append(f"{rel}: {plugin}:{name} does not exist")
        for name in AGENT_TYPE.findall(text):
            bare = name.split(":")[-1]
            if bare not in agents and name not in BUILTIN_AGENTS | mapped:
                problems.append(f"{rel}: subagent_type {name} is not a shipped agent")
        for name in SLASH_REF.findall(prose):
            if name in NOT_COMMANDS | BUILTIN_COMMANDS | PLACEHOLDERS | mapped:
                continue
            if name not in skills and name not in commands:
                problems.append(f"{rel}: /{name} is not a skill or command in this plugin")

    hooks = out / "hooks/hooks.json"
    if hooks.exists():
        for event, groups in json.loads(hooks.read_text())["hooks"].items():
            for group in groups:
                for hook in group["hooks"]:
                    for script in re.findall(r"scripts/[A-Za-z0-9_./-]+\.(?:js|py|sh)", hook["command"]):
                        if not (out / script).exists():
                            problems.append(f"hooks.json {event}: {script} does not exist")
    for js in out.rglob("*.js"):
        r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        if r.returncode:
            problems.append(f"{js.relative_to(out)}: {r.stderr.strip().splitlines()[-1]}")
        for m in REQUIRE.finditer(js.read_text()):
            target = (js.parent / m.group(1)).resolve()
            if not any(Path(str(target) + ext).exists() for ext in ("", ".js", ".json", "/index.js")):
                problems.append(f"{js.relative_to(out)}: requires missing {m.group(1)}")
    return problems, {"skills": len(skills), "commands": len(commands), "agents": len(agents)}


def cmd_verify(args):
    manifest = load("manifest.json")
    out = Path(args.path) if args.path else ROOT / manifest["out"]
    problems, counts = verify(out, manifest["plugin"], upstream_names(args.local))
    for p in problems:
        print(p)
    summary = ", ".join(f"{v} {k}" for k, v in counts.items())
    if problems:
        sys.exit(f"verify: {len(problems)} problem(s) in {summary}")
    print(f"verify: every reference resolves ({summary})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["build", "check", "diff", "verify"])
    parser.add_argument("--local", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--path", help="verify this directory instead of plugins/stack")
    args = parser.parse_args()
    args.local = dict(item.split("=", 1) for item in args.local)
    {"build": cmd_build, "check": cmd_check, "diff": cmd_diff, "verify": cmd_verify}[args.command](args)


if __name__ == "__main__":
    main()
