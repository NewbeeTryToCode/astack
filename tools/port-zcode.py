#!/usr/bin/env python3
"""Port the built `stack` plugin to ZCode's skill and agent format.

    python3 tools/port-zcode.py            generate plugins/stack-zcode/ and verify it
    python3 tools/port-zcode.py --install  also copy the skills to ~/.zcode/skills and agents to ~/.zcode/agents

Every skill and agent keeps its name under a `stack-` prefix (`stack-poteto-mode`,
`stack-deslop`, `stack-plan`), so nothing shadows skills already installed in ZCode.
Cursor and Claude Code names are rewritten where unambiguous and mapped in
`docs/harness/zcode.md` (the adapter the skills point at) where they are prose.
ZCode ignores plugin agents, so the 23 agents are plain files meant for `~/.zcode/agents/`.
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "plugins" / "stack"
OUT = ROOT / "plugins" / "stack-zcode"
USER_SKILLS = Path.home() / ".zcode" / "skills"
USER_AGENTS = Path.home() / ".zcode" / "agents"

ORIGIN = {"harness/pstack/": "pstack", "cursor-team-kit/": "cursor-team-kit", "": "ECC"}

LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
SLASH_STACK = re.compile(r"/stack:([a-z0-9-]+)")
AGENT_STACK = re.compile(r"(?<![-/])\bstack:([a-z][a-z0-9-]+)")
CMD_PATH = re.compile(r"`<pstack>/commands/([a-z0-9-]+)\.md`")
PLACEHOLDERS = {"url", "name", "target", "file", "path"}
EXPLAIN = {"README.md", "docs/harness/zcode.md"}  # these two explain the /stack: -> /stack- mapping


def mapped_dest(rel):
    """Where a path from the Claude Code tree landed in the ZCode tree."""
    parts = rel.split("/")
    if len(parts) > 1 and parts[0] == "skills" and not parts[1].startswith("stack-"):
        parts[1] = f"stack-{parts[1]}"
    if rel == "docs/harness/claude-code.md":
        return OUT / "docs/harness/zcode.md"
    return OUT / "/".join(parts)


def fm(text):
    """Split a markdown file into (frontmatter dict, body)."""
    if not text.startswith("---\n"):
        return {}, text
    block, _, body = text[4:].partition("\n---\n")
    fields = {}
    for line in block.splitlines():
        key, _, value = line.partition(":")
        if key and value.strip() and not key.startswith(" "):
            fields[key.strip()] = value.strip()
    return fields, body


def origin_of(vendored_rel):
    info = VENDORED["files"].get(vendored_rel)
    if info is None:
        return "stack"
    src = info.get("source", "")
    if src != "cursor-plugins":
        return "ECC" if src == "ecc" else src
    up = info.get("path", "")
    return ORIGIN["cursor-team-kit/"] if up.startswith("cursor-team-kit/") else "pstack"


def rewrite(text):
    text = text.replace("claude-code.md", "zcode.md")
    text = text.replace("the Claude Code adapter", "the ZCode adapter")
    text = text.replace("It maps the Cursor names in pstack skills to Claude Code.",
                        "It maps the upstream names in the bundled skills to ZCode.")
    text = text.replace("In Claude Code,", "In ZCode,")
    text = text.replace("Claude Code", "ZCode").replace("claude code", "ZCode")
    text = SLASH_STACK.sub(r"/stack-\1", text)
    text = AGENT_STACK.sub(r"stack-\1", text)
    text = text.replace("pstack:poteto-agent", "stack-poteto-agent").replace("poteto-agent", "stack-poteto-agent")
    text = text.replace("comment-sicko", "stack-comment-sicko")
    text = CMD_PATH.sub(r"the `stack-\1` skill", text)
    text = text.replace("$ARGUMENTS", "the arguments this skill received")
    return text


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, newline="\n")


def origin_dir_of(out_md):
    """The directory of the file's Claude Code original, after undoing the renames."""
    rel = out_md.relative_to(OUT).as_posix()
    parts = rel.split("/")
    if parts[0] == "skills" and len(parts) > 1 and parts[1].startswith("stack-"):
        parts[1] = parts[1][len("stack-"):]
    if parts[0] == "agents" and parts[-1].startswith("stack-"):
        parts[-1] = parts[-1][len("stack-"):]
    origin = SRC / "/".join(parts)
    if parts[0] == "skills" and not origin.exists():
        return SRC / "commands"  # a command converted into a skill
    return origin.parent


