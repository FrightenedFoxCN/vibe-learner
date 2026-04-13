# Desktop Packaging

## Goal

Produce unsigned preview desktop installers from the current monorepo for:

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

## CI Preview Builds

Preview installers are produced by `.github/workflows/desktop-preview.yml`.

The workflow:

- runs on `workflow_dispatch` plus desktop-relevant `pull_request` changes
- builds one host-native preview installer per OS in a matrix
- uploads the generated installer as a workflow artifact

These artifacts are intentionally unsigned. Signing, notarization, and auto-update release plumbing remain separate release-hardening work.
