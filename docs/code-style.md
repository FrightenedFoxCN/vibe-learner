# 代码风格门禁

仓库通过独立命令管理静态 Lint、格式化与 TypeScript 类型检查（类型检查入口为 `npm run check:web` 与 `npm run check:contracts`）。

## 命令清单

| 命令 | 覆盖范围 |
| --- | --- |
| `npm run style:check` | 全量源码相对基线执行 Lint；对相对 `HEAD` 新增/修改（含暂存与未跟踪）的源码检查格式 |
| `npm run style:check -- --base <commit>` | 同上，改动文件相对指定基线 commit 计算 |
| `npm run lint:web` | 对 Web、共享契约、桌面脚本与仓库工具的 JS/TS 源码执行 ESLint |
| `npm run lint:ai` | 对 AI 后端与仓库 Python 脚本执行 Ruff Lint |
| `npm run format:check` | 仅检查改动源码的格式，不改写文件 |
| `npm run style:all` | 全量 Lint，并检查所有非基线豁免文件的格式 |

## 依赖与规则

在根目录运行 `npm ci`、后端运行 `uv sync --directory services/ai --frozen` 安装锁定版本工具（工具版本锁定在 `package-lock.json` 与 `services/ai/uv.lock`）。

- **ESLint（JS/TS）**：检查未使用变量/导入、`react-hooks/rules-of-hooks` 与 `react-hooks/exhaustive-deps`。允许未使用的回调参数与捕获异常，刻意保留的未使用变量以下划线前缀标注；类型解析使用 `@typescript-eslint/parser`，不依赖生产构建。
- **Ruff（Python）**：检查 `F401`（未使用导入）与 `F841`（未使用局部变量）。
- **格式化**：JS/TS 由 Prettier 负责，Python 由 Ruff 负责，统一 88 列宽与 LF 换行。单文件格式化命令：
  - `npx prettier --write path/to/file.tsx`
  - `uv run --directory services/ai ruff format path/to/file.py`
- **覆盖范围**：涵盖 `apps/`、`packages/`、`services/ai/`、`scripts/` 及根级 JS/TS/Python 配置文件；排除构建/依赖/数据目录、`next-env.d.ts`、JSON 夹具、Markdown、Rust 与 Shell 文件。`packages/shared/src/tool-manifest.ts` 参与 Lint 但跳过格式化（内嵌生成 golden 保持紧凑）。语法错误与缺失规则不可豁免。

## 既有代码基线

`scripts/style/baseline.json` 记录既有代码中的 Lint 豁免与格式豁免：

- **Lint 豁免**：精确绑定路径、规则名、消息、源码行摘要与出现次数。仅平移未改动行不会产生新债，但变更变量名、行内容、路径或新增同类问题均会触发失败。
- **格式豁免**：绑定规范化后的完整源码摘要；任何被修改的文件均须格式化达标。
- **基线只缩不扩**：`npm run style:baseline` 仅在清理存量债或经评审的工具升级时显式更新，日常功能改动不允许新增基线豁免。

## CI 门禁

`.github/workflows/style.yml` 在 Pull Request、推送至 `main` 与手动触发时运行风格门禁；发布流程同时运行 `npm run style:all`，`npm run check` 将 `style:check` 作为前置门禁。
