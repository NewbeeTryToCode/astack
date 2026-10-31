#!/usr/bin/env python3
"""Run one stack role in another backend: a headless Claude Code child that talks to that backend.

    python3 delegate.py resolve builder                       which backend and model a role uses
    python3 delegate.py doctor [--backend go]                 prove the child sends only the backend's key
    python3 delegate.py run --role builder --dir REPO --brief brief.md [--out DIR]
    python3 delegate.py status                                 doctor and outage state of each backend
    python3 delegate.py reset go                               forget a recorded outage

When a backend refuses or fails (quota, credit, auth, rate limit, outage), `run` exits 3, names the
fallback binding, and records the backend as down for its cooldown. While it is down, `run` returns at
once without starting a child, and the role guard lets the Claude fallback write code.

`run` prints one JSON object: the role, backend, model, exit code, the child's final reply, the
models it used, the files it changed since it started, and the transcript path. The caller reviews
the diff itself. A delegate's report is never the verdict.

Roles come from roles.json next to this plugin, overridden key by key by ~/.config/stack/roles.json
(or the file STACK_ROLES_FILE names).
A role bound to `claude:<alias>` runs as a native subagent, so `run` is only needed for other backends
or when a harness without Claude subagents bridges to Claude Code.

The child's environment is built from an allowlist, never inherited. A Claude Code session, above all a
cloud one, carries its own credentials in the environment, and a child that inherits them sends them to
whatever base URL it is given. `doctor` runs the child against a local server that records the request,
and `run` refuses to start until `doctor` has passed for this Claude Code version and backend.
"""

import argparse
import hashlib
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
USER_ROLES = Path(os.environ.get("STACK_ROLES_FILE", Path.home() / ".config" / "stack" / "roles.json"))
STAMP = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "stack" / "delegate-doctor.json"

KEEP = {
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "TERM", "TMPDIR", "TZ",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy", "all_proxy",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "GIT_SSL_CAINFO",
    "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
}


def merge(base, override):
    """Override wins key by key, at every depth. Lists and plain values replace."""
    out = dict(base)
    for key, value in override.items():
        out[key] = merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def load_roles():
    roles = json.loads((PLUGIN / "roles.json").read_text())
    if USER_ROLES.exists():
        roles = merge(roles, json.loads(USER_ROLES.read_text()))
    return roles


def resolve(roles, role):
    """`builder` -> [{"backend": "go", "model": "glm-5.3", "via": "delegate"}]. Panels give one entry each."""
    name = roles["pstack_roles"].get(role, role)
    if name not in roles["roles"]:
        sys.exit(f"no role named {role!r} in roles.json")
    bindings = roles["roles"][name]
    out = []
    for binding in bindings if isinstance(bindings, list) else [bindings]:
        backend, _, model = binding.partition(":")
        if backend not in roles["backends"]:
            sys.exit(f"role {name} names backend {backend!r}, which roles.json does not define")
        out.append({"role": name, "backend": backend, "model": model, "via": "agent" if backend == "claude" else "delegate"})
    return out


def child_env(roles, backend, model, base_url=None, key=None, session=None):
    """The child's whole environment: the allowlist, plus what this backend needs, plus nothing else."""
    env = {k: v for k, v in os.environ.items() if k in KEEP or k.startswith("LC_")}
    if backend == "claude":
        for k, v in os.environ.items():
            if k.startswith(("CLAUDE_", "ANTHROPIC_")):
                env[k] = v
        return env
    spec = roles["backends"][backend]
    key = key if key is not None else os.environ.get(spec["key_env"], "")
    if not key:
        sys.exit(f"{spec['key_env']} is not set, so the {backend} backend has no key")
    env.update({
        "STACK_DELEGATE_ROLE": backend,
        "ANTHROPIC_BASE_URL": base_url or spec["base_url"],
        "ANTHROPIC_API_KEY": key,
        "ANTHROPIC_MODEL": model,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CODE_MAX_RETRIES": str(spec.get("max_retries", 2)),
    })
    for alias, target in spec.get("alias_models", {}).items():
        env[f"ANTHROPIC_DEFAULT_{alias.upper()}_MODEL"] = target
    if spec.get("session_header"):
        env["ANTHROPIC_CUSTOM_HEADERS"] = f"{spec['session_header']}: {session or 'stack-' + uuid.uuid4().hex[:16]}"
    return env


def claude_version():
    return subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()


# ---- doctor -----------------------------------------------------------------------------

