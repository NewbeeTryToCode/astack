// ECC guardrails for omp.
//
// omp events are translated into the Claude Code hook payloads the vendored ECC
// scripts already parse, so the guardrails keep one implementation. The scripts
// stay CommonJS under scripts/hooks/; this file is the only ESM entry point.

import { spawn, spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const HOOKS = path.join(ROOT, "scripts", "hooks");
const MAX_BUFFER = 16 * 1024 * 1024;

const DISABLED_BY_STACK = [
  "post:observe:continuous-learning",
  "post:skill:track",
  "post:session-activity-tracker",
  "post:ecc-metrics-bridge",
  "post:ecc-context-monitor",
  "post:governance-capture",
  "post:bash:command-log-audit",
  "post:bash:command-log-cost",
];

function hookEnv(cwd) {
  const env = {
    ...process.env,
    CLAUDE_PLUGIN_ROOT: process.env.CLAUDE_PLUGIN_ROOT || ROOT,
    ECC_PLUGIN_ROOT: process.env.ECC_PLUGIN_ROOT || ROOT,
    CLAUDE_PROJECT_DIR: process.env.CLAUDE_PROJECT_DIR || cwd,
  };
  if (env.STACK_ECC_TELEMETRY !== "1") {
    const disabled = new Set(
      String(env.ECC_DISABLED_HOOKS || "")
        .split(",")
        .map((id) => id.trim())
        .filter(Boolean),
    );
    for (const id of DISABLED_BY_STACK) disabled.add(id);
    env.ECC_DISABLED_HOOKS = [...disabled].join(",");
  }
  // The fallback runtime is the omp binary itself. Without BUN_BE_BUN it starts a new omp
  // session instead of running the hook script, and every hook call spawns another one.
  if (NODE === process.execPath) env.BUN_BE_BUN = "1";
  return env;
}

function findNode() {
  for (const bin of [process.env.STACK_NODE, "node", "bun"]) {
    if (!bin) continue;
    const result = spawnSync(bin, ["--version"], { encoding: "utf8", timeout: 5000 });
    if (!result.error && result.status === 0) return bin;
  }
  return process.execPath;
}

const NODE = findNode();

function run(script, args, payload, timeout = 30000) {
  const result = spawnSync(NODE, [path.join(HOOKS, script), ...args], {
    input: JSON.stringify(payload),
    encoding: "utf8",
    env: hookEnv(payload.cwd),
    cwd: payload.cwd,
    timeout,
    maxBuffer: MAX_BUFFER,
  });
  if (result.error) {
    return { exitCode: 1, stdout: "", stderr: String(result.error.message || result.error) };
  }
  return { exitCode: result.status ?? 0, stdout: result.stdout || "", stderr: result.stderr || "" };
}

function runAsync(script, args, payload, timeout = 45000) {
  try {
    const child = spawn(NODE, [path.join(HOOKS, script), ...args], {
      env: hookEnv(payload.cwd),
      cwd: payload.cwd,
      stdio: ["pipe", "ignore", "ignore"],
      detached: true,
    });
    child.on("error", () => {});
    child.stdin.on("error", () => {});
    child.stdin.end(JSON.stringify(payload));
    child.unref();
  } catch {
    // Async post checks must never break a tool result.
  }
}

function parse(result) {
  const out = { block: false, reason: "", context: "" };
  const text = String(result.stdout || "").trim();
  if (text) {
    try {
      const data = JSON.parse(text);
      const specific = data.hookSpecificOutput && typeof data.hookSpecificOutput === "object"
        ? data.hookSpecificOutput
        : {};
      if (data.decision === "block") {
        out.block = true;
        out.reason = String(data.reason || specific.permissionDecisionReason || "");
      }
      if (specific.permissionDecision === "deny") {
        out.block = true;
        out.reason = String(specific.permissionDecisionReason || data.reason || "");
      }
      if (typeof specific.additionalContext === "string") out.context = specific.additionalContext;
      if (typeof data.additionalContext === "string") out.context = data.additionalContext;
      if (typeof data.systemMessage === "string") {
        out.context = out.context ? `${out.context}\n${data.systemMessage}` : data.systemMessage;
      }
    } catch {
      if (result.exitCode === 2) out.block = true;
      out.context = text;
    }
  }
  if (!out.block && result.exitCode === 2) {
    out.block = true;
    out.reason = out.reason || String(result.stderr || "").trim() || "blocked by stack guardrail";
  }
  return out;
}

function aggregate(entries, payload) {
  const out = { block: false, reason: "", contexts: [] };
  for (const entry of entries) {
    const result = parse(run(entry.script, entry.args, payload, entry.timeout));
    if (result.block) {
      out.block = true;
      out.reason = result.reason || out.reason;
    }
    if (result.context) out.contexts.push(result.context);
    if (entry.stderr && result.exitCode !== 0 && !result.block) {
      const detail = String(result.stderr || "").trim();
      if (detail) out.contexts.push(detail);
    }
  }
  return out;
}

function claudeToolName(tool) {
  const name = String(tool || "").toLowerCase();
  if (name === "bash") return "Bash";
  if (name === "edit") return "Edit";
  if (name === "write") return "Write";
  return String(tool || "");
}

function toolInput(tool, input) {
  const source = input && typeof input === "object" ? input : {};
  const name = String(tool || "").toLowerCase();
  if (name === "bash") return { command: String(source.command || "") };
  if (name === "edit") {
    return {
      file_path: String(source.file_path || source.path || ""),
      old_string: String(source.old_string || source.old_text || ""),
      new_string: String(source.new_string || source.new_text || ""),
    };
  }
  if (name === "write") {
    return {
      file_path: String(source.file_path || source.path || ""),
      content: String(source.content || ""),
    };
  }
  return source;
}

function basePayload(ctx, event, name) {
  return {
    hook_event_name: name,
    session_id: String(ctx.agent?.id || "omp"),
    transcript_path: "",
    cwd: ctx.cwd || process.cwd(),
    tool_name: event.toolName || "",
    tool_use_id: event.toolCallId || "",
    tool_input: event.input || {},
  };
}

function preflightEntries(tool) {
  const name = String(tool || "").toLowerCase();
  if (name === "bash") {
    return [{ script: "pre-bash-dispatcher.js", args: [], timeout: 10000, stderr: true }];
  }
  if (name === "edit" || name === "write") {
    return [
      {
        script: "run-with-flags.js",
        args: ["pre:config-protection", "scripts/hooks/config-protection.js", "standard,strict"],
        timeout: 5000,
        stderr: true,
      },
    ];
  }
  return [];
}

function hookifyPre() {
  return {
    script: "run-with-flags.js",
    args: ["pre:hookify-runtime", "scripts/hooks/hookify-runtime.js", "minimal,standard,strict"],
    timeout: 10000,
    stderr: true,
  };
}

function hookifyPrompt() {
  return {
    script: "run-with-flags.js",
    args: ["prompt:hookify-runtime", "scripts/hooks/hookify-runtime.js", "minimal,standard,strict"],
    timeout: 10000,
    stderr: true,
  };
}

function stopEntries() {
  return [
    {
      script: "lifecycle-hook-bootstrap.js",
      args: ["stop:hookify-runtime", "scripts/hooks/hookify-runtime.js", "minimal,standard,strict", "10000"],
      timeout: 10000,
      stderr: true,
    },
    {
      script: "lifecycle-hook-bootstrap.js",
      args: ["stop:format-typecheck", "scripts/hooks/stop-format-typecheck.js", "standard,strict", "300000"],
      timeout: 300000,
      stderr: true,
    },
    {
      script: "lifecycle-hook-bootstrap.js",
      args: ["stop:check-console-log", "scripts/hooks/check-console-log.js", "standard,strict", "30000"],
      timeout: 30000,
      stderr: true,
    },
  ];
}

export default function stackGuardrails(pi) {
  if (/^0|false|no|off$/i.test(String(process.env.ECC_HOOKS_ENABLED || ""))) return;

  pi.on("tool_call", async (event, ctx) => {
    if (!event || !event.toolName) return;
    const payload = basePayload(ctx, event, "PreToolUse");
    payload.tool_name = claudeToolName(event.toolName);
    payload.tool_input = toolInput(event.toolName, event.input);
    const result = aggregate([...preflightEntries(event.toolName), hookifyPre()], payload);
    if (result.block) return { block: true, reason: result.reason || "blocked by stack guardrail" };
    if (result.contexts.length) return { additionalContext: result.contexts.join("\n") };
    return undefined;
  });

  pi.on("tool_result", async (event, ctx) => {
    if (!event || !event.toolName) return;
    const payload = basePayload(ctx, event, "PostToolUse");
    payload.tool_name = claudeToolName(event.toolName);
    payload.tool_input = toolInput(event.toolName, event.input);
    payload.tool_response = {
      success: !event.isError,
      content: event.content,
      details: event.details,
    };
    const raw = run("posttooluse-dispatcher.js", ["sync"], payload, 30000);
    const result = parse(raw);
    runAsync("posttooluse-dispatcher.js", ["async"], payload, 45000);
    const context = [result.context, String(raw.stderr || "").trim()].filter(Boolean).join("\n");
    if (context) return { additionalContext: context };
    return undefined;
  });

  pi.on("before_agent_start", async (event, ctx) => {
    const prompt = typeof event?.prompt === "string" ? event.prompt.trim() : "";
    if (!prompt) return undefined;
    const payload = {
      hook_event_name: "UserPromptSubmit",
      session_id: String(ctx.agent?.id || "omp"),
      transcript_path: "",
      cwd: ctx.cwd || process.cwd(),
      prompt,
      user_prompt: prompt,
    };
    const result = parse(run(hookifyPrompt().script, hookifyPrompt().args, payload, 10000));
    if (result.block) {
      return {
        message: {
          customType: "stack-guardrail",
          content: result.reason || "blocked by stack prompt guardrail",
          display: false,
          attribution: "agent",
        },
      };
    }
    if (result.context) {
      return {
        message: {
          customType: "stack-guardrail",
          content: result.context,
          display: false,
          attribution: "agent",
        },
      };
    }
    return undefined;
  });

  pi.on("session_stop", async (event, ctx) => {
    if (event?.stop_hook_active) return undefined;
    const payload = {
      hook_event_name: "Stop",
      session_id: String(ctx.agent?.id || "omp"),
      transcript_path: "",
      cwd: ctx.cwd || process.cwd(),
      stop_hook_active: Boolean(event?.stop_hook_active),
    };
    const result = aggregate(stopEntries(), payload);
    if (result.block) return { decision: "block", reason: result.reason || "blocked by stack stop guardrail" };
    if (result.contexts.length) return { continue: true, additionalContext: result.contexts.join("\n") };
    return undefined;
  });
}
