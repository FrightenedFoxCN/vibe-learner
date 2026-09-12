# 图像定位改进实验设计（准备中）

本文件记录未启动 live 的实现准备。用户随后指定论文 `2604.20329` 与 grounding-segment-anything，研究 agent 正在核查；当前路线只是无模型权重的工程 baseline，不能称上述论文复现。等待研究结果再冻结配置。

## 当前可执行路线

- `visual_grounding_fixtures.py` 生成 12 个新 PNG 场景：5 个不同位置、字号或相似字符串的文字任务，4 个几何/柱形图任务，2 个目标缺失和 1 个重复目标歧义任务。均为 640×360，原图及编号图约 1.2–7.1 KiB。这是合成开发分布，不是 12 个真实教材来源。
- `visual_grounding_detector.py` 只接收 PNG bytes，调用真实 Tesseract 5.5.3（eng，PSM 11）TSV 合并行框，以及 OpenCV 饱和像素连通组件；不读取作者绘图坐标、PDF 文本框或 gold。颜色组件只适合此处简单几何候选，**不是语义物体识别**。
- direct 臂让 M3 输出完整原图的归一化 `[x0,y0,x1,y1]`；som 臂给原图与有编号的真实 detector proposals 图，让 M3 仅选择 proposal ID，应用确定性映射回像素。两臂均有 absent/ambiguous 明确弃权结果。
- gold 只用于评分；改变 gold 不改变模型输入的本地测试通过。每个样本记录原图 SHA/尺寸/bytes、实际 wire 输入、proposal 来源和 OCR 版本/耗时、所选区域、像素/归一化映射、IoU、目标覆盖、proposal recall 与弃权。

预设任务门：positive 的 IoU≥0.5 且目标覆盖≥0.8；negative/ambiguous 要返回对应弃权状态。proposal recall 是单独的 detector 指标，不能将不存在合适 proposal 的失败归因于 M3 选框。协议/schema 失败也须单列。当前本地 9 个 positive 的真实 proposal 均达到门槛；这只说明该合成 fixture 对本地 detector 容易，尚无 M3 质量结果。

准备命令为 `python -m vibe_learner.prepare_visual_grounding --budget-from EXISTING_CONFIG --output NEW_CONFIG --fixtures NEW_DIRECTORY --transport fake`，可用 `--cases` 先选少量 smoke。准备器拒绝覆盖既有 config/fixture 路径。live 配置仅由 root 使用共享账本和冻结源码后启动。

## 预算及证据限制

12 场景×2 臂=24 个样本，每个 1 次 wire；首轮先做 provider-free adapter 验证，再由 root 选择 2 场景 live smoke。整批最多 24 次请求，每次 input reservation 100000 + output 2048，即最多 2,449,152 操作预留 tokens；这不是视觉计费上限认证。并发/RPM/TPM/总预算沿用共享账本。每请求最多两张内联 PNG，继续受 transport 4 张、单张 32 KiB/1024² 的硬界约束。

detector 在两臂都运行以获得可比的 proposal recall 诊断，direct wire 不看到检测输出。比较部署成本时应区分 direct 不必承担的辅助检测诊断开销与 SoM 必需的检测/标注开销，并比较实际 tokens/耗时；不得只用相同 wire 数宣称等成本。

后续若引入真实物体图片，必须记录图片出处及许可、原图与实际输入图 SHA、缩放/量化过程，并独立标注 gold。真实图片不得以简单颜色组件的合成成功替代 GroundingDINO/SAM 等检测/分割能力。只有显示改进后，再进入少量实际 Study tools admission/commit/read-back 验收；当前 adapter 明确 proposal-only，不制造 Harness adoption 证据。

## 本地检查

`test_visual_grounding.py` 覆盖严格 JSON/坐标/弃权、实际 OCR 和图像界限、gold 隔离、确定性评分及依赖 manifest。依赖 manifest 包含脚本、字体、Tesseract executable/eng traineddata 哈希和 Pillow/OpenCV/Numpy 版本。不修改生产模型、schema、共同 transport 或其他 lane 文件。
