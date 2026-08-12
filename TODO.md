# TODO

## 酒馆与角色可靠性

完成 Tavern 的 Harness 项不代表其他工作流已接入 Harness；全链路状态以“审计与质量门”及 `docs/harness-schema-ownership.md` 为准。

- [x] `TAV-001` 建立独立 Tavern Room / Participant / Message / Run 规范化 schema；验收：Alembic 迁移存在，SQLite schema 测试通过，消息序号与 run 幂等键具备唯一约束。
- [x] `TAV-002` 完成 Tavern CRUD 与 direct 单角色闭环；验收：创建、恢复、归档、直聊 API 集成测试通过。
- [x] `TAV-003` 完成 facilitated 多角色顺序互动与剩余角色 child retry；验收：服务器按 roster 固化顺序、每位目标至多发言一次、逐角色落盘、部分失败保留、重试不重复已完成角色。
- [ ] `TAV-004` 增加 pending/generating run 超时接管、停止与取消；验收：进程中断后不会永久锁房间，已完成消息不重放，接管与原 worker 通过 CAS 竞争。
- [x] `HRN-TAV-001` 实现 Tavern 专用 persona compiler 与 strict ActorReply；验收：任意闲聊不被拉回教材，模型不能决定 speaker/sequence。
- [ ] `HRN-TAV-002` 建立身份、称呼、目标、跨角色冒充和 prompt injection 回归矩阵；验收：测试记录 schema-valid rate、repair rate 与身份一致率。
- [ ] `HRN-TAV-PERF-001` 为 Tavern prompt 增加字符/token 总预算、场景快照尺寸和嵌套深度限制；验收：最坏 6 人长对话仍在配置预算内，截断/摘要写入 trace。
- [ ] `SCH-TAV-001` 决定并实现 run/message/step 软引用策略；验收：`run_id`、`message_id`、`reply_to_message_id` 要么具备可迁移外键与插入顺序，要么由统一 invariant scanner 检测并阻断破损图。
- [ ] `UX-001` 新增 Tavern Workspace（发布前置：`TAV-004`）；验收：空状态、1–6 人选择、单聊、多人讨论、tail 向上翻页、刷新恢复、IME Enter 和 390px 移动视口通过独立人工检查。
- [ ] `UX-TAV-REC-001` 建立 Tavern run 派生恢复视图；验收：父 run 保持 immutable partial，但存在 completed child 时显示“已由重试恢复”，不再次暴露可重试操作。
- [ ] `TAV-RECOVERY-CLIENT-001` 前端 API client 自动执行 Tavern `502` 同 key 终态恢复；验收：保留原 revision/key，按 `run.status` 归一化 completed/partial/failed，不把 HTTP 200 等同成功完成。
- [ ] `TAV-RUN-VIEW-001` 增加可靠的 retry-chain 聚合读取；验收：单次读取不会因 run list 分页截断而遗漏 child，latest leaf 决定可恢复动作。
- [ ] `TAV-ERROR-001` Tavern 冲突/执行失败改用结构化错误 envelope；验收：code、run/child ID、current revision 与 recovery action 可直接 decode，前端不解析冒号字符串。
- [ ] `TAV-UX-COPY-001` 固化 pending/generating/completed/partial/failed/blocked/retry/stale/archived 中文文案；验收：blocked 不显示为角色失败，raw code 只进入 Reliability Details/debug。

## 审计与质量门

