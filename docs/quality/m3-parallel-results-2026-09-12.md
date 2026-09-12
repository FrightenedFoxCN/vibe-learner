# MiniMax-M3 并行实验总记录与生产更新交接

日期：2026-09-12。用户本次明确授权后，完成首日优先的引用、原文/摘要写入、跨会话事件三条研究线，并完善独立实验 infra。**共 284 个真实样本、698 次 M3 HTTP 200 请求、3,952,533 provider reported total tokens；另保留 32 个 DNS 受阻样本。实际 wire 峰值为 4。**

最有价值的候选是原文来源绑定：在 24 份新来源上通过 24/24，而同条件模型重写 baseline 为 19/24。引用词法候选改善了本组来源选择，但不能据此认定整体引用蕴含或生产质量通过。30 个事件场景的现有检索已覆盖预设证据锚点，oracle 没有证明新的检索收益。摘要实验先暴露字段口径含糊，明确字段定义后两臂均为 8/8，不支持采用额外提示候选。

**生产代码、数据库迁移、默认模型设置均未修改。** 下述是研究结果与待审采用建议，不是发布许可。独立人工、正式留出、原 SDK transport、真实前端及适用平台验收仍未完成；MQ 质量票保持开放。

## 交付入口

- [完整证据包](evidence/m3-priority-lanes-2026-09-12/evidence.zip)：全部 7 个 campaign 的原 manifest/report、316 份样本领域记录、累计账本、实验源码；主混合批与两个摘要批附执行时源码快照。
- [交付清单与校验](evidence/m3-priority-lanes-2026-09-12/delivery.json)：包及文件摘要、覆盖审计、测试结果、域身份隔离、恢复和累计成本核对。
- [主混合批机器审核](evidence/m3-priority-lanes-2026-09-12/mixed-audit.json)、[来源选择重放](evidence/m3-priority-lanes-2026-09-12/citation-selection-replay.json)。
- [辅助事实复核](evidence/m3-priority-lanes-2026-09-12/assisted-fact-review.json)：108 份回答逐项核对；由本任务的 Codex 助手进行、非盲、非独立，不作为正式 judge 或留出认证。
- [摘要原批](evidence/m3-priority-lanes-2026-09-12/summary-v1-audit.json)、[字段校准后批次](evidence/m3-priority-lanes-2026-09-12/summary-v2-audit.json)、[评分口径修正记录](evidence/m3-priority-lanes-2026-09-12/data-calibration.json)。
- [先行记忆/接口诊断全文](m3-parallel-memory-results-2026-09-12.md)、[本地 JSON 解码机制诊断](evidence/m3-priority-lanes-2026-09-12/decoder-format-diagnostic.json)。
- [运行器使用与复现命令](../../tools/model-quality/README.md)、[原并行计划](m3-parallel-exploration-2026-09-12.md)、[唯一质量待办](TODO.md)。

## 环境、配置与隔离

所有模型请求只发往 `https://api.minimax.cn/v1/chat/completions`，仅从环境 `K3_API_KEY` 读取认证；698 次响应的 model 均为 `MiniMax-M3`。没有写入密钥、修改 `.env` 或访问生产数据。另有一次不带认证的根 URL 连通性检查返回 HTTP 404，它不是模型推理请求。

运行环境为本机 macOS、服务自己的 uv/Python 3.12 环境、`LITELLM_LOCAL_MODEL_COST_MAP=True`；uv cache 定向到可写临时目录。Python/依赖版本、锁文件摘要、Git revision、dirty digest、完整 app/adapter 源码摘要以每批 manifest 为准。服务网络 SDK 入口由实验 native bridge 替换；不能据此宣称原 LiteLLM/SDK 路径已等价验证。

每个 case/variant/repetition 使用新 spawn 进程、独立 SQLite、storage、Document、Session。真实 Document process → Study Chat admission → proposal/严格 decode → effect/Session commit → receipt → read-back → 新容器重启读回。Harness operation identity 均从实际 domain admission 获取，研究 sample hash 不充当领域身份。

主混合批有 78 个来源/场景：引用 24、事件 30、原文 24，各做 baseline/candidate 配对，共 156 个样本；单调度器按 seed 912 打乱 block 并交错条件，共享最多 4 worker 和 4 wire 在途。同一事件样本的两次 seed 与最终 query 保持顺序，每次 seed 均提交实际 Turn；不跨样本复用数据库或答案。120 个 seed operation 全部提交并读回，128 次 seed wire 全部计费入账。

