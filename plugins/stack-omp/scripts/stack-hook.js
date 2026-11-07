#!/usr/bin/env node
'use strict';

// Runs one ECC hook entry point from this plugin as its own main module, the way ECC's inline
// hook commands do. ECC's tracking and metrics checks inside the dispatchers stay off unless
// STACK_ECC_TELEMETRY=1. Continuous learning is not shipped at all: rewire owns memory.
// Usage: node stack-hook.js <entry.js> [args...]

const path = require('path');
const { spawnSync } = require('child_process');

const DISABLED_BY_STACK = [
  'post:observe:continuous-learning',
  'post:skill:track',
  'post:session-activity-tracker',
  'post:ecc-metrics-bridge',
  'post:ecc-context-monitor',
  'post:governance-capture',
  'post:bash:command-log-audit',
  'post:bash:command-log-cost',
];

const [entry, ...args] = process.argv.slice(2);
if (!entry) {
  process.stderr.write('[stack] hook entry point missing\n');
  process.exit(0);
}

const env = { ...process.env };
env.CLAUDE_PLUGIN_ROOT = env.CLAUDE_PLUGIN_ROOT || path.resolve(__dirname, '..');
if (env.STACK_ECC_TELEMETRY !== '1') {
  const disabled = new Set(String(env.ECC_DISABLED_HOOKS || '').split(',').map((id) => id.trim()).filter(Boolean));
  DISABLED_BY_STACK.forEach((id) => disabled.add(id));
  env.ECC_DISABLED_HOOKS = [...disabled].join(',');
}

const result = spawnSync(process.execPath, [path.join(env.CLAUDE_PLUGIN_ROOT, entry), ...args], {
  env,
  stdio: 'inherit',
  cwd: process.cwd(),
});
if (result.error) {
  process.stderr.write(`[stack] could not run ${entry}: ${result.error.message}\n`);
  process.exit(0);
}
process.exit(result.status === null ? 0 : result.status);