- [x] `HRN-CORE-001` 建立跨工作流 HarnessTrace 契约与生命周期文档；验收：Python/TypeScript schema 对齐，Tavern 只持有领域 policy、不私有化通用 trace。
- [x] `SCH-HRN-001` 建立跨工作流 schema/所有权基础与 v2 证据契约；验收：input/proposal/committed/API 角色有目录，v1 保持可读且不伪造证据，v2 具备 operation/trace identity、独立版本、attempt、SHA-256 digest、commit/rollback evidence，Python/TypeScript nullability 对齐并有 fixtures。
- [x] `HRN-CTX-BASE-001` 建立 v3 workflow-neutral context foundation；验收：v2 wire/fixtures 原样可读，v3 具备闭集 workflow/stage/resource/artifact、服务端 operation ID、`(workflow, stage)` 组件注册表、严格 trace-safe manifest allowlist、契约绑定 digest、自校验 context digest 和 Python/TypeScript golden fixtures。该项只证明 context identity 与 integrity reference，不代表任一业务工作流已接入或可重放。
- [ ] `HRN-CTX-ARTIFACT-001` 建立受保护 artifact resolver；验收：不可变 opaque ID、artifact/type/contract 注册、先鉴权后读取、留存与过期规则、read-back digest，返回 `resolved/not_found/expired/forbidden/digest_mismatch/schema_unsupported` 等 typed result，并覆盖删除、篡改、跨主体访问和批量解析预算。现有 `document_debug` / `planning_trace` 可清理缓存不得冒充永久 replay artifact。
- [ ] `HRN-CTX-PERF-001` 为 context build/digest/resolve 建立预算；验收：限制 manifest canonical bytes、单/总 snapshot bytes、引用数量和 resolver I/O，最坏 fixture 记录 p50/p95，超限在模型/worker 执行前失败。
- [ ] `HRN-CTX-001` 将 v3 context/trace lifecycle 接入全部工作流（依赖 `HRN-CTX-BASE-001`、`HRN-CTX-ARTIFACT-001`，其他 HRN 流程依赖本项）；验收：真实版本化 parser/heuristic/toolset/compiler/decoder，受保护 snapshot refs 可解析并校验，敏感原文不入 trace，失败与 commit evidence 完整。仅在各业务迁移全部完成后关闭。
- [ ] `HRN-RECOVERY-MIG-001` 统一旧 `ModelRecoveryRecord`、Planning round recovery 与 v3 attempt/check 的映射（依赖 `HRN-CTX-001`，Plan/Persona/Scene/Study/Tavern v3 接入依赖本项）；验收：同一 operation 可关联，旧 API 保持兼容，新指标不重复计数，并有明确弃用路径。
- [ ] `AUD-001` 修复 Study Session 并发追加丢消息（`HRN-STUDY-001` 发布前置）；验收：两个并发 append 均保留且序号唯一。
- [ ] `HRN-DOC-001` 将 extraction/OCR/Section/Chunk/Study Unit cleanup 接入 v3；验收：各 stage 记录 parser/heuristic 版本、页覆盖/边界/排序/source-ID/密度预算 invariant，任意阶段失败都写终态 evidence，document 与 debug 原子提交或可恢复且 forced-OCR fixture 可回放。
- [ ] `HRN-PLAN-001` 将计划 proposal、工具调用和跨聚合持久化接入 validate/repair/commit；验收：工具参数与 plan proposal 严格解码，ID 由应用分配，document/debug/plan/trace 原子提交或 staging 可恢复，具备 idempotency/revision 与 commit-failure fixtures。
- [ ] `HRN-PERSONA-001` 建立 Persona 生成 Harness；验收：严格 proposal 不含应用 ID/source/time，slot/身份/称呼 invariant、版本化 prompt/context、失败零持久化和 fixture replay 通过。
- [ ] `HRN-SCENE-001` 建立 Scene 生成 Harness；验收：model proposal 不含 layer/object/reuse ID，递归深度/节点数/唯一 ID/selected path invariant、失败零持久化和 fixture replay 通过。
- [ ] `HRN-STUDY-001` 将学习对话写操作改为 typed effect proposal；验收：memory、affinity、follow-up 创建/取消、scene、projected PDF/overlay、plan confirmation 与 turn append 在严格最终回复校验后以单事务/CAS提交，失败、重复请求或并发请求均无半提交。
- [ ] `HRN-TAV-V3-001` 将 Tavern 生产证据从 v1 切换到 v3（依赖 `HRN-CTX-001`、`HRN-RECOVERY-MIG-001`）；验收：旧 v1/v2 可读，run/step/message 产生 v3，actor parent lineage、partial/failed/not-committed、per-step commit 与 child retry trace 可聚合，前端 v1/v2/v3 fixtures 通过。
- [ ] `HRN-WEB-001` 建立前端 `unknown -> value | typed DecodeError` runtime decoder、结构化错误、超时/取消和 stale response harness；验收：Document/Plan/Persona/Scene/Study/Tavern 的缺字段、非法 enum/null、NaN、乱序、重复与 same-key 恢复均有确定路径并转发 v1/v2/v3 trace。Python 后端仍是 canonical digest authority，浏览器不得用 `JSON.stringify` 伪装同构 digest。
- [ ] `HRN-EVAL-001` 建立跨工作流 fixture/eval 运行器与版本基线；验收：覆盖 malformed、boundary、retry exhaustion、duplicate、concurrency、commit failure，报告 schema-valid/repair/failure/commit-consistency/p95，并由各 workflow 注册最低 accuracy 指标（OCR 文本/覆盖、Section/Study Unit 边界、plan grounding/tool correctness、Persona/Tavern identity、Scene 结构、Study citation/effect correctness、frontend decode），用版本化基线和回退阈值使 CI 失败。
- [ ] `QG-001` 替换 Next 16 已失效的 `next lint`，统一 `check` 命令并接入发布工作流。
- [x] `QG-TAV-API-001` 为 Tavern direct/facilitated、continue、partial、retry、幂等与 SQLite 升级增加 HTTP/仓储集成测试。
- [ ] `QG-002` 为跨 Document/Plan/Persona/Scene/Study/Tavern 响应增加共享 runtime decoder fixtures，并为 Tavern 增加关键前端交互测试。
- [ ] `SEC-001` 为聊天附件增加 session ID 校验、单文件/总字节上限和先鉴权后落盘顺序。
- [ ] `UX-NAV-001` 重构顶级导航信息架构与 390px 行为；验收：学习、角色与世界、系统分组清晰，加入 Tavern 后标签不压缩或横向溢出，键盘/触控目标可达。
- [ ] `UX-A11Y-001` 为跨页面异步状态补齐 `aria-live` / `role=alert`、焦点恢复和最小 44px 交互目标。
- [ ] `UX-EMPTY-001` 统一空状态的下一步动作；验收：Tavern 无房间/无 persona 时不出现不可操作的禁用 composer 死端。

