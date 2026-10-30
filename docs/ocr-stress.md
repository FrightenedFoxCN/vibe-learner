# OCR-STRESS-001 本机真实模型压力与恢复

本协议使用真实 CPU 神经模型，经生产 Document API 测量多字符集、扫描压力与失败恢复。测试输出须区分识别质量、处理提交、保存进度及正式支持上限。

## 执行边界

- 探针：[ocr_stress_probe.py](../services/ai/tests/acceptance/ocr_stress_probe.py)。使用生产 FastAPI `TestClient` 经 `POST /documents`、`POST /documents/{id}/process` 和 GET 读回；HTTP 在进程内执行，不启动 Web/Next 或后端监听服务。
- 生产 `OnnxtrOcrEngine.extract_page_text`、Document parser、admission、protected artifact resolver、checkpoint、CAS 和 v3 commit 都照常运行。探针只预构造真实 CPU predictor，并观察原调用和 checkpoint 保存；不替换 OCR 文本、模型输出或 `language_hint`。
- 每个 case 一个子进程，临时 SQLite/上传/工件与用户运行数据隔离，顺序运行。Python audit hook 阻断 TCP/DNS，provider 固定 `mock`，实际 OCR 使用本地神经模型。`network_attempts=[]` 是验收条件。
- `EngineConfig` 固定 `CPUExecutionProvider`、intra-op 2 线程、inter-op 1 线程；复跑允许 1–4 线程。未实测真实加速器故障；已有 CPU fallback 单元回归复用，不把显式 CPU 执行说成实机 accelerator fallback。
- `ONNXTR_CACHE_DIR=/tmp/vibe-ocr-models`。只使用下列两个文件，逐个流式校验文件名 SHA-256 前缀和完整摘要；缺失、符号链接或摘要不符时拒绝执行。不会信任目录中其他文件，也不会补下载。

| 文件 | SHA-256 |
| --- | --- |
| `models/db_mobilenet_v3_large-4987e7bd.onnx` | `4987e7bdea372559808bd5add85fda10e179dc639696fb489e59a197a25b4c64` |
| `models/parseq-00b40714.onnx` | `00b40714e00039c8c04891e5fd98ad5cb46c34fa7133ba09e2a55d4b28d42a68` |

本次环境为 macOS 27.0.1 arm64、Python 3.13.5、OnnxTR 0.8.1、onnxruntime 1.24.4、PyMuPDF 1.27.2.2，使用 `services/ai/.venv`。这不是官方 DMG 的离线模型安装验收；OCR manifest `included:false`、安装环境无缓存仍不能算离线 OCR 安装通过。

## 样本与计分

固定自著原文在探针 `TEXTS` 中，分别为英文、法文、德文、中文各八句。Latin 使用 Helvetica，中文使用 MuPDF `china-s` 字体。先渲染成 2 倍 PNG，再放入 595×842 pt PDF；重开 PDF 验证每页没有文本层且含图片。每次保存 PDF、逐页 ground truth、图片/PDF 摘要，禁止用识别到某个标识词代替准确率。

- `sparse`：每页八行、14pt。四个单页基线；16 页按 en/fr/de/zh 循环，各四页。
- `dense`：每页 40 行、11pt、17pt 行距；同一语言八句重复五遍。64 页按上述顺序循环，各 16 页。
- 两种布局都是清洁、平直、重复率高、可压缩的合成扫描。64 页 dense 增加了逐页检测/识别负载，但没有传统教材的独立正文、多栏、脚注、公式、表格、倾斜、模糊、装订阴影和复杂版式，不能代表所有大型 book。

CER = 完整原文与识别文本的 Levenshtein 编辑距离 / 原文字符数；不截断到 100%。`character_match_rate` 是最小编辑对齐中的精确匹配字符数 / 原文字符数，同成本时取更多精确匹配。NFC 规范化，连续空白折叠为一个空格；保留大小写、变音符和标点。另外记录移除全部空白后的同类分数，避免中文仅匹配换行空格造成误读。

质量比较使用清洗前真实 OCR 全文，并可与 `durable_pages[].ocr_result` 对照；debug 的 400 字预览不是全文准确率。`fixture_language` 是样本标签，生产 `language_hint` 仍为 null。计分在最终版探针的 API 请求外执行，不消耗生产 Harness 的预算。

`quality=unsupported` 表示原文包含 PARSeq 默认 `french` vocabulary 无法输出的字符；仍完整记录 CER，不把它记为支持词表质量通过。仅完全被词表覆盖的样本使用预先固定的探针 CER ≤10% 判断；这是探针标准，不是已有正式模型质量门禁。

## 参考结果与限制

macOS arm64、Python 3.13.5、OnnxTR 0.8.1、ORT 1.24.4 的本地 CPU 样本：

逐页数值、执行失败、模型和源码摘要保存在[机器可读参考样本](performance/ocr-stress-local-v1.json)；识别正文与完整读回留在独立工件目录。

| 样本 | CER | 字符匹配率 | 解释 |
| --- | ---: | ---: | --- |
| 英文单页 | 0% | 100% | 本固定原文通过 |
| 法文单页 | 0% | 100% | 本固定原文通过 |
| 德文单页 | 1.90% | 98.10% | 默认词表缺 `ß/ä/ö`，不支持完整德文 |
| 中文单页 | 94.53% | 5.47% | 匹配来自空白；无空白正文匹配率为 0% |

16 页 sparse 处理约 24.28 秒，子进程约 26.99 秒，peak RSS 2.91 GiB；逐页 checkpoint、最终 Document/Debug/v3 commit 和新应用读回一致。

64 页 dense 在原生产 180,000 ms 预算下分三次处理：

