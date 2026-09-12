# Bridge 与教学制品修复：独立源码复核

2026-09-12；reviewer 为未实现这两项修复的 visual_research agent。实际读取 `common.py`、`role_artifacts.py`、`role_exploration.py`、相关 integration tests，以及 production transport projection、MeteredTransport 和实际 runner。此次是代码与测试覆盖审阅，没有发起新的 live 调用，也未修改实现。

结论：当前未发现阻断这次实验复测的问题。两项修复在实验范围内对应原缺陷；不能据此宣称生产多媒体全域验收完成。

## 1. Bridge 与生产响应投影一致性

Bridge 调用的是 production `_normalize_completed_tool_indexes`，没有另写更宽松解析器。该函数仅删除完整 function call 上符合范围的真整数 `index`，要求顶层/嵌套键集合精确、id 非空、function name/arguments 为字符串；unknown 字段、布尔/string/负数/超范围 index、缺失 function 参数仍保留给严格领域 decoder 拒绝。返回新投影对象，未就地破坏原响应。

`test_bridge_parity.py` 覆盖与 `ProviderTransport.execute` 相等、原对象不变、合法 index 可解码、异常字段失败、失败不重试，并穿过 actual Study commit 与 restart readback。此覆盖适合验证修复边界。

证据术语须准确：MeteredTransport 在 Bridge 投影前记录 allowlisted `tool_call_shapes`（index 是否有效整数、已知字段、unknown 数量等）与 usage；**不保存完整原始 response body、arguments 或 provider IDs**。因此可以声明保留原始 wire 的结构证据，不能声明可从 ledger 完整重放原响应。

## 3. 图表依赖与实际交付

`requirement(case.source)` 只解析受控 source 的 typed chart data 与题目要求；`build_delivery` 未读取 gold。Gold 仍仅用于 facts/minutes 等离线判定，未注入模型 prompt 或图表构造器。模型不得输出应用文件路径/digest；Draft extra fields 仍 forbid。

最大值题与差值题均由 `required_questions` 精确约束。空列表、只交一题、交换顺序、重复第一题、未知标签均不能通过；由应用确定性生成的 learner page 引用实际 `chart.svg`，两个题目与 source 数值完整交付。自由 `learner_prompt` 明确仅是 proposal，不冒充已交付页面。

`validate_delivery` 重读 manifest 与实际 SVG/JSON/HTML，按 source 重渲染并比较内容与 digest。仅伪造 matching digest 无法把 9 改成 99 后通过；删除文件、页面断开图表引用、source binding 改变均被拒绝。最后 `export_delivery_bundle` 把实际三份文件内容放入 JSON evidence，满足 runner 对 evidence 文件 JSON 可读的要求。

actual worker 测试调用真实 checkpoint/ledger/result 校验，验证 bundle 能进入结果；导入的 `source_manifest` 覆盖 adapter 目录所有 Python 文件，所以新增 `role_artifacts.py` 有源码 digest。读取 runner 后确认这不只是手动调用 adapter 的局部测试。

## 仍需保持的范围限制

- 这是受控 `media-chart` 实验的 source-bound chart delivery，不是生产附件契约或通用自然语言“所有引用制品存在”检查。其它媒体类型和任意自由问题没有因此完成。
- 当前图表问题集合由应用 source 指定，模型只能提供合规结构；实验结论应表述为完整交付检查与确定性制品生成已补齐，不能说模型独立设计图表的能力已提升。
- Live 成功率、成本与旧失败是否消失仍需本轮实际结果；本次源码审阅不替代 live evidence 或浏览器显示检查。
