# 页面命名与术语

讨论、设计或修改前端页面与区块时，统一使用以下标准名称，避免“左边那个面板”等模糊指代。

## 1. 页面标准名称

| 路由 | 标准名称 | 用途 |
| --- | --- | --- |
| `/` | `Navigation Home` | 产品导航首页 |
| `/plan` | `Plan Workspace` | 教材上传解析、断点续跑、计划生成、修订与历史管理 |
| `/study` | `Study Dialog` | 章节教学对话、PDF/图片投射预览与角色表现 |
| `/persona-spectrum` | `Persona Spectrum` | 人格槽位、人设卡生成与导入/导出 |
| `/scene-setup` | `Scene Setup` | 世界到教室的层级场景树与可复用节点编辑 |
| `/tavern` | `Tavern Workspace` | 多角色自由互动房间与调度恢复 |
| `/settings` | `Settings` | 模型 Provider、输出上限、超时与桌面密钥设置 |
| `/sensory-tools` | `Sensory Tools` | Planning / Study 模型工具开关配置 |
| `/model-usage` | `Model Usage` | Token 与调用统计审计及 CSV 导出 |
| `/manual` | `User Manual` | 应用内置操作手册 |

全局调试控制台为挂载在应用根部的 `Debug Overlay`（`apps/web/components/debug/debug-overlay.tsx`），不属于独立路由页面。

## 2. `Plan Workspace` 与 `Study Dialog` 区块名称

| 区块名 | 对应组件 / 位置 | 职责 |
| --- | --- | --- |
| `Hero Header` | `learning-workspace.tsx` 顶部横幅 | 页面标题、状态提示与快捷入口 |
| `Persona Selector` | `persona-selector.tsx` | 当前人格切换器 |
| `Study Column` | 主内容纵列容器 | 承载核心学习操作流 |
| `Document Setup Panel` | `document-setup.tsx` | 上传教材、设置目标/物理页范围/输出语言并触发生成 |
| `Document Checkpoint Panel` | `document-checkpoint-panel.tsx` | OCR 断点状态展示与显式续跑控制 |
| `Plan History Panel` | `plan-history.tsx` | 历史学习计划选择列表 |
| `Plan Overview Panel` | `plan-overview.tsx` | 当前计划标题、目标、摘要、今日任务与二级目录 |
| `Plan Revision Panel` | `plan-revision-panel.tsx` | 计划修订预览、差异对照、回滚与确认 |
| `Study Unit Revision Panel` | `study-unit-revision-panel.tsx` | 模型教材单元重划建议展示与接受/拒绝 |
| `Study Console` | `study-console.tsx` | 章节对话消息流、输入框、附件、交互题与跳页控制 |
| `Character Shell` | `character-shell.tsx` | 右侧角色表现容器（内含 `Character Event Snapshot` 事件预览区） |

## 3. `Tavern Workspace` 区块名称

| 区块名 | 职责 |
| --- | --- |
| `Tavern Header` | 页面标题、当前房间标题、新建与归档/恢复操作及状态 |
| `Tavern Session Panel` | 房间历史列表与分页切换 |
| `Tavern Setup Panel` | 角色多选、可选场景、房间标题与创建表单 |
| `Tavern Conversation Panel` | 按单调序号排列的用户/导演/角色/系统消息流 |
| `Participant Roster` | 房间阵容顺序、目标勾选与单角色生成状态 |
| `Interaction Composer` | 可见消息输入、可选下轮引导语、回复对象预览与发送/停止操作 |
| `Reliability Details` | 默认折叠的面向用户的 Harness 恢复摘要（原始 Trace 归调试面板） |

## 4. `Document Debug Console` 区块名称（位于全局 `Debug Overlay`）

- `Debug Hero Header`：顶部标题与当前状态提示
- `Document List Sidebar`：左侧文档选择器
- `Parse Summary Card`：解析摘要
- `Process Stream Panel`：流式处理反馈
- `Plan Stream Panel`：流式生成学习计划
- `Section Guess Panel`：章节猜测
- `Study Unit Cleanup Panel`：学习编排清洗结果
- `Planning Outline Panel`：计划输入目录
- `Planning Tools Panel`：计划工具与章节详情
- `Planning Trace Panel`：计划模型 Trace
- `Parse Warning Panel`：解析告警
- `Chunk Inspector Panel`：切块结果
- `Page Extraction Panel`：逐页抽取

## 5. 命名规则与核心数据术语

### 命名规则

- `Panel`：页面内独立内容卡片；
- `Header`：页面顶部横幅区域；
- `Sidebar`：仅指全局 `Document Debug Console` 内的左侧文档选择器；
- `Shell`：仅指角色表现容器（`Character Shell`），不用于普通学习卡片；
- `Study Unit`：清洗后的可规划学习单元；仅指代原始解析树或教材引用时才使用 `Section`。

### 核心数据术语

| 术语 | 含义 |
| --- | --- |
| `Document` | 上传的教材文件及其处理状态与元信息 |
| `Section` | 调试产物中由解析器检出的原始章节结构 |
| `Study Unit` | 由原始章节经编排清洗得到的可规划学习单元 |
| `Learning Plan` | 持久化的学习计划（含 `schedule` 与嵌套 `schedule_chapters`） |
| `Study Session` | 绑定单个 Document、Persona 与活动 Study Unit 的教学对话会话 |
| `Character Event` | 供角色表现层消费的结构化表演指令 |
| `Tavern Room` | 独立自由互动容器（含可选场景与角色快照） |
| `Tavern Participant` | 房间级不可变 Persona 快照与 `prompt_hash` |
| `Tavern Message` | 房间内单调递增序号的仅追加归属消息 |
| `Tavern Run` | 幂等、带修订号校验的生成尝试（含调度表、步骤、上下文摘要与 Trace） |
| `Tavern Speaker Step` | 单个计划内角色尝试（含状态与 reply anchor） |
| `Harness Trace` | 跨工作流通用的校验、修复与提交证据 |
