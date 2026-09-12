# M3 Planning、多媒体教学与多智能体架构检查

2026-09-12 独立只读实现审查。此次审查未调用 live provider、未修改生产实现；测试仅使用本地 mock。并行实验的实际模型结果由本轮主报告另行记录。

## 结论

Planning 与 Study 是有界的单模型多轮工具运行时。Tavern 有多个角色，但采用确定顺序逐个生成。实验框架能够并行运行独立 worker；这三种结构不能互相替代，更不能把并行实验数当成产品多智能体能力。

M3 可通过已有多模态输入路径测试教材页图像、图片理解、PDF/图片投射与标注，并测试结构化练习和 Mermaid/数学排版。当前生成图片实现按模型名称限制能力，M3 不在白名单；音频、视频也不属于本次 Study 已实现的附件输入路径。注册 31 个 Study 工具不等于当前请求可用 31 个工具。

## 架构及代码证据

| 边界 | 实际实现 | 证据 |
| --- | --- | --- |
| Planning | 同一 messages 历史多轮请求；`parallel_tool_calls=False`；收到多个调用仍顺序执行 | `services/ai/app/services/openai_plan_runner.py:66`, `:86`, `:124` |
| Study | 同一模型有界循环；普通轮次和豁免工具轮次分别计数；工具依次执行 | `services/ai/app/services/provider_study.py:140`, `:146`, `:174`, `:200` |
| 工具能力 | 6 个 Planning、31 个 Study 的版本化目录；当前运行时按开关、文件、绑定计划、runtime、disabled 集合投影子集 | `services/ai/app/models/tool_manifest.py:461`, `:471`; `services/ai/app/services/provider_study.py:594`; `services/ai/app/services/study_session_chat_runtime.py:86` |
| Tavern | facilitated 为 2–4 个目标，按 room display_order 生成；每个 actor 提交后下个 actor 再读其消息；失败保留已提交消息并阻塞后续角色 | `docs/tavern-architecture.md:61`, `:71`; `services/ai/app/services/tavern.py:684` |
| 实验并行 | 独立进程执行 sample，共享账本限流与并发控制；不是产品中的互相协作 agent | `tools/model-quality/model_quality/runner.py:110`, `:242`, `:248` |
| 本轮角色探索草稿 | 同一模型先生成、再以独立 reviewer prompt 核验、最后修订；proposal-only，无领域 admission/commit；不能充当独立质量认证 | 当前工作树 `tools/model-quality/integrations/vibe_learner/role_exploration.py:28`, `:42`（并行开发中的实验脚本，最终版本以运行冻结快照为准） |
| Harness | 模型只拥有 proposal 内容；应用分配 ID、revision、sequence、receipt。主输出提交不证明外部 provider exactly-once 或所有效果成功 | `docs/harness-architecture.md:40`; `docs/harness-architecture.md:47` |

## 功能可测范围

| 功能 | 当前可测内容 | 条件与判定限制 |
| --- | --- | --- |
| Planning 六工具 | 单元详情、澄清、结构估分、单元重编排、页文本、页图像 | estimator 只评结构元数据，不能判教学质量/事实正确；图像需 multimodal 开关和文件。见 `tool_manifest.py:462` 与 `plan_tool_runtime.py:646` |
| 教材与附件视觉输入 | 读教材页图；上传图作为 multimodal parts；读投射 PDF 页图 | 图像工具结果实际转成图像 parts，见 `provider_study.py:783`, `:817`；上传图片受能力开关约束，见 `study_chat_attachments.py:120`, `:193` |
| PDF/图片投射标注 | 上传附件投射、切页、文字高亮、区域框选、清除 overlays | 应以 persisted Session read-back、effect receipt、真实框坐标对应内容检查成功；合法归一化坐标不证明框选正确。工具目录 `tool_manifest.py:486` |
| 生成教学图片 | 有独立 Responses image_generation 实现 | `provider_image.py:15` 白名单包含 GPT/o3，未包含 M3；`:35` 同时要求 Responses 可用。`model_provider.py:1065` 传入当前 chat_model，并非已配置的独立 M3→图像模型路由。`study_session_chat_runtime.py:93` 因此隐藏工具。应记录能力不可用，而非模型生成失败 |
| 结构化练习 | 选择题、填空题与提交后评分 | 检查公开题干不泄漏答案；持久化后展示；服务端 grading 不进入浏览器。不能只以 question 字段存在为内容正确 |
| 图表/公式教学 | Markdown、Mermaid、KaTeX | `apps/web/components/rich-text-message-client.tsx:6`, `:27`, `:72`。仍需浏览器渲染及图表语义复核；并非任意 HTML 交互仿真运行时 |
| 音频/视频 | 当前 Study 输入未实现对应分支 | `study_chat_attachments.py:120` 至 `:133` 只接受 image/PDF/text，其他媒体返回 unsupported；本结论限定该产品路径，不推断 M3 原生模型能力 |

## 实验建议及开放缺口

1. Planning 与多媒体可用独立数据库、文件目录、operation ID 和预算账本并行实验；避免多个 worker 修改同一 Study Session 或 Tavern Room 导致把 CAS 冲突误判为 M3 质量失败。
2. 分开记录「工具未暴露」「暴露但未调用」「调用失败」「提交成功但内容错误」「正确且重启读回一致」。对视觉框选和教学内容保留人工或独立复核；schema 成功不能关闭质量项。
3. 若比较单次生成与 reviewer/repair，应报告实际 wire/token/延迟及失败分母。当前 role exploration 是同模型自我核验实验，不是已上线教学 supervisor、并行专家或独立模型评审架构。
4. 当前产品没有证据表明 Planning/Study 使用独立 agent 的任务分解、专家结果选择、独立权限或跨 agent durable handoff。若之后采用这些结构，候选阶段应无状态，选择后只进入一次已有 Harness 合法提交路径。
5. 历史短 Tavern 容量数据不外推到长 Planning 或图片请求；对应历史限制见 `docs/quality/m3-parallel-exploration-2026-09-12.md:33`。

## 本地验证

在 `services/ai` 执行：

```sh
UV_CACHE_DIR=/private/tmp/m3-architecture-uv-cache uv run --offline python -m unittest tests.test_provider_image tests.test_tool_manifest
```

14 tests passed（0.251s）；覆盖工具目录/严格 schema/golden、一轮批量详情预算、生成图片能力闸与无支持时零 provider 请求。只有 PyMuPDF Swig 弃用警告。第一次使用默认 uv cache 被沙箱拒绝读取，改用临时 cache 后成功；未作权限提升。这些测试不是 live M3 或浏览器视觉验收。
