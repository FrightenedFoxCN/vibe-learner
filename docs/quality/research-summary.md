# MiniMax-M3 研究接手摘要

2026-09-12 新增：[并行实验总记录与生产更新交接](m3-parallel-results-2026-09-12.md)。三条优先 lane 已执行，实验候选、数据校准、失败和源码快照完整保留；不代表独立质量门或生产采用。

## 当前状态与阅读顺序

历史真实模型实测已在第 121 轮后停止；最后实验提交 `deed0ae`，没有待收尾的模型实验。2026-09-12 后续任务新增联网研究、首日 2000M tokens 的执行规划和 provider-free 本地复现；随后已完成[独立实验运行器](../../tools/model-quality/README.md)和[4 请求 M3 基础设施预检](evidence/m3-parallel-infrastructure-preflight-2026-09-12.json)，随后又完成[自动扩容与 Study/Tavern 领域接入验收](evidence/m3-autoscale-domain-adapters-2026-09-12.json)：4 个样本的持久化与重启读回均通过，但 Study 两例没有专门记忆写入却声明已保存。独立质量确认批次尚未启动，质量门仍开放。最新资源与调度口径见[高并行计划](m3-parallel-exploration-2026-09-12.md)，不以消耗额度或运行满一天为目标。

本次[真实请求容量测量](evidence/m3-live-concurrency-capacity-2026-09-12.json)使用生产 Tavern prompt/schema 与重复合成短样本：4 并发两个有效窗口共 201 请求，全部 HTTP 200，约 96 请求/分钟，窗口 P95 为 3.69–4.03 秒；8 并发约 47 秒内 147 请求出现 1 次 HTTP 429，已停发，未测 16/32/64。供应商硬限制仍未知，429 不能区分并发、RPM 或 TPM；该结果不外推到长 Study/Planning 或图片。前两次仪器修正前的 156 请求窗口不足，保留成本与失败分母，不计为有效容量证据。当前账本保留 provider_overload 停止状态，质量门不变。

1. [生产行为文档](../model-runtime-quality.md)：已采用的 31 个生产/共享契约提交及限制。
2. [独立质量 TODO](TODO.md)：唯一的详细任务状态、证据入口和关闭标准。
3. [保留研究证据](evidence/research-notes.md)：未采用候选、未关闭失败及混合观察，沿用原轮次编号。
4. [Agentic design 与 ACL 2025/2026](agentic-design-research-2026-09-12.md)：已联网核验的来源、对应子任务与候选假设；[当前本地诊断](evidence/agentic-preflight-local-2026-09-12.json)不计为新的 M3 轮次。

研究起点为 `26dfdf9`。需要完整旧过程时可执行 `git show deed0ae:docs/quality/minimax-m3-v1.md`，或从同一版本恢复已清理的单个证据文件。不重写 Git 历史，不删除产品代码、回归测试、旧 Harness 基线或研究探针。

## 已知结论

- 最有确定依据的采用项是运行时边界修复：实际图片传递、工具证据保留、字符/页预算、场景目标 ID、原文来源和时间、重试归属、无依据引用兜底。它们不证明最终内容可靠。
- Planning 的 3 次同轮详情读取缓解了原有限额拒绝；未证明稳定减少 Provider 轮次。结构估分仅观察源元数据，不能用高分衡量计划完成质量。
- 人格方法可以反映到比较、解释和边界分析活动，但与图片事实准确性必须分别判定。图片实收本身也不能证明图像有益；中文双页续接和法文数学留下了反例。
- 原文检索比盲目截断保留了更多更新；模型仍能把已取回事实的对象或时间绑定错。检索、读取推理与持久写入需分层评分。
- 缓存、生成式摘要压缩、通用提前成稿、统一格式提醒、默认逐字记忆、整体 Persona/Study 范围提示均没有足够证据支持采用。不要把探针的实验开关当成生产默认行为。
- 本机 Vision OCR 有中文识别收益，也有字符/脚注错误；只是诊断和补充 Planning 输入，没有生产 Document Harness、打包或跨平台采用。

## 最近的可继续反例

- 轮次 119：7 个合成词法引用反例。当前中文整段 token 漏相关项，照搬记忆 bigram 又误匹配“这个”；英文功能词、法文子串也产生误引。候选未采用。
- 轮次 120：审计 8 个种子 receipt，6 个有专门记忆效果、2 个只有 Turn 持久化；发现无依据“地点改为北门”。不要把这两种写入混计。
- 轮次 121：摘要/逐字/逐字/摘要，4 个独立数据库、12 次 Chat 调用，全部提交并写后读回。摘要均保留合成源事实；逐字一例完全一致，另一例将 3 处 U+2019 改为 ASCII 却声称逐字一致。一例最终状态文案停留于 committed=false，四例均因词法重叠附无关数学引用。
- 轮次 117 的独立数据库探针消除了重复样本串入；教师人格仍可能多说或拒绝笔记任务。它与轮次 116 的首个验证样本共用证据，不能重复计入独立样本量。

优先从 TODO 的 MQ-01/MQ-02 领取一个有界任务，先复现再改动，不预先把某个词法算法、Prompt 或强制写入模式当作答案。

## 运行与复现