共用 60 RPM、4M 保守预留 TPM、100,000 输入预留、60 秒 wire timeout；主混合批最多 12 wire/sample、600 秒 sample deadline，摘要批最多 8 wire/sample、300 秒 deadline。主混合批与摘要批均为 adaptive thinking、4,096 输出上限、temperature 0.1。先行诊断中有 disabled/2,048 条件，必须按其独立 manifest 解读，不能混为同配置对照。预留不是实际输入 token 数；seed 不代表模型支持采样 seed。

## 实验流水账

下列时间为 UTC；北京时间为 UTC+8。失败、不确定和测量修正前的批次全部保留。

| Campaign | UTC 请求窗口 | 样本 | 模型 wire | reported tokens | 说明 |
| --- | --- | ---: | ---: | ---: | --- |
| `m3-memory-pairs-20260912-v1` | 06:56:27–06:56:47 | 32 | 无 HTTP 响应 | unknown | 沙箱 DNS 受阻，32 次预留共 3,265,536，非模型质量失败 |
| `m3-memory-pairs-20260912-v2` | 06:57:51–06:58:59 | 32 | 44 | 234,938 | 指令对照；4 个严格联合通过 |
| `m3-memory-policy-20260912-v1` | 07:00:50–07:03:21 | 48 | 92 | 521,969 | thinking/首轮指定工具对照；10 通过、1 uncertain |
| `m3-memory-shape-20260912-v1` | 07:06:03–07:07:29 | 16 | 50 | 296,778 | 原生 index envelope 诊断；10 通过、1 uncertain |
| `m3-priority-mixed-20260912-v1` | 07:44:19–07:56:22 | 156 | 424 | 2,353,010 | 三条优先 lane 混合并行；49 联合通过、9 uncertain |
| `m3-summary-facts-20260912-v1` | 08:00:46–08:02:24 | 16 | 40 | 250,860 | 摘要初始定义；9 联合通过、1 uncertain，含口径问题 |
| `m3-summary-facts-20260912-v2` | 08:05:46–08:07:05 | 16 | 48 | 294,978 | 明确每个字段含义；16/16 通过，复用来源故不称独立确认 |

真实样本终态合计：98 completed、174 candidate_failed、12 uncertain。各 lane 的 rubric 不同且经历数据校准，**不能把该合计换算为一个通用模型质量分数**。12 个 uncertain 均有 `study_chat_uncertain_chat_model_invalid_payload`，没有新增 HTTP 429/529 或 usage 缺失；操作不确定性不等于网络失败。

复用此前账本 `tools/model-quality/runs/m3-window-20260912.sqlite3`。原窗口 512 次 / 674,112 charged-or-reserved；本轮增加 730 次账本尝试，其中 698 次已知模型请求、32 次 DNS 未知预留。最终窗口 **1,242 次 / 7,892,181 charged-or-reserved、0 在途**。全窗口保留 33 次未知 usage（本轮 DNS 32 次加历史 429 1 次），不释放未知预留或重置旧开销。供应商计费金额、token 权重与赠送额度计量仍未知；这是操作性预算，不是供应商账单或 2G 硬上限认证。

## L1：引用与来源选择

24 个单页来源/问题对，中英法各 8：每语言 4 个相关、4 个无关。无关题明确标注当前材料无关，属于容易判定的开发样本；不是复杂多页检索或隐含蕴含基准。

候选仅在 citation selector 内使用 NFKC/casefold、英文/法文停用词及中文 bigram；没有修改全局 persona slot tokenizer。模型上下文、问题和预算相同，selector 在生成之后投影引用。

| 指标 | baseline | normalized 候选 |
| --- | ---: | ---: |
| 离线重放：相关来源命中 | 8/12 | 12/12 |
| 离线重放：无关问题正确不引用 | 5/12 | 12/12 |
| 已提交回答：相关来源命中 / 有效相关回答 | 7/11 | 11/11 |
| 已提交回答：无关引用次数 | 6 | 0 |
| 已提交回答：正确不引用 / 有效无关回答 | 5/11 | 10/10 |
| 未提交、引用指标 unavailable | 2 | 3 |

