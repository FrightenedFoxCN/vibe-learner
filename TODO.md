# TODO

## 酒馆与角色可靠性

- [x] `TAV-001` 建立独立 Tavern Room / Participant / Message / Run 规范化 schema；验收：Alembic 迁移存在，SQLite schema 测试通过，消息序号与 run 幂等键具备唯一约束。
- [x] `TAV-002` 完成 Tavern CRUD 与 direct 单角色闭环；验收：创建、恢复、归档、直聊 API 集成测试通过。
- [x] `TAV-003` 完成 facilitated 多角色顺序互动与剩余角色 child retry；验收：服务器按 roster 固化顺序、每位目标至多发言一次、逐角色落盘、部分失败保留、重试不重复已完成角色。
- [ ] `TAV-004` 增加 pending/generating run 超时接管、停止与取消；验收：进程中断后不会永久锁房间，已完成消息不重放，接管与原 worker 通过 CAS 竞争。
- [x] `HRN-001` 实现 Tavern 专用 persona compiler 与 strict ActorReply；验收：任意闲聊不被拉回教材，模型不能决定 speaker/sequence。
- [ ] `HRN-002` 建立身份、称呼、目标、跨角色冒充和 prompt injection 回归矩阵；验收：测试记录 schema-valid rate、repair rate 与身份一致率。
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
- [ ] `HRN-DOC-001` 将解析/OCR/清洗阶段接入通用 trace；验收：每阶段版本、检查项、恢复策略和耗时可回放。
- [ ] `HRN-PLAN-001` 将计划 schema、工具调用和持久化接入 validate/repair/commit；验收：模型副作用在校验前不提交，trace 可用于 fixture replay。
- [ ] `HRN-STUDY-001` 将学习对话工具写操作改为 effect proposal；验收：最终回复失败时记忆、好感、follow-up、场景均不发生半提交。
- [ ] `HRN-WEB-001` 建立前端 runtime decoder、超时/取消和 stale response harness；验收：缺字段、乱序和重复响应均有确定降级路径。
- [ ] `HRN-EVAL-001` 建立跨工作流 fixture/eval 运行器与版本基线；验收：解析、计划、人格/场景、Study Chat、Tavern、前端解码分别报告通过率、修复率、失败率和 p95。
- [ ] `HRN-CTX-001` 统一跨工作流 context envelope；验收：解析器版本、计划工具集、人格/场景快照、Study Session revision、Tavern roster/policy 与前端请求序列均生成可比较的版本化 digest。

- [ ] `AUD-001` 修复 Study Session 并发追加丢消息；验收：两个并发 append 均保留且序号唯一。
- [ ] `QG-001` 替换 Next 16 已失效的 `next lint`，统一 `check` 命令并接入发布工作流。
- [x] `QG-TAV-API-001` 为 Tavern direct/facilitated、continue、partial、retry、幂等与 SQLite 升级增加 HTTP/仓储集成测试。
- [ ] `QG-002` 为 Tavern 增加共享 runtime decoder 测试与关键前端交互测试。
- [ ] `SEC-001` 为聊天附件增加 session ID 校验、单文件/总字节上限和先鉴权后落盘顺序。

## 性能与文档

- [ ] `PERF-001` 将完整 Learning Workspace Provider 从无关页面下沉；验收：404/设置页不再加载学习工作台数据，首屏 gzip 不回退超过 5%。
- [ ] `PERF-002` 延迟导入 LiteLLM/OCR 重依赖；验收：mock 模式 `/health` 冷启动小于 2 秒。
- [ ] `DOC-001` 对齐 68 个现有业务路由、SQLite/PostgreSQL 默认说明和当前页面入口。
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
