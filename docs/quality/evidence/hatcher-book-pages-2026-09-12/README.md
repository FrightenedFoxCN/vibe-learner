# Hatcher 书页测试资料

本目录只保留实际进入书页定位实验的四张页面、对应标注图和坐标清单；整书 PDF、未选页面、联系表与网页快照已经移除。

## 测试页面

- `AT-p14.png`：*Algebraic Topology* 物理第 14 页，genus-2 八边形任务。
- `AT-p31.png`：*Algebraic Topology* 物理第 31 页，`B_{-3}` 链环图任务。
- `TNbook-p30.png`：*Topology of Numbers* 物理第 30 页，下方 Farey 图任务。
- `TNbook-p99.png`：*Topology of Numbers* 物理第 99 页，`p q r s` 局部树边图任务。
- 四张 `*-gold.png`：目标区域红框、关联正文蓝框的事前目视标注。
- `AT-selected.json`、`TNbook-selected.json`：坐标、请求、物理/印刷页码、整书摘要和作者官网来源 URL。

标注来自未查看检测器或模型输出的单个 Codex agent 目视检查，不是人工专家共识或留出认证。页面仅用于本仓库的受控模型质量实验；作者官网可下载不自动证明任意再分发许可。

这四页随后用于 `Picture` 母框、递归候选和母框内子图裁剪实验；整页、OCR/单字符与图形候选的职责边界及结果见[书页定位报告](../../m3-book-grounding-results-2026-09-12.md)。整书没有重新加入仓库。

## 完整性验证

在本目录执行 `shasum -a 256 -c SHA256SUMS` 可核验四张测试页、四张标注图和两份坐标清单。
