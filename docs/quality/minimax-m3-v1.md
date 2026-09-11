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
