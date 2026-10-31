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
    env.update(HOME=str(home), USERPROFILE=str(home), XDG_DATA_HOME=str(home / ".local/share"), CLAUDE_PLUGIN_ROOT=str(PLUGIN), **(extra_env or {}))
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


class SetupTests(unittest.TestCase):
    def test_install_rules_is_idempotent(self):
        with tempfile.TemporaryDirectory() as home:
            script = PLUGIN / "skills/setup-stack/scripts/install-rules.py"
            # USERPROFILE too: Python >= 3.12 on Windows reads Path.home() from it, not HOME
            env = dict(os.environ, HOME=home, USERPROFILE=home)
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
            server.server_close()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual([f["title"] for f in out["findings"]], ["page 1 skips the first page"])
        self.assertEqual(seen["auth"], "Bearer k")
        self.assertEqual(seen["body"]["model"], "x-ai/grok-4.7")
        self.assertIn("page 1 is the first page", seen["body"]["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