def doctor(roles, backend):
    """Run the child against a local recorder and check every model request it sends."""
    seen = []

    class Recorder(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
            body = b'{"type":"error","error":{"type":"invalid_request_error","message":"stack doctor"}}'
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Recorder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    probe = "stack-doctor-" + uuid.uuid4().hex[:8]
    env = child_env(roles, backend, "doctor-probe", base_url=f"http://127.0.0.1:{server.server_port}", key=probe, session="stack-doctor")
    env["NO_PROXY"] = env["no_proxy"] = ",".join(filter(None, [env.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
    with tempfile.TemporaryDirectory() as tmp:
        child = subprocess.Popen(["claude", "-p", "reply ok", "--output-format", "json"], cwd=tmp, env=env,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 90
        while time.time() < deadline and child.poll() is None and not any("/messages" in path for path, _ in seen):
            time.sleep(0.2)
        if child.poll() is None:
            child.kill()
        child.wait()
    server.shutdown()

    messages = [h for path, h in seen if "/messages" in path]
    header = roles["backends"][backend].get("session_header")
    problems = []
    if not messages:
        problems.append("the child sent no model request to the base URL")
    for h in messages:
        if "authorization" in h:
            problems.append("the child sent an Authorization header, which is not this backend's key")
        if h.get("x-api-key") != probe:
            problems.append("the child did not send the backend key as x-api-key")
        if header and header not in h:
            problems.append(f"the child did not send {header}")
    problems = sorted(set(problems))
    result = {"backend": backend, "claude": claude_version(), "requests": len(messages), "ok": not problems,
              "problems": problems, "checked_at": int(time.time())}
    if result["ok"]:
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        stamps = json.loads(STAMP.read_text()) if STAMP.exists() else {}
        stamps[backend] = result
        STAMP.write_text(json.dumps(stamps, indent=2))
    return result


# ---- outages ----------------------------------------------------------------------------

BACKEND_ERROR = re.compile(r"API Error|rate.?limit|usage limit|quota|credit|overloaded|unauthori[sz]ed|authentication"
                           r"|requires a credential|\b(401|402|403|429|5\d\d)\b", re.I)


TRANSIENT = re.compile(r"overloaded|\b5\d\d\b", re.I)


def cooldown(spec, reply):
    """Minutes to treat the backend as down: short for a transient failure, long for quota, credit or auth."""
    if TRANSIENT.search(reply or "") and not re.search(r"quota|credit|limit|401|402|403|429", reply or "", re.I):
        return spec.get("transient_cooldown_minutes", 5)
    return spec.get("cooldown_minutes", 30)


def status_file():
    return STAMP.parent / "backend-status.json"


def backend_failure(code, is_error, reply, changed):
    """True when the child stopped because the backend refused or failed, not because of the task."""
    return (code != 0 or is_error) and not changed and bool(BACKEND_ERROR.search(reply or ""))


def mark_down(backend, reason, minutes):
    path = status_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    status = json.loads(path.read_text()) if path.exists() else {}
    status[backend] = {"down_until": int(time.time() + minutes * 60), "reason": reason[:300]}
    path.write_text(json.dumps(status, indent=2))


def backend_down(backend):
    """The outage record while it lasts, else None."""
    path = status_file()
    entry = json.loads(path.read_text()).get(backend) if path.exists() else None
    return entry if entry and entry.get("down_until", 0) > time.time() else None


def clear_down(backend):
    path = status_file()
    if path.exists():
        status = json.loads(path.read_text())
        status.pop(backend, None)
        path.write_text(json.dumps(status, indent=2))


def fallback_for(roles, backend):
    return roles.get("fallbacks", {}).get(backend, "claude:sonnet")


def doctor_passed(backend):
    if not STAMP.exists() or not shutil.which("claude"):
        return False
    stamp = json.loads(STAMP.read_text()).get(backend, {})
    return stamp.get("ok") and stamp.get("claude") == claude_version()


# ---- run --------------------------------------------------------------------------------

def git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True).stdout.strip()


def lines(text):
    return set(filter(None, text.splitlines()))


def dirty(directory):
    """Uncommitted and untracked files with a hash of their content, so later changes can be told apart."""
    paths = lines(git(directory, "diff", "--name-only", "HEAD")) | lines(git(directory, "ls-files", "--others", "--exclude-standard"))
    return {p: hashlib.sha256((directory / p).read_bytes()).hexdigest() if (directory / p).is_file() else None for p in paths}


def changed_since(directory, start, before):
    """Files the child changed: new differences from the start commit, and dirty files whose content moved."""
    now = dirty(directory)
    moved = lines(git(directory, "diff", "--name-only", start)) if start else set()
    return sorted({p for p in moved | set(now) if p not in before} | {p for p in before if now.get(p) != before[p]})


def run(roles, role, directory, brief, out, tools):
    binding = resolve(roles, role)[0]
    backend, model = binding["backend"], binding["model"]
    down = backend != "claude" and backend_down(backend)
    if down:
        until = time.strftime("%H:%M", time.localtime(down["down_until"]))
        return {"role": binding["role"], "backend": backend, "model": model, "backend_failed": True,
                "skipped": f"{backend} is marked down until {until}: {down['reason']}", "fallback": fallback_for(roles, backend)}
    if backend != "claude" and not doctor_passed(backend):
        check = doctor(roles, backend)
        if not check["ok"]:
            sys.exit("refusing to delegate, doctor failed: " + "; ".join(check["problems"]))
    if not shutil.which("claude"):
        sys.exit("claude is not on PATH, so there is no child to run")

    directory = Path(directory).resolve()
    out = Path(out or tempfile.mkdtemp(prefix=f"stack-{role}-"))
    out.mkdir(parents=True, exist_ok=True)
    transcript = out / "transcript.jsonl"
    start = git(directory, "rev-parse", "HEAD")
    before = dirty(directory)
    env = child_env(roles, backend, model)
    cmd = ["claude", "-p", Path(brief).read_text(), "--permission-mode", "acceptEdits",
           "--allowedTools", *(tools or roles["delegate_tools"]), "--output-format", "stream-json", "--verbose"]
    if backend == "claude":
        cmd += ["--model", model]
    began = time.time()
    with open(transcript, "w") as f:
        code = subprocess.run(cmd, cwd=directory, env=env, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL).returncode

    reply, models, turns, is_error = "", set(), 0, False
    for line in open(transcript):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "assistant":
            models.add(event["message"].get("model"))
        if event.get("type") == "result":
            reply, turns, is_error = event.get("result", ""), event.get("num_turns", 0), bool(event.get("is_error"))
    changed = changed_since(directory, start, before)
    if out.resolve().is_relative_to(directory):
        own = out.resolve().relative_to(directory).as_posix() + "/"
        changed = [f for f in changed if not f.startswith(own)]
    result = {"role": binding["role"], "backend": backend, "model": model, "exit": code, "reply": reply,
              "models_used": sorted(m for m in models if m and not m.startswith("<")), "turns": turns,
              "seconds": round(time.time() - began), "start": start, "head": git(directory, "rev-parse", "HEAD"),
              "changed": changed, "transcript": str(transcript)}
    if backend != "claude" and backend_failure(code, is_error, reply, changed):
        mark_down(backend, reply, cooldown(roles["backends"][backend], reply))
        result.update(backend_failed=True, fallback=fallback_for(roles, backend))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("resolve")
    p.add_argument("role")
    p = sub.add_parser("doctor")
    p.add_argument("--backend", default="go")
    p = sub.add_parser("status")
    p = sub.add_parser("reset")
    p.add_argument("backend")
    p = sub.add_parser("run")
    p.add_argument("--role", required=True)
    p.add_argument("--dir", required=True, help="repository or worktree the child works in")
    p.add_argument("--brief", required=True, help="file with the full brief, goal first")
    p.add_argument("--out", help="folder for the transcript (default: a temp folder)")
    p.add_argument("--tools", nargs="*", help="allowed tools, replacing delegate_tools from roles.json")
    args = parser.parse_args()

    roles = load_roles()
    if args.command == "resolve":
        result = resolve(roles, args.role)
    elif args.command == "doctor":
        result = doctor(roles, args.backend)
    elif args.command == "status":
        result = {name: {"doctor_passed": bool(doctor_passed(name)), "down": backend_down(name), "fallback": fallback_for(roles, name)}
                  for name in roles["backends"] if name != "claude"}
    elif args.command == "reset":
        clear_down(args.backend)
        result = {"backend": args.backend, "down": None}
    else:
        result = run(roles, args.role, args.dir, args.brief, args.out, args.tools)
    print(json.dumps(result, indent=2))
    if args.command == "doctor" and not result["ok"]:
        sys.exit(1)
    if args.command == "run" and result.get("backend_failed"):
        sys.exit(3)


if __name__ == "__main__":
    main()
