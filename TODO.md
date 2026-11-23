# TODO

本文件是仓库唯一的未完成任务与研究事项入口。日常约束见 [AGENTS.md](AGENTS.md)，系统文档见 [docs/README.md](docs/README.md)。

## 优先级定义

- **P1**：用户可用性、数据一致性、首屏架构边界或阻塞后续重构的地基问题。
- **P2**：组件结构、样式收口、代码卫生、测试守护与体验改进。
- **P3**：文档完善、工程整理与候选验证。

## 前端修整与重构计划

> 已完成基础准备：启用 Tailwind CSS v4（`apps/web/postcss.config.mjs` + `apps/web/app/globals.css` `@theme inline` 语义映射与 `@layer` 分层）。后续工作按以下三阶段推进，每阶段须保持 `npm run check` 与生产构建通过。

### Phase 1：首屏解耦与工程卫生（P1）

- [ ] **P1-FE-01 切断 API 聚合桶与循环依赖**
  - 拆分 `apps/web/lib/api/_shared.ts` 中对 `./tavern`、`./study` 及各域解码器的反向循环依赖，仅保留与域无关的传输/错误/序列化原语。
  - 将全部 10 个 `apps/web/lib/data/*.ts` 改为直接导入对应 `apps/web/lib/api/*.ts`，不再经过汇总桶 `apps/web/lib/api.ts`。
  - 将仍引用旧 barrel 的 4 处文件迁移至 `lib/data/*`：`plan-revision-panel.tsx`、`tavern-workspace-panels.tsx`、`use-tavern-workspace-state.ts`、`use-tavern-run-recovery.ts`。
- [ ] **P1-FE-02 根布局与重依赖按需懒加载**
  - 将 `apps/web/components/debug-overlay.tsx` 的面板体、文档调试与诊断时间线/审计/存储视图改为打开时 `next/dynamic` 懒加载，避免将 6,000+ 行诊断 JSON Schema 同步打入全站首屏。
  - 将 `react-pdf/dist/Page/TextLayer.css` 下沉至 `projected-pdf-viewer.tsx`，将 `katex/dist/katex.min.css` 下沉至富文本组件，并将 `rich-text-message.tsx` 改为 `next/dynamic` 按需加载 `rich-text-message-client.tsx`。
  - 完成后运行 `npm run bench:web-bundle` 验证首屏 gzip 体积显著下降且满足基线门禁。
- [ ] **P1-FE-03 依赖与死代码清理**
  - 将 `rehype-katex` 从根 `package.json` 移入 `apps/web/package.json`，移除未使用的 `rehype-mathjax`、`@playwright/test`、`@testing-library/react`、`jsdom`。
  - 删除 15 个指向已不存在测试目录的 `apps/web/playwright*.config.ts`。
  - 删除 3 个零引用死文件：`apps/web/components/character-renderer.tsx`、`apps/web/lib/scene-profile.ts`、`apps/web/scripts/harness-stage-decode.ts`；评估清理 `NEXT_PUBLIC_TAVERN_ROOM_PROFILING` 残留分支。

### Phase 2：Tailwind CSS v4 收口与共享 UI 基元（P1 / P2）

- [ ] **P1-FE-04 建设共享 UI 基元与格式化工具**
  - 新建 `apps/web/components/ui/`（基于 Tailwind v4 语义 Token）：`Button`、`Badge`、`Alert`、`Card`、`Collapsible`、`ConfirmDialog`（统一替代 6 处原生 `window.confirm` 与零散删除弹窗）。
  - 新建 `apps/web/lib/format.ts` 统一日期、时间、耗时格式化，替换分散在 8 个组件中的重复实现。
- [ ] **P2-FE-05 淘汰 TS 样式对象与内联样式，清理 `!important`**
  - 将 3 个 TS `CSSProperties` 样式表（`persona-workspace-styles.ts`、`scene-workspace-styles.ts`、`settings-styles.ts`，合计 2,025 行）迁移为 Tailwind CSS v4 工具类与语义基元。
  - 清理 169 处散落 JSX 内联 `style={{}}` 与 135 处硬编码 hex/rgba 色值，统一归口至设计基线 Token（`--negative` / `--accent` / `--panel` 等）。
  - 随迁移逐步移除 `apps/web/app/globals.css` 中的 36 处 `!important` 与废弃业务类，最终收敛 `globals.css` 至 Token、基础层与少量布局骨架。

### Phase 3：按域重组、巨型组件拆解与清债（P2）

- [ ] **P2-FE-06 规范目录结构与薄路由边界**
  - 按域整理 `apps/web/components/`（`ui/`、`layout/`、`plan/`、`study/`、`tavern/`、`debug/` 与既有 `persona/`、`scene/`、`settings/`）。
  - 重构 `apps/web/app/model-usage/page.tsx`（690 行）与 `apps/web/app/sensory-tools/page.tsx`（689 行）为薄路由 + 域组件 + controller hook，与其余路由保持一致。
- [ ] **P2-FE-07 拆解超千行巨型组件**
  - `study-console.tsx`（2,077 行 / 53 Props）拆分为消息流、交互题卡片、附件与输入区、角色事件详情与状态栏子组件。
  - `study-dialog-page.tsx`（1,170 行）下沉预览与副作用逻辑至独立 Hook/面板组件。
  - `tavern-workspace-panels.tsx`（1,043 行）按 7 个标准区块拆分为独立文件。
  - 拆解 `document-setup.tsx`（1,103 行）、`plan-overview.tsx`（1,035 行）、`persona-workspace-view.tsx`（1,391 行）与 `scene-workspace-view.tsx`（1,127 行）。
- [ ] **P2-FE-08 清零前端 ESLint 基线债务与补齐单元测试**
  - 逐域修复 `scripts/style/baseline.json` 中的 53 条前端 Lint 豁免（重点排查 46 条 `react-hooks/exhaustive-deps`，消除潜在陈旧闭包风险），并同步收紧基线。
  - 梳理 5 个未复用 `strict-response-decode.ts` 的解码器，抽取重复基础原语。
  - 围绕拆出的纯逻辑模块、格式化工具与核心解码器补充 `node --test` 单元测试并纳入 `test:invariants:web`。

## 未排期研究

每项研究在立项前须明确触发证据、假设、时间盒（time-box）、产出物以及采用/放弃标准：

| 编号 | 主题 | 前置评估条件 |
| --- | --- | --- |
| `RND-RUST-001` | 热点模块 Rust 重写 | 先以 profiling 证明 Python/TypeScript 存在明确性能瓶颈 |
| `RND-THEME-001` | 多主题与深色模式 | 先明确用户需求、design tokens、对比度基线与关闭开关 |
| `RND-LIVE2D-001` | 角色 Live2D 渲染接入 | 先确认资源授权、内存与帧率预算、动画降级策略 |
| `RND-TTS-001` | 语音合成（TTS）接入 | 先明确隐私、延迟、成本、可取消传输、字幕与静音降级 |
| `RND-DESKTOP-001` | 桌面自动更新、崩溃上报与分发签名 | 先明确发布策略、开发者签名/公证链路与包体性能预算 |
| `SKILL-DISTILL-001` | 可复用工作流沉淀 | 仅抽取稳定、可验证、无密钥与无用户数据的流程；事实真源仍归 `AGENTS.md` 与 `docs/` |

## 变更准入要求

- 涉及性能门禁调整的事项须遵循 [性能预算](docs/performance-budgets.md)，完整记录夹具、环境与原始样本。
- 涉及接口或路由变更的事项须同步运行 `npm run gen:api-reference` 并通过 `npm run check`。
