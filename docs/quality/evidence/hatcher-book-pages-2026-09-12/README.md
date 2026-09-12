# Hatcher 书籍页面测试资料留档

2026-09-12 按用户要求从 `/tmp/m3-hatcher/` 完整复制，共 28 个原始文件；原文件逐字节保留。

## 内容

- `AT.pdf`：Allen Hatcher, *Algebraic Topology*；`AT-p{10,14,17,31,94}.png` 为页面图片，`AT-contact.png` 为总览。
- `TNbook.pdf`：Allen Hatcher, *Topology of Numbers*；`TNbook-p{10,23,29,30,99}.png` 为页面图片，`TNbook-contact.png` 为总览。
- 六张 `hatcher-*-gold.png`：目标区域红框、关联正文蓝框的标注页面。
- `manual-gold.json`：六个测试案例、目标坐标、关联文本、来源和校验值；`manual-gold.sha256` 为其原始校验记录。
- `AT-selected.json`、`TNbook-selected.json`：每本书各两个案例的兼容选择清单。
- `home.html`、`ATpage.html`、`TNpage.html`：原 agent 保存的来源网页。
- `make_manifest.py`：原始标注生成脚本，作为历史记录保留。

文件名中的页码为从 1 开始的 PDF 物理页码，不是书中印刷页码。

## 来源与使用

原清单记录来源为作者官网的 [Algebraic Topology 页面](https://pi.math.cornell.edu/~hatcher/AT/ATpage.html) 和 [Topology of Numbers 页面](https://pi.math.cornell.edu/~hatcher/TN/TNpage.html)。本次仅留档已有本地资料，没有重新下载。

原始 JSON 和脚本保留 `/tmp/m3-hatcher/` 绝对路径；读取留档资料时，将此前缀映射为本目录即可。原脚本仍向临时目录写入，留档不修改其行为。原清单中“仅保存在 /tmp”的描述属于生成时的历史状态，本次用户要求已将整批资料复制入仓库。

标注来自单个 Codex agent 的目视检查，不是人工专家共识，也不是模型实测结果。此次留档不改变原资料的版权或再分发许可。

## 完整性验证

在本目录执行 `shasum -a 256 -c SHA256SUMS` 可核验全部 28 个原始文件。
