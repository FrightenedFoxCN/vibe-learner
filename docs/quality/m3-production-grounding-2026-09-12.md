# M3 实验候选的生产实现与验收

2026-09-12，基于用户明确授权，将[实验结论](m3-parallel-results-2026-09-12.md)落实到工作区生产代码。未部署、未更改默认模型、未修改生产数据库；原桌面图标改动保持原样。

## 采用范围

- 引用选择使用独立 `study_grounding.citation_tokens`：NFKC、casefold、英文/法文功能词过滤、中文双字切分。问题与资料两侧都归一化，采用词集合交集，避免 `art` 错中 `cart`。仍限制在当前 Study Unit/Section 的页范围、最多三个引用；不更改 persona slot 分词或跨会话检索。这是候选资料选择，不是语义蕴含判定。
- 原文保存使用明确的用户指令，不从自然语言猜测保存授权：

  ```text
  /remember-verbatim archive
  档案中的原句是：“Don’t alter 007 — Rémi.”
  这只是引用，不是共同经历。
  /end-remember
  ```

  整条 learner message 必须匹配；键限 1–120 个 ASCII 字母/数字/下划线/短横线，正文最多 4000 字符。正文首尾空白不符合现有 memory effect v1 契约时返回 422，绝不静默裁剪。正文内部换行、标点、前导数字零保持不变。普通摘要、转述和嵌在引文里的指令不自动启用绑定。
- Study Dialog 的 Study Console 增加折叠说明。模型仍须提出严格有效的 `write_session_memory`；服务器只对匹配的授权键绑定原文，未知字段/错误键不能被掩盖。没有对应 prepared effect 时，不允许成功提交。模型未调用工具或工具关闭时也不会冒充保存成功。
- native M3 的整数 `index` 规范化已存在于生产 `ProviderTransport`，本次保留原实现，针对性测试和真实 LiteLLM SDK 路径均验证。
- 不采用无明确收益的摘要额外提醒、全历史 oracle；不修改通用输出 JSON 解码规则。

## 契约与恢复

新增 `study_grounding:study-grounding-v1` 应用组件，Python/TypeScript 操作阶段注册与 workflow golden 同步更新。Tool Manifest、模型工具参数、公开 API DTO 和持久化 effect v1 均未扩展。

新写入的 `StudyChatProtectedSnapshot` 为 v2，显式保存未经 hidden prefix 拼接的 learner message。只有 Harness resolver 完成当前 operation/artifact/grant 授权后才从该快照解析来源。v1 仅保持读取兼容，禁止把 v1 载荷注册成 v2。来源文本不进入 safe manifest/digest DTO，模型不能分配应用身份或回执字段。

原文效果沿用 admitted operation、typed effect collector 与 Session/Turn 原子提交；幂等 request digest 包含指令和原文。同 ID 改原文被拒绝，重复请求和重启恢复仅读回。当前 `primary_output_only` 的证明范围不扩大。

## 验收与证据

结果与日志见[交付清单](evidence/m3-production-grounding-2026-09-12/delivery.json)。

- `npm run check:release`：共享契约、Web 类型/恢复、Harness PR eval、完整 backend unittest（858 项）与生产 Web build，最终退出码 0。
- 新增原文授权/非法输入/错误键、无效果失败、多页引用/词片段误命中、旧快照只读、真实应用提交/CAS/重启恢复测试。
- Playwright 路由验收：13 项通过；新增 Study Dialog 原文指令说明和输入保真浏览器用例 1 项通过，[截图](evidence/m3-production-grounding-2026-09-12/study-grounding.png)已目视核对。
- 国内 `https://api.minimax.cn/v1/chat/completions`，环境 `K3_API_KEY`，真实 LiteLLM SDK → 生产 transport/decode/application → SQLite commit → 重启读回；3/3 样例通过，5 次成功 SDK 调用，26,446 reported tokens。两条原文保存和一条法语引用，都是新素材的小样本 smoke，不是总体质量估计。
- live harness 仅在 SDK 外包裹配额计数，未替换网络 transport。生产 SDK 原本 `num_retries=0`，本次校验该值；最多 18 SDK 调用、每样例 6 次、单并发，独立 SQLite 配额账本。没有调用 embedding/responses 端点。
- 首次 sandbox DNS 失败发生于派发前；随后首轮验收脚本重复传 `num_retries` 引发本地 TypeError，三个样例均未执行 SDK 原函数/HTTP，保留三笔 uncertain 预留 312,288 tokens。修正脚本后在新目录进行上述真实验收，失败证据不覆盖。

完整发布门禁通过不等于供应商 exactly-once 或独立质量认证。MQ 质量票不关闭；多页竞争、跨领域词法误相关、真实用户文本与独立人工审核仍需持续跟踪。本次没有进行 macOS/Windows 安装包验收。

## 发布与回退

这是可评审的工作区实现。发布前应排空旧进行中的 Study 操作，避免跨应用组件/快照版本运行。无数据库 migration；部署按既有发布流程进行。遇到原文功能问题，暂停使用显式指令并保留回执，不能重放 uncertain provider 操作。回退代码时保留已提交 Session/Turn/effect 和 v2 artifact；旧代码不能据 v2 artifact 继续生成。历史 Session 公开读回格式保持一致。