def fix_links(out_md, origin_dir):
    """Re-point relative links at where the target landed in the ZCode tree."""
    text = out_md.read_text()
    here = out_md.parent
    changed = False
    for target in LINK.findall(FENCE.sub("", text)):
        if re.match(r"^[a-z]+:", target) or target.startswith("#") or target in PLACEHOLDERS:
            continue
        path = target.split("#")[0]
        if not path:
            continue
        resolved = (origin_dir / path).resolve()
        if not (resolved.is_file() or resolved.is_dir()):
            continue
        try:
            rel = resolved.relative_to(SRC.resolve()).as_posix()
        except ValueError:
            continue
        dest = mapped_dest(rel)
        new = Path(os.path.relpath(dest, here)).as_posix().replace(os.sep, "/")
        if new != target:
            text = text.replace(f"]({target})", f"]({new})")
            changed = True
    if changed:
        write(out_md, text)


def generate():
    global VENDORED
    VENDORED = json.loads((SRC / "VENDORED.json").read_text())
    if OUT.exists():
        shutil.rmtree(OUT)
    skills = OUT / "skills"
    commands = {p.stem for p in SRC.glob("commands/*.md")}

    # skills: copy each directory under a stack- prefixed name, rewrite its SKILL.md
    for src_skill in sorted(SRC.glob("skills/*/")):
        name = f"stack-{src_skill.name}"
        shutil.copytree(src_skill, skills / name)
        for md in (skills / name).rglob("*.md"):
            md.write_text(rewrite(md.read_text()), newline="\n")
        out_skill_md = skills / name / "SKILL.md"
        fields, body = fm(out_skill_md.read_text())
        head = [f"name: {name}", f"description: {fields.get('description', name)}",
                f"metadata:\n  origin: {origin_of(f'skills/{src_skill.name}/SKILL.md')}"]
        write(out_skill_md, "---\n" + "\n".join(head) + "\n---\n" + body)

    # commands become skills too: /stack:plan is /stack-plan, a plain skill invocation
    for src_cmd in sorted(SRC.glob("commands/*.md")):
        name = f"stack-{src_cmd.stem}"
        fields, body = fm(src_cmd.read_text())
        desc = fields.get("description", f"the {src_cmd.stem} command")
        skill_dir = skills / name
        skill_dir.mkdir(parents=True)
        text = (f"---\nname: {name}\ndescription: {desc}\nwhen_to_use: {desc}\n"
                f"metadata:\n  origin: {origin_of(f'commands/{src_cmd.stem}.md')}\n---\n# {src_cmd.stem}\n\n")
        arg = fields.get("argument-hint", "").strip()
        if arg:
            text += f"Arguments: `{arg}` — use them wherever the body says to use the arguments.\n\n"
        write(skill_dir / "SKILL.md", text + rewrite(body))

    # agents: ZCode ignores plugin agents, so these are plain files for ~/.zcode/agents
    for src_agent in sorted(SRC.glob("agents/*.md")):
        fields, body = fm(src_agent.read_text())
        head = [f"name: stack-{fields.get('name', src_agent.stem)}", f"description: {fields.get('description', '')}"]
        if fields.get("tools"):
            head.append(f"tools: {fields['tools']}")
        write(OUT / "agents" / f"stack-{src_agent.stem}.md", "---\n" + "\n".join(head) + "\n---\n" + rewrite(body))

    # docs: the ZCode adapter replaces the Claude Code one; rules and licenses ride along
    shutil.copytree(SRC / "docs", OUT / "docs")
    (OUT / "docs/harness/claude-code.md").unlink()
    for md in (OUT / "docs").rglob("*.md"):
        md.write_text(rewrite(md.read_text()), newline="\n")
    shutil.copy(ROOT / "tools" / "zcode-adapter.md", OUT / "docs/harness/zcode.md")
    shutil.copytree(SRC / "rules", OUT / "rules")
    shutil.copytree(SRC / "LICENSES", OUT / "LICENSES")
    write(OUT / "README.md", README)
    for md in OUT.rglob("*.md"):
        fix_links(md, origin_dir_of(md))

    version = json.loads((SRC / ".claude-plugin" / "plugin.json").read_text()).get("version", "0.0.0")
    write(OUT / ".zcode-plugin" / "plugin.json", json.dumps({
        "name": "stack", "version": version,
        "description": "astack's stack plugin ported to ZCode: pstack judgment/verification + ECC planning and guardrails as stack-* skills",
        "skills": ["./skills"],
    }, indent=2) + "\n")
    market = ROOT / ".zcode-plugin" / "marketplace.json"
    if not market.exists():
        write(market, json.dumps({"name": "astack", "plugins": [
            {"name": "stack", "source": "./plugins/stack-zcode", "version": version,
             "description": "stack ported to ZCode skills"}]}, indent=2) + "\n")

    verify()
    print(f"generated {OUT.relative_to(ROOT)}")