## 性能与文档

- [ ] `PERF-001` 将完整 Learning Workspace Provider 从无关页面下沉；验收：404/设置页不再加载学习工作台数据，首屏 gzip 不回退超过 5%。
- [ ] `PERF-002` 延迟导入 LiteLLM/OCR 重依赖；验收：mock 模式 `/health` 冷启动小于 2 秒。
- [ ] `DOC-001` 对齐 68 个现有业务路由、SQLite/PostgreSQL 默认说明和当前页面入口。
- [ ] `DOC-003` 修正 `docs/architecture.md` 的旧 `/debug` 页面、PostgreSQL-only/no-database 矛盾，并补齐 Tavern/Harness/Persona/Scene 当前边界；验收：与代码和根 `AGENTS.md` 一致。
- [x] `DOC-002` 更新根 `AGENTS.md` 的仓库快照、Tavern 术语、测试命令与已知风险。

## 计划创建模块

- [ ] 允许模型逐步修改计划，而非一次性完成生成；
- [ ] 压缩计划生成的轮次，鼓励模型进行并行的工具调用；

## 预期优化

- [x] UI：重组一些比较混乱的页面的 UI；
- [ ] debug：调试页面重接；
- [ ] 工具清理和 Prompt 优化：整理一下现有的工具，结构有点混乱；
- [ ] 审计并鼓励真正的工具调用；
- [ ] 启动速度优化；
- [ ] 蒸馏有用的 skills.md 并搭载；
- [ ] 写一个完善的使用文档和功能介绍；

## 未来优化

- [ ] Rust 重写：见新分支；
- [ ] 根据人格和场景设置进行 ui 的动态调整，更多 ui 主题；
- [ ] Live2D 支持和 TTS：这个很麻烦，以后再说；
