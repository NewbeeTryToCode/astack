#!/usr/bin/env python3
"""Copy the ECC rule sets bundled in the stack plugin into an omp rules folder.

    python3 install-rules.py --sets common rust --scope user
    python3 install-rules.py --sets common python --scope project --project /path/to/repo

omp scans `rules/*.md` non-recursively, so each set is flattened to
`stack-<set>-<rule>.md`. Re-running replaces each chosen set.
"""

import argparse
import shutil
import sys
from pathlib import Path

RULES = Path(__file__).resolve().parents[3] / "rules"


def target(scope, project):
    if scope == "user":
        return Path.home() / ".omp" / "agent" / "rules"
    root = Path(project).resolve()
    if not (root / ".git").exists():
        sys.exit(f"{root} is not a repository root")
    return root / ".omp" / "rules"


def main():
    sets = sorted(p.name for p in RULES.iterdir() if p.is_dir()) if RULES.exists() else []
    if not sets:
        sets = sorted({p.name.split("-")[1] for p in RULES.glob("stack-*-*.md")})
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sets", nargs="+", required=True, choices=sets)
    parser.add_argument("--scope", choices=["user", "project"], required=True)
    parser.add_argument("--project", default=".", help="repository root for --scope project")
    args = parser.parse_args()

    dest_dir = target(args.scope, args.project)
    dest_dir.mkdir(parents=True, exist_ok=True)

    for name in args.sets:
        for old in dest_dir.glob(f"stack-{name}-*.md"):
            old.unlink()
        flat = sorted(RULES.glob(f"stack-{name}-*.md"))
        if flat:
            for src in flat:
                shutil.copy2(src, dest_dir / src.name)
        else:
            for src in sorted((RULES / name).glob("*.md")):
                shutil.copy2(src, dest_dir / f"stack-{name}-{src.name}")
        files = sorted(p.name for p in dest_dir.glob(f"stack-{name}-*.md"))
        print(f"{dest_dir}: {', '.join(files)}")
    if "common" not in args.sets and not any(dest_dir.glob("stack-common-*.md")):
        print("note: the language sets link to common/; add --sets common so those links resolve")


if __name__ == "__main__":
    main()
