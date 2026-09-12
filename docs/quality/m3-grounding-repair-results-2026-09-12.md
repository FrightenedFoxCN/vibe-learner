# M3 Bridge、教学制品修复与论文方法定位实验

2026-09-12，依据用户要求优先补齐实验 Bridge 和教学制品完整性，同时推进定位优化实验。此文随本轮证据完善；生产默认模型和应用代码未修改。

## 已完成的修复

### Bridge 与生产响应规范化

实验 Bridge 现在直接复用生产 `_normalize_completed_tool_indexes`。只移除完整工具调用上的合法整数 index；未知字段、非法 index、缺失参数及工具输入仍接受原有严格拒绝。原始 wire 形状与 usage 在投影前计量，不增加隐藏重试，不存储完整 provider 正文/推理。

四项针对性回归通过：与实际 ProviderTransport 输出一致、原对象不变、非法字段继续拒绝、WireFailure/GateClosed不重试，以及带原生 index 的实际 Study写入、receipt和重启读回。另有[未编写实现的子agent复核](m3-bridge-artifact-independent-review-2026-09-12.md)。

新实测选择旧材料中的2个Planning、4个多媒体样本：15请求、88,948 reported tokens。Planning 2/2提交并重启读回。多媒体6个工具调用的合法index被生产规则投影，图片两例均成功调用工具并提交；其中一个定位通过、另一个仍失败。单选一例仍最终载荷uncertain，另一例真实创建、选择A评分正确并重启一致。

该成功单选的原始严格评分仍为candidate_failed：旧规则只接受裸`4`或`x=4`，实际正确选项是“该方程的解为 $x=4$，与教材中的结论一致”。[派生审核](evidence/m3-grounding-repair-2026-09-12/bridge-artifact-audit.json)记录此评分口径错误，原样本状态未改。另一个单选uncertain说明原index问题不能解释全部失败。

**历史解释修正：**上一轮`provider_tool_call_shape_invalid`混入了Bridge绕过生产规范化的实验路径差异；不能直接写成生产M3工具兼容缺陷，也不能用受其影响的少量编排对照判模型优劣。历史源快照、请求费用和失败均保留，不重写旧结果。此修复实现响应投影一致性，不宣称整个native实验Bridge等价于原LiteLLM SDK认证。

### 教学制品完整性

[完整说明](m3-artifact-completeness-2026-09-12.md)。受控图表任务从公开source-data生成实际SVG和数据文件，类型化任务要求绑定两道题；应用生成HTML交付页，模型不拥有路径、digest或制品身份。检查真实文件、源数据重渲染、HTML引用、问题完整性及JSON交付bundle。缺图、漏题、错标签、未交付引用和同步篡改内容/hash均拒绝。

真实M3三臂（一次生成、自检、审核修订）3/3完成有图的交付，共7请求、9,776 reported tokens。三个结果都交付最大值题与C减A题，没有用评分gold生成图，也没有把自由草稿当最终网页。历史v5三个无制品chart样本仅派生重审为delivery_unproven。

[实际live交付预览](evidence/m3-grounding-repair-2026-09-12/role-chart/learner.html)及[完整JSON bundle](evidence/m3-grounding-repair-2026-09-12/role-chart/artifact-bundle.json)。这是受控实验chart-reading交付；任意自然语言题目的通用依赖识别、生产所有附件类型并未因此通过。

两个修复的9个实测样本合计22请求、98,724 tokens，三批执行源码已冻结；终态resume均零新增请求，未重放uncertain。

## 论文依据和定位实验

用户指定[Image Generators are Generalist Vision Learners / Vision Banana](https://arxiv.org/abs/2604.20329)已实际阅读方法、评估和附录，并目视关键页面；同时核对Grounded Segment Anything论文、代码及GroundingDINO/SAM2官方加载路径。详见[论文与实现研究](m3-visual-grounding-research-2026-09-12.md)。

Vision Banana是经过视觉任务微调的图像生成器→RGB任务输出→确定性解码，官方项目当前未发现可运行权重/代码。它的连通域是生成mask的解码，不等于对自然照片做颜色连通域即可复现。可借鉴的是presence判定、指称改写、视觉输出与确定性坐标/掩码映射的职责划分。

本轮对照将明确区分：真实Tesseract OCR行框和合成几何组件的SoM-inspired方案；真实预训练GroundingDINO tiny→SAM2 tiny的检测/分割；M3直接预测框。前者不称通用object recognition，后者不将模型置信度或预测IoU冒充标注真值精度。自然图人工box gold不来自任何待测模型，样本许可和输入量化变换均记录。

## 第一批定位对照：OCR/组件候选与SoM选择

4个先行smoke与完整24样本分别保留。完整批为12个合成开发场景×两臂，其中5文字、3几何、1柱图、2无目标、1重复目标歧义。两臂同原PNG和请求；SoM额外获得编号候选图，并把输出从坐标改成region ID，由应用确定性映射。因而这是工作流比较，不是M3纯视觉能力提升证明。

| 完整24样本指标 | M3直接框 | OCR/组件 + M3选择 |
|---|---:|---:|
| 任务联合通过 | 7/12 | 12/12 |
| 文字定位 | 1/5 | 5/5 |
| 几何定位 | 3/3 | 3/3 |
| 柱图最高柱 | 0/1 | 1/1 |
| 无目标/歧义正确弃答 | 3/3 | 3/3 |
| M3请求 | 12 | 12 |
| reported tokens | 9,958 | 12,131 |

候选臂多2,173 tokens（约21.8%）；其中检测器真实读取PNG，通过Tesseract TSV和饱和像素组件产生区域，未读取生成时gold。所有9个positive的候选召回都达本次阈值，故这批尚未验证目标存在但检测器漏检的处理。另设此类失败诊断，不能把未找到候选直接等同目标不存在。

另一子agent独立重算24条IoU/覆盖率/通过状态，并重跑12张PNG检测和标记；候选、图像字节/摘要与wire输入一致。该复核仍为同任务辅助复核，不是独立留出。Direct也为审核目的运行了本地detector，样本墙钟时间因此不能直接当作纯M3生产延迟；CPU检测与provider耗时需分开解释。

![左为直接框，右为候选选择后的确定性映射](evidence/m3-visual-grounding-20260912/synthetic-comparison.png)

真实浏览器也已验证修复后的live图表交付：SVG实际加载尺寸310×310，两题DOM内容准确可见，无评分材料泄露。[截图](evidence/m3-grounding-repair-2026-09-12/role-chart/browser.png)和[验收数据](evidence/m3-grounding-repair-2026-09-12/role-chart/browser-acceptance.json)均保存；这不替代生产Study UI验收。
