---
paths:
  - "**/*.rs"
  - "**/Cargo.toml"
---
# Rust Hooks

> This file extends [common/hooks.md](stack-common-hooks.md) with Rust-specific content.

## PostToolUse Hooks

Configure in `~/.omp/agent/settings.json`:

- **cargo fmt**: Auto-format `.rs` files after edit
- **cargo clippy**: Run lint checks after editing Rust files
- **cargo check**: Verify compilation after changes (faster than `cargo build`)