在 `services/ai` 使用 `uv run python` 和 `PYTHONPATH=.`。M3 实测使用 `K3_API_KEY` 环境变量、`https://api.minimax.cn/v1`、`MiniMax-M3`；国际端点曾认证失败，不重复输出或索要密钥。不要把密钥、Vault 密码、推理正文、完整电子书或页图写进 Git。

新的输出目录必须独立且不存在，避免覆盖原样本或共享数据库导致检索污染。例：

```bash
cd services/ai
PYTHONPATH=. uv run python tests/acceptance/minimax_memory_write_pairs.py --output /tmp/m3-memory-write-new-run
```

这条命令会调用真实 Provider；摘要中的命令不构成自动执行授权。其他探针先读源码或 `--help`，不要凭旧临时路径复用用户主 Vault。用户曾授权电子书压力测试，但 Downloads 文件和 `/tmp` 数据不是仓库可移植 fixture；重跑时重新检查来源、页码与可用性。

| 研究方向 | 保留的探针入口（相对 services/ai） |
| --- | --- |
| 引用 | `tests/acceptance/citation_tokenization_probe.py` |
| Study 多语言独立样本 | `tests/acceptance/minimax_study_event_isolated.py`、`minimax_study_probe.py` |
| 写入摘要/逐字模式 | `tests/acceptance/minimax_memory_write_pairs.py` |
| 原文窗口边界 | `tests/acceptance/minimax_memory_selector_limits.py`、`memory_neighborhood_backoff.py` |
| 压缩与时间关系 | `tests/acceptance/minimax_temporal_compression_probe.py`、`minimax_temporal_followup_probe.py`、`minimax_event_time_pairs.py` |
| Planning 图文/人格与配置 | `tests/acceptance/minimax_planning_probe.py`、`minimax_planning_image_pairs.py`、`minimax_native_modality_pairs.py` |
| 提前成稿与工具策略 | `tests/acceptance/minimax_planning_finalization_pairs.py`、`minimax_tool_choice_probe.py` |
| OCR | `tests/acceptance/native_vision_ocr.swift`、`minimax_native_ocr_planning_pairs.py` |
| Tavern / Persona / Scene | `tests/acceptance/minimax_tavern_domain_probe.py`、`minimax_domain_probe.py`、`minimax_setting_comparison.py` |

## 实验纪律和容易误判的地方

- 配对交错运行，一次只改清楚定义的变量。至少先用少量样本确认传输协议，再扩大独立案例和重复次数；样本量不自动构成质量认证。
- 数据库运行时设置可覆盖请求配置。多模态探针已修正实际设置应用，仍需记录 effective settings；SDK 包装前的 tool_choice/图片标记不能替代 HTTP 实收证据。
- 分别记录完整领域 admission/commit/read-back 和直接 Provider 探针。proposal 的 not_applicable commit 不等于失败，也不能用它证明后续保存。
- failed seed、超时、schema 回显、grader 错误必须保留，不能只报告合法输出；首次成功与修复后提交分开。包含摘要生成、复用和原文回查的全部成本。
- cached_tokens 缺失视为未知，不记作零；没有冷暖和前缀控制时不从时延差归因缓存。M3 原生多模态不等于本项目已提供图片工具或 image-01 图片生成。
- 正式源只保留安全指标、合成内容和必要生成结果。证据里历史 `/tmp` 数据库与书本页图可能已失效，缺失时如实记为无法重放，不能称完整独立证据。
- 旧 QG-002 不变。维护者编写的回归和主智能体评审不可冒充独立人工/专家认证；对新发现改写后，应另设未参与开发的案例。

## 外部研究线索

以下为本次研究读取过的资料，未在整理时重新联网核验；只支持实验假设，不是本仓库收益承诺。

- [MiniMax 自动缓存](https://platform.minimax.io/docs/api-reference/text-prompt-caching)：关注稳定前缀及实际 cached_tokens；显式缓存的支持不能从其他模型推断到 M3。
- [M3 工具调用指南](https://platform.minimaxi.com/docs/guides/text-m3-function-call.md)：完整 assistant 消息回传建议；历史回传实验未形成生产策略，不能记录推理正文到公开证据。
- [Anthropic 上下文工程](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)：先保召回、再减冗余，按需回取与结构化笔记。
- [Mem0](https://arxiv.org/html/2504.19413v1)：拆分事实提取、更新、检索；其模型与基准收益不外推到 M3。
- [LongMemEval](https://arxiv.org/abs/2410.10813)：抽取、跨会话推理、时间、更新和无依据拒答分层评测。
- [The Sleeping Agent](https://arxiv.org/abs/2608.11775)：日期保留假设；本项目追问已证明“日期字段正确”仍可能掩盖取消/归档事件混并。

## 清理与验证口径

纯已完成工程轮次 3、5、12、13、14、23、73 的过程正文从当前记录移除，生产规则和提交映射已迁入正式文档。仅删除不被其余仓库材料引用的独占过程证据；混合失败及其依赖保留，Tavern 配对性能基线保留。完整历史可从 `deed0ae` 恢复。

最近生产代码验证为 850 项后端测试、116 项定向测试通过；这不是本次文档清理重新执行的发布门。本次只验证文档链接、提交映射、证据 JSON/JSONL 可解析性及 diff，不发起模型请求。
