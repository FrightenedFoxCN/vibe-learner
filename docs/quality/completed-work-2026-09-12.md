# 2026-09-12 已完成工作归档

本页从活动待办中收拢已完成的过程记录。这里的“完成”指指定实验、修复或资料留档完成，不关闭 MQ-01 至 MQ-10、平台验收或生产采用门。原始报告、失败样本和源码保持原位。

## 完成事项与证据

| 事项 | 已完成范围 | 证据 |
| --- | --- | --- |
| 三条优先实验与运行器 | 284 个样本、698 次请求及交接；候选仍待独立质量确认 | [总报告](m3-parallel-results-2026-09-12.md) |
| Planning / 多媒体探索 | 77 条记录、154 请求尝试；有界实验结束 | [报告](m3-planning-multimedia-results-2026-09-12.md) |
| Bridge 工具 index 投影修复 | 复用生产规范化、代码复核、有限真实提交与重启读回 | [修复和实测](m3-grounding-repair-results-2026-09-12.md)、[独立源码复核](m3-bridge-artifact-independent-review-2026-09-12.md) |
| 实验图表制品完整性 | 源数据绑定、真实 SVG / HTML / JSON 交付、双题校验及 live 浏览器检查 | [实现](m3-artifact-completeness-2026-09-12.md)、[后续实测](m3-grounding-repair-results-2026-09-12.md) |
| 图像定位诊断 | 合成与自然图共 50 个请求；保留候选选择和 mask 失败，不晋级生产 | [结果](m3-visual-grounding-results-2026-09-12.md) |
| Hatcher 测试素材 | 四张实际测试页、四张事前标注图与两份坐标清单；整书和未选页面已移除 | [资料说明](evidence/hatcher-book-pages-2026-09-12/README.md) |
| 数学书页定位、Reflection 与 DocLayout-YOLO | 坐标网格负面结果归档；Picture 母框 8/8 containment，M3 母框内细化严格 6/8；生产默认未变 | [书页定位报告](m3-book-grounding-results-2026-09-12.md) |

## 从根待办移入的过程记录

2026-09-12：历史第 121 轮停止后，本次用户重新授权了独立并行实验；已完成 284 个真实样本、698 次国内 M3 请求及引用/原文与摘要/跨会话三条优先 lane。原文绑定候选 24/24，数据口径校准后的摘要 16/16；候选仍待独立复核，生产默认未变。完整记录见[并行实验交接](m3-parallel-results-2026-09-12.md)，质量状态仅由独立质量 TODO 维护。

2026-09-12：新增 [Planning、多媒体与多智能体探索](m3-planning-multimedia-results-2026-09-12.md)，完成有界并行与失败复核；强制取证、坐标提示及全量审核均未证明可直接采用的收益，生产默认不变。后续状态仍只维护在独立质量 TODO。


## 从质量待办移入的历史记录

归属根 [TODO](../../TODO.md) 的 `QG-MODEL-QUALITY-001`；旧 `QG-002` / `web-strict-decode-adversarial-v1` 不变。历史真实模型实测已在第 121 轮后停止；2026-09-12 新增[ACL 2025/2026 与 agentic design 研究](agentic-design-research-2026-09-12.md)、[首日 2000M tokens 高并行计划](m3-parallel-exploration-2026-09-12.md)与[当前版本本地诊断](evidence/agentic-preflight-local-2026-09-12.json)，随后已新增[独立可复用运行器](../../tools/model-quality/README.md)及[4 请求 M3 基础设施预检](evidence/m3-parallel-infrastructure-preflight-2026-09-12.json)；随后[自动扩容和 Study/Tavern 领域接入验收](evidence/m3-autoscale-domain-adapters-2026-09-12.json)已完成，Study 发现未写记忆却声称已保存的失败；本次重新授权后已完成[三条优先 lane 并行实验与交接](m3-parallel-results-2026-09-12.md)：284 个真实样本、698 次 M3 请求，原文绑定候选 24/24；独立质量确认仍未完成，也没有持续自动化。首日优先 MQ-01/02/03，MQ-10 贯穿；额度是上限，按足以决策的小批执行。生产已采用项见[正式文档](../model-runtime-quality.md)，接手方法见[研究摘要](research-summary.md)。

本次[真实请求容量测量](evidence/m3-live-concurrency-capacity-2026-09-12.json)使用生产 Tavern prompt/schema 与重复合成短样本：4 并发两个有效窗口共 201 请求，全部 HTTP 200，约 96 请求/分钟，窗口 P95 为 3.69–4.03 秒；8 并发约 47 秒内 147 请求出现 1 次 HTTP 429，已停发，未测 16/32/64。供应商硬限制仍未知，429 不能区分并发、RPM 或 TPM；该结果不外推到长 Study/Planning 或图片。前两次仪器修正前的 156 请求窗口不足，保留成本与失败分母，不计为有效容量证据。该轮结束时保留 provider_overload；本次经审计恢复并降低到固定 4 并发/60 RPM，最终累计账本 1,242 次、7,892,181 charged-or-reserved、0 在途。历史限流/未知预留保留，质量门不变。

