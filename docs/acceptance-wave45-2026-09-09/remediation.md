# 修复与桌面验收 · 2026-09-09

原报告中的 Study 工具装配阻断和纯目标计划失败已修复并通过 M3 复测；追加发现的 Planning 恢复快照问题和 Unix 桌面 sidecar 残留也已修复。**本轮验证的主链路通过，仍不代表全部 Wave 4/5 采用门关闭。** 原始失败文件继续保留。

后续已补测人格与场景的桌面构建、保存、重启回读及联用，并修复权重覆盖和物体编辑时保存失败等问题。最新安装包和验证结果见 [人格与场景补充验收](persona-scene/README.md)。

## 修复内容

- Study 的 UI 工具目录只维护标签/分类，provider description 直接投影自 Tool Manifest。31 个 Study 工具的生产 schema 装配回归通过；独立目录审计从 10 项漂移变为 0。
- Planning 输入明确提供父 Study Unit 的 Section 引用白名单。纯目标计划使用空 Section 引用及既有阶段页锚点；提示不再同时要求重复的 learn/review 排期和唯一 unit_id。
- Planning 的未知 unit/Section 引用现在进入已有的一次有界修复。修复输入使用工具执行后的 Study Unit 快照，并禁用所有工具，避免继续改变已检查的引用集合；耗尽后仍拒绝提交。应用提交前原有校验保留。
- 修复反馈保留允许列表中的具体、无内容错误码，例如 `duplicate_schedule_unit_ref`，不再只给出泛化的 `value_error`。Planning 的禁用工具分支也不再意外暴露澄清/完成度工具。
- Unix 桌面启动 sidecar 时分配独立进程组，退出时清理整个进程组，覆盖 PyInstaller launcher 和实际 Python 服务。旧实现只 kill launcher，实测会留下监听端口；修复后对应端口消失。Windows 路径本轮未更改、未验收。

这些是既有 proposal/引用/唯一性约束和工具开关语义的修复，未扩大公开 schema 或放宽提交规则，未修改历史操作。既有 v1 prompt/component 合同保持可读；真实输入仍由操作保护快照保存。历史 uncertain Study receipt 没有被重新解释或重放，复测使用新 client_request_id。

## 验证结果

| 项目 | 证据与结果 |
|---|---|
| 最终发布门 | 532 后端测试、163 前端测试通过，共享/type、PR eval、Web production build 通过；常规门内 2 个 optional live 用例跳过，另行实际执行见下一行 |
| Study/Tavern live-wire | 2/2 通过，0 skip；读取实际 M3 操作 |
| 原 Study 失败场景 | 同一 Session 的新请求 committed，查询回读一致 |
| 原纯目标输入 | “Learn introductory algebra.” 的新请求 committed |
| 教材计划 | 最终相同教材/目标复测 HTTP 200、v3 passed/committed、3 个排期；中间候选的失败样本也保留 |
| 静态/构建 | git diff whitespace 检查、cargo check --offline、macOS app build、codesign --verify --deep --strict 通过 |
| 桌面 Vault | 当前构建成功解锁原 Vault；没有改写 Vault 密码或保存 K3 测试密钥 |
| 桌面模型配置 | 默认和 plan/chat/setting 三个业务均显式指定 MiniMax 官方地址/M3；K3_API_KEY 仅注入 sidecar session-secrets 内存 |
| 桌面计划 | 原生 Plan Workspace 选择“仅学习目标”，输入 Desktop acceptance 合成代数目标，M3 3 轮/4 次工具调用后显示“目标计划已生成，会话已创建” |
| 桌面 Study | 自动开场及手动提问均提交；界面显示两轮、已同步；数据库对应两个 committed 操作及 committed v3 trace（第二个 repaired） |
| 桌面互动题/回读 | 提交结果持久化，Session revision=3 / last_turn_sequence=2；重启后原答案、结果和两轮对话仍可见 |
| 桌面退出 | 修复后实例端口 62856 在退出后无 listener，见 desktop/lifecycle.json |

桌面会话 `session-3e25d72f4d`、计划 `plan-afac10f6b2`；只导出本次生成对象的元数据和 trace 状态，没有把用户既有教材/会话内容复制进验收证据。桌面使用既有内置人物及默认场景，和完全隔离的 HTTP 合成夹具区分记录。

本次桌面 M3 usage：Plan 3 条、18,640 tokens；Chat 6 条、52,370 tokens。它们是 provider-reported usage 记录，不是账户账单。测试后恢复原模型设置，清除测试 session-secrets，保留测试计划/会话供复查。

原生主链路发生于包含 Study/目标计划修复的构建；后续追加的 Planning 恢复快照修复由独立回归及真实教材 HTTP 复测验证，再统一打入最终交付包。最终安装包的启动/回读/退出另行记录，不能把不同候选的失败样本隐藏为一次全绿运行。

最终包已安装到 `/Applications/Vibe Learner.app`，可执行文件与 sidecar 的 SHA-256 和最终构建一致，签名验证通过。旧包可回退备份位于 `/tmp/Vibe Learner-before-wave45-01a08596.app`。安装后原生启动并解锁原 Vault，Study Dialog 再次显示两轮对话、提交答案及已记录判分结果；未发起新的模型请求。原生 Command-Q 退出后，最终实例端口 63200 无 listener，见 `desktop/installed-lifecycle.json`。

## 未关闭事项

- 桌面互动题出现同义答案误判：“11；11；成立”未匹配模型参考答案“11,11,成功”等变体。记录持久化路径通过，语义判分质量未通过；本轮没有用针对单个词的替换规则修改评分合同，也没有重写已提交答案。
- 完整 OCR、最大输入组合、全部浏览器/桌面故障恢复与保护回放、尚未完成的独立 eval suite、代表性性能样本和实际账单仍沿用原报告的开放状态。
- 上游输出仍可能失败；一次或几次实测成功不是总体成功率或费用/延迟承诺。

## 证据

- `catalog-audit-fixed.json`：独立工具目录审计。
- `retest/summary.json`、`retest/chat*.json`、`retest/goal_stream.json`：原失败场景的新请求。
- `retest/document_plan.json`：最终教材计划；`document_plan-before-reference-repair.json` 保留前次失败。
- `release-final.log`、`live-decode-fixed.log`：最终发布门及真实 wire 验收。
- `desktop/readback.json`、`desktop/lifecycle.json`、`desktop/build-sha256.json`：桌面持久化、退出和构建身份。
- `desktop/installed-build.json`、`desktop/installed-lifecycle.json`：最终安装包身份、原生回读和退出清理。
- `desktop/original-settings.json`：不含密钥的原设置，用于恢复。
