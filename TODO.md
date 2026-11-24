# TODO

本文件是仓库唯一的未完成任务与研究事项入口。日常约束见 [AGENTS.md](AGENTS.md)，系统文档见 [docs/README.md](docs/README.md)。

## 优先级定义

- **P1**：用户可用性、数据一致性、首屏架构边界或阻塞后续重构的地基问题。
- **P2**：组件结构、样式收口、代码卫生、测试守护与体验改进。
- **P3**：文档完善、工程整理与候选验证。

## 前端修整与重构计划

> 已完成基础准备：
> - 启用 Tailwind CSS v4（`apps/web/postcss.config.mjs` + `apps/web/app/globals.css` `@theme inline` 语义映射与 `@layer` 分层）。
> - 修复分层引入的层叠回归：第三方 CSS（KaTeX、react-pdf TextLayer）统一以 `@import … layer(vendor)` 引入，层序为 `theme, vendor, base, components, utilities`。**未分层 CSS 会压过所有层**，此后任何第三方或全局 CSS 都不得以未分层方式（含 JS `import "*.css"`）引入。
>
> 每个条目须保持 `npm run check` 与生产构建通过。执行顺序：Phase 1 → P1-FE-04 → P2-FE-06（纯 `git mv` 独立提交）→ 按域垂直切片推进 P2-FE-05 / P2-FE-07（同一域的拆分与样式迁移一次完成，避免对同一巨型文件二次翻动）→ P2-FE-08。

### Phase 1：首屏解耦与工程卫生（P1）

- [x] **P1-FE-01 切断 API 聚合桶与循环依赖**
  - 拆分 `apps/web/lib/api/_shared.ts` 中对 `./tavern`、`./study` 及各域解码器的反向循环依赖，仅保留与域无关的传输/错误/序列化原语。
  - 将全部 10 个 `apps/web/lib/data/*.ts` 改为直接导入对应 `apps/web/lib/api/*.ts`，不再经过汇总桶 `apps/web/lib/api.ts`。
  - 将仍引用旧 barrel 的 4 处文件迁移至 `lib/data/*`：`plan-revision-panel.tsx`、`tavern-workspace-panels.tsx`、`use-tavern-workspace-state.ts`、`use-tavern-run-recovery.ts`。
- [x] **P1-FE-02 根布局与重依赖按需懒加载**
  - 首屏改造前后的六路由采样、环境与门槛见 [性能预算](docs/performance-budgets.md)。
  - 将 `apps/web/components/debug/debug-overlay.tsx` 的面板体、文档调试与诊断时间线/审计/存储视图改为打开时 `next/dynamic` 懒加载，避免将约 6,000 行诊断 JSON Schema（export / query / storage）同步打入全站首屏。
  - 将 KaTeX 与 react-pdf TextLayer 样式从全局下沉至富文本组件与 `projected-pdf-viewer.tsx`；下沉后仍须位于 `vendor` 层（以含 `@import … layer(vendor)` 的样式入口引入），不得退回未分层的 JS `import`。
  - 将 `rich-text-message.tsx` 改为 `next/dynamic` 按需加载 `rich-text-message-client.tsx`，加载期以纯文本兜底渲染，避免流式消息闪烁与布局跳动。
  - 将 `/study`、`/plan` 加入 `scripts/performance/web-bundle.mjs` 的测量路由并重录基线；统一脚本默认端口（13417）与 `docs/performance-budgets.md` 示例端口（3417）。完成后运行 `npm run bench:web-bundle` 验证首屏 gzip 体积显著下降且满足基线门禁。
- [x] **P1-FE-03 依赖与死代码清理**
  - 用 [前端人工验收清单](docs/frontend-manual-acceptance.md) 替代不可运行的 Playwright 配置，保留自动化不变量测试。
  - 将 `rehype-katex` 从根 `package.json` 移入 `apps/web/package.json`，并显式声明当前仅靠依赖提升解析的 `katex`；移除未使用的 `rehype-mathjax`、`@testing-library/react`、`jsdom`。
  - 先删除 15 个指向不存在目录 `tests/browser` 的 `apps/web/playwright*.config.ts`，再移除仅被其引用的 `@playwright/test`（若前置决策保留浏览器测试则相应调整）。
  - 删除 3 个零引用死文件：`apps/web/components/character-renderer.tsx`、`apps/web/lib/scene-profile.ts`、`apps/web/scripts/harness-stage-decode.ts`，并运行 `npm run style:baseline` 清除其在 `scripts/style/baseline.json` 中的残留条目；评估清理 `NEXT_PUBLIC_TAVERN_ROOM_PROFILING`（`next.config.mjs` 与 `tavern-workspace.tsx`）残留分支。

### Phase 2：Tailwind CSS v4 收口与共享 UI 基元（P1 / P2）