2026-09-12 生产候选实现：独立引用分词与显式原文来源绑定已落地工作区，见 [实现与验收](m3-production-grounding-2026-09-12.md)。发布门禁与 3 例真实 SDK smoke 通过；不据此关闭独立质量/正式留出/平台验收票。


2026-09-12 Planning/多媒体后续授权实验已完成，见[本轮总报告](m3-planning-multimedia-results-2026-09-12.md)：77个实验记录、154请求尝试（142 HTTP200、12实验请求HTTP400），519,988已知tokens，峰值4。MQ-04/05：Plan 12/12生命周期通过，但强制取证无稳定内容收益；需区分条件遗漏、来源外扩展与无依据教材结构断言，并修正概率目标的诱导口径。MQ-07/09：填空错误作答和PDF高亮通过，单选2例uncertain，图片框选/坐标提示未过定位门。MQ-10：同模型角色校准三臂各4/4有限字段通过、首稿已经正确，额外审核未证收益；图表交付完整性尚未纳入rubric。同任务另一子agent重算图像与复核来源，不等同外部独立留出。候选均未晋级、默认配置不变、无持续实测；未来只读专项审核与OCR坐标映射仍为研究建议。

2026-09-13 按用户更正暂缓 multimodal，新增[纯文本迭代与多智能体早停记录](m3-text-iteration-results-2026-09-13.md)：8 个全新开发 family、三个单请求臂共 24 次 M3 请求、36,294 reported tokens、无 unknown usage。约束清单在一个无依据 `chart_questions` 错误上形成净修复；另四个原始失败经审计属于时间格式或否定语境 rubric 问题。因真实 baseline 错误仅一例，按早停规则未运行 reviewer/self-revise，未改生产默认、未引入小模型。

同日第二轮使用另外 12 个 entity/source-disjoint family，对 baseline 与约束清单共发 24 次请求、31,201 reported tokens、无 unknown usage。自动结构检查两臂均 12/12；逐份人工语义审查为 baseline 10 pass/2 minor、约束清单 8 pass/4 minor，后者的解释性扩写反而引入更多无依据上下文。无双例错误簇，故未启动多智能体 reviewer；约束清单淘汰，默认不变。逐例证据仍见[同一报告](m3-text-iteration-results-2026-09-13.md)。

同日第三轮在另外 12 个新 family 上比较 baseline 与 source-minimal，共 24 次请求、34,444 reported tokens。逐句人工审查为 baseline 4 pass/6 minor/2 major、候选 9 pass/2 minor/1 major；候选虽修复两个 baseline major，却新增把计划记录变成真实滤芯作业的 major，故不直接晋级。随后仅冻结回放两个 baseline major：等两 wire 的 self-revision 与 same-model specialist→repair 共 8 次 HTTP 200、13,016 tokens。自动结构 4/4，但人工去标签复核两臂均 0/2 修复；specialist 多 17.0% tokens、无独有净贡献，已早停。论文只提供 evaluator-optimizer、错误分类恢复与边际裁剪的研究路径，不作为复现或收益证据；multimodal 暂缓，生产默认与 Harness 边界均未变。完整证据见[同一报告](m3-text-iteration-results-2026-09-13.md)。

按用户更正，第三轮的 source-minimal 没有因一例候选 major 而终止整条路线，而是保持“不直接晋级”并继续提示级改版。第四批 12 个新 family 中，v1 人工 6 pass/5 minor/1 major，v2 为 9 pass/3 minor/0 major，v2 同时少用 11.0% reported tokens。第五批再用 12 个新 family 比较 v2/v3：人工分别 8 pass/4 minor/0 major 与 9 pass/3 minor/0 major，v3 少用 12.6% tokens；自动 exact facts 中多项失败经逐稿复核是来源支持的角色前缀与 gold 规范化差异，未按关键字判错。v3 仍有完整 span 和台账认识状态 minor，仅保留为独立确认候选；不改生产默认、不重复相似开发测试、不引入小模型。证据见[同一报告](m3-text-iteration-results-2026-09-13.md)。

2026-09-13 实验后采用记录：上述“生产默认不变”是第五批实验收尾时的历史决定；随后用户明确授权将 `source-minimal-v3` 设为生产默认，采用范围仅限 Learning Plan 与 Study Chat。该授权不把开发批次追溯改写成独立留出或生产采用测试，也不关闭 MQ-10：现有证据来自开发合成样本和内部人工语义审查，尚无独立学习效果认证。multimodal 继续暂缓；Tavern、Persona/Scene、Harness schema 及垂域小模型不在本次采用范围内。
