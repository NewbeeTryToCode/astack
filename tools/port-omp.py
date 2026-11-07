#!/usr/bin/env python3
"""Port the built `stack` plugin to omp.

    python3 tools/port-omp.py            generate plugins/stack-omp/ and verify it
    python3 tools/port-omp.py --check    fail if plugins/stack-omp differs from a fresh port
    python3 tools/port-omp.py --install  copy the plugin into ~/.omp/agent/stack-omp

Every skill keeps its upstream name under a `stack-` prefix (`stack-poteto-mode`,
`stack-deslop`, `stack-plan`), and every agent keeps its name under the same prefix, so
nothing shadows a skill or agent already installed in omp. Commands stay `commands/*.md`
and omp exposes them as `/stack:<name>`.

The Claude Code adapter is replaced by `docs/harness/omp.md`. The model rule and the
guardrail hooks are omp-native: `setup-models.py` writes `~/.omp/agent/config.yml` and
the managed role block in `~/.omp/agent/RULES.md`, and `extensions/stack-guardrails.mjs`
maps omp events to the vendored ECC hook scripts.
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "plugins" / "stack"
OUT = ROOT / "plugins" / "stack-omp"
OVERRIDES = ROOT / "tools" / "omp"
MARKET = ROOT / ".omp-plugin" / "marketplace.json"

LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
SLASH = re.compile(r"`/stack:([a-z0-9-]+)((?: [^`]*)?)`")
SLASH_BARE = re.compile(r"`/([a-z][a-z0-9-]+)`")
STACK_REF = re.compile(r"(?<![-/\w])stack:([a-z][a-z0-9-]+)")
SUBAGENT = re.compile(r'subagent_type: "([a-zA-Z0-9:_-]+)"')
SUBAGENT_BARE = re.compile(r"subagent_type:\s+(generalPurpose|general-purpose|shell|explore|Explore)\b")
BARE_AGENT = re.compile(r"(?<![-/\w])(poteto-agent|comment-sicko|thermo-nuclear-code-quality-review)\b")
PLACEHOLDERS = {"url", "name", "target", "file", "path"}
EXPLAIN = {"README.md", "docs/harness/omp.md"}
START = "<!-- stack:models:start -->"
END = "<!-- stack:models:end -->"

VENDORED = {}
SKILLS = set()
COMMANDS = set()
AGENTS = set()


def fm(text):
    """Split a markdown file into (frontmatter lines, body)."""
    if not text.startswith("---\n"):
        return [], text
    end = text.index("\n---\n", 4)
    return text[4:end].splitlines(), text[end + 5:]


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, newline="\n")


def mapped_dest(rel):
    parts = rel.split("/")
    if parts[0] == "skills" and len(parts) > 1 and not parts[1].startswith("stack-"):
        parts[1] = f"stack-{parts[1]}"
    if parts[0] == "agents" and len(parts) > 1 and not parts[1].startswith("stack-"):
        parts[1] = f"stack-{parts[1]}"
    if rel == "docs/harness/claude-code.md":
        return OUT / "docs/harness/omp.md"
    if parts[0] == "rules" and len(parts) > 2:
        return OUT / "rules" / f"stack-{parts[1]}-{'-'.join(parts[2:])}"
    return OUT / "/".join(parts)


def origin_dir_of(out_md):
    parts = out_md.relative_to(OUT).as_posix().split("/")
    if parts[0] == "skills" and len(parts) > 1 and parts[1].startswith("stack-"):
        parts[1] = parts[1][len("stack-"):]
    if parts[0] == "agents" and len(parts) > 1 and parts[-1].startswith("stack-"):
        parts[-1] = parts[-1][len("stack-"):]
    if parts[:2] == ["docs", "harness"] and parts[-1] == "omp.md":
        parts[-1] = "claude-code.md"
    if parts[0] == "rules" and len(parts) == 2 and parts[1].startswith("stack-"):
        # stack-<set>-<rule>.md cannot be reversed without the manifest; links in rules
        # are fixed from the rule's set directory before flattening.
        pass
    origin = SRC / "/".join(parts)
    if parts[0] == "skills" and not origin.exists():
        return SRC / "commands"
    return origin.parent


def fix_links(out_md, origin_dir):
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


def rewrite_slash(m):
    name, args = m.group(1), m.group(2)
    if name in SKILLS:
        return f"`/skill:stack-{name}{args}`"
    return m.group(0)


def rewrite_bare_slash(m):
    name = m.group(1)
    if name in SKILLS and name not in COMMANDS:
        return f"`/skill:stack-{name}`"
    return m.group(0)


def rewrite_stack_ref(m):
    name = m.group(1)
    if name in COMMANDS:
        return f"stack:{name}"
    if name in SKILLS or name in AGENTS:
        return f"stack-{name}"
    return m.group(0)


def rewrite_subagent(m):
    name = m.group(1)
    if name in {"general-purpose", "generalPurpose", "shell"}:
        return 'agent: "task"'
    if name in {"explore", "Explore"}:
        return 'agent: "scout"'
    if name in AGENTS:
        return f'agent: "stack-{name}"'
    if name.startswith("stack:"):
        bare = name.split(":", 1)[1]
        if bare in AGENTS or bare in SKILLS:
            return f'agent: "stack-{bare}"'
    return m.group(0)


def rewrite_subagent_bare(m):
    name = m.group(1)
    if name in {"generalPurpose", "general-purpose", "shell"}:
        return 'agent: "task"'
    if name in {"explore", "Explore"}:
        return 'agent: "scout"'
    return m.group(0)


def rewrite(text):
    text = text.replace("Everything Claude Code", "\x00ECC\x00")
    text = text.replace("claude-code.md", "omp.md")
    text = text.replace("the Claude Code adapter", "the omp adapter")
    text = text.replace("It maps the Cursor names in pstack skills to Claude Code.",
                        "It maps the upstream names in the bundled skills to omp.")
    text = text.replace("In Claude Code,", "In omp,")
    text = text.replace("Claude Code", "omp").replace("claude code", "omp")
    text = text.replace("Claude executor", "omp executor")
    text = text.replace("Everything omp", "Everything Claude Code")
    text = text.replace("\x00ECC\x00", "Everything Claude Code")
    text = text.replace("generalPurpose", "task").replace("general-purpose", "task")
    text = text.replace("skills/poteto-mode/SKILL.md", "skills/stack-poteto-mode/SKILL.md")
    text = text.replace(".cursor-plugin/plugin.json", ".omp-plugin/plugin.json")
    text = text.replace("Leave `model` unset when the value is `auto` or `inherit-parent`.",
                        "Leave `model` unset when the role block is missing; omp then uses the session model.")
    text = text.replace("If the Task tool rejects a slug, use the default and say so. If it rejects the default, use the closest valid slug of the same family from its error message.",
                        "If omp rejects a selector, use the role's approved fallback and say so; do not substitute a different family silently.")
    text = text.replace("${CLAUDE_PLUGIN_ROOT}", "<stack>")
    text = text.replace("CLAUDE_PLUGIN_ROOT", "<stack>")
    text = text.replace("~/.claude/rules", "~/.omp/agent/rules")
    text = text.replace("~/.claude/projects", "~/.omp/agent/sessions")
    text = text.replace("~/.claude/", "~/.omp/agent/")
    text = text.replace("~/.cursor/rules/pstack-models.mdc", "~/.omp/agent/RULES.md")
    text = text.replace("~/.cursor/plugins/", "<stack>/")
    text = text.replace("pstack-models.mdc", "RULES.md").replace("pstack-models.md", "RULES.md")
    text = text.replace("grok-4.7-xhigh-fast", "the stack code selector")
    text = text.replace("claude-opus-5-5-xhigh", "the stack judgment selector")
    text = text.replace("claude-sonnet-5-5-xhigh", "the stack code selector")
    text = SLASH.sub(rewrite_slash, text)
    text = SLASH_BARE.sub(rewrite_bare_slash, text)
    text = STACK_REF.sub(rewrite_stack_ref, text)
    text = SUBAGENT.sub(rewrite_subagent, text)
    text = SUBAGENT_BARE.sub(rewrite_subagent_bare, text)
    text = text.replace("subagent_type:", "agent:")
    text = text.replace("Agent(subagent_type=", "Task(agent=")
    text = BARE_AGENT.sub(r"stack-\1", text)
    text = text.replace("AskQuestion", "ask").replace("TodoWrite", "todo")
    text = text.replace("pstack:poteto-agent", "stack-poteto-agent")
    text = re.sub(r"(?<![\w./-])/setup-pstack\b", "/skill:stack-setup-pstack", text)
    text = re.sub(r"(?<![\w./-])/setup-stack\b", "/skill:stack-setup-stack", text)
    text = text.replace("pstack/skills/", "skills/stack-")
    text = text.replace("~/.cursor/projects/<slug>/agent-transcripts/<uuid>/<uuid>.jsonl",
                        "~/.omp/agent/sessions/<slug>/<timestamp>_<id>.jsonl")
    text = text.replace("~/.cursor/projects/*/", "~/.omp/agent/sessions/*/")
    text = text.replace("~/.cursor/projects/", "~/.omp/agent/sessions/")
    text = text.replace("<agent-transcripts>", "~/.omp/agent/sessions/<slug>")
    text = text.replace("agent-transcripts/", "sessions/")
    text = text.replace("~/.cursor/skills/", "~/.omp/agent/skills/")
    text = text.replace(".cursor/skills/", ".omp/skills/")
    text = text.replace(".cursor/worktrees/", ".omp/worktrees/")
    text = text.replace("Cursor's built-in `create-skill` flow", "the built-in skill authoring flow")
    text = text.replace("the stack code selector", "the stack_code role selector")
    text = text.replace("the stack judgment selector", "the stack_judgment role selector")
    text = text.replace("An `auto` or `inherit-parent` entry in this line means the parent model, so omit `model` for it.",
                        "A missing entry means the session model, so omit `model` for it.")
    text = text.replace("An `auto` or `inherit-parent` entry is the parent model, so it never judges.",
                        "A missing entry means the session model, so it never judges.")
    text = text.replace("For `auto` or `inherit-parent`, omit `model` so the workers run on the parent model.",
                        "If the role line is missing, omit `model` so the workers run on the session model.")
    text = text.replace("left unset for `auto` or `inherit-parent`", "left unset when the role line is missing (the session model)")
    text = text.replace("A role set to `auto` or `inherit-parent` runs on the chat's model",
                        "A role with no selector runs on the session model")
    text = text.replace("Families go by prefix: `claude-*`, and `grok-*` with `cursor-grok-*` and `composer-*`.",
                        "Families go by the selector's provider prefix, for example `anthropic/`, `openai/`, `opencode-go/` and `openrouter/`.")
    text = text.replace("A refused `composer-*` entry runs on the `stack_code` role selector.",
                        "A refused selector runs on the `stack_code` role selector.")
    text = text.replace("a Claude parent gets", "a parent on one family gets")
    text = text.replace("A Claude parent gets", "A parent on one family gets")
    text = text.replace("A refused `composer-*` entry runs on `the stack_code role selector`.",
                        "A refused selector runs on the stack_code role selector.")
    text = text.replace("Otherwise use standard speed, the same slug without `-fast`.",
                        "Otherwise use standard speed and avoid a provider fast variant unless the job is urgent.")
    text = text.replace("`run_in_background: true` (a steer or resume of a running agent too, because a foreground call holds your turn while other reports wait)",
                        "background execution (omp runs subagents in the background by default, so a steer or resume does not hold your turn)")
    text = text.replace("`run_in_background: true`", "background execution (the default)")
    text = text.replace('environment: "cloud"', "isolated: true")
    text = text.replace("Use `environment: \"local\"` only when", "Use a local, non-isolated run only when")
    text = text.replace("<pstack>", "<stack>")
    text = text.replace('isolation: "worktree"', "isolated: true")
    text = text.replace("A omp ", "An omp ")
    text = text.replace("a omp ", "an omp ")
    text = text.replace("In a Cursor chat", "In an omp chat")
    text = text.replace("Cursor confirms the plugin is installed.", "omp confirms the plugin is installed.")
    text = text.replace("Cursor's built-in wake mechanism", "omp's built-in loop mode")
    text = text.replace("restart Cursor", "restart omp")
    text = text.replace("Cursor's docs list", "omp's docs list")
    text = text.replace("Cursor's Plan Mode", "omp's plan mode")
    text = text.replace("Cursor's own skill", "the harness's own skill")
    text = text.replace("Cursor's built-in babysit skill", "the harness's built-in babysit skill")
    text = text.replace("Cursor's built-in `create-skill`", "the built-in skill authoring flow")
    text = text.replace("Cursor built-ins", "harness built-ins")
    text = text.replace("Cursor built-in", "harness built-in")
    text = text.replace("Cursor's built-in", "the built-in")
    text = text.replace("A Cursor Project", "A coordinator session")
    text = text.replace("Set a role to `auto` or `inherit-parent` so it runs on the chat's own model.",
                        "Leave a role without a selector so it runs on the session model.")
    text = text.replace("**Treating `auto` as a model slug.** `auto` and `inherit-parent` mean \"omit the model field so the subagent inherits the parent chat model.\"",
                        "**Treating a role name as a model slug.** A role without a selector means \"omit the model field so the subagent uses the session model.\"")
    text = text.replace("pstack is built for Cursor, and it also installs in omp with `/plugin marketplace add cursor/plugins`, then `/plugin install pstack@cursor-plugins`. There, each command takes a `pstack:` prefix, such as `/pstack:poteto-mode`.",
                        "This port installs in omp from the astack marketplace with `/marketplace add NewbeeTryToCode/astack` and `/marketplace install stack@astack`. Commands take a `stack:` prefix, such as `/stack:plan`, and skills are `/skill:stack-<name>`.")
    text = text.replace("From here you can type normal follow-ups. To keep `/skill:stack-poteto-mode` on for the whole chat, pick it from the `/` menu with Option+Enter (Mac) or Alt+Enter (Windows) instead of Enter. That makes it a [Custom Mode](https://cursor.com/docs/skills#using-a-skill-as-a-custom-mode), which stays in context on every turn until you exit it. Custom Modes are available in the Agents Window and the CLI. Plain Enter attaches the skill to one message, and it fades as the chat moves on.",
                        "From here you can type normal follow-ups. To keep `/skill:stack-poteto-mode` on for the whole chat, use omp's plan mode or loop mode. A plain invocation attaches the skill to one message, and it fades as the chat moves on.")
    text = text.replace("spawn Cursor subagents with per-role models, and Custom Modes and `/loop` are Cursor features, so those parts may not work there.",
                        "spawn `stack-*` subagents with the role selector from `~/.omp/agent/RULES.md`; omp's plan mode and loop mode cover those parts.")
    text = text.replace("- omp's docs list Custom Modes in the Agents Window and the CLI. Elsewhere, start each new task with `/skill:stack-poteto-mode`.",
                        "- Otherwise start each new task with `/skill:stack-poteto-mode`.")
    text = text.replace("- Option+Enter on Mac or Alt+Enter on Windows, or Use as Mode from the skill entry, makes it a Custom Mode. It stays in context every turn until the user exits the mode, and it stays out of casual turns.",
                        "- Use omp's plan mode or loop mode when the mode should stay in context across turns.")
    text = text.replace("Link [Cursor's skills docs](https://cursor.com/docs/skills) when this comes up.",
                        "Link the [upstream skills docs](https://cursor.com/docs/skills) when this comes up.")
    return text


def skill_frontmatter(name, fields):
    keep = []
    for line in fields:
        key = line.split(":", 1)[0].strip()
        if key in {"name", "description", "disable-model-invocation", "disableModelInvocation", "hide"}:
            continue
        keep.append(line)
    lines = [f"name: stack-{name}"]
    desc = next((line.split(":", 1)[1].strip() for line in fields if line.startswith("description:")), "")
    if desc:
        lines.append(f"description: {rewrite(desc)}")
    lines += ["metadata:", "  origin: astack"]
    lines += keep
    return lines


def agent_frontmatter(name, fields):
    keep = []
    desc = ""
    tools = ""
    for line in fields:
        key, _, value = line.partition(":")
        key = key.strip()
        if key == "name":
            continue
        if key == "description":
            desc = value.strip()
            continue
        if key == "tools":
            tools = value.strip()
            continue
        if key in {"is_background", "is-background", "model"}:
            continue
        keep.append(line)
    lines = [f"name: stack-{name}"]
    if desc:
        lines.append(f"description: {rewrite(desc)}")
    if tools:
        lines.append(f"tools: {tools}")
    lines += keep
    return lines


def copy_tree(src, dest, rewrite_md=True):
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src).as_posix()
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rewrite_md and path.suffix == ".md":
            write(target, rewrite(path.read_text()))
        else:
            shutil.copy2(path, target)


def generate(out=OUT, src=SRC, overrides=OVERRIDES):
    global OUT, SRC, VENDORED, SKILLS, COMMANDS, AGENTS
    OUT, SRC = out, src
    if out.exists():
        shutil.rmtree(out)
    SKILLS = {p.parent.name for p in src.glob("skills/*/SKILL.md")}
    COMMANDS = {p.stem for p in src.glob("commands/*.md")}
    AGENTS = {p.stem for p in src.glob("agents/*.md")}
    VENDORED = json.loads((src / "VENDORED.json").read_text()) if (src / "VENDORED.json").exists() else {"files": {}}

    # skills: copy each directory under a stack- prefixed name, rewrite its SKILL.md
    for src_skill in sorted(src.glob("skills/*/")):
        name = src_skill.name
        dest = out / "skills" / f"stack-{name}"
        shutil.copytree(src_skill, dest)
        for md in dest.rglob("*.md"):
            md.write_text(rewrite(md.read_text()), newline="\n")
        skill_md = dest / "SKILL.md"
        fields, body = fm(skill_md.read_text())
        write(skill_md, "---\n" + "\n".join(skill_frontmatter(name, fields)) + "\n---\n" + body)

    # setup skills are omp-specific and replace the generated copies
    for name in ("setup-stack", "setup-pstack"):
        override = overrides / f"{name}.md"
        if override.exists():
            dest = out / "skills" / f"stack-{name}" / "SKILL.md"
            write(dest, rewrite(override.read_text()))
    for script in ("install-rules.py", "setup-models.py"):
        src_script = overrides / "scripts" / script
        if src_script.exists():
            dest = out / "skills" / "stack-setup-stack" / "scripts" / script
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_script, dest)
            dest.chmod(0o755)

    # commands stay commands; omp exposes them as /stack:<name>
    for src_cmd in sorted(src.glob("commands/*.md")):
        dest = out / "commands" / src_cmd.name
        write(dest, rewrite(src_cmd.read_text()))

    # agents: prefix the name so the plugin cannot shadow an installed agent
    for src_agent in sorted(src.glob("agents/*.md")):
        name = src_agent.stem
        fields, body = fm(src_agent.read_text())
        dest = out / "agents" / f"stack-{name}.md"
        write(dest, "---\n" + "\n".join(agent_frontmatter(name, fields)) + "\n---\n" + rewrite(body))

    # a judgment-only delegate, pinned to @stack_judgment by the operator config so
    # omp's retry.fallbackChains applies when Claude hits a usage limit
    judgment_src = src / "agents" / "poteto-agent.md"
    if judgment_src.exists():
        _, body = fm(judgment_src.read_text())
        write(out / "agents" / "stack-judgment.md",
              "---\nname: stack-judgment\n"
              "description: Judgment delegate for stack judgment roles. Runs on the stack_judgment role and its usage-limit fallback chain; spawn it without a per-call model.\n"
              "---\n" + rewrite(body))

    # rules: flatten set/rule.md to rules/stack-<set>-<rule>.md so omp's non-recursive
    # native and plugin rule loaders discover every file
    for set_dir in sorted(p for p in (src / "rules").iterdir() if p.is_dir()):
        for rule in sorted(set_dir.glob("*.md")):
            text = rewrite(rule.read_text())
            dest = out / "rules" / f"stack-{set_dir.name}-{rule.name}"
            write(dest, text)
            fix_links(dest, set_dir)

    # docs: the omp adapter replaces the Claude Code one
    shutil.copytree(src / "docs", out / "docs")
    (out / "docs/harness/claude-code.md").unlink()
    for md in (out / "docs").rglob("*.md"):
        md.write_text(rewrite(md.read_text()), newline="\n")
    stack_doc = out / "docs/harness/stack.md"
    if stack_doc.exists():
        text = stack_doc.read_text()
        text = re.sub(r"(?ms)^## Models\n.*?(?=^## )", MODELS_SECTION, text)
        text = re.sub(r"(?ms)^## Hooks\n.*?(?=^## )", HOOKS_SECTION, text)
        text = re.sub(r"(?ms)^## Rules\n.*?(?=^## )", RULES_SECTION, text)
        write(stack_doc, text)
    write(out / "docs/harness/omp.md", (overrides / "adapter.md").read_text())
    setup_guide = out / "docs/guide/01-setup.md"
    if setup_guide.exists():
        text = setup_guide.read_text()
        text = re.sub(r"(?ms)^## Install the plugin\n.*?(?=^## Pick your models)", INSTALL_SECTION, text)
        text = re.sub(r"(?ms)The defaults run at `xhigh` reasoning.*?(?=^You only override)", DEFAULTS_SECTION, text)
        text = re.sub(r"(?ms)You might be wondering what happens if you use Auto\..*?(?=^## Accept the verification)",
                      AUTO_SECTION, text)
        write(setup_guide, text)

    # scripts and licenses ride along; the guardrail extension drives the hook scripts
    shutil.copytree(src / "scripts", out / "scripts")
    # omp loads plugin MCP servers from a root .mcp.json, the same file Claude Code reads
    if (src / ".mcp.json").exists():
        shutil.copy2(src / ".mcp.json", out / ".mcp.json")
    shutil.copytree(src / "LICENSES", out / "LICENSES") if (src / "LICENSES").exists() else None
    write(out / "extensions/stack-guardrails.mjs", (overrides / "stack-guardrails.mjs").read_text())

    version = json.loads((src / ".claude-plugin" / "plugin.json").read_text()).get("version", "0.0.0")
    manifest = {
        "name": "stack",
        "version": version,
        "description": "astack's stack plugin for omp: pstack judgment and verification plus ECC planning, specialists and guardrails.",
        "author": {"name": "NewbeeTryToCode"},
        "repository": "https://github.com/NewbeeTryToCode/astack",
        "license": "MIT",
        "keywords": ["pstack", "poteto-mode", "ecc", "verification", "planning", "hooks", "omp"],
    }
    write(out / ".omp-plugin/plugin.json", json.dumps(manifest, indent=2) + "\n")
    write(out / ".claude-plugin/plugin.json", json.dumps(manifest, indent=2) + "\n")
    write(out / "package.json", json.dumps({
        "name": "astack-stack-omp",
        "version": version,
        "private": True,
        "description": manifest["description"],
        "omp": {"extensions": ["./extensions/stack-guardrails.mjs"]},
    }, indent=2) + "\n")
    write(out / "README.md", README.format(version=version))

    for md in out.rglob("*.md"):
        if md.relative_to(out).as_posix() in {"docs/harness/omp.md", "README.md"}:
            continue
        fix_links(md, origin_dir_of(md))

    write_market()
    return out


def write_market():
    if MARKET.exists():
        return
    version = json.loads((SRC / ".claude-plugin" / "plugin.json").read_text()).get("version", "0.0.0")
    write(MARKET, json.dumps({
        "name": "astack",
        "owner": {"name": "NewbeeTryToCode", "email": "36224565+NewbeeTryToCode@users.noreply.github.com"},
        "metadata": {"description": "astack's stack plugin for omp"},
        "plugins": [{
            "name": "stack",
            "source": "./plugins/stack-omp",
            "version": version,
            "description": "pstack judgment, verification and playbooks with ECC planning, specialists and guardrails, in one omp plugin.",
        }],
    }, indent=2) + "\n")


def tree(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def check():
    committed = OUT
    if not committed.exists():
        sys.exit("plugins/stack-omp is missing; run `python3 tools/port-omp.py`")
    with tempfile.TemporaryDirectory() as tmp:
        fresh = tree(generate(Path(tmp) / "stack-omp"))
    current = tree(committed)
    drift = sorted(f for f in fresh.keys() | current.keys() if fresh.get(f) != current.get(f))
    if drift:
        print("plugins/stack-omp does not match a fresh port:", *drift[:40], sep="\n  ")
        sys.exit(1)
    print("check: plugins/stack-omp matches a fresh port")


def verify(out=OUT):
    problems = []
    skills = {p.parent.name for p in out.glob("skills/*/SKILL.md")}
    commands = {p.stem for p in out.glob("commands/*.md")}
    agents = {p.stem for p in out.glob("agents/*.md")}
    src_skills = {p.parent.name for p in SRC.glob("skills/*/SKILL.md")}
    src_commands = {p.stem for p in SRC.glob("commands/*.md")}
    src_agents = {p.stem for p in SRC.glob("agents/*.md")}
    if len(skills) != len(src_skills):
        problems.append(f"expected {len(src_skills)} skills, found {len(skills)}")
    if len(commands) != len(src_commands):
        problems.append(f"expected {len(src_commands)} commands, found {len(commands)}")
    expected_agents = len(src_agents) + (1 if (out / "agents/stack-judgment.md").exists() else 0)
    if len(agents) != expected_agents:
        problems.append(f"expected {expected_agents} agents, found {len(agents)}")
    for name in sorted(skills):
        if not name.startswith("stack-"):
            problems.append(f"skill {name} is missing the stack- prefix")
        fields, _ = fm((out / "skills" / name / "SKILL.md").read_text())
        if f"name: {name}" not in fields:
            problems.append(f"skills/{name}/SKILL.md: frontmatter does not name {name}")
        if not any(line.startswith("description:") for line in fields):
            problems.append(f"skills/{name}/SKILL.md: no description")
    for name in sorted(agents):
        if not name.startswith("stack-"):
            problems.append(f"agent {name} is missing the stack- prefix")
        fields, _ = fm((out / "agents" / f"{name}.md").read_text())
        if f"name: {name}" not in fields:
            problems.append(f"agents/{name}.md: frontmatter does not name {name}")
    for md in out.rglob("*.md"):
        rel = md.relative_to(out).as_posix()
        text = md.read_text()
        prose = FENCE.sub("", text)
        if rel not in EXPLAIN and "claude-code.md" in prose:
            problems.append(f"{rel}: unrewritten Claude Code adapter reference")
        if "/stack:poteto-mode" in prose or "/stack:how" in prose or "/stack:deslop" in prose:
            problems.append(f"{rel}: skill referenced as a /stack: command")
        if "/stack:plan" in prose and "plan" not in commands:
            problems.append(f"{rel}: /stack:plan is not a command")
        for target in LINK.findall(prose):
            if re.match(r"^[a-z]+:", target) or target.startswith("#") or target in PLACEHOLDERS:
                continue
            if target.startswith("<") or target.startswith("$"):
                continue
            if not (md.parent / target.split("#")[0]).exists():
                problems.append(f"{rel}: broken link {target}")
    for rule in out.glob("rules/*.md"):
        if not rule.name.startswith("stack-"):
            problems.append(f"{rule.relative_to(out)}: rule is not flattened with a stack- prefix")
    extension = out / "extensions/stack-guardrails.mjs"
    if not extension.exists():
        problems.append("extensions/stack-guardrails.mjs is missing")
    else:
        import subprocess
        r = subprocess.run(["node", "--check", str(extension)], capture_output=True, text=True)
        if r.returncode:
            problems.append(f"extensions/stack-guardrails.mjs: {r.stderr.strip().splitlines()[-1]}")
    required = ("docs/harness/omp.md", ".omp-plugin/plugin.json", "package.json")
    if (SRC / ".mcp.json").exists():
        required += (".mcp.json",)
    for name in required:
        if not (out / name).exists():
            problems.append(f"{name} is missing")
    return problems


def install():
    dest = Path.home() / ".omp" / "agent" / "stack-omp"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(OUT, dest)
    print(f"copied the plugin to {dest}")
    print("add this to ~/.omp/agent/config.yml so omp loads the extension and its sibling skills:")
    print("extensions:")
    print(f"  - {dest}")
    print("or install it with `/marketplace add <this repo>` and `/marketplace install stack@astack`")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="fail if plugins/stack-omp differs from a fresh port")
    p.add_argument("--install", action="store_true", help="copy the generated plugin into ~/.omp/agent/stack-omp")
    args = p.parse_args()
    if args.check:
        check()
        return
    generate()
    problems = verify()
    if problems:
        print(*problems, sep="\n")
        sys.exit(f"verify: {len(problems)} problem(s)")
    print(f"generated {OUT.relative_to(ROOT)}")
    print(f"verify: {len(list(OUT.glob('skills/*/SKILL.md')))} skills, "
          f"{len(list(OUT.glob('commands/*.md')))} commands, "
          f"{len(list(OUT.glob('agents/*.md')))} agents, "
          f"{len(list(OUT.glob('rules/*.md')))} rules, every link resolves")
    if args.install:
        install()


INSTALL_SECTION = """## Install the plugin

