"""Behavior tests for the omp port in plugins/stack-omp.

    python3 -m unittest discover -s tests -v

The port is generated from plugins/stack by tools/port-omp.py. These tests drive the
generated setup scripts and the guardrail extension the way omp does.
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
PLUGIN = ROOT / "plugins" / "stack-omp"
SETUP = PLUGIN / "skills" / "stack-setup-stack" / "scripts"
import importlib.util

_spec = importlib.util.spec_from_file_location("port_omp", ROOT / "tools" / "port-omp.py")
port_omp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(port_omp)


class PortTests(unittest.TestCase):
    def test_generated_port_verifies(self):
        self.assertEqual(port_omp.verify(PLUGIN), [])

    def test_port_matches_a_fresh_generation(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/port-omp.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_skills_and_agents_are_prefixed(self):
        for skill in PLUGIN.glob("skills/*/SKILL.md"):
            self.assertTrue(skill.parent.name.startswith("stack-"), skill)
            self.assertIn(f"name: {skill.parent.name}", skill.read_text())
        for agent in PLUGIN.glob("agents/*.md"):
            self.assertTrue(agent.stem.startswith("stack-"), agent)
            self.assertIn(f"name: {agent.stem}", agent.read_text())

    def test_rules_are_flattened_for_the_non_recursive_loader(self):
        rules = sorted(p.name for p in (PLUGIN / "rules").glob("*.md"))
        self.assertIn("stack-common-testing.md", rules)
        self.assertIn("stack-rust-testing.md", rules)
        self.assertFalse((PLUGIN / "rules" / "common").exists())

    def test_claude_code_adapter_is_replaced(self):
        self.assertFalse((PLUGIN / "docs/harness/claude-code.md").exists())
        self.assertTrue((PLUGIN / "docs/harness/omp.md").exists())
        self.assertIn("Per-call model", (PLUGIN / "docs/harness/omp.md").read_text())

    def test_guardrail_extension_blocks_no_verify(self):
        script = Path(tempfile.mkdtemp()) / "check.mjs"
        script.write_text(f"""
import extension from {json.dumps(str(PLUGIN / "extensions/stack-guardrails.mjs"))};
const handlers = {{}};
extension({{ on(name, fn) {{ handlers[name] = fn; }} }});
const ctx = {{ cwd: {json.dumps(str(ROOT))}, agent: {{ id: "test" }} }};
const result = await handlers.tool_call(
  {{ toolName: "bash", input: {{ command: "git commit --no-verify -m wip" }}, toolCallId: "1" }},
  ctx
);
process.stdout.write(JSON.stringify(result ?? null));
""")
        try:
            result = subprocess.run(["node", str(script)], capture_output=True, text=True,
                                    env={**os.environ, "HOME": str(Path.home())})
        finally:
            shutil.rmtree(script.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload and payload.get("block"), payload)
        self.assertIn("--no-verify", payload.get("reason", ""))


class SetupTests(unittest.TestCase):
    def test_install_rules_writes_flat_user_rules_idempotently(self):
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "HOME": home}
            for _ in range(2):
                result = subprocess.run(
                    [sys.executable, str(SETUP / "install-rules.py"), "--sets", "common", "rust", "--scope", "user"],
                    capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
            rules = Path(home) / ".omp/agent/rules"
            self.assertTrue((rules / "stack-common-testing.md").exists())
            self.assertTrue((rules / "stack-rust-testing.md").exists())
            self.assertFalse((rules / "common").exists())

    def test_setup_models_merges_config_and_writes_the_role_block(self):
        with tempfile.TemporaryDirectory() as agent:
            config = Path(agent) / "config.yml"
            config.write_text("modelRoles:\n  default: opencode-go/deepseek-v4.1-flash\n"
                              "task:\n  maxConcurrency: 8\ncustomKey: 1\n")
            env = {**os.environ, "HOME": str(Path.home()), "PI_CODING_AGENT_DIR": agent}
            for _ in range(2):
                result = subprocess.run(
                    [sys.executable, str(SETUP / "setup-models.py"),
                     "--code", "opencode-go/deepseek-v4.1-flash:high",
                     "--judgment", "opencode-go/deepseek-v4.1-flash:max",
                     "--max-effort", "max", "--no-validate"],
                    capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
            text = config.read_text()
            self.assertIn("stack_code: opencode-go/deepseek-v4.1-flash:high", text)
            self.assertIn("stack_judgment: opencode-go/deepseek-v4.1-flash:max", text)
            self.assertIn("perCallModel: on", text)
            self.assertIn("maxConcurrency: 8", text)
            self.assertIn("customKey: 1", text)
            self.assertEqual(text.count("stack_code:"), 1)
            rules = (Path(agent) / "RULES.md").read_text()
            self.assertIn("<!-- stack:models:start -->", rules)
            self.assertIn("interrogate reviewers:", rules)
            self.assertEqual(rules.count("<!-- stack:models:start -->"), 1)

    def test_setup_models_writes_judgment_fallback_without_openrouter(self):
        with tempfile.TemporaryDirectory() as agent:
            env = {**os.environ, "HOME": str(Path.home()), "PI_CODING_AGENT_DIR": agent}
            result = subprocess.run(
                [sys.executable, str(SETUP / "setup-models.py"),
                 "--code", "opencode-go/deepseek-v4.1-flash:high",
                 "--judgment", "anthropic/claude-opus-5-5:xhigh",
                 "--panel-primary", "opencode-go/gpt-5.6-luna:xhigh",
                 "--panel-extra", "opencode-go/glm-5.3-flash:high",
                 "--interrogate-extra", "opencode-go/grok-4.7:xhigh",
                 "--judgment-fallback", "opencode-go/gpt-5.6-luna:xhigh",
                 "--max-effort", "xhigh", "--no-validate"],
                capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = (Path(agent) / "config.yml").read_text()
            self.assertIn("stack_panel_primary: opencode-go/gpt-5.6-luna:xhigh", text)
            self.assertIn("stack_interrogate_extra: opencode-go/grok-4.7:xhigh", text)
            self.assertIn("fallbackOn: usage-limit", text)
            self.assertIn("fallbackChains:", text)
            self.assertIn("- opencode-go/gpt-5.6-luna:xhigh", text)
            self.assertIn("agentModelOverrides:", text)
            self.assertIn("stack-judgment: \"@stack_judgment\"", text)
            rules = (Path(agent) / "RULES.md").read_text()
            self.assertIn("use agent stack-judgment", rules)
            self.assertIn("opencode-go/grok-4.7:xhigh", rules)
            self.assertNotIn("openrouter:", rules)


if __name__ == "__main__":
    unittest.main()
