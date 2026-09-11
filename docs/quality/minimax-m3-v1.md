# MiniMax-M3 质量检定 v1

2026-09-12 用户授权恢复真实模型质量工作，持续迭代，逐次记录依据并提交。
旧 QG-002 / web-strict-decode-adversarial-v1 保持不可变。本记录属于
QG-MODEL-QUALITY-001；没有完成独立人工校准前不关闭质量门。

## 实测约定

- 使用环境变量 K3_API_KEY，仅向确认的 MiniMax 官方 API 发送认证头；报告和 Git 不包含凭据。
- 使用合成教材、人物、关系、场景与历史；完整领域检定使用隔离数据库，不修改用户资料。
- 分开记录直接 prompt/provider 探针、领域 Harness admission/commit/read-back 和前端展示证据。直接探针不能证明完整 Harness 通过。
- 每项先跑至少 3 次探索样本，确认协议后扩展到至少 10 个独立案例、每例 3 次；覆盖正常、冲突指令、格式、关系 grounding、长上下文与恢复。样本数是起点，不能单独证明质量足够。
- 报告成功率的分母包含全部计划样本；上游、数据、grader、度量失败单列，不能当作候选成功。记录初次成功率和修复后成功率。
- 优化前后使用相同案例配对并交错运行，保存配置、Git revision、prompt 版本、原始 usage、延迟及具体输出问题。新发现进入开发集；另保留未用于改写 prompt 的评估集。
- Markdown 需验证 JSON 外无围栏、正文实际换行、代码块/表格/数学与 Mermaid 的渲染；人格需核对措辞、关系、称呼、角色权限与不替他人发言。机器格式检查和主智能体语义评审分别报告。

## 覆盖矩阵

| 范围 | 实测重点 | 证据要求 |
| --- | --- | --- |
| Document、逐页抽取、Section、切块 | 双语、标题噪声、顺序、引用完整性 | 真实解析结果与人工可核对的合成原文 |
| OCR、Study Unit 清洗 | 扫描识别、丢字、公式、错误合并 | 真实 OCR 和清洗；M3 只作辅助评审，不冒充 OCR 引擎 |
| Planning、六个工具、Plan revision | 目标/时间约束、引用、工具参数、修改范围 | 真实 provider + 严格 proposal + 持久化读回 |
| Persona | 关键词、文本、整体/单槽辅助、关系与称呼 | 内容提案、用户字段保护、持久化投影 |
| Scene | 关键词/文本生成、层数、空间规则 | 严格树提案与领域读回 |
| Study Chat、31 个工具 | 指令、Markdown、教学/判分、引用、人格 | 工具按能力覆盖；私有答案不进入提交前公开投影 |
| Tavern | 单人/多人、续写、锚点、人格、长历史 | 验证后提交及原始失败/恢复证据 |
| Frontend decode | 对真实生成产物严格解码和渲染 | 原基线 + 新版本案例，不修改旧基线 |

## 官方依据与待验证假设

2026-09-12 读取：

