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
| Hatcher 资料留档 | 28 个原始文件逐字节复制、SHA-256 全部通过 | [资料说明](evidence/hatcher-book-pages-2026-09-12/README.md) |

## 从根待办移入的过程记录

2026-09-12：历史第 121 轮停止后，本次用户重新授权了独立并行实验；已完成 284 个真实样本、698 次国内 M3 请求及引用/原文与摘要/跨会话三条优先 lane。原文绑定候选 24/24，数据口径校准后的摘要 16/16；候选仍待独立复核，生产默认未变。完整记录见[并行实验交接](m3-parallel-results-2026-09-12.md)，质量状态仅由独立质量 TODO 维护。

2026-09-12：新增 [Planning、多媒体与多智能体探索](m3-planning-multimedia-results-2026-09-12.md)，完成有界并行与失败复核；强制取证、坐标提示及全量审核均未证明可直接采用的收益，生产默认不变。后续状态仍只维护在独立质量 TODO。


## 从质量待办移入的历史记录

归属根 [TODO](../../TODO.md) 的 `QG-MODEL-QUALITY-001`；旧 `QG-002` / `web-strict-decode-adversarial-v1` 不变。历史真实模型实测已在第 121 轮后停止；2026-09-12 新增[ACL 2025/2026 与 agentic design 研究](agentic-design-research-2026-09-12.md)、[首日 2000M tokens 高并行计划](m3-parallel-exploration-2026-09-12.md)与[当前版本本地诊断](evidence/agentic-preflight-local-2026-09-12.json)，随后已新增[独立可复用运行器](../../tools/model-quality/README.md)及[4 请求 M3 基础设施预检](evidence/m3-parallel-infrastructure-preflight-2026-09-12.json)；随后[自动扩容和 Study/Tavern 领域接入验收](evidence/m3-autoscale-domain-adapters-2026-09-12.json)已完成，Study 发现未写记忆却声称已保存的失败；本次重新授权后已完成[三条优先 lane 并行实验与交接](m3-parallel-results-2026-09-12.md)：284 个真实样本、698 次 M3 请求，原文绑定候选 24/24；独立质量确认仍未完成，也没有持续自动化。首日优先 MQ-01/02/03，MQ-10 贯穿；额度是上限，按足以决策的小批执行。生产已采用项见[正式文档](../model-runtime-quality.md)，接手方法见[研究摘要](research-summary.md)。

本次[真实请求容量测量](evidence/m3-live-concurrency-capacity-2026-09-12.json)使用生产 Tavern prompt/schema 与重复合成短样本：4 并发两个有效窗口共 201 请求，全部 HTTP 200，约 96 请求/分钟，窗口 P95 为 3.69–4.03 秒；8 并发约 47 秒内 147 请求出现 1 次 HTTP 429，已停发，未测 16/32/64。供应商硬限制仍未知，429 不能区分并发、RPM 或 TPM；该结果不外推到长 Study/Planning 或图片。前两次仪器修正前的 156 请求窗口不足，保留成本与失败分母，不计为有效容量证据。该轮结束时保留 provider_overload；本次经审计恢复并降低到固定 4 并发/60 RPM，最终累计账本 1,242 次、7,892,181 charged-or-reserved、0 在途。历史限流/未知预留保留，质量门不变。

2026-09-12 生产候选实现：独立引用分词与显式原文来源绑定已落地工作区，见 [实现与验收](m3-production-grounding-2026-09-12.md)。发布门禁与 3 例真实 SDK smoke 通过；不据此关闭独立质量/正式留出/平台验收票。


2026-09-12 Planning/多媒体后续授权实验已完成，见[本轮总报告](m3-planning-multimedia-results-2026-09-12.md)：77个实验记录、154请求尝试（142 HTTP200、12实验请求HTTP400），519,988已知tokens，峰值4。MQ-04/05：Plan 12/12生命周期通过，但强制取证无稳定内容收益；需区分条件遗漏、来源外扩展与无依据教材结构断言，并修正概率目标的诱导口径。MQ-07/09：填空错误作答和PDF高亮通过，单选2例uncertain，图片框选/坐标提示未过定位门。MQ-10：同模型角色校准三臂各4/4有限字段通过、首稿已经正确，额外审核未证收益；图表交付完整性尚未纳入rubric。同任务另一子agent重算图像与复核来源，不等同外部独立留出。候选均未晋级、默认配置不变、无持续实测；未来只读专项审核与OCR坐标映射仍为研究建议。
