# Agentic design 与模型质量研究：ACL 2025 / 2026

检索与仓库检查日期：2026-09-12。目标是在短期 M3 资源窗口内，尽快定位本项目质量瓶颈、筛选值得采用的设计并留下可复核证据。**首日可用上限以用户最新更正的 2000M tokens（20 亿）为准**；其余额度随后到账，不计入首日预算，也不以耗尽额度为成功标准。

本文是研究结论与假设索引；执行顺序、预算、并发和实验退出条件见[高并行探索计划](m3-parallel-exploration-2026-09-12.md)。任务状态继续只维护在[质量 TODO](TODO.md)，本轮没有关闭 MQ 或改变生产默认策略。历史 M3 实测在第 121 轮停止，本轮新增的是联网研究、执行规划和本地诊断证据。

## 1. 仓库现状决定研究顺序

当前生产已修复实际图片传递、工具证据保留、字符/页预算、记忆来源/时间、原文窗口、重试归属和零匹配引用兜底，详见[运行时质量文档](../model-runtime-quality.md)。这些是比较基线，不应再列为待接入能力。

历史第 121 轮有 4 个独立数据库、12 次 Chat，全部提交并写后读回，但逐字模式仍有一例改动三个 U+2019 字符，一例最终文案停留在 `committed=false`，四例附了无关数学引用。由此优先检验“证据是否正确进入答案和效果”，而非继续堆积提交成功案例。历史轮数不是独立案例数，也不是 held-out 样本量。

| 顺序 | 现有任务 | 要回答的具体子问题 | 首批证据与代码入口 |
| --- | --- | --- | --- |
| 首日核心 | MQ-01 引用 | 检索遗漏、词法误命中、引用不支持结论，分别占多少？无来源时能否不引用？ | [词法反例](evidence/minimax-citation-tokenization-v1.json)；[pedagogy.py](../../services/ai/app/services/pedagogy.py) |
| 首日核心 | MQ-02 写入 | 请求的是摘要还是逐字？字符/事实是否忠实？专门记忆效果、Turn 保存、最终状态是否一致？ | [写入对照](evidence/minimax-memory-write-pairs-v1.jsonl)；[study_chat_effects.py](../../services/ai/app/services/study_chat_effects.py) |
| 首日核心 | MQ-03 记忆 | 没取回、取回后读错、写错如何分离？取消、归档、重新启用与未知时间如何区分？ | [选择器边界](evidence/minimax-memory-selector-limits-v1.json)；[study_memory.py](../../services/ai/app/services/study_memory.py)、[memory_excerpt.py](../../services/ai/app/services/memory_excerpt.py) |
| 条件启动 | MQ-04/05 Planning | 来源/页码/分钟/教学方法能否独立验证？多次工具调用是否增加有效证据？ | [法文短源](evidence/minimax-french-short-native-pairs-review-v1.json)、[收束对照](evidence/minimax-french-finalization-pairs-review-v1.json) |
| 条件启动 | MQ-06/07 Study、Tavern | 人格是否改变任务权限？诊断错因与反馈是否正确？视觉定位、出题泄漏、续接是否满足请求？ | [填空复核](evidence/minimax-study-fill-blank-review-v1.json)、[视觉定位](evidence/minimax-study-grid-review-v1.json)、[Tavern 迁移](evidence/minimax-tavern-grounding-transfer-review-v1.json) |
| 后续专项 | MQ-08/09 | 缓存/摘要的完整成本与事实保留；OCR 误差如何传播到教学；图片生成适配另行评估 | [缓存对照](evidence/minimax-study-cache-pairs-v1.jsonl)、[Vision 诊断](evidence/minimax-native-vision-ocr-review-v1.json) |
| 全程 | MQ-10 | 样本是否独立？grader 是否校准？改善能否迁移到新实体、新教材和真实 UI？ | [研究接手摘要](research-summary.md)、[Harness 架构](../harness-architecture.md) |

