# 工程机制与约定

本文汇集跨模块的工程约束与边界约定，作为 [AGENTS.md](../AGENTS.md) 核心铁律的展开说明。

## 1. 契约与数据分层

- **前后端契约同步**：新增或修改后端路由与响应结构时，同步更新对应后端模型（如 `models/api.py`、`models/tavern.py`）、`packages/shared/src/`、前端域 API 与严格解码器（`apps/web/lib/api/*.ts`、`apps/web/lib/data/*.ts`、`apps/web/lib/*-decode.ts`），并运行 `npm run gen:api-reference`。
- **单一兜底归属层**：遵循 [数据流分层与兜底责任](data-flow-layers.md)——外部未知形状只在 `services/ai/app/core/coerce.py` 归一化；域模型保持 strict；前端解码器只校验形状，不发明语义默认值。
- **组件契约版本语义**：应用组件契约版本标识经过评审的算法行为，而非依赖包版本或模型名。未经评审的组件登记为 `null` 并阻止构造上下文，不得使用 `pending-*`、`latest`、`unknown` 或包版本号充当采用证据。
- **独立词汇表**：严格区分 `HarnessStage`（领域操作，如 `page_extraction` 或单个规划工具执行）、`HarnessAttemptPhase`（阶段内的 `generate`/`decode`/`validate`/`repair`/`commit`/`rollback`）与流式进度事件名（如 `page_parsed`）。Python/TypeScript 注册表与共享 golden fixture 保持原子一致。

## 2. Harness 生命周期与身份

- **全仓库统一生命周期**：所有模型或启发式工作流遵循 `typed input → versioned context → strict decode → invariant validation → bounded recovery → atomic commit → trace`。
- **受控上下文构造**：v3 上下文只能由已准入的 `HarnessOperationBindingV1` 与可执行 `HarnessWorkflowManifestV1` 条目构造；清单登记或测试夹具仅为路由/配置证据，不代表生产采用。
- **操作身份分配**：Harness 身份与领域操作准入在同一数据库事务内分配；不得从 provider `tool_call_id` 推导，不得为历史行捏造；若产品留存策略清理了领域行，不可变绑定记录保留为准入墓碑。
- **受保护内容授权**：`HarnessSafeManifest` 仅对显式审查过的无敏感内容 DTO 计算摘要；用户输入、教材、Prompt、对话记录必须置于授权制品解析器之后。制品授权绑定服务端解析的本地安装主体（principal）与精确的 operation/artifact/contract/permission 范围，不是可传递的 bearer token；SHA-256 仅证明完整性，不证明保密性或可重放性；Python 为规范摘要权威。
- **强类型持久效果**：每个持久效果通过单一已准入 Harness 操作与全局槽位（slot）获得稳定日志身份，绑定不可变的 adapter/contract/target，使用数据库时钟认领围栏，并在产出终态前要求精确读回或补偿证据；不支持读回的外部 Provider 效果保持 `uncertain`。
- **统一工具清单**：版本化 `Tool Manifest` 是全部 6 个 Planning 工具与 32 个 Study 工具的唯一目录；Provider Schema、输入/结果适配器、脱敏 Trace 投影、调用上限与 Provider ID 关联必须与共享 golden fixture 保持一致。
- **运行时与历史兼容**：`HarnessOperationRuntime` 拥有持久化围栏的 v3 生命周期状态。v1/v2 历史证据保持只读兼容；历史恢复迁移仅做 fail-closed 投影，需要真实准入绑定与既有 v3 trace attempt。

## 3. 提案、提交与所有权

- **提案与提交严格分离**：模型或启发式提案必须使用领域自有的 proposal schema，不得包含系统生成的 ID、身份、顺序、修订号、时间戳或已提交副作用。
- **精确提交证据**：v3 提交声明必须匹配已注册的完整 operation key 与版本化 committed projection，通用资源证据不足以宣称提交成功。
- **Tavern 主输出边界**：Tavern 角色消息与服务端私有操作/效果回执元数据原子持久化（不暴露于公开 API/OpenAPI）；`get_actor_commit_read_back` 在同一数据库快照内校验 Message/Run/Step/Participant/reply-anchor；其提交策略为 `primary_output_only`，仅证明单条主消息，不证明事务中的全部 Room/Run/Step 副作用。
- **Study Session 状态所有权**：Session revision 与 Turn sequence 是应用拥有的已提交状态，不得进入模型提案；Session CAS 属于并发基础设施，不等同于持久化请求准入或 Harness 提交证据。
- **交互题服务端隔离**：交互题的模型提案、私有评分规格、公开题面、已提交结果与 Turn 绑定作答输入五者严格分离；未作答前评分材料仅存服务端，浏览器只渲染持久化 Session 读回。

## 4. 持久化与写边界

- **先修写边界再宣称采用**：Study 遵循并发安全追加 → 操作准入/回执 → 强类型效果契约 → 效果提交/暂存 → v3 trace；Document 与 Planning 拥有持久化准入、原子提交投影与 v3 生命周期证据；Scene 保持模型提案、用户保存、已提交投影与 API DTO 四层分离。
- **禁用集合覆写**：Documents、Learning Plans、Study Sessions 与 Tavern 均走各自 Repository 的行级写入与 revision CAS，不走集合级 `LocalJsonStore.save_list`。

## 5. 前端界面与文档组织

- **三大界面职责隔离**：保持**学习 UI**、**角色表现层（Character Shell）**与**调试控制台（Debug Overlay）**三者解耦，不互相混用状态或布局。
- **独立复核**：面向用户体验或可靠性的关键问题在闭环前需做独立场景复核，不只依赖单条正常路径测试。
- **文档归位**：细节设计与规范按主题维护在 `docs/` 中，保持根目录 `README.md` 与 `AGENTS.md` 精炼。