- [x] **P1-FE-04 建设共享 UI 基元与格式化工具**
  - 新建 `apps/web/components/ui/`（基于 Tailwind v4 语义 Token）：`Button`、`Badge`、`Alert`、`Card`、`Collapsible`、`ConfirmDialog`。
  - `ConfirmDialog` 替代 8 处原生 `confirm`（含 `use-persona-persistence.ts` 等以参数注入的默认实现）与零散删除弹窗。注意两类约束：注入签名由 `(message) => boolean` 变为 `Promise<boolean>` 会改变调用方控制流；`use-persona-draft.ts` 的链接点击捕获守卫必须同步 `preventDefault()`，须改为“先拦截、确认后再路由跳转”，`beforeunload` 仍保留浏览器原生提示。
  - 新建 `apps/web/lib/format.ts` 统一日期、时间、耗时格式化，替换分散在 7 个组件中的重复实现（`plan-history`、`plan-overview`、`study-debug-panels`、`document-debug-panels`、`document-setup`、`scene-workspace-view`、`model-usage/page`）。
- [x] **P2-FE-05 淘汰 TS 样式对象与内联样式，清理 `!important`**
  - 真实规模：`style={…}` 共约 1,300 处，其中字面量 `style={{}}` 159 处，其余为引用 TS 样式对象；热点为 `persona-workspace-view`、`scene-workspace-view`、`settings-sections`、`study-console`、`document-debug-panels`、`model-usage/page`（各 100+ 处）。
  - 将 3 个 TS `CSSProperties` 样式表（`persona-workspace-styles.ts`、`scene-workspace-styles.ts`、`settings-styles.ts`，合计 2,022 行）随所属域切片迁移为 Tailwind CSS v4 工具类与语义基元。
  - 将 135 处硬编码 hex/rgba 色值归口至设计基线 Token（`--negative` / `--accent` / `--panel` 等）；建立例外白名单而非强行清零：`brand-mark.tsx` 品牌 SVG、`mermaid-diagram.tsx` 主题配置（无法读取 CSS 变量）、`projected-pdf-viewer.tsx` 数据驱动的叠加色（改用 `color-mix` 替代 hex 拼接透明度）。
  - 随迁移逐步移除 `apps/web/app/globals.css` 中的 37 处 `!important` 与废弃业务类，最终收敛 `globals.css` 至 Token、基础层与少量布局骨架。

### Phase 3：按域重组、巨型组件拆解与清债（P2）

- [x] **P2-FE-06 规范目录结构与薄路由边界**
  - 按域整理 `apps/web/components/`（`ui/`、`layout/`、`plan/`、`study/`、`tavern/`、`debug/` 与既有 `persona/`、`scene/`、`settings/`）；目录迁移以纯 `git mv` + 导入路径修正的独立提交完成，先于任何拆分。
  - 重构 `apps/web/app/model-usage/page.tsx`（690 行）与 `apps/web/app/sensory-tools/page.tsx`（689 行）为薄路由 + 域组件 + controller hook，与其余路由保持一致。
- [x] **P2-FE-07 拆解超千行巨型组件**（与 P2-FE-05 按域同批完成）
  - `study-console.tsx`（2,077 行 / 53 Props）拆分为消息流、交互题卡片、附件与输入区、角色事件详情与状态栏子组件。
  - `study-dialog-page.tsx`（1,170 行）下沉预览与副作用逻辑至独立 Hook/面板组件。
  - `tavern-workspace-panels.tsx`（1,043 行）按 7 个标准区块拆分为独立文件。
  - 拆解 `document-setup.tsx`（1,103 行）、`plan-overview.tsx`（1,035 行）、`persona-workspace-view.tsx`（1,391 行）与 `scene-workspace-view.tsx`（1,127 行）。
- [x] **P2-FE-08 清零前端 ESLint 基线债务与补齐单元测试**
  - 逐域修复 `scripts/style/baseline.json` 中的 53 条前端 Lint 豁免（合计 54 处；41 条位于 `apps/web/hooks/`），并同步收紧基线。46 条 `react-hooks/exhaustive-deps` 须逐条审查：补齐依赖会改变 effect 触发时机，需排除重复请求、循环触发与陈旧闭包，不得机械修复。
  - 将手写校验的解码器迁移至 `strict-response-decode.ts` 原语：`study-chat-operation-decode.ts`（526 行）、`tavern-decode.ts`（758 行）、`study-question-attempt.ts`（`model-tools` / `model-usage` / `runtime-settings` 已经由 `model-response-decode.ts` 复用，无需处理）。
  - 围绕拆出的纯逻辑模块、格式化工具与核心解码器补充 `node --test` 单元测试并纳入 `test:invariants:web`。

### Phase 4：前端浏览器审查 UI 与响应式优化（P1 / P2）

> 依据真实浏览器多视口（桌面 `1440×900`、笔记本 `1280×800`、移动 `390×844`）空态与填充态截图审查结果整理，逐项修复并按模块独立提交；每批修改后以 `npm run check` 与浏览器复检闭环。

#### P1（视觉损坏、交互遮挡与核心工作区体验）

