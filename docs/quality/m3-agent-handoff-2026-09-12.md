# M3 实验与生产修改：智能体交接

## 当前状态

用户已授权实验、生产代码修改、验收及 Git 提交。本轮交付已完成，尚未 push 或部署。后续智能体从当前提交继续，不要重新执行旧 campaign 或重写历史证据。

- [实验总报告](m3-parallel-results-2026-09-12.md)：284 个真实样本、698 次 M3 请求、3,952,533 reported tokens，另保留 32 个 DNS 失败样本。
- [生产实现与验收](m3-production-grounding-2026-09-12.md)：引用独立分词、显式原文指令与授权来源绑定。
- [生产交付清单](evidence/m3-production-grounding-2026-09-12/delivery.json)：最终发布门禁、858 项后端测试、13 项浏览器路由测试、1 项新功能浏览器测试；真实生产 SDK smoke 3/3、5 次调用、26,446 tokens，重启读回一致。
- [完整实验包](evidence/m3-priority-lanes-2026-09-12/evidence.zip)与[生产证据包](evidence/m3-production-grounding-2026-09-12/evidence.zip)已校验哈希。包中的 Git revision 是实验时基线，具体执行源码快照和导出时源码范围见报告，不是本次提交 ID。

## 生产边界

先读根 `AGENTS.md`、[Harness 架构](../harness-architecture.md)及生产实现报告。

- `services/ai/app/services/study_grounding.py`：`study-grounding-v1`，引用专用 Unicode/中文分词；不改 persona slot 或跨会话检索分词。
- `/remember-verbatim KEY\n正文\n/end-remember` 仅对整条 learner message 生效。不是自然语言“请记住”的通用自动保真。正文 1–4000 字符，首尾空白按现有 effect v1 契约拒绝，不静默裁剪。
- `study_chat_application.py`：从当前操作已授权 v2 protected snapshot 解析原始 learner message；模型须提出指定键的合法工具调用，缺少对应 effect 不得成功提交。
- `study_session_chat_runtime.py`：严格工具参数验证后绑定正文；原有 typed effect/CAS/receipt 提交边界保持。
- `study_v3.py`：新快照 v2；v1 仅保留 decode 兼容，不能重新注册为 v2。公开 Session/Turn、Tool Manifest 与 memory effect v1 形状未变。
- Python/TypeScript component/stage/workflow golden 已同步。生产 transport 原有严格整数 `index` 投影未重复修改。

## 后续建议与开放项

1. 进行独立代码/质量复核，尤其检查多页竞争、词法相关但语义无关的引用、显式原文指令 UX 与失败提示。现有小样本不能证明引用蕴含或普适模型质量。
2. 若准备部署，排空旧 Study 进行中操作，按原发布流程执行；无 migration。回退保留所有已提交状态与 v2 artifacts，不能重放 uncertain provider 请求。
3. 保持 [质量 TODO](TODO.md) 中独立留出、人工复核、SDK 扩展场景与平台验收开放。macOS/Windows 安装包未做本轮验收。
4. 摘要强化提示与全历史 oracle 本轮无明确收益，不要默认采用。不要放宽 domain decoder 以提高表面成功率。

## 复现与账本注意

- `npm run check:release` 是完整发布门禁；新增测试在 `tests.test_study_grounding`、`tests.test_study_grounding_acceptance` 与 `apps/web/tests/browser/study-grounding.spec.ts`。
- 本地 `tools/model-quality/runs/` 是被忽略的实验数据；可移交证据已在 tracked ZIP 中。旧批次 source-frozen，当前源码变化后直接 `--resume` 应拒绝。不得重置旧 ledger 或把失败样本替换成成功结果。
- 旧总账为 1,242 次 wire、7,892,181 charged-or-reserved tokens，0 在途。新生产 SDK smoke 使用独立账本，不混入旧统计。
- 新 SDK smoke 第一轮脚本重复传 `num_retries`，3 次本地错误发生于真正 SDK 调用前，312,288 预留仍保留；v2 修正后 5 次真实调用通过，记录分别归档。
- 新增 live smoke 脚本：`tools/model-quality/examples/accept_production_grounding.py --output NEW_DIRECTORY`，需现有 `K3_API_KEY` 与合适 PYTHONPATH。任何后续实测必须用新目录、明确预算和授权；密钥不写入文件。
- 当前没有持续自动化或待观察的 live 请求。

## 工作树所有权

`apps/desktop/src-tauri/icons/icon.icns` 在本轮开始前已有修改，未纳入本次提交，留给其所有者处理。不要顺手还原或提交该文件。
