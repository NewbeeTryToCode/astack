#!/usr/bin/env python3
"""Copy the ECC rule sets bundled in the stack plugin into a Claude Code rules folder.

    python3 install-rules.py --sets common rust --scope user
    python3 install-rules.py --sets common python --scope project --project /path/to/repo

Re-running replaces each chosen set, so the result is the same however often it runs.
"""

import argparse
import shutil
import sys
from pathlib import Path

RULES = Path(__file__).resolve().parents[3] / "rules"


def main():
    sets = sorted(p.name for p in RULES.iterdir() if p.is_dir())
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sets", nargs="+", required=True, choices=sets)
    parser.add_argument("--scope", choices=["user", "project"], required=True)
    parser.add_argument("--project", default=".", help="repository root for --scope project")
    args = parser.parse_args()

    base = Path.home() / ".claude" if args.scope == "user" else Path(args.project).resolve() / ".claude"
    target = base / "rules" / "stack"
    if args.scope == "project" and not (Path(args.project) / ".git").exists():
        sys.exit(f"{Path(args.project).resolve()} is not a repository root")

    for name in args.sets:
        dest = target / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(RULES / name, dest)
        files = sorted(p.name for p in dest.glob("*.md"))
        print(f"{dest}: {', '.join(files)}")
    if "common" not in args.sets and not (target / "common").exists():
        print("note: the language sets link to common/; add --sets common so those links resolve")


if __name__ == "__main__":
    main()
