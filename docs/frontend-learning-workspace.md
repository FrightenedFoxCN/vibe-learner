# 前端页面边界与分层架构

本文定义 `apps/web` 各业务工作区的状态归属、路由边界与代码分层约定。改动或重构前端时应保持职责分离，避免渲染、异步编排、状态迁移与文案常量重新揉回单个巨型组件。

## 1. 路由分组与 Provider 作用域

| 路由 | 归属域 | 状态边界 |
| --- | --- | --- |
| `/`、`/manual` | 导航首页与用户手册 | 无业务域 Provider，仅展示导航与静态手册 |
| `/plan`、`/study` | `(learning)` 路由组 | 共享 `LearningWorkspaceProvider`；仅在此路由组内初始化教材/计划/会话数据 |
| `/persona-spectrum` | Persona 域 | 独立组合与域 Hook，不初始化学习域资源 |
| `/scene-setup` | Scene 域 | 独立组合与域 Hook，不初始化学习域资源 |
| `/tavern` | Tavern 域 | 独立状态、查询、恢复与变更 Hook，不初始化学习域资源 |
| `/settings`、`/sensory-tools`、`/model-usage` | 系统配置与观测 | 各自按需消费对应 `lib/data/*` 模块 |

根布局挂载两个轻量级跨路由基础设施：

- **`LearningPageCacheProvider`**：跨页面保留局部草稿（内存中的已选 `File` 对象与可序列化的 `sessionStorage` 表单/预览定位草稿；硬刷新后 `File` 不恢复）。
- **`DebugProvider` 与 `DebugOverlay`**：接收当前页只读调试投影并在页面离开时自动清理；学习域卸载时同步取消本地流读取、作废过期响应 ticket，并向已知流操作发出取消请求（模糊 Study Chat 写操作保留原身份供返回时查询恢复）。

## 2. 学习工作区六层架构（`/plan` 与 `/study`）

### ① 页面组合层

- 文件：`apps/web/components/learning-workspace.tsx`（`/plan`）、`apps/web/components/study-dialog-page.tsx`（`/study`）
- 职责：组装子面板、绑定 Controller 状态与回调、控制页面级布局。
- 禁止：直接发起 API 调用、编排多步异步流、内联重复业务文案常量。

### ② 工作流编排层（Controller Hooks）

`apps/web/hooks/use-learning-workspace-controller.ts` 组合多个职责单一的子 Owner，每个异步 Owner 按需接收窄接口端口（API / 存储 / 时钟）：

| Owner | 职责 |
| --- | --- |
| `WorkspaceSnapshotLoader` | 初始/聚焦/手动快照加载、在途聚焦请求合并与过期查询抑制 |
| `useWorkspaceLibraries` | Persona / Scene 列表刷新身份、选中同步与存储事件监听 |
| `usePlanGeneration` | 上传、解析/规划流式过程、取消控制与初始 Session 创建 |
| `usePlanMutations` | 计划与 Study Unit 变更、资源级准入与用户反馈 |
| `useStudySessionNavigation` | Session 历史、创建与串行章节切换 |
| `useStudyMessages` | 学习者/隐藏消息发送、请求身份分配与准入失败处理 |
| `useStudyChatRecovery` | 纯查询恢复、显式重试资格判定与视图围栏 ticket |
| `useStudyCommitActions` | 交互题判分与计划确认的提交投影及回调资格判定 |
| `useStudyContinuation` | 开场白、定时自动续接、暂停与延迟答复回调 |
| `learning-workspace-model` | 目录、主题、场景与配置的纯派生投影 |

核心协作规则：

- 存在待确认操作时阻塞新的自动生成；
- 定时器触发时读取当前最新 Session revision，失败后等待权威刷新而不在 busy 切换时重轮询；
- 学习者消息完成时仅消费本次请求前捕获的延迟回调，保留在途期间新入队的作答；
- 异步结果统一经过 `async-result-fence.ts`（绑定操作身份、当前 Plan/Session 主体、单调视图版本与字段目标）；Persona 与 Scene 的异步生成与导入使用同一围栏原语。

### ③ Reducer 状态层

- 文件：`apps/web/lib/learning-workspace-reducer.ts`
- 职责：定义规范 `LearningWorkspaceState` 与 Action，集中处理状态迁移（文档、计划、会话、回复、选中态、提示与忙碌状态）。
- 禁止：网络请求、浏览器事件监听或视图渲染。

### ④ 纯状态与展示投影工具

- `apps/web/lib/learning-workspace-state.ts`：确定性、无副作用的快照合并、文档 upsert 与默认 Session 构造。
- `apps/web/lib/plan-panel-data.ts`：计划历史排序、选中解析与 `Plan Overview Panel` 展示数据映射。

### ⑤ 文案与遥测常量

- `apps/web/lib/learning-workspace-copy.ts`、`apps/web/lib/learning-workspace-telemetry.ts`：集中维护重复提示语与工作流日志前缀，不散落回组件层。

### ⑥ 数据与解码层

- 数据入口统一走 `apps/web/lib/data/*.ts`，底层传输位于 `apps/web/lib/api/*.ts`，严格解码位于 `apps/web/lib/*-decode.ts`。

## 3. 核心页面区块与交互约定

### `/plan`（Plan Workspace）

核心子区块：`PersonaSelector`、`DocumentSetup`、`DocumentCheckpointPanel`、`PlanOverview`、`PlanRevisionPanel`、`StudyUnitRevisionPanel`。

`Plan Overview` 固定展示规则：

- `courseTitle` 为主标题，`objective` 为其下辅助目标文本；
- `todayTasks`、`schedule` 与嵌套 `scheduleChapters` 均为顺序阅读内容，采用纵向流式布局，不排成多列卡片网格；
- 嵌套 `scheduleChapters` 在父 `schedule` 项下展开并保留物理页码锚点。

### `/study`（Study Dialog）

核心子区块：`PersonaSelector`、`StudyConsole`、`CharacterShell` 与内嵌 PDF/图片预览面板。

核心交互规则：

- 章节目录源自当前计划的 `schedule[].unitId` 映射到的教材 Study Units（为空时回退至文档 `sections`）；切换父排期项才切换或创建对应 `study_unit_id` 的 Session，并清理旧回复；切换子章节只更新本地预览与快捷跳页锚点。
- 消息列表校验连续 Turn 序号，按时间从旧到新渲染并滚动至最新已提交 Turn。
- 模糊网络结果展示显式查询操作并锁定新发送，仅在 `not_committed + safe_to_retry` 时允许重发；准入前明确拒绝要求先刷新 Session。
- 未发送草稿、答题草稿与预览位置支持跨路由与同标签页刷新恢复。
- 模型侧成功恢复记录仅展示在调试面板中，不打扰主学习界面。

## 4. 新功能归位决策

改动或新增前端行为时，按以下顺序确定归属层：

1. 纯 UI 渲染与局部交互细节 → `components/`
2. 跨请求异步编排、定时与恢复 → `hooks/`
3. 规范状态迁移 → `lib/*-reducer.ts` 或 `lib/*-state.ts`
4. 线上解码与数据访问 → `lib/*-decode.ts` + `lib/api/` + `lib/data/`
5. 重复提示文案与日志格式化 → `lib/*-copy.ts` / `lib/*-telemetry.ts`
