"""Behavior tests for the built plugin in plugins/stack.

    python3 -m unittest discover -s tests -v

Each test drives the plugin the way Claude Code or the operator would: hook JSON on stdin,
the setup scripts on the command line, and the verifier against a copy with a part removed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "stack"
sys.path.insert(0, str(ROOT / "tools"))
import stack  # noqa: E402


def run_hook(command, payload, home, extra_env=None):
    """Run a hooks.json command the way Claude Code does, with the payload on stdin."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ECC_", "STACK_", "CLAUDE_PLUGIN"))}
    env.update(HOME=str(home), XDG_DATA_HOME=str(home / ".local/share"), CLAUDE_PLUGIN_ROOT=str(PLUGIN), **(extra_env or {}))
    env.pop("CLAUDE_CONFIG_DIR", None)
    shell = command.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))
    return subprocess.run(["bash", "-c", shell], input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=payload.get("cwd"))


def hook_command(event, matcher, needle):
    for group in json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"][event]:
        if group.get("matcher") == matcher:
            for hook in group["hooks"]:
                if needle in hook["command"]:
                    return hook["command"]
    raise AssertionError(f"no {event} {matcher} hook with {needle}")


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.repo = self.tmp / "repo"
        self.home.mkdir()
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def bash(self, command):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
                "cwd": str(self.repo), "session_id": "test"}

    def test_bash_preflight_blocks_no_verify(self):
        r = run_hook(hook_command("PreToolUse", "Bash", "pre-bash-dispatcher"), self.bash("git commit --no-verify -m wip"), self.home)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("--no-verify", r.stderr)

    def test_bash_preflight_allows_plain_command(self):
        r = run_hook(hook_command("PreToolUse", "Bash", "pre-bash-dispatcher"), self.bash("ls"), self.home)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_hooks_can_be_switched_off(self):
        r = run_hook(hook_command("PreToolUse", "Bash", "pre-bash-dispatcher"), self.bash("git commit --no-verify -m wip"),
                     self.home, {"CLAUDE_PLUGIN_OPTION_HOOKS_ENABLED": "false"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_config_protection_blocks_weakening_a_linter(self):
        (self.repo / ".eslintrc.json").write_text('{"rules": {"no-console": "error"}}')
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(self.repo), "session_id": "test",
                   "tool_input": {"file_path": str(self.repo / ".eslintrc.json"), "old_string": '"error"', "new_string": '"off"'}}
        r = run_hook(hook_command("PreToolUse", "Write|Edit|MultiEdit", "config-protection"), payload, self.home)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def post_edit(self, extra_env=None):
        (self.repo / "a.ts").write_text("console.log('x')\n")
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "cwd": str(self.repo), "session_id": "test",
                   "tool_input": {"file_path": str(self.repo / "a.ts"), "old_string": "y", "new_string": "x"},
                   "tool_response": {"success": True}}
        return run_hook(hook_command("PostToolUse", ".*", "posttooluse-dispatcher.js sync"), payload, self.home, extra_env)

    def written_to_home(self):
        return sorted(p.relative_to(self.home).as_posix() for p in self.home.rglob("*") if p.is_file())

    def test_post_edit_warns_about_console_log(self):
        r = self.post_edit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("console.log", r.stderr)

    def test_tracking_hooks_stay_off_unless_asked(self):
        self.post_edit()
        self.assertEqual(self.written_to_home(), [], "ECC tracking wrote files with stack's defaults")
        self.post_edit({"STACK_ECC_TELEMETRY": "1"})
        self.assertIn(".claude/metrics/tool-usage.jsonl", self.written_to_home(), "STACK_ECC_TELEMETRY=1 did not turn tracking back on")

    def test_continuous_learning_is_not_shipped(self):
        self.assertFalse((PLUGIN / "skills/continuous-learning-v2").exists())


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.copy = self.tmp / "stack"
        shutil.copytree(PLUGIN, self.copy)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def problems(self):
        return stack.verify(self.copy, "stack")[0]

    def test_built_plugin_verifies(self):
        self.assertEqual(stack.verify(PLUGIN, "stack")[0], [])

    def test_missing_routed_skill_is_caught(self):
        shutil.rmtree(self.copy / "skills/deslop")
        self.assertTrue(any("deslop" in p for p in self.problems()), self.problems())

    def test_missing_agent_is_caught(self):
        (self.copy / "agents/poteto-agent.md").unlink()
        self.assertTrue(any("poteto-agent" in p for p in self.problems()), self.problems())

    def test_missing_hook_script_is_caught(self):
        (self.copy / "scripts/hooks/config-protection.js").unlink()
        self.assertTrue(any("config-protection" in p for p in self.problems()), self.problems())

    def test_unmapped_upstream_name_is_caught(self):
        skill = self.copy / "skills/how/SKILL.md"
        skill.write_text(skill.read_text() + "\nSee `tdd-workflow` and `verification-loop`.\n`santa-loop` too.\n")
        problems = stack.verify(self.copy, "stack", {"santa-loop", "tdd-workflow"})[0]
        self.assertTrue(any("santa-loop" in p for p in problems), problems)
        self.assertFalse(any("tdd-workflow" in p for p in problems), "a Name map entry was reported")


