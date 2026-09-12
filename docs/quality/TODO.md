# 模型质量待办

归属根 [TODO](../../TODO.md) 的 `QG-MODEL-QUALITY-001`；旧 `QG-002` / `web-strict-decode-adversarial-v1` 不变。已完成的实验、容量测量及修复记录见[阶段归档](completed-work-2026-09-12.md)。生产已采用项见[正式文档](../model-runtime-quality.md)，接手方法见[研究摘要](research-summary.md)。当前没有持续自动化，不自动继续真实模型调用。

每项关闭都需保留失败分母、生产实际配置和 commit/read-back 证据；schema、提交、语义、人格、渲染、成本分别评分。独立复核前不关闭总质量门。

| 状态 / ID | 问题与下一步 | 保留证据 | 关闭标准 |
| --- | --- | --- | --- |
| [ ] MQ-01 引用 | 无兜底后仍会因函数词/子串给无关教材引用；中文整段 token 丢召回。本轮 24 对来源 selector 重放中候选命中相关 12/12、无关弃引 12/12，但只有单页易判定材料；真实未提交结果不算弃引成功，仍需多页与独立蕴含复核。 | [词法反例](evidence/minimax-citation-tokenization-v1.json)、[最新写入对照](evidence/minimax-memory-write-pairs-v1.jsonl) | 中英法相关/无关/否定留出案例，真实 Study 的引用精度与召回分别复核，保留不确定与无来源情况。 |
| [ ] MQ-02 原文和写入状态 | 逐字模式改变 U+2019 标点却声称完全一致；模型最终仍说 committed=false；写入可能新增原文没有的地点/生效时间。本轮明确原文绑定 24/24，baseline 19/24；摘要需先固定字段语义，校准后两臂均 8/8，不能据此关闭。 | [写入 rubric](evidence/minimax-memory-write-rubric-v1.json)、[四组实测](evidence/minimax-memory-write-pairs-v1.jsonl)、[效果审计](evidence/minimax-study-memory-write-audit-v1.json)、[领域接入验收：2 例未调用记忆工具却声明已保存](evidence/m3-autoscale-domain-adapters-2026-09-12.json) | 独立数据库比较摘要/逐字模式；按字符核对逐字结果，核对事实与效果 receipt；区分 Turn 持久化和专门记忆写入，不将泛称“记下”一律误判。 |
| [ ] MQ-03 记忆检索与时间关系 | 原文窗口可能漏远处更新、否定或长句限定；压缩混并取消/归档和记录/事件时间。本轮 30 事件场景两臂锚点均覆盖，57 个已提交回答目标事实经非独立辅助复核吻合；JSON 格式/载荷失败单列，不证明大历史已通过。 | [选择器边界](evidence/minimax-memory-selector-limits-v1.json)、[邻域回退反例](evidence/minimax-memory-neighborhood-backoff-v1.json)、[时间追问](evidence/minimax-temporal-followup-v1.jsonl)、[隔离样本](evidence/minimax-study-event-isolated-v1.jsonl) | 分开检索/读取/写入错误，覆盖中段更新、重新启用、未知时间、多对象关系；保留种子失败，禁止跨样本串答案；新对象留出复核。 |
| [ ] MQ-04 Planning 来源、时长与人格 | 图片可改善取证，也会把同一译文续接当成双译本、混淆正文评论/译注，法文数学及物理/印刷页码仍错；活动时长与任务不一致。 | [图片×人格](evidence/minimax-book-persona-image-pairs-v1.jsonl)、[方法槽对照](evidence/minimax-planning-method-only-review-v1.json)、[法文短源](evidence/minimax-french-short-native-pairs-review-v1.json)、[中文 OCR 对照](evidence/minimax-babel-native-ocr-review-v1.json)、[初始时长候选](evidence/minimax-babel-initial-timing-review-v1.json) | 同源图片有/无×人格方法交错对照；核对实际图片输入、来源、页码、活动分钟及人格与活动的关系，提交率不能代替专家内容评审。 |
| [ ] MQ-05 工具调度与成本 | 重复修订、估分、错误恢复和长书超时；硬性收束、tool_choice=none、提高分辨率或预算未证明稳定收益。 | [长书工具策略](evidence/minimax-french-tool-policy-pairs-review-v1.json)、[收束对照](evidence/minimax-french-finalization-pairs-review-v1.json)、[自然修复](evidence/minimax-natural-backtrack-review-v1.json) | 保持输入与限额可比较，计入失败、修复、首次成功、端到端 P50/P95 与完整内容质量；实际 wire 行为匹配声称的调度。 |
| [ ] MQ-06 人格与 Markdown 指令 | 教師人格扩大或拒绝记笔记任务、误认第三方、添加讲解/邀请；格式提醒迁移不稳定，Tavern 会编造关系/共同经历。 | [范围候选](evidence/minimax-study-scope-pairs-v1.jsonl)、[人格边界](evidence/minimax-persona-task-boundary-review-v1.json)、[Tavern 迁移](evidence/minimax-tavern-grounding-transfer-review-v1.json)、[格式对照](evidence/minimax-study-format-pairs-v1-grade.json) | 正常/冲突指令和不同人物关系的留出对照；人格措辞与任务权限分开审查；真实浏览器检查列表、围栏、公式及其他所用 Markdown。 |
| [ ] MQ-07 Study 题目、工具与视觉定位 | 填空题可能提前泄露答案，工具模板/缺省回填需语义审查；坐标网格已归档为负面结果。书页 `Picture` 母框内细化在开发集严格 6/8；默认关闭的纯读候选工具与 Harness 组件已接入，仍缺页面隔离留出和真实生产 provider acceptance。 | [填空复核](evidence/minimax-study-fill-blank-review-v1.json)、[工具覆盖](evidence/minimax-tool-coverage-v1.json)、[定位网格](evidence/minimax-study-grid-review-v1.json)、[书页定位与 DocLayout-YOLO](m3-book-grounding-results-2026-09-12.md)、[计划确认](evidence/minimax-study-plan-confirmation-review-v1.json)、[续接](evidence/minimax-study-follow-up-delivery-review-v1.json) | 逐工具确认实际执行和领域效果，题目提交前不泄漏答案、正确/错误答案语义验证；视觉定位按 OCR 文本/单字符与 Picture/Formula 候选分流，在页面隔离留出上复核递归候选和母框内回退。覆盖记录不是全部 32 个 Study 工具质量认证。 |
| [ ] MQ-08 缓存与压缩 | 静态前缀没有证实稳定收益；摘要生成/读取有成本且可能损失状态，未采用生产模型压缩器。 | [缓存对照](evidence/minimax-study-cache-pairs-v1.jsonl)、[摘要复用](evidence/minimax-memory-reuse-review-v2.json)、[时间压缩](evidence/minimax-temporal-compression-4096-v2.jsonl) | 控制冷暖、前缀、配置和调用顺序，记录实际 cached_tokens（缺失为未知）、全部摘要/回查成本及事实保留率；不以 token 减少推导计费或时延改善。 |
| [ ] MQ-09 OCR 与图片生成接入 | macOS Vision 仅有本机诊断，未进入 Document 生命周期/打包；M3 图片理解不等于 image-01 生成能力。 | [Vision](evidence/minimax-native-vision-ocr-review-v1.json)、[解析诊断](evidence/minimax-babel-native-parse-diagnostic-v1.json)、[官方能力](evidence/minimax-official-capability-review-v1.json) | 真实 admission→解析/效果→read-back、语言/版面复核及平台打包；图片生成另做 provider 适配和受保护制品授权验收。 |
| [ ] MQ-10 独立质量基线 | 当前为维护者/模型探索；本轮补齐明确 rubric、失败/未知分母、源码快照、108 回答辅助复核与数据口径校准，但仍是非独立、非盲、多轮复用开发样本，不能称 held-out 或全平台验收。 | [历史观察与失败](evidence/research-notes.md)、各行原始 JSON/JSONL 及 rubric | 新增未参与改写的案例，独立校准 grader，分离数据/基础设施/评分器与候选失败；完成真实前端和适用平台验收后才关闭总票。 |

所有历史上下文见[保留研究证据](evidence/research-notes.md)。其中旧版问题已修复的部分用于解释混合实验，不能重复挂为新工程缺陷；若需处理，应先在当前版本复现。

## 当前修复边界与剩余验收

- MQ-04/05：Planning 强制取证未证明稳定内容收益；历史工具形状失败混入 Bridge 投影差异，不能直接归因于生产模型。Bridge 修复与有限实测已完成，仍需来源、时长与独立内容复核。
- MQ-07/09：实验级图表完整交付、双题约束和浏览器显示检查已完成；书页 Picture 母框内细化从原始 Direct 0/8 提升到 6/8，但仍有小元素框过小，且只在开发集测试。生产 Study UI、通用附件和 OCR 接入未因此通过。
- MQ-10：保留历史失败分母和派生重审；同任务代码复核与小批实测不替代独立留出验收。图表旧样本缺交付的口径已修正，不再将其列为尚未补齐的实验基础设施。

对应证据与已完成范围见[阶段归档](completed-work-2026-09-12.md)。
