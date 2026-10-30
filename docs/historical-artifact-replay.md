# 历史受保护制品重放验收

`services/ai/tests/acceptance/historical_artifact_replay.py` 使用未修改的旧应用 Git `e3a03a9` 生成 SQLite 持久化数据，再用当前 Alembic schema 和 runtime 做重放。旧应用使用本地 mock provider；数据由旧代码实际写出，属于合成测试记录。

四个领域各选一个旧应用实际写出的主 protected artifact：Document (`DocumentProcessProtectedInput@...v1`)、Planning (`LearningPlanProtectedInput@...v1`)、Persona (`PersonaGenerationProtectedInput@...v1`) 和 Scene (`SceneGenerationProtectedInput@...v1`)。旧 artifact 的 payload bytes、SHA-256 digest、contract、operation binding 和 grant 从旧 SQLite 直接读出；脚本不会用当前代码重新伪造这些源 artifact。旧版本同时写入了 Document 各阶段、Study 和 Tavern artifact，迁移 seed 会将它们一并保留。

每个选中的旧 grant 都先在其真实 `expires_at + 1s` 读回并得到 typed `expired`，然后使用同一 operation/artifact/contract scope 重新授权，再精确读回原 bytes 和 digest。当前 resolver 仍拒绝未授权的内容路径；当前 Document、Planning、Persona、Scene adapter 随后消费已授权、已解码的历史输入，输出严格当前 DTO，并记录通过的 v3 runtime trace。重放只使用确定性本地 callback，未向 provider 发请求。

## 复现

```bash
npm run test:acceptance:historical-replay -- \
  --output /tmp/historical-artifact-replay.json
```

命令会临时归档旧应用、运行旧 seed、将其 Alembic schema 升级到当前 head，完成四领域重放后删除临时目录。输出中的 `source_revision`、artifact digest、旧 operation ID、续期结果和 adapter trace ID 可用于逐项核对；payload 原文不写入报告。

成功条件是四个旧合同均能续期和重放，Document、Planning、Persona、Scene 的 `replay_status` 均为 `passed`。[参考报告](acceptance/historical-artifact-replay-2026-10-30.json) 保留 source revision、digest 和 trace 身份。删除、摘要损坏、跨 principal、未知 envelope 和批量 fail-closed 矩阵由 artifact resolver 测试覆盖。
