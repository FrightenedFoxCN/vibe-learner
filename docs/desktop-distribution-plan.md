# Desktop Distribution Plan

## Status

- This is a deferred architecture plan, not an active implementation task.
- The packaging and desktop-app conversion work should start only after the current frontend/backend/runtime boundaries are more stable.
- Last updated: 2026-04-12

## Goal

Package Vibe Learner as a cross-platform desktop application that can be distributed to macOS, Windows, and Linux users while preserving the current local-first workflow:

- local document upload and parsing
- local JSON/file persistence
- optional remote model provider access
- local debug and planning trace inspection

This document exists to preserve the architectural decision path so the work can be resumed later without redoing the exploration from scratch.

## Current Baseline

The repository currently runs as a split local application:

- frontend: `apps/web` as a Next.js 16 app-router UI
- backend: `services/ai` as a FastAPI service
- persistence: local JSON files and uploaded PDFs under `services/ai/data/`
- model provider: mock by default, OpenAI-compatible provider when configured

Current implementation details that directly affect desktop packaging:

- frontend API calls assume `NEXT_PUBLIC_AI_BASE_URL` and default to `http://127.0.0.1:8000`
- backend CORS currently allows local web development origins
- backend data paths are rooted relative to the repository layout
- OCR fallback currently shells out to `tesseract`
- runtime settings currently persist API credentials into local JSON-backed storage

## Why This Is Deferred

Desktop packaging is not just a UI wrapper. It cuts across multiple unstable boundaries:

- frontend runtime strategy
- backend process lifecycle
- OCR/runtime native dependency bundling
- application data directory layout
- secret storage
- install/update/signing workflow

Doing this before the architecture settles would create churn in both the app shell and the business logic. The current recommendation is to finish the main product/runtime structure first, then package the stabilized system.

## Architecture Options Considered

### Option A: Electron + existing frontend + Python sidecar

Pros:

- fastest proof-of-concept
- lowest immediate migration cost
- can keep most current frontend assumptions

Cons:

- heavier memory footprint and package size
- still needs sidecar process management for FastAPI
- does not reduce long-term complexity much

### Option B: Tauri + static React frontend + Python sidecar

Pros:

- lighter desktop shell
- better long-term distribution story
- aligns well with a local loopback backend process

Cons:

- requires frontend runtime cleanup
- Next.js-specific pieces should be reduced or replaced
- still needs native dependency packaging for OCR

### Option C: Full desktop rewrite with non-Python backend

Pros:

- cleanest long-term runtime story
- possible single-stack packaging later

Cons:

- highest rewrite cost
- would delay product work significantly
- not justified while the Python parsing/planning stack is still evolving

## Recommended Direction

When this work is revisited, the recommended target is:

- desktop shell: `Tauri 2`
- frontend: progressively reduce coupling to Next.js runtime features and move toward a desktop-friendly SPA build
- backend: keep `services/ai` as a local FastAPI sidecar first, instead of rewriting core logic
- OCR: explicitly bundle `tesseract` and required language data, or replace OCR with a packaged alternative after measurement

This is the most pragmatic path because it preserves the working Python pipeline while avoiding the weight of a permanent Electron architecture.

## Proposed Future Runtime Shape

At implementation time, the desktop build should behave like this:

1. Desktop shell starts.
2. Shell allocates or discovers a local loopback port.
3. Shell launches the packaged AI service as a child process.
4. Frontend loads using the runtime-injected backend base URL.
5. Backend reads and writes from an OS-specific application data directory, not from repo-relative paths.
6. Secrets are stored in platform credential storage where possible.
7. App shutdown cleans up child processes reliably.

## Required Preconditions Before Starting

The following should be in place before desktop work begins:

- frontend routing and state boundaries are stable enough that the app can be built without depending on a Next.js server runtime
- backend startup/configuration is explicit and can run from packaged paths
- data storage root is configurable through environment or launch arguments
- OCR dependency strategy is decided and tested on all target platforms
- runtime credential handling is moved away from plain local JSON where feasible
- release targets are explicit: macOS, Windows, Linux package formats and signing expectations

## Planned Workstreams

### 1. Frontend runtime decoupling

- remove assumptions that the app runs only as `localhost:3000`
- isolate routing/navigation/state from framework-specific hosting details
- prepare a production desktop build path for the UI bundle

### 2. Backend packaging readiness

- make data root configurable
- make startup/configuration paths packaging-safe
- ensure all file-system writes land in per-user application data directories
- audit streaming endpoints and PDF file serving under desktop loopback usage

### 3. Native dependency packaging

- package OCR runtime and language data
- validate PyMuPDF and related native dependencies on each target OS
- define fallback behavior when OCR runtime is unavailable or partially installed

### 4. Desktop shell integration

- manage child process lifecycle
- inject runtime backend URL into the frontend
- define windowing, menu, file-open, and installer behavior

### 5. Secrets, updates, and release pipeline

- move API key storage toward keychain/credential manager integration
- define installer/updater approach
- define signing/notarization requirements for each platform

## Risks To Revisit Later

- OCR packaging may be the main blocker for a truly self-contained installer
- the current frontend may still carry enough Next.js coupling to make a direct desktop wrapper awkward
- local file-backed persistence may become a liability before desktop packaging starts
- model-provider configuration and API key handling need a stronger security story before consumer distribution

## Open Questions

- Should the desktop build remain functionally identical to the local web build, or intentionally drop some debug/developer surfaces?
- Is offline-only planning a future requirement, or is network access to model providers acceptable for the desktop product?
- Should PDF viewing remain loopback-served from FastAPI, or move into a desktop-native/local-file strategy?
- Is shipping OCR for English only acceptable at first, or does the product need multilingual OCR at launch?

## Exit Criteria For Starting This Project

This plan should move from deferred to active only when:

- the team agrees that current architecture churn has slowed down
- desktop distribution becomes a priority rather than a speculative direction
- packaging prerequisites in this document have owners and sequencing
- a release target and acceptance bar are defined for at least one platform

## Suggested First Revisit Deliverables

When the work is reopened, the first concrete deliverables should be:

- a short architecture decision record confirming shell choice
- a packaging spike for one target OS
- a data-root/configuration refactor plan
- an OCR bundling validation report
- a release checklist covering signing, updates, and crash recovery