1. [API 概览](https://platform.minimax.io/docs/api-reference/api-overview)：模型 ID `MiniMax-M3`，标称上下文 1,000,000 tokens。
2. [OpenAI SDK](https://platform.minimax.io/docs/api-reference/text-openai-api)：`https://api.minimax.io/v1`；M3 默认开启 thinking，`reasoning_split` 控制是否将其与正文分离。
3. [自动缓存](https://platform.minimax.io/docs/api-reference/text-prompt-caching)：512 input tokens 起，按工具→system→messages 前缀匹配，OpenAI usage 中 `prompt_tokens_details.cached_tokens` 可观测。缓存寿命随负载调整。
4. [显式缓存](https://platform.minimax.io/docs/api-reference/anthropic-api-compatible-cache)：当前支持表未列 M3，不能直接假设 M3 支持 cache_control。

优先检验稳定工具/schema/人物前缀、动态请求后置的收益。缓存字段缺失记为未知，不能记为零命中或自行估算真实计费。比较完整历史、当前最早优先裁剪、候选有来源的记忆策略；分别统计早期约定、人物关系、近期锚点、事实召回和 P50/P95。不得通过静默提高预算或丢弃约束换取性能通过。

## 轮次 0：仓库基线

- 起始 Git revision：`26dfdf9`。
- `npm run eval:harness:pr`：退出码 0，全部 14 个既有确定性套件通过，包含 Plan revision 的 7 个案例。仅证明确定性回归，未证明真实模型质量。
- 代码观察：Tavern preflight 按最早优先逐条裁剪 transcript，persona/scene 超限则拒绝。早期事实丢失及裁剪成本需实测后判断，当前未更改生产算法。
- 国际端点认证返回 401 authorized_error；[国内官方文档](https://platform.minimaxi.com/docs/api-reference/text-openai-api) 确认 `https://api.minimax.cn/v1`。国内端点最小探针返回 200、model=MiniMax-M3、正文 OK、约 1.015 秒。后续样本均使用国内端点。

## 轮次 1：Tavern 原生传输探索

命令（从 services/ai 执行）：

```bash
PYTHONPATH=. uv run python tests/acceptance/minimax_quality_probe.py --output /tmp/minimax-tavern-baseline-v1.jsonl --repetitions 3
```

[12 个原始样本](evidence/minimax-tavern-baseline-v1.jsonl)。四个固定合成案例各三次；复用生产 RemoteTavernProvider 的 prompt、decoder 和恢复，但注入 urllib 原生 HTTP，尚未覆盖 LiteLLM、领域校验和 admission/commit。

- 12/12 一次解码成功，无恢复调用；12/12 原生正文含 think 标签，因此不是直接可解析的 JSON 对象。生产宽容提取成功与严格传输格式分别报告。
- 三条 Markdown 列表 3/3、Python 围栏 3/3；称呼案例 3/3 含阿岚。主智能体检查，未做浏览器渲染或独立人工校准。
- **确认的 grounding 失败**：role_boundary 第三次编造“上回替你回了一句‘好’，你反悔了三回”。输入没有任何历史，且人格明确禁止编造具体共同经历；解码仍成功。此样本说明 schema 通过不代表关系/记忆可靠。
- 同一回复还出现“淋了雨没擦干脑子”；对温厚人物而言可能过度冒犯，列为人格评审问题，不将主观判断伪装成确定性硬门。
- 列表第二次建议雨大时在“大树下”停留，缺少雷雨边界，列为内容质量问题。
- 下一步：对照 reasoning_split；扩展未见过的 grounding 案例，再以完整领域 Harness 验证修复结果。
- 检查：14 套确定性评测通过，Tavern provider 5 项单测通过，探针 Python 编译和 git diff --check 通过。

## 轮次 2：传输核对与事实约束候选

- [reasoning_split 对照](evidence/minimax-tavern-split-v1.jsonl)：12/12 一次解码，12/12 正文直接为 JSON。原生基线中位延迟 6195ms，对照 5719ms；顺序小样本且缓存波动明显，不能宣称统计显著性能提升。
- [生产 SDK 核对](evidence/minimax-tavern-sdk-baseline-v1.jsonl)：4/4 一次解码，4/4 正文直接为 JSON，无需额外配置。LiteLLM 已处理原生推理内容，不更改生产适配器。仍出现无依据的“刚才路上碰见一阵急雨”的具体记忆。
- [grounding-experiment-v1](evidence/minimax-tavern-grounding-candidate-v1.jsonl)：在探针中追加事实来源、不得替用户决定和温厚拒绝约束，12/12 一次解码。三次边界回复未再出现智力/精神状态嘲讽；但 relationship 第二次仍编造“皖南、四天雨、卖伞”等事件。
- **结论：暂不采用候选**。JSON 成功不等于语义问题消失；扩展无历史/缺失记忆的明确上下文及新问法后再测。未修改已注册生产 prompt，因此无生产组件版本变更。
- 当前完成 40 个 Tavern 候选样本与 2 次区域连通性请求；仍未完成所有领域的 Harness 质量检定。

## 轮次 3：降低长历史裁剪的本地成本

实测发现 preflight 为每个待移除的历史消息重新序列化剩余后缀。256 条等长合成消息裁掉 235 条时，三次探索中位数约 648ms。优化为查找满足全部原有预算的最小移除前缀；保持全量快路径、空历史错误优先级和最终内容。

[30 组/长度交错配对原始数据](evidence/tavern-preflight-comparison-v1.json)，每组直接运行 Git `991876b` 的旧实现与当前实现，并断言完整 messages、retained messages、全部 report 字段相等。每种长度先暖机一组，再统计 30 组；Python/macOS/arm64 版本在原始数据中。

| 消息数 | 旧 P50 / P95 ms | 新 P50 / P95 ms |
| --- | --- | --- |
| 32 | 71.07 / 76.13 | 30.82 / 33.89 |
| 128 | 265.68 / 281.14 | 35.63 / 38.22 |
| 256 | 631.49 / 655.47 | 41.86 / 43.43 |

90/90 配对内容完全一致。256 条场景 P50 降低约 93.4%；这是本地 prompt 预算处理收益，不是 provider 时延或缓存命中收益，也没有解决被裁掉事实的召回问题。

验证：64 项 Tavern prompt/provider/API/facilitated 回归通过（包含既有穷举后缀 oracle）；新增渲染次数上限回归防止重新退化为逐条扫描；`npm run check` 通过。预算阈值和已注册 prompt 文本不变，此改动只优化相同算法行为的执行方式。

复现：

```bash
cd services/ai
PYTHONPATH=. uv run python tests/acceptance/tavern_preflight_comparison.py --samples 30 --output /tmp/tavern-preflight-comparison.json
```

## 轮次 4：空历史候选与 Persona/Scene 领域基线

[空历史候选 12 个样本](evidence/minimax-tavern-empty-history-v1.jsonl)在 grounding-experiment-v1 上明确当前无 transcript，并提供一般经验与虚构回忆的对比示例。12/12 一次解码；三个人格闲聊样本未再出现具体地名或既往共同事件。但 role_boundary 第二次出现无场景依据的“喝完这盏茶一起出门”，仍有临时场景幻觉；目前不推广生产 prompt。

[Persona/Scene 12 个领域原始样本](evidence/minimax-domain-baseline-v1.jsonl)覆盖两领域的关键词与长文本输入，各三次，使用真实 M3、生产 LiteLLM、隔离 SQLite、操作准入和 v3 trace，成功生成后实际保存并读回。

- 10/12 最终成功生成并等值读回；其中 5 个 generation trace 为 passed，5 个为 repaired。2 个失败为 `setting_model_invalid_json`（Scene 文本）与 `setting_model_invalid_payload`（Persona 关键词）。修复成功不能计作首次通过。
- 采样器最初错误要求 proposal generation 的 commit_evidence 为 committed，而生产契约正确使用 not_applicable，保存是后续独立动作。原始行的 success 因此全部为 false。保留原始文件，另提供[明确重判记录](evidence/minimax-domain-baseline-v1-regrade.json)，不覆盖历史结果；三项评分器回归验证 passed/repaired、缺失读回/trace、错误 commit policy 的区分。
- 首个尝试在模型调用前因 trace scan limit=10000 超过 100 的接口限制退出，修正采样器后换全新目录运行；属于采样器错误，不计入候选失败。
- Persona 文本第一个样本的 relationship 保留了平等研究关系，但前两张卡片分别出现“学生”，与输入“不是学生”冲突。现有 prompt 反复要求“教师人格/教材导学”，需要验证增加教学能力与人际关系分离的约束。
- Scene 成功样本存在较高修复时延（最长约 106.9 秒）。新增逐调用 usage、finish_reason 和合成候选 JSON 观测，下一批确认截断与结构错误的归因；不根据单个错误码推定原因。
- 本轮领域脚本未启用 OCR、web search，没有覆盖 Document/Planning/Study 或完整工具目录；不得据此关闭全 Harness 质量任务。隔离原始数据库保留在 `/tmp/minimax-domain-baseline-v1b/`，不提交数据库、诊断日志或凭据。

## 轮次 5：Persona 嵌套结构校验纳入有界修复

[8 个逐调用观测样本](evidence/minimax-persona-schema-observed-v1.jsonl)中，4 个回复在 finish_reason=stop 时漏掉全部卡片的 kind 字段，失败码为 setting_model_invalid_payload。它们没有触发重试：原实现只在 JSON 解析阶段使用恢复逻辑，PersonaCardBatchContentProposalV1 的嵌套严格校验发生在恢复逻辑之外。

修复把同一个严格批量 schema 校验器传入现有 Chat/Responses 恢复流程。每个传输仍最多两次调用，JSON 失败和嵌套校验失败共享这个额度；不会给失败结果补造 kind，也不接受模型生成的应用 ID。修复指令明确每张卡片的 title/kind/label/content 和 tags 类型。只有第二次完整校验成功才记录恢复成功，重复无效输出仍失败。卡片数量规则保持独立且严格。

PersonaGenerationHarnessPolicy 升为 persona-generation-harness-v2，Python 模型、工作流 manifest、TypeScript 与 golden fixture 原子更新。历史 DTO 迁移基线仍保留 v1；测试只对这项经复核的 policy 版本声明差异，模型 schema 摘要不变。

- [8 个修复后新样本](evidence/minimax-persona-schema-repair-v2.jsonl)：8/8 最终成功，7 次首次成功、1 次漏 kind 后由 M3 实际重新生成并成功。不同轮次样本有随机性，不把 4/8 → 8/8 当成已经证明的总体成功率。
- [4 个生产领域样本](evidence/minimax-persona-policy-v2.jsonl)：4/4 generation→save→read-back 成功；2 个 passed、2 个 repaired，均有真实准入和 policy v2 终态 trace，commit_evidence 仍正确为 proposal 的 not_applicable。
- 24 项 provider/persona/scene/manifest/lifecycle 测试通过，包含 Chat 和 Responses 的漏字段修复、复合 JSON→schema 失败不超过两次、重复伪造 ID 拒绝、失败不记录恢复成功。npm run check 通过。
- 完整 backend 回归 783 项通过（67.4 秒）；git diff --check 与凭据排除检查通过。

## 轮次 6：人格关系与场景精简对照（未采用）

[Persona 24 个配对样本](evidence/minimax-persona-comparison-v1.jsonl)覆盖合作研究、旅伴、平级同事与成年姐弟/姐妹关系，每类三组交错对照。旧提示 9/12 解码成功，关系约束候选 11/12；这批执行于 schema 修复前，缺字段影响了可比较样本数，不能当成语义胜率。候选多数保留称呼和人际关系，但有“妹妹”这样的性别推断，基线也出现“兄长兼师傅”等关系扩展。当前先修复已定位的结构问题，关系候选尚未进入生产。

[4 个带逐调用观测的领域样本](evidence/minimax-domain-observed-v1.jsonl)确认 Scene 两例初次回复都是 finish_reason=length 且 completion_tokens=4096，随后使用现有 6144 token 额度重试成功。

[Scene 18 个配对样本](evidence/minimax-scene-comparison-v1.jsonl)覆盖茶馆、阴天天文台、停电修伞作坊，每类三组。两边均 9/9 最终成功且各发生 12 次调用；初次截断从 3/9 变为 2/9，但候选仍有一次其他修复，P50 总调用延迟从 29415ms 变为 33982ms。精简指令没有稳定减少物体数或重复说明，不能宣称性能提升，因此不采用。全部原始输出保留以便后续按细节保留、空间约束和成本重新对照。

## 轮次 7：实际 PDF → Study Chat → 前端严格解码

[首批 12 个 Study 操作](evidence/minimax-study-baseline-v1.jsonl)使用实际生成并解析的英文线性方程 PDF，四种用户请求各三次：三条 Markdown 列表、数学与 Python 校验、不存在的教材作者/年份、等待作答的互动选择题。全部 12 个操作 committed，receipt 查询与 Session 读回相等。

- 3/3 列表请求恰好三项，3/3 作者/年份请求没有确认不存在的教材事实（主智能体审阅）；部分使用实际 read_page_range_content 工具核对。
- 3/3 Python 示例在 code rich block 中，包含实际换行和 assert，不在 reply 字段的围栏中。三段代码经过限制 AST 节点和可调用对象后执行，均验证 x=4。单看 reply 是否含 python 围栏会产生误判。
- 3/3 互动题具有持久化的公开题目投影，未将 server-only 的 grading spec 放进公开字段。仍需更广泛判分语义与真实 UI 验收。
- 采样器最初把 domain operation ID 直接用作 Harness ID，导致 terminal_traces 为空；不是产品缺失 trace。通过数据库中的真实不可变 binding 只读解析后，12/12 均有 committed v3 终态，完整证据另存为 [bindings 与 traces](evidence/minimax-study-bindings-v1.json)。脚本已改为正确解析 binding、检查全部 execution 都有终态。
- 前端两个新冻结实测用例通过：生产 Study receipt/exchange 严格解码器接受全部 12 个样本，三段代码保持 multiline rich block；加入现有 Web reliability 测试。旧 QG-002 对抗基线不变。这里没有宣称浏览器视觉验收完成。

[修正采样器后新增 4 个操作](evidence/minimax-study-observed-v1.jsonl)中，列表、代码、来源核对三例成功并带完整 v3 证据；互动题在两次实际 provider 调用后失败，receipt 正确为 uncertain，error_code=study_chat_uncertain_chat_model_invalid_payload，终态 not_committed。未对 uncertain 请求自动重放。该失败进入下一轮诊断，不能被首批 12 个成功样本覆盖。

缓存后续线索：Study 的 system 开头包含 persona/session context，历史消息在本轮教材材料前。人物/单元变化与历史构造可能缩短缓存公共前缀；需要在相同语义与工具权限下实测，不能仅凭排列猜测命中率提升。当前未调整生产 prompt 顺序。

本轮归档检查：更新后的 npm run check 通过，两个新增前端冻结实测回归通过，脚本编译和凭据排除检查通过。互动题后续诊断结果见轮次 8。


## 轮次 8：互动题失败复现与诊断归因

[3 个新会话](evidence/minimax-study-question-diagnostics-v1.jsonl)全部提交成功，共 4 次调用。其中一次初始回复记录 raw_json_object_valid=false 后重试成功；没有 proposal_schema_errors 不代表 schema 通过。空文本假说也未获得证据，严格 proposal 已先执行 strip 和 min_length=1 检查。

[6 个进一步观测会话](evidence/minimax-study-question-guards-v1.jsonl)仅 2/6 最终成功，共 15 次调用（包含工具轮次，不能全部算重试）。失败包括 JSON 解析失败、一次 length 截断、interactive_question 层 value_error。成功通过 schema 的回复均 text 非空且没有公开 grading-key 标志。保留四个失败操作的 uncertain/not_committed 证据，未重放这些操作。

诊断器后续增加生产 decoder 的接受/拒绝标志，区分合法 fenced JSON 与裸 JSON 解析；对互动题 value_error 仅保存已审阅的固定错误码白名单，不保存候选值、任意异常文本或私有判分答案。新增回归验证缺 answer_key 可定位而候选题干不泄露。当前没有放松生产校验，也没有据此宣称互动题质量通过。


## 轮次 9：Planning 领域与工具失败分别计量

[6 个真实 Planning 操作](evidence/minimax-planning-baseline-v1.jsonl)覆盖教材计划、教材来源边界、无教材 Python 目标，各两次。6/6 Plan 均 committed、API 严格模型解码并等值读回，生成 stage 均有 committed 终态。初版评分器错误要求工具 stage 也必须 committed，导致 boundary_success 全部 false；原始记录不改写，另存[重判说明](evidence/minimax-planning-baseline-v1-regrade.json)。新增评分回归确保成功提交不掩盖工具失败、缺终态或读回失败。

27 次工具 stage 中 10 次 failed，最终计划仍可提交。调用覆盖 get_study_unit_detail、read_page_range_content、revise_study_units、estimate_plan_completion 四项，尚未覆盖全部六工具。两个无教材目标的本地 trace 均显示两次 get_study_unit_detail 参数拒绝；不能用最后 Plan 成功掩盖这些浪费调用。教材计划第一轮还有多次 revise_study_units 尝试，下一轮需捕获每个操作的工具结果错误，避免 document-scoped 最新 trace 被后续计划覆盖。当前没有根据通用 stage_evidence_failed 错误码猜测精确根因。

[4 个互动题错误码样本](evidence/minimax-study-question-reasons-v1.jsonl)中 2/4 成功；两个失败操作的首次与恢复共四次响应均明确 study_question_answer_key_required。当前 CHAT_JSON_SCHEMA 将 answer_key 标为可选，提示没有解释其 server-only 属性。正在实验性验证“选择题必须填写 answer_key，但公开展示不包含答案”的补充说明；未修改生产 prompt 或校验器。


Planning 根因补充：[四个内容脱敏工具错误](evidence/minimax-planning-budget-errors-v1.json)来自两个无教材 Plan 的独立本地 trace，均为 tool_round_budget_exceeded，不是参数 JSON/schema 错误。当前 summary 的“参数拒绝”用语不够精确。manifest 默认每工具每轮一次；这两个回复同轮三次 get_study_unit_detail，后两次被正确拒绝。采样器已增加逐操作 tool_diagnostics，避免后续覆盖并保留固定错误码；未提高生产预算或放宽工具准入。


## 轮次 10：互动题私有字段提示候选

[6 个候选会话](evidence/minimax-study-question-contract-candidate-v1.jsonl)共 13 次调用，5/6 提交成功。一例两次 production_decode=rejected 后仍失败，另有三例需要恢复；其中两例初始内容被生产 decoder 判断为 plain_text，仍在后续 parse 阶段触发恢复。没有再次观测到 answer_key_required，但仍有非结构化/JSON 失败。候选仅在实验脚本中向 system/recovery 追加字段条件和服务器私有判分说明，完整 suffix 与配置限制逐行记录；真实 trace 仅证明领域生命周期，不能视作已审阅生产 prompt 的质量认证。

这批样本非交错随机对照，成功率也不稳定，因此暂不推广生产。下一轮需要配对比较，并检查“等待作答”的语义与公开投影，不能只看缺字段减少。生产严格校验保持不变。


## 轮次 11：Planning 逐操作失败与调试摘要修正

[3 个逐操作观测](evidence/minimax-planning-tools-observed-v1.jsonl)全部最终提交，工具失败分别为两次 invalid_study_unit_revision、三次 provider_tool_call_shape_invalid、两次 tool_round_budget_exceeded。真实工具错误揭示最终成功之外的成本，当前继续诊断前两类原因。

修复调试 trace_summary 把同轮/整次调用次数超限显示为对应预算限制，不再笼统显示“参数拒绝”。错误码、工具准入、预算与 provider 返回内容均保持原有契约；这是依据四次已归档预算失败做的诊断展示修正，不是模型成功率优化。另启动预算说明候选与生产对照，结果未齐前不推广提示。


预算摘要修正验证：19 项 provider/planning/manifest/采样评分回归通过；另用真实错误投影函数检查同轮与整次两类摘要，固定 error code 不变。

[6 个预算提示候选](evidence/minimax-planning-budget-candidate-v1.jsonl)中 4/6 提交成功，两个教材计划均在 provider 请求抛出 ModelRequestError 后终止，未将其重新播放。其余四个成功操作未出现预算超限；两个无教材目标将三次详情查询拆至不同轮，均未再触发同轮拒绝，但这可能增加总延迟，并不自动等于成本优化。三次 invalid_study_unit_revision 仍然存在。样本不能证明总体收益，当前不推广生产提示；下一批采样记录纯数字上游 HTTP status，以进一步区分 provider 错误，不保存任意错误消息。


## 轮次 12：严格工具信封的 index 兼容线索

[3 个信封观测操作](evidence/minimax-planning-shape-observed-v1.jsonl)中 2/3 提交成功；教材计划在 provider 请求阶段失败。无教材操作的一轮四个工具信封全部带额外 index 字段，function 内仍只有 name/arguments，四个工具均被 provider_tool_call_shape_invalid 拒绝。生产 decoder 只接受 id/type/function，已定位到这一结构差异，尚未改变严格边界。

下一批仅记录 index 的整数值和类型，核对它是否为按数组顺序排列的传输元数据，再评估在 SDK 适配层消除该兼容差异；不允许借此接受操作身份或未知字段。上一批未记录 index 值，不能据字段名推定其安全性或声称兼容修复完成。


## 轮次 13：完整工具调用的传输序号兼容

[2 个序号观测基线](evidence/minimax-planning-index-observed-v1.jsonl)均提交成功，这两个样本没有 index，不能用来证明兼容修复。

[4 个初版兼容样本](evidence/minimax-planning-index-normalized-v1.jsonl)在 position-matching 实验中进一步记录到：同一轮三个完整调用的 index 都为整数 0。初版仅删除 index 等于数组位置的字段，导致后两项仍被严格 decoder 拒绝，说明“index 代表数组位置”的推断不成立。该初版没有作为生产提交。

修正后的传输适配仅对完整 id/type/function 信封移除有界非负整数 index；保留原始 id、数组顺序、参数与所有未知字段。bool、字符串、负数、超界值、不完整调用和额外应用身份字段不会被修补，仍由下游严格 decoder 拒绝。该适配不组装流式碎片，不从 index 分配应用身份，不更改工具输入/结果或 Harness 领域契约。

32 项传输/工具投影/Planning/manifest 回归通过；完整后端 787 项通过于初版适配，随后针对重复零序号的修正重新通过 18 项传输与严格工具投影回归。新增测试覆盖 SDK 原对象不被修改、重复零序号的完整调用通过生产 decoder、非法索引和伪造身份继续保留供严格拒绝。当前新实测正在统一修正版本上验证。

用户进一步明确运行时限制也应优化。新增只读 get_study_unit_detail 同轮上限 1→3 的实验，整个操作上限仍为 4，其他工具不变；实验 trace 仅证明生命周期，不代表新预算已注册采纳。最终对照使用统一传输实现、交错顺序，比较 provider 轮次、时延和预算失败，而非只比较提示词。


## 轮次 14：提高只读详情工具同轮容量

[3 组交错对照](evidence/minimax-planning-round-pairs-v1.jsonl)保持同一提示、修正后的 index 适配和合成目标，只改变 get_study_unit_detail 的同轮上限 1→3。六个操作均提交并等值读回；基线每例两次预算拒绝，共 6 次，候选 0 次。两边 provider 请求总数都为 8，不宣称减少模型轮次。端到端中位时延 36,276ms→26,560ms，但三组中一组候选更慢，小样本不能证明稳定时延收益。主智能体检查两边计划均遵守先列表后字典、不预设循环基础；这不是独立质量认证。

[先行四例](evidence/minimax-planning-detail-parallel-v1.jsonl)同样全数提交且工具失败为 0，但执行时使用较早的 position-matching 传输适配，保留作补充证据，不混入三组主对照。

采用范围仅为 Planning get_study_unit_detail 每轮最多三次；整次操作仍最多四次，其他 36 个工具仍每轮一次，执行顺序仍串行、按 provider_call_order，不增加执行线程。Python manifest、共享 TypeScript 与 golden fixture 原子修改；结构差异检查确认仅该条目的预算字段变化。没有改变输入/结果 schema 或默认全局预算。

旧 pilot 把第二次详情调用拒绝写入开发者回归用例，导致初次 check 失败。历史 pilot-eval-cases-v1、其评审摘要和旧 baseline 保持原样；新 planning-detail-budget-regression-v2.json 验证第四次拒绝，并以 developer_authored 回归取代旧预算用例参与当前执行。原 held-out 内容和评审摘要不变。新 baseline 单独保存于 planning_tool_eval_detail_budget_v2，明确使用 PlanningDetailBudgetMaintainerReview，不伪称新回归经过独立评审；通过率阈值仍为 1.0。新测试还验证前三次允许、第四次拒绝、下轮仅余一次总额度及其他工具上限不变。

[正式预算的两个新操作](evidence/minimax-planning-detail-budget-production-v2.jsonl)没有实验覆盖，2/2 提交并等值读回，工具失败为 0。后续仍需覆盖更大教材与长期成本，当前没有关闭 QG-MODEL-QUALITY-001。

验证：npm run check 通过（包含当前 pilot、stage 和 Plan revision gates）；完整后端 789 项通过。上述正式预算样本在提交前运行，git_revision 表示基线 bfab1ca，实际测试版本包含本轮 manifest 与回归迁移修改；不是单独 checkout 基线的结果。


## 轮次 15：Study 静态 system 前缀候选（不采用）

[12 个交错新会话](evidence/minimax-study-cache-pairs-v1.jsonl)，基线和候选各六例。候选仅把原 system 开头的 persona/session 占位块移至结尾，完整静态内容、工具和历史消息顺序不变；本地核对 system 字符数与行内容多重集合完全一致，实验未修改生产提示。

两边 6/6 提交并读回一致，全部恰好三条 Markdown 列表。基线六次 provider 请求，五次缓存 128 token、一次未知；候选七次请求，五次 128、一次 0、一次 5367。高命中出现在同一操作的工具调用后续请求中，不是跨会话首次调用的稳定收益。不得把缺失 usage/prompt_tokens_details 计为零。基线/候选操作中位时延 4909.5/4679ms，样本小且候选多一次工具调用，不据此宣称稳定性能优化，暂不采用排序改动。

下一轮使用 98 条合成长历史对照完整历史、最近八条、实际模型摘要加最近八条；分别计量事实召回和摘要生成成本。该实验只验证 provider 上下文策略，不伪造领域准入，也不声称实现了生产压缩器。