Add the astack marketplace and install the stack plugin:

```text
/marketplace add NewbeeTryToCode/astack
/marketplace install stack@astack
```

omp confirms the plugin is installed. Skills are `stack-<name>`, agents are `stack-<name>`, and commands keep the `stack:` prefix, such as `/stack:plan`. The [omp adapter](../harness/omp.md) covers the rest.

"""

DEFAULTS_SECTION = """The setup skill picks from `omp models --json`. It uses `xhigh` by default, lifts a model to its highest supported level under `unlimited`, and never exceeds `max`. A model that does not support the chosen level uses the highest level it does support.

"""

AUTO_SECTION = """A role with no selector runs on the session model. Panels are lists; one subagent runs per entry, and the list length sets the panel size. Setup also configures `swarm workers`, the default for every swarm worker unless a race names a model for each arm.

"""

MODELS_SECTION = """## Models

omp uses exact `provider/model-id[:level]` selectors, not the Claude aliases below. The role block in `~/.omp/agent/RULES.md` maps each astack role to one or more selectors, and `/skill:stack-setup-stack` writes it. Read [Models in the omp adapter](./omp.md#models) for the per-call gate, grants and effort rules. The Cursor and Claude tables in the upstream copy do not apply.

"""

HOOKS_SECTION = """## Hooks

The guardrails run through `extensions/stack-guardrails.mjs`, which maps omp `tool_call`, `tool_result`, `before_agent_start` and `session_stop` events to the vendored ECC scripts. `/skill:stack-setup-stack` reports the controls. The Claude `hooks/hooks.json` and plugin options in the upstream copy do not apply.

"""

RULES_SECTION = """## Rules

`/skill:stack-setup-stack` installs the chosen ECC rule sets as flat `stack-<set>-<rule>.md` files in `~/.omp/agent/rules/` or `<repo>/.omp/rules/`. omp scans `rules/*.md` non-recursively. `~/.omp/agent/RULES.md` is the sticky rule and carries the model routing block.

"""


README = """# stack for omp

astack's `stack` plugin ported to omp: pstack (judgment, verification, the `poteto-mode`
playbooks), cursor-team-kit (`deslop`, `control-cli`, `control-ui`, `verify-this`) and ECC
(planning, specialists, security, guardrails) as prefixed skills, commands, agents and rules.

- every skill and agent keeps its upstream name under the `stack-` prefix
- commands stay `commands/*.md`; omp exposes them as `/stack:<name>`
- the Claude Code adapter is replaced by [docs/harness/omp.md](docs/harness/omp.md) — read it once per session
- rules are flattened into `rules/stack-<set>-<rule>.md` so omp's non-recursive rule loaders see them
- the ECC guardrails run through `extensions/stack-guardrails.mjs`, which maps omp events to the vendored hook scripts

Install from the repository marketplace:

```bash
/marketplace add NewbeeTryToCode/astack
/marketplace install stack@astack
```

Then run `/skill:stack-setup-stack` once. It detects your omp models, writes the per-role
routing rule to `~/.omp/agent/RULES.md`, enables per-call model selection in
`~/.omp/agent/config.yml`, and installs the rule sets you choose.

Version: {version}
"""


if __name__ == "__main__":
    main()
