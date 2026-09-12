# M3 Planning 全流程探索与修复（2026-09-13）

## 结论

本轮在隔离分支 `codex/m3-planning-exploration` 上完成了从 PDF 结构恢复、受保护 Planning 上下文、单轮工具调用、严格 JSON 解码、本地语法修复、领域校验、原子提交到 Harness v3 Trace 的全流程检查。

生产策略从“鼓励反复取证并强制细分”收敛为“确定性结构优先、代表性正文内置、一个工具轮补齐关键缺口、随后严格输出”。在两个真实教材样本上，该策略消除了工具循环和大多数无效 token，同时保留严格 schema、Study Unit 引用、物理页范围与 committed read-back 校验。

## 数据边界

- 样本来自本机 Downloads；测试只向 MiniMax-M3 发送解析后的教材文本、结构元数据和必要的工具结果，没有上传 PDF 或页图。
- 仓库证据只保存计数、耗时、token、章节标题、错误类别、契约版本和安全摘要。
- 原始教材文本、provider reasoning、完整 provider 输出、API key 和 `/tmp` 数据库均不进入仓库。

## 发现与修复

### 1. 确定性章节结构恢复

Macbeth 样本原先只得到 5 个可规划 Study Unit，并遗漏 Chapter 1。解析器现在：

- 保留 `Chapter N` 结构编号，不再把它误判为孤立页码或页眉；
- 合并分离的 Chapter marker、编号和附近显示标题，并有限修复 OCR `IO` → `10`；
- 在缺少嵌入式 PDF outline 时，从可见 CONTENTS 恢复连续编号标题，并以顺序和高相似度在正文中定位；
- 更稳定地隔离 Front Matter、Glossary、Characters 和其他 Back Matter。

修复后 Macbeth 得到 Front Matter、Chapter 1–14、Back Matter，14/14 正文章节均可规划。

### 2. Planning prompt v3

旧提示鼓励模型持续调用工具和细分长章节，导致虚构 `Chapter x.y`、跨章情节漂移和预算耗尽。v3 改为：

- 没有来源子标题时，每个 Study Unit 只生成一个父级章节锚点；
- 只有明确结构错误才允许 `revise_study_units`；
- 每个 Study Unit 的初始受保护上下文自带一个最多 240 字的中部代表性摘录；
- 一个工具轮后收束，`focus` 最多 260 字，`today_tasks` 为 3–5 项；
- 明确区分请求页范围与实际返回范围，禁止把截断后的未返回页面视为已核验。

### 3. 页文本读取的诚实覆盖范围

`read_page_range_content` 现在返回 `content_page_start`、`content_page_end`、`truncated` 和 `next_page_start`。结果按页排序并只声明实际覆盖范围；字符上限包含 chunk 之间的分隔符。

### 4. 单轮工具预算

Planning runner 最多执行一个工具轮。`get_study_unit_detail` 和 `read_page_range_content` 在同一轮最多各 3 次，每个 operation 仍最多 4 次，运行时仍串行并保持 provider call order。该行为变更绑定到 `planning-toolset-v2`。

受控 Tao 真实实验在同一轮执行 2 次页文本读取和 1 次 Study Unit 详情读取，三次均成功且无预算拒绝；确定性 pilot 另验证同名工具第 4 次调用被 `tool_round_budget_exceeded` 拒绝。

### 5. 严格 JSON 与本地 repair

所有 Planning provider 请求使用 JSON object mode 和低温度。模型输出 JSON 语法失败时，先用本地 `json-repair` 修复语法，再重新执行完整 Pydantic schema、Study Unit 引用和页范围校验；只有本地修复仍无法通过严格契约时，才发送精简外部 repair 请求。语法修复不放宽领域约束。

## 真实 M3 结果

| 样本与策略 | 结果 | Provider tokens | 延迟 | 工具行为 | 结构质量 |
| --- | --- | ---: | ---: | --- | --- |
| Macbeth，旧生产提示、修复后解析 | 成功 | 68,623 | 64.2 s | 5 次预算拒绝 | 14 章齐全，但仍有虚构子节和跨章事实漂移 |
| Macbeth，正式 v3，第 1 次 | 成功 | 17,121 | 57.6 s | 无工具调用 | 14/14，每章一个来源锚点，Chapter 7 未提前写入 Chapter 8 情节 |
| Macbeth，正式 v3，第 2 次 | 成功，本地 repair | 18,498 | 68.5 s | 无外部 repair | 14/14；非法 JSON 本地修复后通过全部严格校验 |
| Tao，旧生产提示 | 失败 / 502 | 417,963 | 24 个 provider 回合 | 21 次预算拒绝 | 未提交计划 |
| Tao，正式 v3、Toolset v1 | 成功 | 15,363 | 29.8 s | 3 次页读取中 2 次被旧同轮预算拒绝 | 退化为 2 个父章 |
| Tao，正式 v3、Toolset v2，自然选择 | 成功 | 19,231 | 40.8 s | 2 次 Study Unit 详情，0 失败 | 保守的 2 个父章，无虚构细分 |
| Tao，正式 v3、Toolset v2、受控首工具 | 成功 | 20,779 | 51.3 s | 2 次页读取 + 1 次详情，0 失败 | 恢复 7+3 个来源支持的小节及物理页锚点 |

Macbeth v3 两次平均 17,810 tokens，相对 68,623 tokens 下降约 74.0%。Tao 自然 Toolset v2 运行相对旧生产下降约 95.4%；包含受控页取证的运行仍下降约 95.0%。旧 Tao 运行的主要问题不是单次输出长度，而是多轮上下文重复增长和失败工具调用。

## 架构判断

- 当前收益主要来自确定性解析、紧凑受保护上下文、单轮工具和本地严格 JSON repair。
- 本轮没有证据支持引入 reviewer 模型、多智能体规划器或垂域数学模型；它们会增加延迟、token 和新的失败边界，却不解决来源结构与预算纪律问题。
- 7+3 个 Tao 小节只有在工具结果明确提供结构时才进入计划；自然运行选择保守父章同样属于正确行为，而不是质量失败。

## 验证与限制

- Tool Manifest、provider projection、Planning contracts、runner、JSON repair 和页预算定向测试：50 项通过。
- 当前 Planning deterministic pilot：9/9 样本通过，gate passed；同时验证第 4 次同轮详情读取和页读取均被拒绝。
- 后端全量回归：874 项通过；仓库级 `npm run check` 通过共享合约、Web 类型/可靠性、全部 Harness PR pilot、十个阶段回归和 Plan Revision gate。
- 两次 Toolset v2 Tao 运行均完成 operation admission、严格验证、原子提交、API read-back 和 Harness v3 terminal trace，工具失败均为 0。
- 外部模型仍有随机性；本结果证明当前样本与运行配置下的行为，不等价于所有教材、语言或 provider 的普遍质量认证。
- `json-repair` 只处理 JSON 语法；事实正确性仍依赖受保护证据、结构规则和严格领域校验。

精简机器可读证据见 `docs/quality/evidence/m3-planning-flow-2026-09-13/summary.json`。