- [x] **P1-UI-01 修复 `Character Shell` 样式表未导入**
  - 在 `apps/web/components/study/character-shell.tsx` 引入已存在的 `study-character-shell.css`（位于 `@layer components`），修复 `Study Dialog` 右侧角色状态栏标签与数值粘连裸排问题。
- [x] **P1-UI-02 修复 `Tavern Workspace` 巨型复选框与移动端空态半宽塌陷**
  - 修正 `apps/web/components/tavern/tavern-workspace.css` 的 `44px` 兜底选择器，排除 `checkbox/radio` 本体而由外层 `label` 承载 `44px` 触控热区，遵守 [前端设计基线](docs/frontend-design-baseline.md) 的 `18px` 复选框视觉尺寸。
  - 在 `max-width: 800px` 断点中同步覆盖 `.tavern-workspace-grid.empty-room` 为单列，修复移动端空态左侧栏塌陷至半屏宽。
- [ ] **P1-UI-03 修复 `Model Usage` 柱状图最高柱裁切与移动端表格挤碎**
  - 为 `apps/web/components/model-usage/model-usage-chart.tsx` 增加顶部数值留白、Y 轴刻度与完整列宽呈现，防止最高柱顶部标签画到 SVG 外被裁切。
  - 为 `apps/web/components/model-usage/model-usage-tables.tsx` 按列数设置合理 `min-w-*` 并收敛 `wrap-anywhere`，确保 `390px` 窄屏下通过外层 `overflow-x-auto` 局部横向滚动而非将单元格挤成 2 字符竖条。
- [ ] **P1-UI-04 修复全局 `Debug Overlay` 浮钮遮挡核心操作**
  - 调整 `apps/web/components/debug/debug-overlay.module.css` 与相关底部布局策略，缩小/收紧浮钮并在移动端避让吸底输入区与右侧主操作按钮，防止遮挡 `Study Dialog` 发送按钮与 `Study Notes` 删除按钮。
- [ ] **P1-UI-05 修复 `Plan Workspace` 表单样式割裂、按钮挤压与操作层级倒置**
  - 补齐 `document-setup-fields.tsx` 中 `PDF 物理页范围` 输入框与辅助说明的样式类名，统一 `.output-language-field` 与 `PersonaMiniCard` 为直角基线与一致表单节奏。
  - 修复 `Plan Overview` 中 `编辑题目` 按钮被压成竖排换行的问题，将排期项核心动作 `开始` 提升为主按钮、`完成` 退为次按钮，并将主要按钮与输入控件高度收敛至设计基线。
- [ ] **P1-UI-06 修复 `Scene Setup` 固定 104px 空白提示条与移动端首屏自动滚走工具栏**
  - 将 `scene-workspace-view.tsx` 顶部反馈条由固定 `h-[104px]` 改为内容自适应高度（`min-h-8 max-h-24`）。
  - 限制 `use-scene-workspace-controller.ts` 仅在用户主动切换节点时执行 `scrollIntoView`，避免移动端初次加载自动将树标题与工具按钮卷到顶栏之下。
- [ ] **P1-UI-07 优化 `Study Dialog` 吸底输入透字、PDF 预览浮条与 `Study Notes` 编辑器响应式布局**
  - 为 `study-console.css` 吸底输入区使用不透明背景与顶部分割线，修复滚动消息透影；改善 PDF 顶栏图标按钮热区，避免浮条遮压教材标题区。
  - 优化新版 `Study Notes`：移动端全屏 `Markdown 编辑器` 默认使用 `源码` 模式并将格式工具栏改为单行横向滚动；桌面端将 `删除` 按钮与 `保存 / 下载 .md` 拉开间距防止误触；清理侧栏笔记列表摘要中的原始 Markdown 标记噪声。

#### P2（跨页一致性、信息架构与细节打磨）

- [ ] **P2-UI-08 优化 `Tavern Workspace` 移动端阅读顺序与视觉语言收口**
  - 移动端进入已有房间时优先呈现 `Tavern Conversation Panel`，再承接输入与阵容；去除 `Tavern Header` 大面积径向渐变，并将英文工程眉标/修订文案收口为克制的中文展示。
- [ ] **P2-UI-09 优化 `Persona Spectrum` / `Scene Setup` 工具栏辨识度与只读态区分**
  - 为纯图标高频工具栏补充清晰可见短标签或分组语义，内置只读人格在表单顶部明确标示只读态与复制入口；修复 `persona-slots-pane.tsx` 标题栏中 `.secondary-actions` 顶部悬空横线与高度不齐问题。
- [ ] **P2-UI-10 收口全站视觉基线与细节打磨**
  - 统一各页 `H1` 标题字号梯度与圆角规范；将 `Sensory Tools` 的 39 处 `用途说明` `<summary>` 高度从 `32px` 提升至基线 `≥ 36px`。
  - 格式化 `Settings` 的 `最近保存` 时间戳（复用 `formatTimestamp`）；统一侧栏与首页/手册的「用户手册」命名；将 `Model Usage` 筛选器英文工程词（`Workflow` / `Operation`）汉化并对齐移动端筛选网格。

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
