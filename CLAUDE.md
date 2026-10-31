# Instructions for Claude

## Working on this repo

- `plugins/stack` is build output. Edit files the repo owns in `src/`, and turn edits to vendored files into patches with `python3 tools/stack.py diff`.
- Before committing, run `python3 tools/stack.py check`, `python3 tools/stack.py verify` and `python3 -m unittest discover -s tests`.

## Commits and pull requests

- Commit as the repository owner, never as Claude: before the first commit in a clone, run
  `git config user.name "NewbeeTryToCode"` and
  `git config user.email "36224565+NewbeeTryToCode@users.noreply.github.com"`
  (a cloud session's default git identity is Claude's).
- Write no `Co-Authored-By`, `Claude-Session` or other Claude attribution lines in commit messages, and no
  "Generated with Claude Code" line in pull request descriptions.
