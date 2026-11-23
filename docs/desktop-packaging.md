# 桌面打包与发布

本文说明如何从当前 monorepo 构建跨平台 Tauri 桌面安装包（macOS `dmg`、Windows `nsis`、Linux `AppImage`）以及 CI 预览与 Release 发布流程。

## 打包结构

- `apps/web`：构建静态前端资源；
- `services/ai`：通过 `PyInstaller` 打包为本地后端 Sidecar 可执行文件；
- `apps/desktop`：由 Tauri 2 将前端资源、Sidecar 与可选离线 OnnxTR OCR 模型打包为平台原生安装包。

## 1. 本地构建

在仓库根目录执行（需匹配 `.node-version` 指定的 Node.js 26.x 及 Rust ≥ 1.89）：

```bash
npm install
npm run build:desktop
```

产物输出在 `apps/desktop/src-tauri/target/release/bundle/`：

- macOS：`dmg/*.dmg`
- Windows：`nsis/*.exe`
- Linux：`appimage/*.AppImage`

## 2. 离线 OCR 模型打包

若需在安装包内附带离线 OnnxTR OCR 模型，准备包含以下三个文件的目录：

- `detector.onnx`
- `recognizer.onnx`
- `recognizer_vocab.txt`

然后指定路径构建：

```bash
VIBE_LEARNER_ONNXTR_MODEL_SOURCE=/absolute/path/to/onnxtr-models npm run build:desktop
```

构建脚本会将模型暂存至 `apps/desktop/.bundle-resources/ocr/onnxtr/` 并由 Tauri 打包为内置资源。

- **默认容错模式**：未提供模型目录时预览构建仍可完成，但应用不会注入 `VIBE_LEARNER_ONNXTR_MODEL_DIR`（`ocr/onnxtr/manifest.json` 中 `included: false`）；文本层 PDF 解析不受影响，扫描件 OCR 首次使用需联网下载默认模型（初始化失败会显式报错）。
- **强制离线模式**：要求缺失模型直接令构建失败时，额外传入：

```bash
VIBE_LEARNER_REQUIRE_OCR_MODELS=1 npm run build:desktop
```

## 3. Sidecar 与 TLS 证书

`apps/desktop/scripts/prepare-bundle-assets.mjs` 执行 `uv run --with pyinstaller pyinstaller pyinstaller/sidecar.spec` 生成后端二进制，并放置到 `apps/desktop/src-tauri/binaries/`，由 Tauri `bundle.externalBin` 嵌入。

- Sidecar 显式打包 `certifi` 公共 CA 证书；桌面启动时仅在用户未指定自定义证书时填充标准 Python/Requests CA 环境变量。
- `/models` 探测同时加载系统默认根证书与内置 `certifi` 根证书；缺失 CA 数据直接失败，绝不关闭 TLS 校验或主机名验证。

## 4. CI 预览构建

`.github/workflows/desktop-preview.yml` 在 `workflow_dispatch` 或涉及桌面端文件的 Pull Request 上触发，按 OS 矩阵构建并上传预览安装包 Artifact。

**macOS 预览签名边界**：预览产物使用 Tauri 的 ad-hoc 签名（`-`）且关闭 hardened runtime（因 PyInstaller 单文件 Sidecar 运行时解压动态库，ad-hoc 外层签名启用 hardened runtime 会触发系统库校验拒绝）。CI 会挂载生成的 DMG 并强制验证 `codesign --verify --deep --strict`。ad-hoc 签名不等于 Developer ID 正式分发签名，也不满足默认 Gatekeeper 公证要求；正式公证分发需对 Sidecar 及解压出的全部原生依赖使用同一 Developer ID 团队签名后再开启 hardened runtime。

## 5. GitHub Release 发布

`.github/workflows/desktop-release.yml` 在推送匹配 `v*` 的标签时触发（亦可在 Actions UI 对已有标签手动重跑）：

1. 校验标签版本与全部 7 处版本清单严格一致：
   - 根目录 `package.json`
   - `apps/web/package.json`
   - `apps/desktop/package.json`
   - `packages/shared/package.json`
   - `services/ai/pyproject.toml`
   - `apps/desktop/src-tauri/tauri.conf.json`
   - `apps/desktop/src-tauri/Cargo.toml`
2. 版本不匹配在打包前立即失败；
3. 执行门禁检查并构建三端安装包，创建 GitHub Release，上传安装包及 `SHA256SUMS.txt`。

发布命令示例：

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```