重放从冻结 DocumentDebug DTO 计算；所有存在真实 selector 观测的样本均逐项一致。未提交样本不计为成功弃引；原 raw report 中少数 true 空引用指标的口径缺陷另保留并修正于派生报告和新适配器，不重写历史样本。

全部 48 个样本都未满足“只返回指定 JSON”的端到端格式要求。辅助复核发现，43 个已提交回答中 42 个包含正确目标事实或正确说明无来源；另 1 个法文盒子回答丢失了关键名称。还记录了引文缺字和无来源的过滤目的解释。因此应区分**来源与任务相关性、目标事实、引文忠实度、整体蕴含、格式**；本次词法改进不是独立 NLI 认证。

结论：normalized 值得在新、多候选、多页和否定/不蕴含材料上确认；不直接采用或关闭 MQ-01。

## L2：原文与摘要写入

### 原文

24 份新来源覆盖数值、版本、路径、CSV、制表符、不可断空格、数学符号、引号与被引用指令。两臂均启用相同的 native index 兼容和 adaptive；唯一差异是候选在**模型已经提出合法同 key 写入**后，将 content 绑定到本样本已发给 Session 的原文。它不创造工具调用、不更改 key/身份、不覆盖未知参数字段，也不把提示内被引用指令当执行指令。

| 指标 | baseline | source-binding |
| --- | ---: | ---: |
| 联合通过：最终字符、最终 effect、成功读回、commit/restart | 19/24 | 24/24 |
| committed | 23/24 | 24/24 |
| wire / reported tokens | 63 / 367,609 | 64 / 373,223 |
| sample P50 / P95 秒 | 12.49 / 23.03 | 14.05 / 31.14 |

4 个已提交 baseline 失败包含弯引号/撇号改写，以及把“需存档的原句是……这只是引用……”裁成其中一句；另 1 例最终载荷无效。候选保留全部字符及最终 typed effect，24/24 原文和 effect 重新核对一致。

这是**明确逐字请求的受控来源绑定诊断**，不是任意自由文本记忆写入的通用修复。生产必须设计实际 admitted/protected source 绑定，不能把实验 `case.source` 或未经授权的字符串替换直接搬入运行时。新 rubric 按最终匹配效果评分，同时保留全部 memory effects；旧“恰好一次效果”严格结果仍见先行记录。

### 摘要

摘要单独按 JSON 事实对象评分，不要求与原文字符相同。第一批出现了 `date` 未说明旧日期/当前有效日期、姓名转写、描述性值、`unspecified`/`unknown` 等口径混杂。原 9/16 的联合结果保留，不能把它们全部解释成事实幻觉。

第二批明确每个字段含义、当前状态、原文姓名、unknown 表示和新安排日期，仍用相同 8 个来源，所以只是**数据/评分校准**。两臂均 8/8 提交、事实对象、最终效果与重启读回通过；baseline 20 wire / 120,246 tokens，额外 fact-focus 提示 28 wire / 174,732 tokens。无质量收益，额外提示本轮不晋级。

结论：来源绑定值得独立确认；摘要先固定字段语义并校准 grader，不采用无收益的额外提醒，也不据重复已知来源关闭 MQ-02/MQ-10。

## L3：跨会话事件与时间

30 个独立编写的事件场景，覆盖取消/归档/重新启用、记录与生效时间、未知时间、第三方关系、借用与所有权、相近 ID、条件事件、时区、长消息中段与远处更新。每样本两个实际 seed Session、再创建一个 query Session。网络 embedding 被明确禁用，使用生产本地 hash fallback；不能外推到其他 embedding 配置。

baseline 使用现有窗口检索；oracle 从本样本已提交、已授权的 seed 原话构造完整取回，仅作诊断，不是生产候选。两臂的预设证据锚点均覆盖 30/30，无跨样本来源，120/120 seed 提交并读回。

baseline 主回答 committed 27/30，oracle 30/30；严格 JSON+事实联合分别 1/30 与 5/30。逐条辅助复核表明，57 个已提交回答的目标人物/时间/状态均能对应冻结事实；大部分失败是多写说明、列表、未包装成 JSON、`Room Elm` 与 `Elm` 的表示差异。不能把 1/30 写成“只有一次理解正确”。该复核非独立且只看目标事实，不认证全部附加文字。

