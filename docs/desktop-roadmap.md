# Desktop Roadmap

## Status

- Active roadmap for desktop packaging and secure local distribution work.
- Replaces `desktop-distribution-plan.md` as the implementation-facing document.
- Last updated: 2026-04-13

## Summary

Ship Vibe Learner as a cross-platform desktop application using:

- `Tauri 2` as the desktop shell
- statically exported `apps/web` pages as the frontend bundle
- `services/ai` as a packaged local FastAPI sidecar
- `OnnxTR` as the OCR engine for scanned and low-text PDFs
- an application-local encrypted vault unlocked by a user master password

This roadmap keeps the current local-first product shape intact while removing the two current blockers for consumer packaging:

- OCR depends on host-installed `tesseract`
- runtime API keys are persisted in ordinary local storage

## Target Runtime Shape

1. Desktop shell starts.
2. Shell loads an encrypted Stronghold snapshot from the app data directory.
3. User unlocks the app-local vault with a master password.
4. Shell allocates a loopback port and launches the packaged AI service.
5. Shell injects runtime config into the frontend, including the backend base URL.
6. Sidecar reads and writes from a per-user app data root, not repo-relative paths.
7. OCR uses packaged `OnnxTR` models stored inside desktop resources.
8. Sidecar receives API credentials in memory at launch time and never persists them to ordinary files.
9. App shutdown cleans up child processes reliably.

## Non-Goals For First Release

- backend rewrite away from Python
- system keychain / OS settings integration
- automatic updater
- signed production release pipeline
- runtime model switching UI for OCR models

## Milestones

### Milestone 0: Baseline Unification

- Raise backend and sidecar Python baseline to `3.12`.
- Update local development, CI, and packaging scripts to use one Python line for backend and sidecar builds.
- Create `apps/desktop` as the Tauri workspace.
- Add a dedicated desktop web export build for `apps/web`.
- Add a runtime injection path so the web app can consume `window.__VIBE_LEARNER_DESKTOP_CONFIG__`.

### Milestone 1: Secure Application-Local Secrets

- Use `tauri-plugin-stronghold` as the encrypted local vault.
- Require a user-created master password on first secure setup.
- Store API credentials only in Stronghold, never in backend JSON, SQLite, or logs.
- Keep ordinary runtime settings in backend storage, but replace raw secret values with configured-state flags over time.
- Add lock, unlock, change-password, reset-vault, and status flows.
- Auto-lock the vault when the app exits; idle auto-lock is a follow-up.

### Milestone 2: OCR Replacement With OnnxTR

- Replace `tesseract` shell-out OCR with an `OnnxTR`-based OCR engine.
- Keep current parser behavior where OCR is a low-text or forced fallback, not the default for every page.
- Package OCR models with the desktop app instead of downloading on first run.
- Target multilingual OCR from the first desktop release, while keeping one fixed curated model set.
- Return explicit OCR engine metadata and failure reasons so scanned-PDF issues are diagnosable.

### Milestone 3: Desktop Shell And Sidecar Lifecycle

- Let Tauri allocate or discover a loopback port and inject it into the frontend runtime.
- Launch the packaged FastAPI sidecar as a child process.
- Move storage to a per-user app data directory through launch-time environment variables.
- Keep PDF file serving and page image rendering on the loopback backend path for the first release.
- Add health checks and deterministic startup timeout handling.

### Milestone 4: Frontend Desktop Compatibility

- Export `apps/web` as static pages for desktop builds.
- Preserve the current real pages:
  - `/`
  - `/plan`
  - `/study`
  - `/persona-spectrum`
  - `/scene-setup`
  - `/sensory-tools`
  - `/settings`
  - `/model-usage`
- Remove assumptions that the frontend always talks to `http://127.0.0.1:8000`.
- Keep page-local storage behavior, but separate page cache from secret storage concerns.

### Milestone 5: Packaging And Release Artifacts

- Package the Python sidecar with `PyInstaller`.
- Embed OCR model assets and sidecar binaries through Tauri resources / sidecar packaging.
- Produce testable installers for:
  - macOS `dmg`
  - Windows `nsis`
  - Linux `AppImage`
- Add CI matrix builds that produce unsigned preview installers.

## Security Model

### Secret Storage

- Secrets live in an encrypted Stronghold snapshot inside the app data directory.
- The snapshot is unlocked with a master password chosen by the user.
- The desktop app may cache unlocked state in memory for the current app session only.
- Secrets are injected into the backend sidecar process in memory at launch time.
- The backend must treat those values as process-only inputs and must not persist them.

### Threat Model

This model is intended to protect against:

- casual inspection of app data files
- accidental leakage into logs, JSON files, SQLite rows, and exported debug artifacts
- straightforward extraction from copied storage directories

This model does not claim to protect against:

- malware reading unlocked process memory
- a compromised local machine
- weak user master passwords

## OCR Plan

### Why Replace Tesseract

The current OCR path shells out to `tesseract` and assumes host installation. That is a packaging blocker and a stability risk for scanned PDFs in desktop builds.

### OnnxTR Direction

- Use `OnnxTR` as the packaged OCR runtime.
- Standardize the backend and sidecar on Python `3.12`.
- Bundle model assets with the desktop app.
- Keep OCR fallback page-scoped so text-native PDFs do not pay the full OCR cost.
- Add OCR engine metadata to debug output and UI summary surfaces.

### OCR Acceptance Criteria

- text-native PDFs still parse without OCR overhead
- low-text and scanned PDFs recover usable content through OnnxTR
- OCR failure yields an explicit non-crashing state
- debug artifacts record OCR engine, model ID, and warning summary

## API And Type Changes

### Planned Contract Changes

- Add desktop runtime config types shared between the web bundle and Tauri shell.
- Add OCR engine metadata to document debug responses.
- Gradually replace raw secret fields in runtime settings responses with configured-state flags.
- Introduce desktop vault status commands and desktop-only secure secret update flows.

### Compatibility Strategy

- Keep existing web routes working during the transition.
- Add non-breaking desktop-specific fields before removing raw secret values.
- Only remove persisted plaintext secret handling after the desktop vault path is fully wired.

## Initial Implementation Slice

The first implementation slice started with:

- creating this roadmap
- scaffolding `apps/desktop`
- adding desktop-aware frontend runtime config injection support
- preparing the workspace for a dedicated desktop web export build

The next implementation slice should wire:

- Stronghold master-password unlock flow
- sidecar launch and injected backend base URL
- OCR engine abstraction with an `OnnxTR` implementation

## References

- [desktop-distribution-plan.md](./desktop-distribution-plan.md)
- [architecture.md](./architecture.md)
- [api-reference.md](./api-reference.md)
- https://v2.tauri.app/start/create-project/
- https://v2.tauri.app/reference/javascript/stronghold/
- https://pypi.org/project/onnxtr/
- https://pypi.org/pypi/onnxruntime

