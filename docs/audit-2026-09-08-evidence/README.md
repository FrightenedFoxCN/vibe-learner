# 2026-09-08 复审复现脚本

这些脚本用于复现 `63372db` 基线上的发现，保留原始故障场景。脚本使用临时数据库、
mock provider 或受控异步函数，不使用现有业务数据。

- `repro-tavern-reorder.py`：双角色发言后重排，检查历史 committed projection。
- `repro-persona-top-level.py`：注入错误的顶层字段类型，检查 provider 与 Harness 输出。
- `repro-settings-unmount.cjs`：抽取基线生产保存函数，模拟保存 A 时编辑 B 后卸载。

Python 脚本在 `services/ai` 下以 `PYTHONPATH=.` 和 `uv run python` 执行。
Settings 脚本从仓库根目录以 Node 执行，依赖基线源代码的 ref 结构；修复后的持续
回归使用 `apps/web/tests/settings-save-lifecycle.test.cjs`，不将历史脚本当作最新测试。

修复后预期行为及最新验证见 `../audit-2026-09-08-remediation.md`。