本地另复现了裸 `{"answer":"42"}` 会被当作不合格 StudyChatReply，而把它放在合法外层 proposal 的 text 中可通过。它解释了一种输出边界风险，但没有保留 live 原始模型载荷，不能据此认定每个 uncertain 的精确原因。

结论：本批未证实 oracle 的检索收益，不采用全历史扩容；优先处理任务输出与外层 proposal 边界，后续用更多干扰 Session、top-k 竞争、不同来源和独立 grader 检查。MQ-03 仍开放。

## Infra 完成内容与验证

- overload-only 审计恢复：排空、冷却、过期与容量所有权检查，固定最多 4 并发，保留所有旧费用和 uncertain。
- 真实派发前 DNS 检查；本次 DNS 受阻样本保留，新实现避免解析失败时仍逐个创建 wire/领域 operation。
- 单调度器混合 lane、命名空间隔离、逐样本进程/DB；seed wire 单独标记，阶段依赖不并行。
- 合成 PDF 抽取与原始文本一致性检查；每个 seed/操作都有 admission 和 receipt 检查点。
- observed tool 与成功执行分开；只保存 allowlisted 结构遥测，不存参数/推理或 provider ID。
- rubric 校准：拒绝重复 JSON key，未提交引用不算弃引成功，原文最终效果与重复写入分开，摘要事实与字符一致分开。
- 只读聚合、来源选择重放、逐文件 SHA-256、嵌套执行源码快照校验、导出密钥字节检查；不导出数据库或诊断日志。

最终 **36 项通用单元测试、15 项领域集成测试通过**，包括 seed 失败保留且不派发 query、无效果却声称保存、真实隔离提交/重启、DNS 无 wire、overload 不清其他停止闸、未知 usage 保留与嵌套快照防泄漏。`git diff --check` 通过。应用生产代码未改，未运行也不声称通过 `check:release`。

主混合、摘要 v1/v2 的同源码 `--resume` 分别保持 424/40/48 wire，不重放 completed/failed/uncertain。先行 policy/shape 的 92/50 wire 也已验证不增加。最终全部 campaign 终态、0 在途，没有创建持续自动化。

仍未实现阶段预算子池、加权 lane 公平队列、跨主机合并、供应商计费硬界和自动领域 crash 后 query-only 工具。当前混合随机调度与全局滑动限流足以完成本次有界工作；不把它们写成上述能力。进程崩溃后的领域审核应使用保存的 admission 身份，不能重放整个多轮实验。

## 生产区后续更新顺序

1. **评审 native/SDK 适配边界。** 原生 M3 的额外整数 index 有直接证据；先验证实际生产 SDK 是否已经规范化，再决定在哪里投影。保留未知字段/非法参数拒绝，不能放宽 domain decoder。
2. **设计明确逐字写入的来源绑定。** 从 admitted protected snapshot 解析用户授权的原文；字段归属、授权、工具输入、effect 与回执保持分离，评审并注册组件/契约版本。候选源码仅作可重放参考。
3. **单独确认 citation tokenizer。** 不直接改共用 `_tokenize` 影响 persona slots；在多页、多候选、无明显“无关”提示的资料上检验 recall 与 entailment，独立复核后再采用。
4. **处理呈现格式与模型外层 proposal 的冲突。** 正确事实不应因用户要求 JSON 就被混淆成外层 schema；保留严格模型 proposal、安全过滤和 server-only 字段边界，先补真实 SDK/浏览器失败复现。
5. **固定摘要字段口径并独立校准。** 新素材与独立审核者确认事实、当前状态、未知值和重复写入规则；已曝光的开发来源不再标为留出。
6. **执行发布验收。** 确认候选后，运行对应合同/并发/恢复测试及 `npm run check:release`，完成实际前端和适用平台验收，再更新生产默认。研究输出不会自动触发发布。

按原计划，本轮完成三条首日优先 lane 的有界实验和 WP-01/02/03 的适用切片，准备了 WP-04 复核证据与评分口径；正式独立审核尚未就绪。L4–L8 是条件启动的研究菜单，本轮未启动，不能冒充已验收。已有证据已足以决定哪些候选应复核、哪些不晋级，故停止新增模型调用，不消耗剩余额度凑样本。
