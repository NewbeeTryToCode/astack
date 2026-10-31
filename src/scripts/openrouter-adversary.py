#!/usr/bin/env python3
"""Ask a non-Claude model, through OpenRouter, for ways a change breaks its intent.

The model only proposes. Each finding carries a command that should show the failure, and the
Claude executor that called this script runs every command and keeps only the ones that do.

    python3 openrouter-adversary.py --model x-ai/grok-4.7 --intent intent.md --diff change.diff [--context FILE ...]

Prints JSON: {"model": ..., "findings": [{"title", "command", "expected", "reason"}]}.
Exit 3 means no OPENROUTER_API_KEY: the caller skips this panel entry and says so.
In a cloud session whose proxy injects the key, set OPENROUTER_API_KEY to any placeholder.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("STACK_OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
MAX_CHARS = 120_000

BRIEF = """You are an adversarial reviewer. Break this change.

A finding counts only if a command run in the repository root shows the wrong behavior.
For each finding give: a short title, one shell command that reproduces the failure on the
changed code (a failing test, a repro script written with a heredoc, or a CLI call), the output
the stated intent requires, and one sentence on why the code fails. Leave out style, naming,
structure, and risks that need a future change to matter. An empty list is a valid answer.

Answer with JSON only, no prose and no code fence:
{"findings": [{"title": "...", "command": "...", "expected": "...", "reason": "..."}]}"""


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def ask(model, key, prompt, timeout):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": BRIEF}, {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }).encode()
    request = urllib.request.Request(URL, body, {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Title": "stack interrogate",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())["choices"][0]["message"]["content"]


def parse(content):
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    findings = json.loads(text[start:end + 1]).get("findings", [])
    keep = ("title", "command", "expected", "reason")
    return [{k: str(f.get(k, "")) for k in keep} for f in findings if isinstance(f, dict) and f.get("command")]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="OpenRouter model id, such as x-ai/grok-4.7")
    parser.add_argument("--intent", required=True, help="file with the restated intent")
    parser.add_argument("--diff", required=True, help="file with the diff under review")
    parser.add_argument("--context", nargs="*", default=[], help="extra files the model should read")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        print("no OPENROUTER_API_KEY: skip this openrouter panel entry", file=sys.stderr)
        sys.exit(3)

    parts = [f"## Intent\n{read(args.intent)}", f"## Diff\n{read(args.diff)}"]
    parts += [f"## {path}\n{read(path)}" for path in args.context]
    prompt = "\n\n".join(parts)
    if len(prompt) > MAX_CHARS:
        prompt = prompt[:MAX_CHARS] + "\n\n[truncated: review only what is shown]"

    try:
        content = ask(args.model, key, prompt, args.timeout)
    except urllib.error.HTTPError as e:
        sys.exit(f"OpenRouter answered {e.code} for {args.model}: {e.read().decode(errors='replace')[:300]}")
    try:
        findings = parse(content)
    except (ValueError, AttributeError):
        sys.exit(f"{args.model} did not answer with the findings JSON:\n{content[:600]}")
    print(json.dumps({"model": args.model, "findings": findings}, indent=2))


if __name__ == "__main__":
    main()
