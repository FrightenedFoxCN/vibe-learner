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

[Desktop Preview](../.github/workflows/desktop-preview.yml) 可手动运行，也会在涉及桌面打包的 Pull Request 上触发。它和正式发布、发布前预检都调用[同一套构建矩阵](../.github/workflows/desktop-build.yml)：macOS ARM64 DMG、Windows x64 NSIS、Linux x64 AppImage。三个入口只用不同的 Artifact 后缀区分用途。

**macOS 预览签名边界**：预览产物使用 Tauri 的 ad-hoc 签名（`-`）且关闭 hardened runtime（因 PyInstaller 单文件 Sidecar 运行时解压动态库，ad-hoc 外层签名启用 hardened runtime 会触发系统库校验拒绝）。CI 会挂载生成的 DMG 并强制验证 `codesign --verify --deep --strict`。ad-hoc 签名不等于 Developer ID 正式分发签名，也不满足默认 Gatekeeper 公证要求；正式公证分发需对 Sidecar 及解压出的全部原生依赖使用同一 Developer ID 团队签名后再开启 hardened runtime。

## 5. 发布前预检与 GitHub Release

1. 将升版后的候选提交合入并推送到 `main`。更新根目录和三个 npm 工作区的清单、Python 的 `pyproject.toml`、Tauri 的 `tauri.conf.json` 和 `Cargo.toml`，并同步对应锁文件。
2. 在 GitHub Actions 手动从 `main` 运行 [Desktop Release Preflight](../.github/workflows/desktop-preflight.yml)，或执行 `gh workflow run desktop-preflight.yml --ref main`。预检校验七处版本一致，然后实际构建三端安装包并验证 macOS 签名；只上传 Artifacts，不创建 Release。
3. 等该次预检全部成功，核对运行页面展示的完整提交 SHA，再给**该次预检的提交**打标签。若要发布更新的提交，重新预检；PR Preview 不替代发布预检。
4. 推送 `v*` 标签触发 [Desktop Release](../.github/workflows/desktop-release.yml)。它先验标签与七处版本一致，再通过 GitHub API 查同仓库、同 SHA 的成功预检。找不到或查询出错会阻断打包与发布。通过后执行 Web 门禁、按同一矩阵重新构建三端安装包，发布安装包和 `SHA256SUMS.txt`。

发布命令示例（使用已成功预检的运行 ID 与候选版本）：

```bash
set -e
run_id="<成功预检的运行 ID>"
commit=$(gh run view "$run_id" --json headSha --jq .headSha)
test "$(git rev-parse HEAD)" = "$commit"
tag="vX.Y.Z"
uv run --project services/ai python scripts/release/validate.py versions --tag="$tag"
uv run --project services/ai python scripts/release/validate.py preflight \
  "$(gh repo view --json nameWithOwner --jq .nameWithOwner)" "$commit"
git tag -a "$tag" "$commit" -m "$tag"
git push origin "refs/tags/$tag"
```

以上命令从候选提交的本地工作区执行。已有标签的发布可在 Actions 中重跑；不要移动已经发布的标签。
