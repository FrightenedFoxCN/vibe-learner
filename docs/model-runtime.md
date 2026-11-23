# 模型运行时行为与边界

本文汇总 Planning、Study、Persona、Document、Tavern 及其共享 Provider 传输层的运行时行为与约束。生命周期与预算配置见 [Harness 工程手册](harness/README.md) 与 [配置与预算](harness/configuration.md)。

## 1. Provider 传输与兼容边界

- **统一瞬态重试**：`ProviderTransport` 统一管理 LiteLLM Chat Completion / Responses / Embedding 的瞬态重试（覆盖超时、网络错误与 `408/409/425/500/502/503/504`，最多重试 2 次）；Chat Completion 关闭 SDK 内部重试以避免重试倍增；限流（`429`）与非法载荷直接暴露原因。
- **截止时间检查**：每次 Provider 尝试前检查剩余有效期限；已发出的同步 HTTP 请求受其传输超时限制（仅 Tavern 的兼容 Chat 适配器支持本地连接取消）。
- **工具调用信封兼容**：SDK 适配层剥离完整工具调用信封中的合法非负整数 `index` 字段，保留原 ID、顺序与参数；非法索引、不完整调用、额外身份或未知字段交由严格解码器拒绝，不拼装流式片段。
- **安全错误投影**：工具错误与预算拒绝保留强类型错误码与修复路径，不向前端或日志泄漏原始敏感载荷。

## 2. Planning 运行时规则

- 生产默认文本策略为 `source-minimal-v3`（登记为 `LearningPlanPrompt@planning-prompt-v8`），输出提案为 `LearningPlanProposalV3`，详见 [学习计划链路与契约](learning-plan.md)。
- 每轮 Provider 请求固定 `max_tokens = 8192`，覆盖初始工具选择、最终生成与严格修复轮。
- 详情摘录先按修订后 Study Unit 页范围限定，再匹配来源 Section；无本地证据时返回空，不以父 Section 开头冒充；跨页 chunk 保留真实页范围。
- 页文本工具严格计入首个超长 chunk 与段落分隔符的字符预算；图片工具在分配页码前校验并限制页范围，整轮工具回执完成后再附加图像证据。
- 严格提案修复保留已获取的工具证据与图像，并与提交阶段共享同一套章节不变量校验；修复提示明确区分应用时间戳与学习时长。
- 宽跨度信号仅在“至多 2 个单元且跨度 ≥ 80 页”或子标题稀疏时触发，不因单元数量少单独扣分。`estimate_plan_completion` 仅评估源教材结构元数据，不认证计划内容质量。

## 3. Study、记忆检索与教材引用

- 生产默认文本策略为 `source-minimal-v3`（登记为 `StudyChatPrompt@study-chat-prompt-v3`）：在保持来源限定、认识状态与时间语义的前提下做最小改写；仅可如实陈述已成功执行的工具效果，不得把未执行、失败或不确定的工具结果表述为已完成事实。
- 互动题回复清理保留 Markdown 空白；模型显式返回 `interactive_question = null` 时不回填工具草稿。
- 开启多模态时，PDF 图像工具的本地渲染结果直接附入模型消息；公开 Trace 仅保留元数据，不含原图。
- 场景查询工具返回应用级场景/物品 ID 及父子关系，场景与物品列表上限均为 128 项，截断显式标记并受 Provider 字节预算约束。
- **记忆检索与摘录**：保留领域来源、说话者与原始记录时间；学生原文摘录上限 800 字符、助手上限 160 字符。原文选择器在 800 字符预算内按查询提取句子邻域与多处窗口（属于原文检索而非模型摘要，远距离限定或否定关系可能不在窗口内）。
- **词法回退检索**：当 Embedding 不可用时，使用稳定散列、Unicode/重音规范化与中文 bigram 执行确定性词法回退（与 Python hash seed 无关），不宣称等价于语义检索。
- **教材引用**：无文档、无 chunk 或零词法命中时不编造页码/单元范围，仅对命中 chunk 排序去重（词法命中不证明逻辑蕴含）。

## 4. 可选 PDF 图形版面候选（默认关闭）

Study Chat 提供只读工具 `read_projected_pdf_layout_candidates`，为当前投射 PDF 的单页返回 `Picture` 与独立 `Formula` 候选框（正文与行内公式继续走 OCR 文本定位）。模型选定候选后仍调用 `annotate_projected_pdf_region`，无新增写效果或前端 DTO。

- **实现与隔离**：通过独立外部 Python 子进程调用 DocLayout-YOLO（对 `Picture` 母框递归一次并执行 NMS），最多返回 32 个候选；原页、编号候选页与母框联系表仅作为 Provider 图像证据（最多 3 张），不进入公开结果或 Trace。
- **启动配置**（不随运行时设置热切换，默认 `VIBE_LEARNER_DOCUMENT_LAYOUT_ENGINE=disabled`）：

```bash
VIBE_LEARNER_DOCUMENT_LAYOUT_ENGINE=doclayout-yolo
VIBE_LEARNER_DOCUMENT_LAYOUT_PYTHON=/path/to/isolated/python
VIBE_LEARNER_DOCUMENT_LAYOUT_MODEL_PATH=/path/to/doclayout_yolo_doclaynet.pt
VIBE_LEARNER_DOCUMENT_LAYOUT_MODEL_SHA256=<reviewed-sha256>
VIBE_LEARNER_DOCUMENT_LAYOUT_TIMEOUT_SECONDS=90
```

worker 异常、坐标越界、未知标签或权重 SHA-256 不匹配均返回类型化不可用结果。

- **许可证边界**：本仓库许可证为 GPL-3.0；上游 DocLayout-YOLO 代码为 AGPL-3.0，权重卡标注 Apache-2.0，上游 DocSynth300K 数据卡未声明明确许可证。因此该引擎保持默认关闭且通过外部子进程隔离；若用于分发或网络托管，须先独立复核 AGPL-3.0 源码提供义务与训练数据许可。

## 5. Persona、OCR 与 Tavern 上下文

- **Persona 嵌套校验**：Persona Card 嵌套结构的严格 Schema 校验纳入既有恢复预算（`persona-generation-harness-v2`），Chat/Responses 每次传输最多两次调用，JSON 与嵌套校验共享额度，不补造字段或 ID。
- **OCR 语言证据**：OCR 仅在引擎返回实际识别证据时报告检测语言，不把配置语言冒充为检测结果。
- **Tavern 长历史预检**：在预算上限内减少重复序列化，按确定性规则保留最长合法历史后缀，保持全量快路径与空历史错误优先级不变。
