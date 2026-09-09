# Wave 4/5 联合验收记录 · 2026-09-09

后续修复与桌面实测见 [remediation.md](remediation.md)：原始两个失败项已通过复测，并修复 Planning 恢复快照和 Unix sidecar 退出清理。本文件保留首次验收的原始结论，不覆盖历史失败。

**结论：不通过，保留联合验收门。** 本轮真实调用 MiniMax M3，发现 Study 工具装配阻断和纯目标计划失败；本地性能门通过，但不能据此关闭全部 Wave 4/5。

基线：`d48c20a9fd881bac233704249aeb266cc4b3e232`。开始时已有桌面 icon、Next 生成声明文件改动和本目录的五个未提交脚本。本轮复核、扩展验收脚本并新增证据，未修改产品实现。所有模型输入均为合成教材、目标、人物和场景。真实服务使用临时 SQLite `/tmp/wave45-acceptance-m3-live/acceptance.db`，未更改用户运行配置或 Vault。

## 结果矩阵

| 验收项 | 实际结果 | 判定与范围 |
|---|---|---|
| 完整发布门 | `npm run check:release` 成功；528 后端测试，163 前端测试通过、2 个可选 live 测试跳过；共享/type、3 个 PR eval、Web build 成功 | 回归门通过，不替代独立 live 验收 |
| Wave 5 本地性能 | 各项 30 个原始样本，所有 timing/token/byte/SQL/correctness 门通过 | 本地性能复测通过 |
| Document | 合成三页 PDF 上传、处理、Debug、Planning Context、事件报告成功；父 trace `passed/committed` | 文本 PDF 路径通过；不覆盖扫描 PDF/OCR 与所有最大输入组合 |
| 教材 Planning | M3 生成成功，持久化回读成功，v3 `passed/committed` | 本次成功路径通过 |
| 纯目标 Planning | HTTP 200，末事件为 `stream_error`；502 `plan_model_invalid_payload`，终态 `not_committed` | 失败；不能按 HTTP 状态算成功 |
| Persona | M3 生成两个人物，v3 `passed/not_applicable` | 提案路径通过；未覆盖所有 slot/assist/保存路径 |
| Scene | M3 生成两层场景，v3 `passed/not_applicable`；非法 layer_count=9 返回 422，场景库前后相同 | 提案及输入拒绝路径通过 |
| Study Chat | HTTP 200，receipt 为 `uncertain`、`safe_to_retry=false`、result=null；查询回读仍未提交 | 失败，见 A01 |
| Tavern 真实 HTTP | 六人名册，按 4+2 两轮生成；反序提交目标仍按服务器名册排序；两轮均 completed；相同请求返回同一 run | 本次正常生成与幂等回读通过 |
| Tavern 长历史 | 独立生产服务调用，六人、40×8000 字符历史，两轮均 completed；6 个 committed v3 trace | 小样本通过；2/6 角色有修复，详见性能数据 |
| 前端独立 wire | Document/Debug/Context/Plan/Persona/Scene/事件报告共 7 项通过；4 个未知 trace 版本注入全部拒绝 | 已采样路径通过 |
| 现有 live-wire 门 | Tavern 通过；Study 在断言 committed 时失败；两个测试均未跳过 | 联合 live-wire 门失败 |
| 浏览器 | Navigation Home、Plan Workspace、Study Dialog、Tavern Workspace 与展开的 Reliability Details 可读取 | 使用已有 13045 前端，界面明确显示本地模拟；不计为 M3 浏览器测试 |
| 桌面 | 已安装 Vibe Learner 启动并显示 `setup-required` / Vault 已锁定 | 仅启动检查；未解锁，未核验安装包与本次 commit 一致，完整桌面门仍开放 |

## A01 · P1 · Study 工具目录漂移导致真实对话无法生成

复现：真实 M3 后端，先创建教材计划，再创建关联 Study Session，发送 “Explain a basis in one paragraph.”。请求约 150 ms 返回 `uncertain`。数据库终态 trace 的真实错误是 `study_tool_description_manifest_mismatch`；路由日志的外层错误为 `harness_runtime_prepare_output_invalid`。

`services/ai/app/services/model_provider.py` 的 `_chat_tools` 比较 `TOOL_CATALOG` 与 Tool Manifest 的 provider description，并在不等时直接抛错。独立只读比较发现 10 项不一致：read_learning_plan_progress、update_learning_plan、update_learning_plan_progress、generate_projected_image、read_projected_pdf_content、read_projected_pdf_images、focus_projected_pdf_page、annotate_projected_pdf_region、clear_projected_pdf_overlays、annotate_projected_image_region。