class OverlayDiffTests(unittest.TestCase):
    """`diff` copies an overlay file back to src/ only when it was edited in plugins/stack alone."""

    def test_overlay_decisions(self):
        built, newer, old = b"built", b"edited in src", b"old"
        h = stack.sha
        self.assertEqual(stack.overlay_action(built, built, h(built)), "same")
        self.assertEqual(stack.overlay_action(b"edited in plugins", old, h(old)), "copy-back")
        self.assertEqual(stack.overlay_action(old, newer, h(old)), "keep-source")
        self.assertEqual(stack.overlay_action(b"edited in plugins", newer, h(old)), "conflict")
        self.assertEqual(stack.overlay_action(built, newer, None), "conflict")


class SetupTests(unittest.TestCase):
    def test_install_rules_is_idempotent(self):
        with tempfile.TemporaryDirectory() as home:
            script = PLUGIN / "skills/setup-stack/scripts/install-rules.py"
            env = dict(os.environ, HOME=home)
            for _ in range(2):
                r = subprocess.run([sys.executable, str(script), "--sets", "common", "rust", "--scope", "user"], env=env, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
            target = Path(home) / ".claude/rules/stack"
            self.assertEqual(sorted(p.name for p in target.iterdir()), ["common", "rust"])
            self.assertIn("pstack owns verification", (target / "common/testing.md").read_text())
            self.assertTrue((target / "rust/testing.md").exists())

    def test_openrouter_adversary_skips_without_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            intent, diff = Path(tmp) / "i.md", Path(tmp) / "c.diff"
            intent.write_text("x")
            diff.write_text("y")
            env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
            r = subprocess.run([sys.executable, str(PLUGIN / "scripts/openrouter-adversary.py"), "--model", "x-ai/grok-4.7",
                                "--intent", str(intent), "--diff", str(diff)], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 3, r.stderr)


class OpenRouterTests(unittest.TestCase):
    def test_request_shape_and_findings_parse(self):
        import http.server
        import threading

        seen = {}
        answer = {"findings": [
            {"title": "page 1 skips the first page", "command": "python3 -c 'from pager import page; print(page(list(range(20)), 1, 10))'",
             "expected": "[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]", "reason": "start uses page_number, not page_number - 1"},
            {"title": "no command, dropped"},
        ]}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen["auth"] = self.headers["Authorization"]
                seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                reply = {"choices": [{"message": {"content": "```json\n" + json.dumps(answer) + "\n```"}}]}
                data = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                intent, diff = Path(tmp) / "i.md", Path(tmp) / "c.diff"
                intent.write_text("page 1 is the first page")
                diff.write_text("-a\n+b\n")
                env = dict(os.environ, OPENROUTER_API_KEY="k", STACK_OPENROUTER_URL=f"http://127.0.0.1:{server.server_port}/")
                env.pop("HTTPS_PROXY", None)
                env.pop("https_proxy", None)
                env["NO_PROXY"] = "127.0.0.1"
                r = subprocess.run([sys.executable, str(PLUGIN / "scripts/openrouter-adversary.py"), "--model", "x-ai/grok-4.7",
                                    "--intent", str(intent), "--diff", str(diff)], env=env, capture_output=True, text=True)
        finally:
            server.shutdown()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual([f["title"] for f in out["findings"]], ["page 1 skips the first page"])
        self.assertEqual(seen["auth"], "Bearer k")
        self.assertEqual(seen["body"]["model"], "x-ai/grok-4.7")
        self.assertIn("page 1 is the first page", seen["body"]["messages"][1]["content"])


def load_delegate():
    import importlib.util
    spec = importlib.util.spec_from_file_location("delegate", PLUGIN / "scripts/delegate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DelegateTests(unittest.TestCase):
    def setUp(self):
        self.delegate = load_delegate()
        self.roles = self.delegate.load_roles()

    def test_pstack_roles_resolve_to_bindings(self):
        builder = self.delegate.resolve(self.roles, "feature, refactoring")
        self.assertEqual(builder, [{"role": "builder", "backend": "go", "model": "glm-5.3", "via": "delegate"}])
        panel = self.delegate.resolve(self.roles, "interrogate reviewers")
        self.assertEqual([b["via"] for b in panel], ["agent", "agent", "delegate"])
        self.assertEqual(self.delegate.resolve(self.roles, "judgment and prose")[0]["model"], "opus")

    def test_every_pstack_role_line_resolves(self):
        for line in self.roles["pstack_roles"]:
            self.assertTrue(self.delegate.resolve(self.roles, line))

    def test_child_env_drops_the_session_credentials(self):
        leaked = {"CLAUDE_SESSION_INGRESS_TOKEN_FILE": "/run/token", "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST": "1",
                  "ANTHROPIC_AUTH_TOKEN": "claude-secret", "CLAUDE_CODE_OAUTH_TOKEN": "claude-secret",
                  "ANTHROPIC_BASE_URL": "https://api.anthropic.com", "CLAUDE_CODE_REMOTE": "true"}
        saved = {k: os.environ.get(k) for k in leaked}
        os.environ.update(leaked)
        try:
            env = self.delegate.child_env(self.roles, "go", "glm-5.3", key="go-key")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertNotIn("claude-secret", " ".join(env.values()))
        self.assertEqual(sorted(k for k in env if k.startswith("CLAUDE_") and k != "CLAUDE_CONFIG_DIR"),
                         ["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"])
        self.assertEqual(env["ANTHROPIC_API_KEY"], "go-key")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://opencode.ai/zen/go")
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)
        self.assertTrue(env["ANTHROPIC_CUSTOM_HEADERS"].startswith("x-opencode-session: "))

    @unittest.skipUnless(shutil.which("claude"), "needs the claude CLI")
    def test_doctor_passes_and_catches_a_leaked_credential(self):
        with tempfile.TemporaryDirectory() as cache:
            self.delegate.STAMP = Path(cache) / "stamp.json"
            clean = self.delegate.doctor(self.roles, "go")
            self.assertTrue(clean["ok"], clean)
            self.assertTrue(self.delegate.doctor_passed("go"))

            honest = self.delegate.child_env

            def leaky(*args, **kwargs):
                env = honest(*args, **kwargs)
                env["ANTHROPIC_AUTH_TOKEN"] = "pretend-claude-credential"
                return env

            self.delegate.child_env = leaky
            caught = self.delegate.doctor(self.roles, "go")
            self.delegate.child_env = honest
            self.assertFalse(caught["ok"], caught)
            self.assertIn("Authorization", " ".join(caught["problems"]))


class RoleGuardTests(unittest.TestCase):
    def guard(self, tool_input, env):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": tool_input}
        full = {k: v for k, v in os.environ.items() if k not in ("OPENCODE_API_KEY", "STACK_ALLOW_CLAUDE_BUILDER")}
        full.update(env)
        return subprocess.run([sys.executable, str(PLUGIN / "scripts/role-guard.py")], input=json.dumps(payload),
                              capture_output=True, text=True, env=full)

    def ready_env(self, cache):
        """A cache whose doctor stamp matches this Claude Code version, and a Go key."""
        delegate = load_delegate()
        stamp = Path(cache) / "stack" / "delegate-doctor.json"
        stamp.parent.mkdir(parents=True)
        stamp.write_text(json.dumps({"go": {"ok": True, "claude": delegate.claude_version()}}))
        return {"XDG_CACHE_HOME": cache, "OPENCODE_API_KEY": "k"}

    @unittest.skipUnless(shutil.which("claude"), "needs the claude CLI")
    def test_sonnet_builder_is_sent_to_the_delegate(self):
        with tempfile.TemporaryDirectory() as cache:
            r = self.guard({"subagent_type": "stack:poteto-agent", "model": "sonnet", "prompt": "build"}, self.ready_env(cache))
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("delegate.py", r.stderr)

    @unittest.skipUnless(shutil.which("claude"), "needs the claude CLI")
    def test_opus_and_other_agents_pass(self):
        with tempfile.TemporaryDirectory() as cache:
            env = self.ready_env(cache)
            self.assertEqual(self.guard({"subagent_type": "stack:poteto-agent", "model": "opus"}, env).returncode, 0)
            self.assertEqual(self.guard({"subagent_type": "general-purpose", "model": "sonnet"}, env).returncode, 0)
            self.assertEqual(self.guard({"subagent_type": "stack:poteto-agent", "model": "sonnet"},
                                        dict(env, STACK_ALLOW_CLAUDE_BUILDER="1")).returncode, 0)

    def test_claude_fallback_passes_when_the_backend_is_not_ready(self):
        with tempfile.TemporaryDirectory() as cache:
            r = self.guard({"subagent_type": "stack:poteto-agent", "model": "sonnet"}, {"XDG_CACHE_HOME": cache})
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_builder_bound_to_claude_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            roles = Path(tmp) / "roles.json"
            roles.write_text(json.dumps({"roles": {"builder": "claude:sonnet"}}))
            env = {"XDG_CACHE_HOME": tmp, "OPENCODE_API_KEY": "k", "STACK_ROLES_FILE": str(roles)}
            self.assertEqual(self.guard({"subagent_type": "stack:poteto-agent", "model": "sonnet"}, env).returncode, 0)


if __name__ == "__main__":
    unittest.main()