def verify():
    out_skills = {p.parent.name for p in OUT.glob("skills/*/SKILL.md")}
    agents = list(OUT.glob("agents/*.md"))
    problems = []
    if len(out_skills) != 105:
        problems.append(f"expected 105 skills (92 + 13 commands), found {len(out_skills)}")
    if len(agents) != 23:
        problems.append(f"expected 23 agents, found {len(agents)}")
    for md in OUT.rglob("*.md"):
        rel = md.relative_to(OUT).as_posix()
        text = md.read_text()
        prose = FENCE.sub("", text)
        if "claude-code.md" in prose or ("/stack:" in prose and rel not in EXPLAIN):
            problems.append(f"{rel}: unrewritten Claude Code reference")
        fields, _ = fm(text)
        if md.name == "SKILL.md" and md.parent.parent.name == "skills" and fields.get("name") != md.parent.name:
            problems.append(f"{rel}: frontmatter name {fields.get('name')!r} != directory")
        for target in LINK.findall(prose):
            if re.match(r"^[a-z]+:", target) or target.startswith("#") or target in PLACEHOLDERS:
                continue
            if not (md.parent / target.split("#")[0]).exists():
                problems.append(f"{rel}: broken link {target}")
    if problems:
        print(*problems, sep="\n")
        sys.exit(f"verify: {len(problems)} problem(s)")
    print(f"verify: 105 skills, 23 agents, every link resolves, no unrewritten names")


README = """# stack for ZCode

astack's `stack` plugin ported to ZCode: pstack (judgment, verification, the `poteto-mode`
playbooks), cursor-team-kit (`deslop`, `control-cli`, `control-ui`, `verify-this`) and ECC
(planning, specialists, security) as 105 `stack-*` skills and 23 `stack-*` agents.

- every skill keeps its upstream name under the `stack-` prefix, so nothing shadows other skills
- the Claude Code adapter is replaced by [docs/harness/zcode.md](docs/harness/zcode.md) — read it once per session
- commands are skills: `/stack:plan` is `stack-plan` here
- the guardrail hooks are Claude Code plugin hooks and are not wired in this port (see the adapter)

Install (user scope): `python3 tools/port-zcode.py --install` from the astack repository,
or add this repository as a ZCode marketplace and install `stack@astack`.
"""


def install():
    n_skills = n_agents = 0
    for src in sorted(OUT.glob("skills/stack-*")):
        dest = USER_SKILLS / src.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        n_skills += 1
    for src in sorted(OUT.glob("agents/stack-*.md")):
        shutil.copy2(src, USER_AGENTS / src.name)
        n_agents += 1
    print(f"installed {n_skills} skills into {USER_SKILLS} and {n_agents} agents into {USER_AGENTS}")
    print("they are discovered on the next ZCode session (user-scope roots)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--install", action="store_true", help="copy the generated skills/agents into ~/.zcode")
    args = p.parse_args()
    generate()
    if args.install:
        install()


if __name__ == "__main__":
    main()
