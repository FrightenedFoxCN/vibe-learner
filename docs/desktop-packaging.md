# Desktop Packaging

## Goal

Produce host-native preview desktop installers from the current monorepo for:

- macOS `dmg`
- Windows `nsis`
- Linux `AppImage`

The packaging flow keeps the current architecture:

- `apps/web` exports static frontend assets
- `services/ai` is bundled as a local desktop sidecar via `PyInstaller`
- Tauri bundles the sidecar binary plus optional OnnxTR OCR assets

## Local Build

Run from the repository root:

```bash
npm install
npm run build:desktop
```

Host-specific outputs land under `apps/desktop/src-tauri/target/release/bundle/`.

Typical installer paths:

- macOS: `apps/desktop/src-tauri/target/release/bundle/dmg/*.dmg`
- Windows: `apps/desktop/src-tauri/target/release/bundle/nsis/*.exe`
- Linux: `apps/desktop/src-tauri/target/release/bundle/appimage/*.AppImage`

## OCR Model Bundling

To include offline OnnxTR assets in the desktop bundle, provide a directory with:

- `detector.onnx`
- `recognizer.onnx`
- `recognizer_vocab.txt`

Then build with:

```bash
VIBE_LEARNER_ONNXTR_MODEL_SOURCE=/absolute/path/to/onnxtr-models npm run build:desktop
```

The build stages those files into `apps/desktop/.bundle-resources/ocr/onnxtr/` and Tauri ships them as bundle resources.

If no model directory is provided, preview packaging still succeeds. In that case the desktop app will not set `VIBE_LEARNER_ONNXTR_MODEL_DIR`, so OCR falls back to runtime defaults instead of fully offline bundled assets.

To make missing OCR assets a hard build failure:

```bash
VIBE_LEARNER_REQUIRE_OCR_MODELS=1 npm run build:desktop
```

## Sidecar Packaging

`apps/desktop/scripts/prepare-bundle-assets.mjs` builds the backend sidecar by running:

- `uv run --with pyinstaller pyinstaller pyinstaller/sidecar.spec`

The generated binary is staged into:

- `apps/desktop/src-tauri/binaries/`

Tauri then embeds it through `bundle.externalBin`.

The sidecar declares and bundles `certifi` as its portable public CA store.
Desktop startup fills standard Python/Requests CA environment variables only
when the user has not supplied a custom bundle. The `/models` probe also builds
a verified SSL context from the platform defaults and adds the bundled certifi
roots explicitly. Missing CA data fails the build or request setup; TLS
verification and hostname checks are never disabled.

## CI Preview Builds

Preview installers are produced by `.github/workflows/desktop-preview.yml`.

Release and preview workflows use Node.js 26.x from the repository
`.node-version` file, matching the root package engine requirement and native
TypeScript test runner. Use the same major version for local validation.

The workflow:

- runs on `workflow_dispatch` plus desktop-relevant `pull_request` changes
- builds one host-native preview installer per OS in a matrix
- uploads the generated installer as a workflow artifact

macOS preview artifacts use Tauri's ad-hoc identity (`-`). Their hardened
runtime is disabled because the PyInstaller one-file sidecar extracts its own
dynamic libraries at runtime; with an ad-hoc outer signature, enabling hardened
runtime makes macOS library validation reject those extracted libraries. CI
mounts the final DMG and requires
`codesign --verify --deep --strict` to pass. Ad-hoc signing is not Developer ID
distribution signing and does not satisfy Gatekeeper or notarization on a
default macOS security policy. A future Developer ID/notarized build must sign
the PyInstaller sidecar and every extracted native dependency with the same
Developer ID team before re-enabling hardened runtime. Auto-update release
plumbing remains separate release-hardening work.

## GitHub Release Builds

GitHub releases are produced by `.github/workflows/desktop-release.yml`.

The workflow:

- triggers when a tag matching `v*` is pushed
- can also be re-run manually from the GitHub Actions UI on an existing tag ref
- validates that the tag version matches all desktop-facing version files:
  - root `package.json`
  - `apps/web/package.json`
  - `apps/desktop/package.json`
  - `packages/shared/package.json`
  - `services/ai/pyproject.toml`
  - `apps/desktop/src-tauri/tauri.conf.json`
  - `apps/desktop/src-tauri/Cargo.toml`
- builds the macOS `dmg`, Windows `nsis`, and Linux `AppImage`
- creates a GitHub Release and uploads the installers plus `SHA256SUMS.txt`

Release usage:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

If the tag does not match the checked-in version values, the workflow fails before any packaging starts.
