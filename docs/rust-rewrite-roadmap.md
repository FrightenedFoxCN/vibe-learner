# Rust Rewrite Roadmap

## Status

- Branch: `rust-rewrite-spike`
- This is a spike branch and scaffold, not a completed rewrite.
- The existing Next.js and FastAPI code remains the production implementation.
- The Rust workspace now passes `cargo check` and `cargo test` in this branch.

## Why This Exists

The repository now has a parallel Rust workspace so the rewrite can start from a clean boundary without disturbing the shipping code. The goal of this branch is to define the future replacement architecture, not to pretend the entire product has already been ported.

## What Was Added

- top-level Cargo workspace at repo root
- shared Rust contracts crate: `crates/vibe-learner-contracts`
- Rust backend skeleton: `services/ai-rs`
- Rust frontend skeleton: `apps/web-rs`
- toolchain pin: `rust-toolchain.toml`
- minimal local JSON/file persistence for Rust `documents` and `personas`
- runtime-verified Rust endpoints for `health`, persona creation, and document upload

## Chosen Rewrite Shape

### Backend

- framework: `axum`
- runtime: `tokio`
- transport: JSON HTTP APIs first
- storage direction: local-first file persistence, matching current product expectations

### Frontend

- framework direction: `dioxus`
- routing: route-per-surface, mirroring current page structure
- target surfaces:
  - Learning Workspace / Plan
  - Study flow
  - Persona Spectrum
  - Scene Setup
  - Settings

### Shared Models

- central Rust contracts crate for API/domain structs
- parity migration should start from shared response payloads before deeper feature logic

## Important Constraint

This rewrite is not close to feature parity yet. The current branch only provides:

- workspace structure
- backend entrypoint and rewrite-status endpoint
- JSON-backed persona listing/creation
- JSON-backed document listing/upload and file persistence
- frontend route shell with backend probe

It does not yet provide:

- PDF upload and parsing
- OCR fallback
- plan generation
- scene generation
- persona assistance
- study session orchestration
- persistence compatibility with existing data

## Recommended Port Order

1. Port core API/domain contracts from Python/TypeScript into `vibe-learner-contracts`.
2. Expand the file-backed persistence and runtime settings model in `services/ai-rs`.
3. Port document ingestion follow-up stages and debug artifact storage.
4. Port planning context and learning-plan generation endpoints.
5. Port persona, scene, and study-session APIs.
6. Rebuild the frontend surface-by-surface against the Rust API.
7. Only then decide whether to delete the legacy Next.js/FastAPI implementation.

## Working Rules For This Branch

- do not silently break the existing JS/Python implementation while the rewrite is incomplete
- prefer clean-room Rust modules over partial glue code hidden inside the current runtime
- keep replacement directory names explicit: `web-rs` and `ai-rs`
- preserve current page vocabulary and product concepts during the port

## Local Environment Note

This workspace has been compiled and tested in this session, but the current command environment still does not expose `cargo` on `PATH`. The installed toolchain binaries were resolved from:

```bash
/Users/ffox/.rustup/toolchains/stable-aarch64-apple-darwin/bin/
```

Use that toolchain directly until shell startup and non-interactive command environments agree on `PATH`:

```bash
RUSTC=/Users/ffox/.rustup/toolchains/stable-aarch64-apple-darwin/bin/rustc \
RUSTDOC=/Users/ffox/.rustup/toolchains/stable-aarch64-apple-darwin/bin/rustdoc \
/Users/ffox/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo check
```

The same pattern works for `cargo test` and `cargo run -p vibe-learner-ai-rs`.