本例在工具 schema 装配阶段失败，未进行该 Study 请求的模型生成。公开 receipt 却进入不可自动重试的 uncertain，因此还需复核“已知调用前失败”向操作终态的映射。这里没有将其误写为上游 M3 错误。修复应统一目录/manifest 契约并补真实工具装配覆盖，不能删除 fail-closed 校验来让测试通过。

证据：[catalog-audit.json](catalog-audit.json)、[chat receipt](live-wire/chat.json)、[回读](live-wire/chat_readback.json)、[runtime-evidence.json](runtime-evidence.json)、[live-decode.log](live-decode.log)。可使用 `audit_catalog.py` 在 `services/ai` 下以 `PYTHONPATH=.` 运行，零 provider 调用独立复现描述漂移。

## A02 · P2 · 纯目标计划实测未生成有效结果

输入 “Learn introductory algebra.”，空 document_id。流最终以 `plan_proposal_invariant_failed:schedule_chapters.0.source_section_ids:unknown_ref` 失败，终态 not_committed。未知引用被正确拦截，但本次真实模型兼容性/成功路径验收未通过。一次失败不能推断普遍失败率，也尚不能单凭该错误确定是 prompt、工具上下文还是模型输出问题。

证据：[完整事件流](live-wire/goal_plan_stream.json)。原验收脚本仅检查部分 HTTP 状态，本轮补充 `outcomes.json` 和终态判断，防止把流式 HTTP 200 当作业务成功。未为获得绿灯重复抽样。

## Wave 5 数据

本地 p95（ms）：runtime 13.27；单快照 1.25；8 快照批处理 5.37（逐个事务 9.44）；64 快照批处理 38.07（逐个事务 88.92）；Tavern preflight/tokenizer 227.65。Planning 保持串行，before/after p95 0.104/0.091 ms 是同一串行实现的采样差异，不构成并行提速证据。原始样本、环境、源文件哈希和预算保存在 [local-benchmark.json](local-benchmark.json)。完整发布门也复跑了现有预算和授权对抗回归；本轮未新增覆盖所有最大输入组合的独立对抗矩阵。

真实 provider：`https://api.minimax.cn/v1`，环境变量 `K3_API_KEY`；模型发现与实际返回模型均为 `MiniMax-M3`。长历史测试 temperature=0.35、max_tokens=2048、timeout=60s、thinking 使用 provider 默认值。跨领域 HTTP 服务 setting/chat max_tokens=4096、timeout=90s、联网检索关闭。

长历史六角色统计：

- 8 次上游请求，HTTP/transport 错误 0；6/6 角色完成，2/6 角色经 `retry_strict_actor_reply` 有界恢复，样本修复率 33.3%，终态失败率 0%。
- prompt 130,999 tokens，completion 3,671 tokens，合计 134,670 tokens。
- 请求 p50 7.86s，样本 p95 20.65s；两轮端到端约 61.38s / 24.71s。
- 对原请求进行回读重放，新增 provider 请求数均为 0。
- 服务器每轮最多支持四个目标，所以是六人名册、4+2 两轮，不是一次六角色 run。生产上下文已先行选择历史；首次 provider preflight 仅含约 24 KiB transcript、removed_message_count=0，不能声称 40 条全量历史均发送给了模型。

另外，跨领域 HTTP 服务记录 18 条 M3 usage：Planning 7 条/32,117 tokens，Setting 3 条/10,645 tokens，Chat（本例为 Tavern 调用）8 条/18,217 tokens。与长历史测试合计为 195,649 个 provider-reported tokens。usage 记录不等于账户账单；**实际费用未核验**，不编造金额。

样本很小，且只含一种 provider/model；本轮没有可信总体 p95、普遍质量/失败率或最大支持输入组合的验收结论。原始 [live-tavern.json](live-tavern.json)、[live-metrics.json](live-metrics.json)、[live-http-usage.json](live-http-usage.json) 均保留。

## 后续关闭条件

1. 修复 A01 并独立复测真实 Study 工具装配、提交和失败分类，跑通未跳过的 Study live-wire 门。
2. 复核 A02 的目标计划引用契约，增加固定输入的成功与故障样本，保留全部失败证据。
3. 完成连接真实后端的浏览器交互、当前构建的桌面流程、OCR/故障/恢复/保护回放与尚未注册 suite 的采用门；本轮有限成功样本不能代替这些门。
4. 明确六角色验收与现有单轮四目标上限的关系，补代表性样本量、最大输入组合及实际费用证据。

本轮执行的是验收而非产品修复；未关闭 roadmap checkbox 所代表的独立采用/验收门。