| 操作 | 新识别页 | 保存进度 | API 秒 | 提交状态 |
| --- | --- | ---: | ---: | --- |
| 初始处理 | 1–28 | 28/64 | 182.16 | 时间预算失败，checkpoint_only |
| 显式续跑 | 29–56 | 56/64 | 181.86 | 时间预算失败，checkpoint_only |
| 再次续跑 | 57–64 | 64/64 | 53.34 | committed |

每页之间协作检查时间，单次 OCR 可使实际耗时稍超预算。两次原始失败均保留 `harness_runtime_wall_time_budget_exceeded`，没有改成一次成功。领域 source-child 和 Harness identity 各自分配，真实 OCR 合计恰好 64 次、无重复页；最终 Document/Debug/receipt/v3 commit 与新应用读回一致。重复已完成 source 的 resume 返回相同 committed projection，新增 OCR 调用 0。全链 peak RSS 4.76 GiB（约 5.11 GB），包含模型、完整输出和证据投影。

密集样本英文/法文正文 CER 仍为 0%；德文 CER 约 1.95%，中文无空白正文 CER 100%。重复同样八句只增加处理负载，不增加独立语言样本；不得以 API 成功提交推导中文可用性。64 页恢复完成也不认证正式支持 64/512 页、多栏公式教材或所有扫描质量。

错误 PDF 和缺模型均验证失败操作、无成功 Document/Debug 提交及重启读回。补入正确模型后，因为配置摘要改变，旧 checkpoint resume 返回 `409 document_checkpoint_input_changed`；新操作可真实识别并提交。公开错误码可能较泛化，精确原因由 checkpoint/v3 trace 保留。

原始报告保留逐页 ground truth、真实 OCR 全文、时延、RSS、checkpoint 与模型摘要。子进程失败不删除报告；最终链汇总只把已恢复的工作流计为完成，不改写前两次预算失败。参考工件位于 `/tmp/vibe-ocr-stress-20261030-final/report.json` 和 `/tmp/vibe-ocr-stress-20261030-dense64-verified/report.json`，复跑时应另存输出目录。

## 稳定复跑

从仓库根目录使用已经安装的生产虚拟环境，不触发依赖同步或下载。输出目录必须不存在；原始工件一直保留。

```bash
ONNXTR_CACHE_DIR=/tmp/vibe-ocr-models services/ai/.venv/bin/python \
  services/ai/tests/acceptance/ocr_stress_probe.py \
  --output-dir /tmp/ocr-stress-new --threads 2 --stress-pages 16
```

可选 16/32 页复跑用 `--stress-pages 16 32`。密集 64 页：

```bash
ONNXTR_CACHE_DIR=/tmp/vibe-ocr-models services/ai/.venv/bin/python \
  services/ai/tests/acceptance/ocr_stress_probe.py \
  --output-dir /tmp/ocr-dense64-new --cases stress \
  --stress-pages 64 --layout dense --threads 2 --stress-timeout 600
```

保留生产预算，出现预算失败时显式续跑同一数据库最新失败 operation：

```bash
ONNXTR_CACHE_DIR=/tmp/vibe-ocr-models services/ai/.venv/bin/python \
  services/ai/tests/acceptance/ocr_stress_probe.py \
  --output-dir /tmp/ocr-dense64-resume-new \
  --resume-artifacts /tmp/ocr-dense64-new/stress-64 \
  --threads 2 --stress-timeout 300
```

如需下一次 resume，仍指向原始 `stress-64` 目录，它的数据库保存最新 child；使用新的输出目录。每次只启动一个有界 child，不自动无限重试。原始操作失败时 CLI 返回 1；最终恢复报告成功不能覆盖原始失败报告。

把原 case 和各次 resume 的目录按顺序传入只读核验；它检查真实数据库中的 identity、source-child、最终提交、全文 checkpoint 与 64 次唯一 OCR 调用，输出最终工作流分母。此命令不调用模型：

```bash
services/ai/.venv/bin/python services/ai/tests/acceptance/ocr_stress_probe.py \
  --output-dir /tmp/ocr-dense64-verified-new --summarize-chain \
  /tmp/ocr-dense64-new/stress-64 \
  /tmp/ocr-dense64-resume-new/resume \
  /tmp/ocr-dense64-resume-next/resume
```

单页/错误 case 子进程上限固定 180 秒；stress/resume 外层上限可为 180/300/600 秒，与生产 Harness 180 秒预算是不同约束。子进程超时会被终止；若已上传 Document，父进程另起不超过 30 秒的 inspection 子进程触发生产 startup recovery 并读回状态，保留 `inspection.json`，不自动重发处理 POST。

```bash
cd services/ai
.venv/bin/python -m unittest tests.test_ocr_stress_probe tests.test_ocr_cpu_fallback tests.test_document_checkpoints
.venv/bin/ruff check tests/acceptance/ocr_stress_probe.py tests/test_ocr_stress_probe.py
.venv/bin/ruff format --check tests/acceptance/ocr_stress_probe.py tests/test_ocr_stress_probe.py
```

上述 unittest 覆盖完整原文计分、Unicode/插入/空输出、纯图像及密集 fixture、模型摘要拒绝、resume checkpoint 复制与 OCR 次数的区分、已有 CPU fallback 和 checkpoint 回归。

正式语言支持、真实旧书/复杂版式的识别质量、其他平台和硬件、512 页/64 MiB 的可完成性以及安装包离线模型分发，不由本压力测试认证。德文与中文虽已量化，独立原文数量仍不足以形成语言质量支持声明；这些限制应保留在本报告，不能用“支持词表失败 0”掩盖。
