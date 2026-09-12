# M3 图片定位：论文实现依据与本机可执行路线

日期：2026-09-12。范围：补充图片公式、教学图表和几何目标定位实验的设计依据；不宣称复现论文结果，也不宣称生产采用。

结论：优先把“识别目标”和“产出坐标”拆开。由独立图像检测产生候选区域，M3 选择区域 ID，应用映射回原图；候选不足时再裁剪识别或拒绝定位。重复提示 M3 直接写归一化坐标没有解决检测和坐标空间混用问题。

## 已核实的一手来源

本次实际读取了以下官方仓库 README 和列出的实现文件，并通过 GitHub API 核对四个仓库的当前 commit。SoM/ViperGPT/VisProg/Grounding DINO 的方法依据是作者发布的实现和说明；首次 arXiv 访问遇到 DNS 错误。后续用户指定的 Vision Banana 和 Grounded SAM PDF 已成功获取，实际读取相关方法、实验和附录并渲染查看，详见下节。论文指标没有转用为 M3 的效果承诺。

| 工作 | 作者论文与代码 | 实际实现证据 | 对本项目的意义 |
| --- | --- | --- | --- |
| Set-of-Mark / SoM | [论文 2310.11441](https://arxiv.org/abs/2310.11441)；[官方代码](https://github.com/microsoft/SoM) | [demo_gpt4v_som.py](https://github.com/microsoft/SoM/blob/130438d9a03359bed6514b2ad35dfa9a17a5e44a/demo_gpt4v_som.py) 使用 SEEM、SAM、Semantic-SAM 产生 mask，并支持 Mark/Mask/Box 标注，再交给 GPT-4V。 | 模型选可指代标记；空间区域来自检测器。OCR 行框替代原版分割器，是 SoM-inspired 工程候选，不能称为原论文复现。 |
| Grounding DINO | [论文 2303.05499](https://arxiv.org/abs/2303.05499)；[官方代码](https://github.com/IDEA-Research/GroundingDINO) | [inference.py](https://github.com/IDEA-Research/GroundingDINO/blob/856dde20aee659246248e20734ef9ba5214f5e44/groundingdino/util/inference.py) 以图像和文本提示检测，使用 box/text 阈值；输出 cxcywh，按图像宽高缩放后转 xyxy。README 说明 CPU 模式。 | 一般物体候选可由开放词汇 detector 提供；不是数学 OCR，对公式笔画、图表细线、小字的效果仍需测。 |
| Grounded SAM | [论文 2401.14159](https://arxiv.org/abs/2401.14159)；[官方代码及说明](https://github.com/IDEA-Research/Grounded-Segment-Anything) | README 说明 Grounding DINO box → SAM mask；RAM/Tag2Text 可先产生类别标签，再检测分割；原始 demo 需要相应预训练权重。 | 当产品需要精细轮廓而非矩形框时有价值；SAM 本身不能证明目标语义正确，错误 detector box 不会自动被 SAM 修复。 |
| ViperGPT | [论文 2303.08128](https://arxiv.org/abs/2303.08128)；[官方代码](https://github.com/cvlab-columbia/viper) | [image_patch.py](https://github.com/cvlab-columbia/viper/blob/09fe3465224766860d8dd4ec48db942f22b05092/image_patch.py) 将 `find`（GLIP/Mask R-CNN）、`crop`、`simple_query`（BLIP）分离，并保留 crop 在原图中的位置。 | 可借鉴受控视觉工具链与裁剪坐标继承；不需要移植其自由生成 Python 执行方式或整套 GPU 模型。 |
| VisProg | [论文 2211.11559](https://arxiv.org/abs/2211.11559)；[官方代码](https://github.com/allenai/visprog) | [step_interpreters.py](https://github.com/allenai/visprog/blob/9626868c0d1007c41d8f210fe99f5c1facc3325f/engine/step_interpreters.py) 提供 LOC/CROP/VQA/COUNT 等模块；LOC 包含坐标处理、阈值及 NMS，步骤可生成可检查中间结果。 | 明确分开检测、局部问答和确定性操作；留存中间区域可以定位失败层次，比全量第二个 LLM 审核更可诊断。 |

## 本机能力检查

实际命令结果：Apple Silicon `arm64`；`tesseract 5.5.3`，可用语言 `eng`、`osd`、`snum`。Backend `.venv` 可导入 PIL、cv2、scipy、fitz；未安装 torch、transformers、pytesseract、Vision、Quartz。这里“未安装”只覆盖该 Python 环境，不推断其他环境。

对仓库和默认 Hugging Face 缓存的 `.safetensors/.pth/.pt/.onnx` 文件搜索没有发现权重；该搜索不证明全盘不存在权重。本轮没有下载大型权重。

Tesseract 对已有定位结果 PNG 的 TSV 输出成功，证明命令与 PNG 解码链可用。这个 PNG 是历史结果对照图，含 gold/baseline 标签，因此**仅用于工具连通性检查，不用于本轮定位效果评测或候选检测输入**。

Swift 的 `VNRecognizeTextRequest` 最小程序编译完成，但当前执行返回 `nilError`、退出码 1。当前不能宣称 Apple Vision 可用，也没有将未验证的错误原因归为 macOS API 缺陷。可运行优先项是 Tesseract 子进程，不需 Python OCR 包。

## 用户指定论文：2604.20329 与 Grounded SAM

### Vision Banana 的实际方法

[Image Generators are Generalist Vision Learners](https://arxiv.org/pdf/2604.20329)，Gabeur 等，当前下载为 v3（arXiv 标记 2026-06-03，封面 2026-06-05），30 页。[作者项目页](https://vision-banana.github.io/)已实际获取检查。PDF 保存在 `/tmp/m3-paper-2604.20329.pdf`，SHA-256 `088b078cbc2b6183ec50fc95910c1daf6e29f7e4928ed17dda6d978a82204dc6`。实际阅读与图像定位相关的第 1–9、24–28 页，以及讨论；第 2 页 Fig.1、第 8 页和第 24 页方法已渲染目视。

- 第 4 页 §2：在 Nano Banana Pro 的原图像生成训练混合中加入低比例视觉任务数据，得到经过 instruction tuning 的 Vision Banana。2D 数据为内部模型标注的网页图像；3D 为渲染数据。它不是给任意现成 MLLM 多加一段提示即可得到的能力。
- 第 3、6 页：语义分割输出为规定 RGB 颜色图；每像素按最近目标颜色解码标签。它将稠密视觉输出放到像素空间，不要求语言模型写几十个坐标数字。
- 第 8 页：SA-Co/Gold 有 168k Image–NP pairs，负查询占多数；由于模型未训练输出空 mask，先由 Gemini 3.1 Flash-Lite 判断物体是否存在，只对阳性图像调用 Vision Banana。ReasonSeg 则先用 Gemini 2.5 Pro 把推理查询改写为描述性指称，再单次调用 Vision Banana。这里对本项目直接有用的是“存在性判断/语言指称”和“像素定位”分工，而非全量多角色互相评论。
- 第 5 页 Tables 4–5：RefCOCOg UMD val cIoU 73.8、ReasonSeg val gIoU 79.3；后者是 Vision Banana + Gemini 2.5 Pro。它们使用不同指标/数据，不应与我们框 IoU 或 12 个开发场景成功率直接比较。
- 第 24 页 Appendix A：实例 mask 需要多阶段解码：背景色容差 14、以种子颜色进行 16-connectivity floodfill、面积小于图像 0.02% 去噪、3×3 腐蚀后保留比例不足 0.1 的细边去除、颜色相近且组合 box 面积扩张不超过 5 倍时合并。该算法处理的是**模型已经生成的 mask 图像**，不能把对原自然图做连通域检测说成复现它。
- 第 28 页 Fig.10 给出失败例：物体分组粒度、复数/整体含义、背景范围和小物体仍会失误。候选架构必须保留缺失/歧义/粒度失误，不能只测试阳性整物体。

在本次读取的作者项目页中只发现论文、演示和作者信息，未发现可下载模型权重、推理代码或 API 链接。因此当前无已核实的 Vision Banana 本机推理入口；本轮不宣称重训/复现，不把 M3 生成 SVG、JSON 或普通图像编辑器充当该模型。

### Grounded SAM 的实际方法与本轮实现调整

[Grounded SAM: Assembling Open-World Models for Diverse Visual Tasks](https://arxiv.org/pdf/2401.14159)，11 页，v1 2024-01-25；下载 `/tmp/m3-grounded-sam-paper.pdf`，SHA-256 `9dd6cbb7b6f0af34fc840d4c7d0e185f8e8d4427ac91a3e9a745fe8e0a7a91cf`。实际阅读第 1–7 页方法与评估；第 4 页 Fig.2 已渲染查看。

第 3–4 页 §3.2 为真实 Grounding DINO text-conditioned box → SAM box-conditioned mask。第 3 页 §2.3 明确其基础 assembly 不要求 LLM controller；第 4 页 §3.3 可用 RAM/BLIP 先产标签；第 6 页 §3.6 列出更轻的 SAM 替代。第 7 页采用 SGinW 多领域评估，不是教材公式精度保证。

据此，本轮应把原有 OCR/像素几何候选保留为轻量对照，增加一套真实 learned detector + segmenter 自然图像实验，避免仅在纯色合成图上给出结论。已向实现 agent 提供以下可执行规格：

| 组件 | 官方 HF 模型与固定 revision | 权重估算及调用 |
| --- | --- | --- |
| Detector | `IDEA-Research/grounding-dino-tiny`，`a2bb814dd30d776dcf7e30523b00659f4f141c71` | HF API 核实 F32 参数 172,249,090，约 689 MB；`AutoProcessor` + `AutoModelForZeroShotObjectDetection`。 |
| Segmenter | `facebook/sam2-hiera-tiny`，`7c218beaf0bb87874785f32b582f640134fc1c09` | HF API 核实 F32 参数 38,946,498，约 156 MB；`Sam2Processor` + `Sam2Model`，detector xyxy 经 `input_boxes` 输入。 |

总权重约 845 MB；这是 Grounded SAM 思路的 SAM2 tiny 变体，不是 2024 原论文相同模型复现。两项 HF card 均列 Apache-2.0。只下载 safetensors 与必要配置/tokenizer，避免同时下载 `.bin/.pt` 重复副本；隔离 `/tmp` 环境，使用 Transformers 内置类、不启用 `trust_remote_code`，不改 backend 依赖。先 CPU float32 smoke，再实测 MPS；Apple Silicon 并不自动证明每个算子可运行。

实际读取的 [Transformers Grounding DINO 文档](https://huggingface.co/docs/transformers/model_doc/grounding-dino)要求多个类别以句点分隔，并使用 `post_process_grounded_object_detection` 映射至 `target_sizes=[image.size[::-1]]`。[SAM2 文档](https://huggingface.co/docs/transformers/model_doc/sam2)展示 `input_boxes=[[[x_min,y_min,x_max,y_max]]]` 与 `post_process_masks(..., original_sizes)`。冻结具体安装版本后需适配该版本 API，不能混用文档新旧 threshold 参数。

供真实实验的已下载 PNG（仅研究素材，非独立 held-out 数据）：

- `/tmp/m3-natural-astronaut.png`，512×512，NASA public domain。
- `/tmp/m3-natural-chelsea.png`，451×300，CC0，Stefan van der Walt。
- `/tmp/m3-natural-coffee.png`，600×400，CC0，Rachel Michetti。

来源为 [scikit-image v0.25.2 data](https://github.com/scikit-image/scikit-image/tree/v0.25.2/skimage/data)；许可已从其 [_fetchers.py](https://github.com/scikit-image/scikit-image/blob/v0.25.2/skimage/data/_fetchers.py) 的 `astronaut`、`chelsea`、`coffee` docstring 实际核实。实现需复制并冻结图像 SHA，gold 由离线评价持有；自然图片可测 cat/cup/person 和不存在对象，避免把典型公开 demo 图称为独立泛化认证。

## 实验路线与边界

### 1. 文字和公式：独立 OCR 行框 + 标记选择

冻结原始 PNG 后运行 `tesseract input.png stdout --psm 11 tsv`；从 TSV 的 word 行按 `(block_num, par_num, line_num)` 合并区域。PSM 6 可作另一固定候选用于成块文字，但不能按测试 gold 为每张图选择最佳模式。公式 OCR 的文本与置信度可能很差，但其行框仍可覆盖目标；不应通过过高置信度阈值把所有公式行删掉。

将每个候选区域画上不遮挡内容的稳定编号；向 M3 同时提供原图和标记图，输出限制为候选 ID 或 abstain。应用从候选表取得坐标，M3 不再生成框数字。请求中的重复公式、上下位置描述仍由 M3 处理；无唯一目标时应明确歧义。

公式中的分数线、根号、上下标可能漏出 OCR box；一行混有说明文字时框又可能过宽。因此该候选先解决空间错误，不能预先承诺精确公式轮廓。

### 2. 失败时局部裁剪与细化

选择区域后附带少量上下文裁剪，按固定比例放大，再运行 OCR 或像素检测。裁剪矩形和缩放系数由程序持有；若局部框为 `(u0,v0,u1,v1)`，裁剪左上角为 `(cx,cy)`，缩放因子为 `s`，则原图 x 为 `cx + u/s`，y 为 `cy + v/s`，最后按原图尺寸归一化。

不要混合 Vision 左下原点、PIL 左上原点、Grounding DINO cxcywh 和前端 normalized xyxy。只有通过已保存变换映射的 box 才能交给前端。裁剪重试应有次数上限，保留失败证据，不能无限重试到通过。

### 3. 几何图形与一般对象

OpenCV 连通域、颜色区域、轮廓可以在当前机器生成矩形、圆、三角形等候选；它们是**像素几何 proposals**，不是通用 object recognition。图表坐标轴可能连接多个柱体，空心图形和文字字形也会产生误候选。需要把 detector 漏检与 M3 选错分开统计。

自然图像和教材插画中的一般物体，下一阶段更适合 Grounding DINO → SoM ID selection；若需要轮廓再接 SAM。需另行建立权重、运行环境、耗时、内存与许可记录，然后用自然图片和教材图片测评。当前无本地可运行权重，不能把这条路线描述为已实验通过。

## 多智能体结构建议

先采用职责清晰的工具工作流：检测 worker 读取 PNG 并产生候选；M3 选择目标；确定性 mapper 生成框；validator 检查区域 ID、范围、图像身份、缺失与歧义。只在检测不足或语义不确定时触发 crop/refine。这是模型与工具分工，不应包装成多个自主 LLM 已证明更优。

如果增加 reviewer，它应看到独立 crop 和明确目标，判断目标是否存在、是否唯一、是否被完整包含；不能用相同坐标提示再次猜框来“投票”。新增角色必须通过选择准确率、漏检率、错误拒绝率、延迟和 tokens 的配对证据证明收益。

## 本轮实验必须保留的判读

- 检测器只能读取 PNG，不能访问 synthetic renderer 返回的目标框、gold 标签或人工标注；gold 仅给离线评估器。
- 分开报告 proposal recall、给定候选后的 selection accuracy、最终 IoU/目标覆盖与误包含、no-target/ambiguity 拒绝表现。没有合适候选时不把错误全归给 M3。
- 原图 direct bbox 与原图 + SoM 使用相同请求和图像；额外图片、候选文本、tokens/latency 均记录。12 个开发场景只能支持机制诊断，不能支持广泛生产精度结论。
- 包括不同布局、相似公式、多目标、无目标、图表与几何；后续需要中文教材扫描、手写、旋转、细小公式、自然图像和真实截图等独立材料。
- 研发候选的定位改善不等于 production annotation tool 已迁移。生产采用仍需领域契约、图像身份和可靠性边界审阅及独立 UI revalidation。
