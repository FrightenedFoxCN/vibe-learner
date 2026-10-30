# Tavern Room React Profiler measurement v1

本协议验证三个列表位置追加 30 个 summary 的 React `actualDuration` P95 ≤50 ms，以及最多 100 个 Room button 的 DOM 门。后端 HTTP 门见[分页协议](tavern-room-http-v1.md)。

## 参考基线

| 区域（0基排序位置） | 初始30项 | 实际追加30项 | 有效样本 | P50 ms | P95 ms | 最大 ms |
| --- | --- | --- | --- | --- | --- | --- |
| 开始 | 0–29 | 30–59 | 30 | 1.80 | 2.30 | 2.30 |
| 中间 | 450–479 | 480–509 | 30 | 1.90 | 2.20 | 2.40 |
| 末尾 | 940–969 | 970–999 | 30 | 1.90 | 2.30 | 2.80 |

每区另有5次完整UI加载/追加预热，共15次预热和90次有效样本；预热原始记录一并保留。P95使用nearest-rank（30项排序后的第29项）。没有删除慢样本；各次有效追加恰好对应1个符合边界的React commit。

结构验收预先选择排序最后一间Room，令其在初始30项窗口之外。实际Room button DOM数量依次 **31 → 61 → 91 → 100**，当前房间仍`aria-pressed=true`且包含于Profiler的roomIds；100项后“载入更多房间”按钮确实不存在。控件断言独立于 90 次计时样本。

## 为什么这是真实React测量

产品仅在`NEXT_PUBLIC_TAVERN_ROOM_PROFILING=1`时以React `Profiler`包裹实际`TavernSessionPanel`；未用纯函数计时、浏览器点击墙钟时间或接口延迟代替React门。构建使用`next build --profile`。独立检查`onRender`记录原始`id/phase/actualDuration/baseDuration/startTime/commitTime`、`roomIds`及`loadingMore`；正常production编译不包Profiler。

测试等待真实Room detail初始化完成，再点击实际“载入更多房间”。采样仅选择点击后`phase != mount`且roomIds精确等于初始30项+新增30项的callback。mount、loading-only等回调不冒充追加样本，**所有回调都存档**。若一次追加有多个匹配commit，协议取其中最大actualDuration。全部时长为React onRender的`actualDuration`，没有额外修正或扣除。

UI超过100项即停止分页，所以不能自然走到1000项夹具的中间/尾部。本测试仅将**首次**list请求转发到同一个真实后端夹具的指定cursor，响应正文和`next_cursor`不改；之后“载入更多”走原产品请求与合并路径。起始窗口由实际HTTP遍历取得，不伪造cursor。这个窗口设置是基准初始化，不宣称用户目前可连续翻遍1000个房间。

## 复现

后端使用 `tavern-room-list-fixture-v1`、seed `vibe-learner-tavern-1000-v1` 的 1,000-Room 临时 SQLite 夹具，包含合法 Persona 快照和 detail/runs/recovery 读取。前端运行在 3417，fixture 服务须允许该来源。参考环境为 Apple M4 / arm64、Node 26、Chromium、1440×1000，无 CPU 限速；每轮使用全新 browser context。精确环境、build ID、组件及采样脚本摘要由原始报告绑定。

可重放命令（先构建profiling版本并启动专属1000-Room backend）：

```bash
NEXT_PUBLIC_TAVERN_ROOM_PROFILING=1 npm exec --workspace @vibe-learner/web -- next build --profile
TAVERN_PROFILE_API_URL=http://127.0.0.1:8897 TAVERN_PROFILE_OUTPUT=/tmp/tavern-room-react-profile.json npm exec --workspace @vibe-learner/web -- playwright test tests/browser/tavern-room-profile.spec.ts
```

未设置`TAVERN_PROFILE_API_URL`时用例明确跳过，不算性能门通过。运行整个spec先生成timing raw，再运行附加cap控件用例；单独运行后者需要已有同夹具的raw文件。

## 原始样本

- [完整回调与有效样本](../acceptance/tavern-room-react-profile-2026-09-11.json)：包含预热、全部 React 回调、list URL、选样规则与环境。
- [100 项控件断言](../acceptance/tavern-room-react-cap-2026-09-11.json)。
- [cursor 窗口及预期 ID](../acceptance/tavern-room-profile-windows-2026-09-11.json)。

React `actualDuration` 只计组件树 render 工作；layout/paint、网络等待和真实设备交互有独立边界。普通 production build 应裁剪 profiling 分支，可检查 `.next/static` 不含 `__tavernRoomProfileSamples`。
