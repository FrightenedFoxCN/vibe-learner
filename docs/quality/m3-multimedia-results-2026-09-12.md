# M3 多媒体教学与坐标优化实验（2026-09-12）

本轮 16 个真实 Study 样本共 44 次国内 MiniMax-M3 HTTP 200 请求、271,404 provider total tokens；未知 usage 为 0。复用既有累计 ledger，没有更换生产默认模型、环境文件或生产 schema。六种操作使用同一份合成方程来源，追加坐标实验也复用已曝光图片，**仅为开发诊断，不是六个独立质量来源或留出验证**。

## 结果

第一批 6 操作 × baseline/evidence-first，共 12 样本；通过 6、候选失败 4、uncertain 2。所有 10 个已提交 Turn 的 receipt、Session 和容器重启读回一致。模型文字成功不替代工具 ok、typed effect 或实际投影状态。

| 操作 | baseline | evidence-first |
|---|---|---|
| 单选题 | invalid_payload，uncertain，无题目提交 | 同左 |
| 填空题 | 题目和评分材料正确；提交 999 被判错，答题后重启一致 | 同左 |
| PDF 投射、文字读取 | 投射成功，但未执行明确要求的 read_projected_pdf_content | 两个工具成功并提交 |
| PDF 原文高亮 | 投射、高亮、保留效果及重启通过 | 同左 |
| 图片框选 | 工具与投影效果已提交，但目标覆盖率和 IoU 均 0 | 同左 |
| 图片框选后清除 | 所需三工具成功，清除后持久化状态正确 | tool shape 校验拒绝，模型如实说明操作未生效 |

填空公开 prompt/回复未发现显式答案泄漏；服务端 accepted_answers 含正确答案 4，公开 grading 字段已隐藏。真实单选创建未成功，因此本轮没有真实单选正确作答的验收结论。provider-free adapter smoke 曾验证单选正确回答 API 与重启，仅属于基础设施验证。

图片真实通过生产附件入口送入模型。第一批 14 次请求带图，追加批 9 次请求带图；每次计量图片 SHA-256、尺寸与数量，原图为 360×200、4,255 bytes PNG。图片框选的业务模型采用 0..1 归一化坐标。真实目标 y 范围约 .296–.461，而第一批 baseline 框 y=.13、height=.10，候选框 y=.16、height=.08，均在文字上方。

![绿色为目标文字框，红色为模型实际持久化框](evidence/m3-multimedia-localization-20260912.png)

第二批只改请求，明确完整原图左上原点及宽 360/高 200 的归一化换算，没有提供目标位置。baseline 与 coordinate-frame 各 2 次，共 4 样本，均未通过定位门。baseline 一次错误框、一次工具 shape 被拒绝；coordinate-frame 一次工具 shape 被拒绝，另一次目标覆盖率 .612、IoU .256，仍低于预定 .8/.45。**坐标解释不足以稳定修复定位，不能采纳为已验证优化。**

工具 shape 失败均记录为 `provider_tool_call_shape_invalid`；错误 trace 出现不是工具成功。第一批单选 `study_chat_uncertain_chat_model_invalid_payload` 保留原状态，不自动重试。HTTP 200 不能证明模型载荷通过完整严格解码。

## 功能和边界

- 已真实检查：PDF 附件持久化、投射、原文读取/高亮；PNG 附件持久化、图像输入、投射、区域标注/清除；填空创建、公开答案隔离、错误答案提交、重启。
- 已发现失败：单选最终载荷、图片坐标定位、部分完整工具调用形状、明确指定工具遗漏。
- 未测试：复杂教材图表、多页跨页关系、真实浏览器展示、真实学生学习增益、音频/视频、图片生成。M3 图片理解不能当成 image-01 生成能力；生产图片生成能力匹配未覆盖 M3，实验 Responses/embedding 旁路禁止，没有调用其他付费 provider。
- Study v3 trace 的 `primary_output_only` 证明 Session/Turn；附件与投影额外核对实际附件、typed projection effect、公开投影状态和重启。这里没有把 Turn 提交解释成所有外部效果的 exactly-once。
- evidence-first 是用户消息提示条件，未新增真实独立 agent。总体多角色实验由本轮其他 lane 单独记录，不能将这里 4 个 worker 或多个工具误称应用已有并行教学 agent。

## 复现与证据

适配器：[multimedia.py](../../tools/model-quality/integrations/vibe_learner/multimedia.py)、[准备器](../../tools/model-quality/integrations/vibe_learner/prepare_multimedia.py)。机器审核：[m3-multimedia-audit-20260912.json](evidence/m3-multimedia-audit-20260912.json)。运行目录为 `tools/model-quality/runs/planning-multimedia-20260912/`，分别为 `multimedia-run` 与 `image-coordinate-run`，均使用 `tools/model-quality/runs/m3-window-20260912.sqlite3`。

第一批 35 wires / 212,455 tokens，wire P50/P95 2,903/11,475 ms；第二批 9 wires / 58,949 tokens，4,192/13,169 ms。小样本与缓存命中不能用于吞吐或价格推断。实验为同资源窗口共享最多 4 个在途请求，不据此声称供应商容量上限。

执行源码快照分别 `multimedia-source.zip`（SHA-256 `c64f5b9e8ab03229a6347b72fd9580d7b362651f1b1fffb1b377c6b556f96b21`）及 `image-coordinate-source.zip`（`f1d4743488a9833e4a548fcbb37329132bdb3223d2ee0f95cd353c418f37f8b9`），各 216 文件。第一批 resume 因并行角色适配/文档变更引起 source digest 不同而拒绝，新增 wire 为 0；没有伪造旧 manifest。第二批终态 resume 接受，wire 保持 9，没有重新执行失败样本。