首批当前版本的纯本地复现见[诊断记录](evidence/agentic-preflight-local-2026-09-12.json)。它用于确认研究起点，不能代替真实 M3、commit/read-back、独立人审或浏览器验收。

当前 HEAD `7157af0` 的三项本地诊断均执行成功，M3 调用为零：引用基线和直接借用 memory tokenizer 的候选均只有 4/7 开发反例符合预期，候选还新增无关匹配；原文窗口 4 例仅同语言控制取回目标；小邻域在 6 组对照中将保留数从 2 提到 3，但丢掉原已保留的“不是真实约定”限定。首轮决策是保留 MQ-01/03，放弃直接替换 tokenizer 或仅缩小邻域的采用提案，继续分层取证实验。这里的比率是固定开发反例统计，不是泛化准确率；MQ-02 的模型写入问题仍引用历史实测，未进行新 M3 复现。

## 2. 检索范围与来源强度

先以 `site:aclanthology.org 2025.acl agent workflow design` 搜索定位，再读取 [ACL 2025](https://aclanthology.org/events/acl-2025/)、[ACL 2026](https://aclanthology.org/events/acl-2026/) 会议目录，按 agent/workflow、memory、planning/tool、tutor/education、citation/multimodal 筛选并核验单篇出版元数据。另读取 Anthropic 官方设计文章。

**ACL 2026 已有正式 Anthology 论文集**，本次引用单篇均能核验标题、venue、2026/7 出版日期和 DOI；不把会前通知、预印本或年份推断当作录用证据。ACL 主会、Findings 与 BEA Workshop 在下文分开标注。官网新闻更新进度不用于否定正式出版记录。

这是面向任务的定向初筛，不是系统综述。本轮阅读范围为正式摘要/元数据和工程文章正文，尚未逐篇核对 PDF 的表格、置信区间、代码、数据许可证或复现成本。下文数字均为**原论文摘要报告**，不是本项目实测。完整来源元数据与阅读范围见[来源记录](evidence/agentic-design-sources-2026-09-12.json)。

## 3. Agentic design：应比较哪些设计

| 来源 | 已报告结论或方法 | 本项目可检验的假设与限制 |
| --- | --- | --- |
| [Building effective agents](https://www.anthropic.com/research/building-effective-agents)，Anthropic 工程文章，2024-12-19 | 区分固定 workflow 和模型动态调度；总结 chaining、routing、parallelization、orchestrator-workers、evaluator-optimizer，强调工具接口与停止条件。 | 用作设计词汇和最小基线；属于工程经验，没有给本项目提供受控收益证据。页面现已注明工具生态发生变化，不据此选新依赖。 |
| [Beyond Frameworks: Unpacking Collaboration Strategies in Multi-Agent Systems](https://aclanthology.org/2025.acl-long.1037/)，ACL 2025 Long | 在 DEI/SES 两类证据任务中拆分治理、参与控制、交互顺序、历史管理；集中治理、有序交互等组合改善质量与 token 权衡。 | 分别实验“是否共享全部历史”“是否有中央分解器”“是否有独立验证者”；结果受证据任务限制，不等于全连接辩论值得默认采用。 |
| [AgentDropout](https://aclanthology.org/2025.acl-long.1170/)，ACL 2025 Long | 动态去除冗余 agent/通信；摘要报告 prompt/completion token 平均减少 21.6%/18.4%。 | 记录每个额外调用新增的有效证据，比较 1/2/4 候选、裁剪无贡献 critic。不能把论文效率数字当作 M3 预期。 |
| [Divide-Then-Aggregate](https://aclanthology.org/2025.acl-long.1401/)，ACL 2025 Long | 工具依赖转换为 DAG，分解可并行子任务后聚合；包含训练数据与模型方法。 | 先并行独立 case。运行时仅将依赖明确、只读的取证节点作为候选；不能据此并发 Scene/Session 写入，也不能假设纯 prompt 可复现训练收益。 |
| [Grammar Search for Multi-Agent Systems](https://aclanthology.org/2026.acl-long.75/)，ACL 2026 Long | 在两个 backbone、数学/QA 任务中搜索固定可组合的架构组件，优于多数比较方法。 | 在小型、可审查的候选语法中搜索，限制模型自由生成整个运行器；目标是筛掉无效结构，保留等预算基线。 |
| [Single-Agent Generation Surpasses Multi-Agent Systems in Semantic Diversity](https://aclanthology.org/2026.findings-acl.1894/)，Findings ACL 2026 | 匹配 prompt 的发散思考实验中，单 agent 和单次多输出具有更高语义多样性。 | 数据生成和 Tavern 候选保留“一次生成多个候选”对照；此结论不证明单 agent 在所有工具/规划任务更好。 |
| [MedDCR: Learning to Design Agentic Workflows for Medical Coding](https://aclanthology.org/2026.findings-acl.627/)，Findings ACL 2026 | Designer 提议，Coder 执行，Reflector 反馈；设计存档支持迭代。 | 分开保存候选设计、运行证据和错误分类；仅用开发集失败反馈生成下一代候选，禁止把留出答案写入反思记忆。原领域是医疗编码，公平预算需进一步读 PDF。 |

形成五类可比较实验臂：当前单次/现有循环基线、单 agent 有界多轮、固定取证→生成→校验流水线、独立候选→选择、错误分类→一次 critic 修复。一次多输出是多候选臂的必要廉价对照。相同输入、有效上下文、工具权限和请求/token 上限下比较，再另报质量—时延—成本曲线；不能通过给复杂臂更多预算把结构收益与算力收益混在一起。

模型负责提出候选，应用仍负责身份、顺序、revision、receipt 和提交。逐字存储应研究“模型识别意图/原文范围，应用执行精确复制与比较”，让可判定约束由程序检查；不让 critic 代替字节或字符校验。实验设计不能放宽 Tool Manifest、受保护制品授权或 Harness v3 事实边界。

## 4. 引用、记忆和时间关系

| 来源 | 对本项目最有价值的结果 | 对应子任务 |
| --- | --- | --- |
| [CiteEval: Principle-Driven Citation Evaluation for Source Attribution](https://aclanthology.org/2025.acl-long.1574/)，ACL 2025 Long | 单纯二/三分类 NLI 支持度不是完整引用质量代理；评审应包含检索上下文、问题和生成文本，CiteBench 有人工标注。 | MQ-01/10：同时记 Recall@k、引用支持/相关性、覆盖、定位准确性、正确拒引。无来源、否定和跨语言要独立分层；不以关键词命中或 NLI 分数单独关票。 |
| [RAG-Critic](https://aclanthology.org/2025.acl-long.179/)，ACL 2025 Long | 数据驱动的分层错误体系、训练的 error critic、按错误定制恢复路径；七个 RAG 数据集验证。 | MQ-01/05：比较“重新检索”和“只重写答案”，明确错误定位后再修复。论文训练 critic 的效果不能归给一条 M3 提示词。 |
| [HiAgent](https://aclanthology.org/2025.acl-long.1575/)，ACL 2025 Long | 按 subgoal 管理单次任务 working memory；五个长程任务中摘要报告成功率翻倍、步骤减少 3.8。 | MQ-05/08：保留当前子目标证据，完成子目标后压缩并可回查；它不是跨会话学习者记忆系统，不能直接替换 session memory。 |
| [TReMu](https://aclanthology.org/2025.findings-acl.972/)，Findings ACL 2025 | 时间线摘要与代码化时间计算；基于 LoCoMo 增广多选题，摘要报告 GPT-4o 从 29.83 到 77.67。 | MQ-03：比较原文、显式事件表、受限日期计算器；记录时间/事件时间/生效时间、未知日期和取消/归档必须分开。不能为构造时间线补出未知日期。 |
| [How Memory Management Impacts LLM Agents](https://aclanthology.org/2026.acl-long.27/)，ACL 2026 Long | 相似经验会诱发相似输出，并传播错误或错误复用。 | MQ-02/03/08：加入过时、被撤销、条件相似却不适用的记忆；“模型曾成功输出”不能作为事实真源。 |
| [Mem2ActBench](https://aclanthology.org/2026.acl-long.370/)，ACL 2026 Long | 从被动回忆扩展到主动选工具与参数 grounding；400 个任务中 91.3% 被人工评为强依赖记忆。 | MQ-03/05/07：除问答正确性，测历史偏好是否进入正确工具、正确对象和参数；效果由真实 read-back 判断。其合成场景不能代表本项目全体用户。 |
| [LongTutor](https://aclanthology.org/2026.acl-long.1371/)，ACL 2026 Long | 专家标注真实学习日志；历史证据获取、知识状态诊断、自适应教学行动是三个不同任务，检索好不等于后两项好。 | MQ-03/07/10：建立“oracle 证据已给出”的读取对照，定位取不到或读错；再测误解诊断和下一步教学行动。 |

首批样本矩阵覆盖中/英/法、长句/无标点、中段更新、多对象、否定、撤销后重启、未知日期。原文由独立合成 fixture 给出，字符忠实用程序核对；日期/关系有显式 gold，未知不计成模型可自由推断的空位。反复替换人名只能算同一模板族，不增加独立样本量。

## 5. Planning、教学、多模态与角色

| 来源 | 已报告结果或可复用评估思路 | 对应子任务与范围限制 |
| --- | --- | --- |
| [From Objectives to Questions](https://aclanthology.org/2025.acl-long.628/)，ACL 2025 Long | EduMath 16k 题、多维教育目标；EQPR 采用 plan-evaluate-optimize，结合 MCTS。 | MQ-04/07：分开评目标、题目有效性、认知难度和反馈；先测有界规划与一次校验，尚无依据直接接入昂贵 MCTS。 |
| [BEA 2025 Shared Task on Pedagogical Ability Assessment](https://aclanthology.org/2025.bea-1.77/)，BEA 2025 Workshop | 错误识别、错误位置、指导、可执行反馈四项教育评测；最佳 macro-F1 为 58.34–71.81，另有 tutor 身份识别赛道。 | MQ-07/10：这四维适合作为独立 rubric；识别“谁写的”成绩高，不等于判断教学质量可靠。 |
| [DeepPlanning](https://aclanthology.org/2026.acl-long.335/)，ACL 2026 Long | 主动搜集信息、局部约束和全局优化共同构成长程规划评测。 | MQ-04/05：分钟合计、前置关系、页范围、覆盖与修订一致性使用可执行约束；旅行/购物结果不证明教学有效。 |
| [Planning-Guided Tutoring with Assessment-Driven Memory](https://aclanthology.org/2026.acl-long.325/)，ACL 2026 Long | ScaffoldLM 使用分步计划和诊断记忆决定下一教学行动。 | MQ-03/04/07：比较 history-only、摘要、诊断记忆+步骤计划；分别看诊断、推进、回退。适合研究假设，不能直接构造新的生产学习者状态 schema。 |
| [MMTutorBench](https://aclanthology.org/2026.acl-long.1068/)，ACL 2026 Long | 770 道题、题目专属 rubric、六维评估，区分关键洞见、操作形式化和执行；摘要报告 OCR pipeline 降低教学质量。 | MQ-04/07/09：同源页图/当前 OCR/人工校正文/结构化图文证据配对；记录字符/公式/布局错误如何传播。不能推断所有 OCR 必然有害，M3 图片理解也不等于 image-01 生成。 |
| [Confirming Correct, Missing the Rest](https://aclanthology.org/2026.bea-1.56/)，BEA 2026 Workshop | 10,836 个 solution–feedback 对显示正确但次优或错误路径容易被误判，诊断对也不保证反馈可执行。 | MQ-07：正确、等价但非预期、部分正确、错误答案分层；教学提示提前揭底与服务器 grading spec 泄漏各自评分，不能混为同一门。 |
| [Simulated Students in Tutoring Dialogues: Substance or Illusion?](https://aclanthology.org/2026.acl-long.1960/)，ACL 2026 Long | 从语言、行为、认知考察学生模拟；简单 prompting 较弱，训练改善仍有限。 | MQ-07/10：M3 可生成对抗轨迹/压力样本，模拟学生成绩不得被报告成真实学习增益。 |
| [Simple Agents, Biased Judges](https://aclanthology.org/2026.acl-long.2006/)，ACL 2026 Long | 319 次配对评审中 human–LLM κ≈0.11、human–human κ=0.29；存在冗长偏好、平局偏差、对乱序不敏感。 | MQ-06/10：Tavern 做匿名、交换次序的真人盲评，加入乱序、身份互换、伪造共同经历负例。该 κ 是原论文值，M3 grader 的偏差需另测。 |

教学子任务至少拆成：取证 → 诊断误解 → 选下一行动 → 出题 → 提示 → 判分/反馈 → 更新学习状态。人格是措辞/教学方法的变量，不能获得扩张任务范围、编造第三方关系或泄漏答案的权限。Planning 的人格方法与源事实准确性分开评分，视觉定位还需真实坐标/IoU 和浏览器呈现证据。

## 6. 对高并行探索的设计结论

1. **优先并行独立实验。** 同一 case 的写入和多轮依赖保持顺序；每个 case/variant/repetition 独立进程、数据库和输出目录。现有探针使用进程全局 patch，直接线程并发会污染候选条件。大量 token 不会解除数据依赖。
2. **先分错误，再增加 agent。** 引用召回失败要重新取证，字符修改由确定性比较发现，日期计算可交受限工具。额外 critic 应针对不能由程序判断的语义问题，并受一次恢复上限约束。
3. **高并行服务于缩短决策时间。** 首日上限 2G tokens，按待决策样本释放小批；当一个候选稳定无收益、违反不变量或已取得足够确认依据时停止该臂，不把剩余额度转成重复样本。
4. **研究与线上资源分开。** 用全局 wire 请求/输入输出 token 账本、限流和 deadline 控制实际请求。当前 Harness budget 字段不等于已存在跨进程预算执行器，现有 CLI 也没有通用 `--concurrency`。
5. **扩大案例多样性和独立审核。** M3 生成、模拟和审阅可并行，但共同盲点仍相关；程序 gold、人工校准、新素材留出与真实 UI 是不同证据。独立性不足时保留开放状态。
6. **沉淀可重用数据，而非默认积累 agent 记忆。** 保存合成输入、来源许可、gold/rubric、effective settings、配对身份、失败归属、脱敏调用账本与产出。公开文档不保存密钥、推理正文、受限教材或用户 Vault。

## 7. 下一批研究交付与退出条件

首批完成的定义是：当前反例可复现；并发能力与实际计量经过小规模预检；MQ-01/02/03 每项至多两个候选有同预算对照；结果可归因到检索/推理/效果；有“采用候选 / 放弃 / 证据不足”的决策记录。可在一天内提前完成，不为达到预定时长继续运行。

进入相应研究线前，优先深读 CiteEval、TReMu、LongTutor、Grammar Search、MMTutorBench、Simple Agents 的 PDF 方法与误差分析；需拉取数据时检查授权与 split，记录模型/backbone、预算、是否训练以及人审规模。阅读全文后可以否定这里的迁移假设，不为了追随论文而扩大实现。

最终采用仍需走领域 adapter 与真实 admission→commit→read-back，保持模型 proposal 和应用记录分离。独立质量总门、实际浏览器和适用平台验收由 MQ-10 继续负责；后续额度到账仅扩充已明确产出和退出标准的批次。
